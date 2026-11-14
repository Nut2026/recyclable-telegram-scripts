"""
A Group Report System that watches your Telegram groups with automatic reports.
Highly configurable system covering:
- user/bot blacklists and whitelists
- flagged sticker emojis, keywords, languages
- restrict contacts, users without profile pictures
- customise report (reply) message, delay, and report frequency
- view your history through a .log file and save your extensive configuration
in .config for a quick return!

How to use:
1. Please install the telethon module.
2. When prompted, enter your Telegram api_id and api_hash.
3. Pick your target groups from the list.
4. Feel free to configure your preferences as prompted!
5. Sit back while the system keeps your group safe.

That's basically it. Don't forget to follow Telegram's ToS at all times. Enjoy!
"""

import os
import re
import json
import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    ApiIdInvalidError,
    AccessTokenInvalidError,
    PhoneNumberInvalidError,
    RPCError,
)
from telethon.tl.types import ChannelParticipantsAdmins

WHITELIST_ADMINS = set()

keywords = set()
logged_users = set()

LANGUAGE_PATTERNS = {
    "Chinese": re.compile(r'[\u4e00-\u9fff]'),
    "Russian": re.compile(r'[\u0400-\u04FF]'),
    "Arabic": re.compile(r'[\u0600-\u06FF]'),
}

CONFIG_FILENAME = "config.json"
FALLBACK_CONFIG_FILENAME = "config_automation.json"

REQUIRED_CONFIG_KEYS = {
    "api_id",
    "api_hash",
    "target_groups",
    "whitelist_admins",
    "blacklist_ids",
    "blacklist_usernames",
    "whitelist_ids",
    "whitelist_usernames",
    "allow_bots",
    "whitelist_bots",
    "blacklist_sticker_emojis",
    "keywords",
    "flag_contacts",
    "flag_languages",
    "flag_no_profile_photo",
    "report_once",
    "reply_message",
    "report_delay",
    "logging_enabled",
    "log_file",
}


class QuestionCounter:
    """
    (X/Y) [question]
    Tracks the current question number and total questions for the configuration process.
    Sub-questions that belong to the same question category (depend on the previous question's result) do not increment the counter. 
    """

    def __init__(self):
        self.current = 0
        self.total = 0

    def start(self, total):
        """Set the total number of questions and reset the counter."""
        self.current = 0
        self.total = total

    def label(self, text):
        """Return 'X/Y - text' for the next top-level question."""
        self.current += 1
        return f"({self.current}/{self.total}) {text}"


Q = QuestionCounter()

_last_log_date = None


def deduplicate_inputs(items):
    """Return a list with duplicates removed, preserving order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


async def append_log(text: str):
    """Append the given text to the log file."""
    async with log_lock:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: open(LOG_FILE, "a", encoding="utf-8").write(text)
        )


async def log_report(sender, message_content, reported=True):
    """Write a report entry to the log file and mark the user as logged.

    If the calendar day has changed since the last logged entry, a
    separator line is written first so the log is grouped by day.

    `logged_users` is only updated when the entry is a genuine report,
    so that "Skipped" entries do not count as "already reported".
    """
    global _last_log_date

    user = sender.first_name or "unknown"
    username = sender.username or "unknown"
    user_id = sender.id

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    today = now.strftime("%Y-%m-%d")
    status = "Reported" if reported else "Skipped"

    log_text = (
        f"{status} | {timestamp} | {user} | {username} | {user_id}\n"
        f"{message_content}\n\n"
    )

    if LOGGING_ENABLED:
        if _last_log_date is not None and _last_log_date != today:
            separator = "-----------------------------\n\n"
            await append_log(separator)

        await append_log(log_text)
        _last_log_date = today

    if reported:
        logged_users.add(str(user_id))


def read_last_log_date():
    """
    Return the YYYY-MM-DD of the last entry in the log file, or None if
    the file doesn't exist / can't be parsed.
    """
    if not LOG_FILE or not os.path.exists(LOG_FILE):
        return None
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return None

    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("|")
        if len(parts) >= 2 and parts[0].strip() in ("Reported", "Skipped"):
            date_part = parts[1].strip()
            if len(date_part) >= 10 and date_part[4] == "-" and date_part[7] == "-":
                return date_part[:10]
    return None


client = None


def safe_input(prompt_text):
    """Read a line from stdin, converting Ctrl+C and EOF into a clean exit."""
    try:
        return input(prompt_text)
    except (KeyboardInterrupt, EOFError):
        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
        raise SystemExit(0)


async def populate_admin_whitelist():
    """Fetch the admins of every target group and add them to the whitelist."""
    global WHITELIST_ADMINS

    for group in TARGET_GROUPS:
        try:
            async for participant in client.iter_participants(
                group,
                filter=ChannelParticipantsAdmins
            ):
                WHITELIST_ADMINS.add(participant.id)
        except Exception:
            continue


def confirm(prompt_text):
    """Ask a yes/no confirmation, returning True only on 'y'."""
    while True:
        raw = safe_input(prompt_text).strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no", "exit", "quit", "q"):
            return False
        print("Error: Please enter 'y' or 'n'.")


def prompt_api_id():
    """Prompt for the Telegram api_id (not a config question - i.e. not included in the question counter)."""
    while True:
        raw = safe_input("\nPlease enter your Telegram api_id: ").strip()
        try:
            return int(raw)
        except ValueError:
            print("Error: api_id must be a number. Please try again.")


def prompt_api_hash():
    """Prompt for the Telegram api_hash (not a config question - i.e. not included in the question counter)."""
    while True:
        raw = safe_input("Please enter your Telegram api_hash: ").strip()
        if raw:
            return raw
        print("Error: api_hash cannot be empty. Please try again.")


def split_tokens(raw):
    """
    Split a raw input string on commas and/or whitespace.
    e.g. "1, 2 3,4"  ->  ["1", "2", "3", "4"]
    """
    return [tok for tok in re.split(r'[,\s]+', raw.strip()) if tok]


async def prompt_target_groups(client, prefix):
    """List the user's groups and return the IDs of the confirmed targets."""
    try:
        dialogs = await client.get_dialogs()
    except FloodWaitError as e:
        print(f"Rate limited. Please wait {e.seconds} seconds.")
        await asyncio.sleep(e.seconds)
        raise SystemExit(0)
    except RPCError as e:
        print(f"\nThere's a Telegram API error, but stay cool! {e}\n")
        raise SystemExit(0)

    groups = [d for d in dialogs if d.is_group]

    if not groups:
        print("\nError: You don't seem to be in any groups.")
        print("Try joining one first and running the script again.\n")
        raise SystemExit(0)

    print("\nYour groups:")
    for i, g in enumerate(groups):
        print(f"{i + 1}. {g.name}")

    while True:
        while True:
            choice_raw = safe_input(
                f"\n{prefix}Enter the numbers of the target groups "
                "(comma or space separated): "
            ).strip()
            if not choice_raw:
                print("Error: Choice cannot be empty. Please try again.")
                continue
            parts = split_tokens(choice_raw)
            try:
                choices = [int(p) - 1 for p in parts]
            except ValueError:
                print("Error: Every entry must be a number. Please try again.")
                continue
            if any(c < 0 or c >= len(groups) for c in choices):
                print("Error: One of those numbers is not in the list. Please try again.")
                continue
            break

        seen = set()
        unique_choices = []
        for c in choices:
            gid = groups[c].id
            if gid not in seen:
                seen.add(gid)
                unique_choices.append(c)

        print("Selected groups:")
        for c in unique_choices:
            print(f"- {groups[c].name}")
        if confirm("Are these correct? (y/n): "):
            return [groups[c].id for c in unique_choices]


def split_user_ids_and_usernames(raw):
    """Split a mixed input into sets of int IDs and lowercased usernames."""
    ids = set()
    usernames = set()
    for item in split_tokens(raw):
        item = item.lstrip("@")
        if not item:
            continue
        try:
            ids.add(int(item))
        except ValueError:
            usernames.add(item.lower())
    return ids, usernames


def prompt_user_lists(prompt_text, label, prefix):
    """Prompt for a mixed list of user IDs and usernames, with confirmation."""
    while True:
        raw = safe_input(f"{prefix}{prompt_text}").strip()
        ids, usernames = split_user_ids_and_usernames(raw)
        if ids or usernames:
            print(f"You entered {label}:")
            for i in sorted(ids):
                print(f"- {i}")
            for u in sorted(usernames):
                print(f"- {u}")
        else:
            print(f"You entered no {label}.")
        if confirm("Is this correct? (y/n): "):
            return ids, usernames


def prompt_str_set(prompt_text, label, prefix, lowercase=True, strip_at=True):
    """Prompt for a list of strings (comma or space separated)."""
    while True:
        raw = safe_input(f"{prefix}{prompt_text}").strip()
        items = split_tokens(raw) if raw else []
        if lowercase:
            items = [i.lower() for i in items]
        if strip_at:
            items = [i.lstrip("@") for i in items]
        items = deduplicate_inputs(items)
        if items:
            print(f"You entered {label}:")
            for i in items:
                print(f"- {i}")
        else:
            print(f"You entered no {label}.")
        if confirm("Is this correct? (y/n): "):
            return set(items)


def prompt_emoji_set(prompt_text, label, prefix):
    """Prompt for a list of emojis (space or comma separated)."""
    while True:
        raw = safe_input(f"{prefix}{prompt_text}").strip()
        items = split_tokens(raw) if raw else []
        items = deduplicate_inputs(items)
        if items:
            print(f"You entered {label}:")
            for i in items:
                print(f"- {i}")
        else:
            print(f"You entered no {label}.")
        if confirm("Is this correct? (y/n): "):
            return set(items)


def prompt_keywords(prompt_text, label, prefix):
    """Prompt for a list of keywords (comma separated only)."""
    while True:
        raw = safe_input(f"{prefix}{prompt_text}").strip()
        items = [p.strip().lower() for p in raw.split(",") if p.strip()]
        items = deduplicate_inputs(items)
        if items:
            print(f"You entered {label}:")
            for i in items:
                print(f"- {i}")
        else:
            print(f"You entered no {label}.")
        if confirm("Is this correct? (y/n): "):
            return set(items)


def prompt_language_choice(prefix):
    """Ask whether to flag foreign languages, and which ones if so."""
    if not confirm(f"\n{prefix}Flag messages written in foreign languages? (y/n): "):
        return set()

    available = list(LANGUAGE_PATTERNS.keys())
    print("\nAvailable languages to flag:")
    for i, lang in enumerate(available):
        print(f"{i + 1}. {lang}")

    while True:
        raw = safe_input(
            f"\n{prefix}Enter the numbers of the languages to flag "
            "(space or comma separated; press Enter for none): "
        ).strip()

        if not raw:
            print("You entered no languages to flag.")
            if confirm("Is this correct? (y/n): "):
                return set()
            continue

        parts = split_tokens(raw)
        try:
            choices = [int(p) - 1 for p in parts]
        except ValueError:
            print("Error: Every entry must be a number. Please try again.")
            continue
        if any(c < 0 or c >= len(available) for c in choices):
            print("Error: One of those numbers is not in the list. Please try again.")
            continue

        selected = deduplicate_inputs(available[c] for c in choices)

        print("Selected languages to flag:")
        for lang in selected:
            print(f"- {lang}")
        if confirm("Are these correct? (y/n): "):
            return set(selected)


def prompt_log_filename(prefix):
    """
    Prompt for the log file's base name (extension always .log).
    The file is always created in the script's own directory.
    Names with spaces between characters are rejected.
    """
    while True:
        raw = safe_input(
            f"\n{prefix}Log file name (without extension, e.g. reports, report_log; "
            "press Enter for 'reports'): "
        )
        stripped = raw.strip()

        if not stripped:
            stripped = "reports"

        if any(ch.isspace() for ch in stripped):
            print("Error: Log file name cannot contain spaces. Please try again.")
            continue

        if stripped.lower().endswith(".log"):
            stripped = stripped[:-4].strip()
            if not stripped:
                print("Error: Log file name cannot be empty. Please try again.")
                continue
            if any(ch.isspace() for ch in stripped):
                print("Error: Log file name cannot contain spaces. Please try again.")
                continue

        filename = f"{stripped}.log"
        full_path = os.path.join(SCRIPT_DIR, filename)

        print(f"You entered log file name: {filename}")
        print(f"It will be saved at: {full_path}")
        if confirm("Is this correct? (y/n): "):
            return full_path


def prompt_reply_message(prefix):
    """Prompt for the reply text sent to violating messages, with confirmation."""
    while True:
        raw = safe_input(f"\n{prefix}Enter the reply to send to violating messages: ").strip()
        if not raw:
            print("Error: Reply cannot be empty. Please try again.")
            continue
        print(f"You entered reply: {raw}")
        if confirm("Is this correct? (y/n): "):
            return raw


def prompt_report_delay(prefix):
    """
    Prompt for the delay (in seconds) before sending the reply.

    Accepts 'none' / empty / 0 for no delay. Numbers must be < 1001.
    """
    while True:
        raw = safe_input(
            f"\n{prefix}Would you like a delay before sending the reply? "
            "(0/Enter for no delay, max 1000 second): "
        ).strip().lower()

        if raw in ("", "none", "no", "n"):
            print("There wouldn't be any delay.")
            if confirm("Is this correct? (y/n): "):
                return 0.0
            continue

        try:
            value = float(raw)
        except ValueError:
            print("Error: Please enter a number, 'none', or press Enter for no delay.")
            continue

        if value < 0:
            print("Error: Delay cannot be negative. Please try again.")
            continue

        if value >= 1001:
            print("Error: Delay must be less than or equal to 1000 seconds. Please try again.")
            continue

        print(f"There would be a {value} seconds delay.")
        if confirm("Is this correct? (y/n): "):
            return value


def keyword_violation(text: str) -> bool:
    """Return True if any flagged keyword appears in the text.
    Uses substring matching so multi-word phrase keywords work correctly."""
    if not keywords:
        return False
    lowered = text.lower()
    return any(word in lowered for word in keywords)


def bot_violation(text: str) -> bool:
    """Return True if the text mentions a bot that isn't allowed."""
    if ALLOW_BOTS:
        return False
    match = bot_pattern.search(text)
    if not match:
        return False
    return match.group(0).lower() not in WHITELIST_BOTS


async def language_violation(event, sender) -> bool:
    """Return True if the message contains a flagged language."""
    if not FLAG_LANGUAGES:
        return False
    text = event.raw_text or ""
    for lang in FLAG_LANGUAGES:
        if LANGUAGE_PATTERNS[lang].search(text):
            return True
    return False


async def no_profile_photo_violation(sender) -> bool:
    """Return True if the user has no profile photo and that is flagged."""
    if not FLAG_NO_PROFILE_PHOTO:
        return False
    try:
        photos = await client.get_profile_photos(sender.id, limit=1)
        return len(photos) == 0
    except Exception:
        return False


def sticker_violation(event) -> bool:
    """Return True if the sticker's emoji is in the blacklisted set."""
    if not event.sticker:
        return False
    try:
        return event.file.emoji in BLACKLIST_STICKER_EMOJIS
    except Exception:
        return False


def contact_violation(event) -> bool:
    """Return True if the message is a contact share and contacts are flagged."""
    if not FLAG_CONTACTS:
        return False
    return event.contact is not None


def is_whitelisted(sender) -> bool:
    """Return True if the sender should be exempt from reporting."""
    username = (sender.username or "").lower().lstrip("@")
    if sender.id in BLACKLIST_IDS:
        return False
    if username in BLACKLIST_USERNAMES:
        return False
    if sender.id in WHITELIST_IDS:
        return True
    if sender.id in WHITELIST_ADMINS:
        return True
    if username in WHITELIST_USERNAMES:
        return True
    return False


async def process_event(event):
    """Check an incoming event for violations and report the sender if needed."""
    sender = await event.get_sender()
    if not sender:
        return

    if is_whitelisted(sender):
        return

    user_id = str(sender.id)
    already_logged = user_id in logged_users

    message_content = None
    violation_detected = False

    if contact_violation(event):
        message_content = "*contact message*"
        violation_detected = True

    elif event.raw_text:
        text = event.raw_text
        if (
            keyword_violation(text)
            or bot_violation(text)
            or await language_violation(event, sender)
            or await no_profile_photo_violation(sender)
        ):
            message_content = text
            violation_detected = True

    elif sticker_violation(event):
        message_content = "*sticker*"
        violation_detected = True

    if not violation_detected:
        return

    await asyncio.sleep(1.5)

    try:
        refreshed = await client.get_messages(event.chat_id, ids=event.id)
        if not refreshed:
            return
    except Exception:
        return

    if REPORT_ONCE and already_logged:
        return

    await asyncio.sleep(REPORT_DELAY)

    await client.send_message(
        event.chat_id,
        REPORT_REPLY,
        reply_to=event.id
    )
    await log_report(sender, message_content, True)


def config_path(filename=CONFIG_FILENAME):
    """Absolute path to the given config file in the script's directory."""
    return os.path.join(SCRIPT_DIR, filename)


def load_config_file():
    """
    Try to load config.json.

    Returns a tuple (status, data):
    - ("missing", None) -> no config.json at all
    - ("invalid", None) -> config.json exists but is not usable
    - ("valid", dict) -> config.json parsed and had every required key
    """
    path = config_path(CONFIG_FILENAME)
    if not os.path.exists(path):
        return ("missing", None)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ("invalid", None)
    if not isinstance(data, dict):
        return ("invalid", None)
    if not REQUIRED_CONFIG_KEYS.issubset(data.keys()):
        return ("invalid", None)
    return ("valid", data)


def save_config_file(data, filename=CONFIG_FILENAME):
    """Write the given configuration dict to the chosen config file."""
    with open(config_path(filename), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


async def main():
    """Run the interactive setup and then the automated report system."""
    global client, bot_pattern
    global ALLOW_BOTS, WHITELIST_BOTS, BLACKLIST_STICKER_EMOJIS
    global TARGET_GROUPS, BLACKLIST_IDS, BLACKLIST_USERNAMES
    global WHITELIST_IDS, WHITELIST_USERNAMES, LOG_FILE, log_lock
    global keywords, logged_users, WHITELIST_ADMINS
    global FLAG_CONTACTS, FLAG_LANGUAGES, FLAG_NO_PROFILE_PHOTO, REPORT_REPLY
    global REPORT_ONCE, LOGGING_ENABLED, _last_log_date
    global REPORT_DELAY

    print("\nWelcome to the power of automation | Configurable Report System for Telegram.")
    print("\n------")

    config_status, loaded = load_config_file()
    used_config = False

    save_filename = (
        FALLBACK_CONFIG_FILENAME if config_status == "invalid" else CONFIG_FILENAME
    )

    if config_status == "invalid":
        print(
            f"\nFound {CONFIG_FILENAME} at: {config_path(CONFIG_FILENAME)} "
            "but it is not a valid configuration for this script."
        )
        print(
            f"Its contents will be left untouched. If you save a new configuration "
            f"later, it will be written to '{FALLBACK_CONFIG_FILENAME}' instead.\n"
        )

    if config_status == "valid":
        print(f"\nFound an existing configuration at: {config_path(CONFIG_FILENAME)}")
        if confirm("Load the previous configuration? (y/n): "):
            used_config = True

            api_id = int(loaded["api_id"])
            api_hash = str(loaded["api_hash"])

            TARGET_GROUPS = list(loaded["target_groups"])

            WHITELIST_ADMINS = set()

            BLACKLIST_IDS = set(int(x) for x in loaded["blacklist_ids"])
            BLACKLIST_USERNAMES = set(str(x).lower() for x in loaded["blacklist_usernames"])
            WHITELIST_IDS = set(int(x) for x in loaded["whitelist_ids"])
            WHITELIST_USERNAMES = set(str(x).lower() for x in loaded["whitelist_usernames"])

            ALLOW_BOTS = bool(loaded["allow_bots"])
            WHITELIST_BOTS = set(str(x).lower() for x in loaded["whitelist_bots"])
            BLACKLIST_STICKER_EMOJIS = set(str(x) for x in loaded["blacklist_sticker_emojis"])
            keywords = set(str(x).lower() for x in loaded["keywords"])

            FLAG_CONTACTS = bool(loaded["flag_contacts"])
            FLAG_LANGUAGES = set(loaded["flag_languages"])
            FLAG_NO_PROFILE_PHOTO = bool(loaded["flag_no_profile_photo"])
            REPORT_ONCE = bool(loaded["report_once"])
            REPORT_REPLY = str(loaded["reply_message"])
            REPORT_DELAY = float(loaded.get("report_delay", 0))

            LOGGING_ENABLED = bool(loaded["logging_enabled"])
            if LOGGING_ENABLED and loaded.get("log_file"):
                LOG_FILE = os.path.join(SCRIPT_DIR, os.path.basename(loaded["log_file"]))
            else:
                LOG_FILE = None
                LOGGING_ENABLED = False

            refresh_admins = bool(loaded["whitelist_admins"])

            session_name = "userbot_session"
            print("\n------\n")
            client = TelegramClient(
                session_name, api_id, api_hash, sequential_updates=False
            )
            await client.start()
            print("Loading...\n")
            print("------")

            if refresh_admins:
                await populate_admin_whitelist()
        else:
            print("\nStarting over with a fresh configuration.\n")

    if not used_config:
        api_id = prompt_api_id()
        api_hash = prompt_api_hash()

        session_name = "userbot_session"

        print("\n------\n")

        client = TelegramClient(
            session_name,
            api_id,
            api_hash,
            sequential_updates=False
        )

        await client.start()
        print("Loading...\n")
        print("------")

        Q.start(total=15)

        prefix = Q.label("")
        TARGET_GROUPS = await prompt_target_groups(client, prefix)

        prefix = Q.label("")
        if confirm(f"\n{prefix}Whitelist all admins? (y/n): "):
            await populate_admin_whitelist()
        else:
            WHITELIST_ADMINS = set()

        prefix = Q.label("")
        if confirm(f"\n{prefix}Add blacklisted users? (y/n): "):
            BLACKLIST_IDS, BLACKLIST_USERNAMES = prompt_user_lists(
                "Blacklisted user IDs and/or usernames "
                "(comma or space separated, no @ needed): ",
                "blacklisted users",
                prefix,
            )
        else:
            BLACKLIST_IDS = set()
            BLACKLIST_USERNAMES = set()

        prefix = Q.label("")
        if confirm(f"\n{prefix}Add whitelisted users? (y/n): "):
            WHITELIST_IDS, WHITELIST_USERNAMES = prompt_user_lists(
                "Whitelisted user IDs and/or usernames "
                "(comma or space separated, no @ needed): ",
                "whitelisted users",
                prefix,
            )
        else:
            WHITELIST_IDS = set()
            WHITELIST_USERNAMES = set()

        prefix = Q.label("")
        if confirm(f"\n{prefix}Allow bots? (y/n): "):
            ALLOW_BOTS = True
            WHITELIST_BOTS = set()
        else:
            ALLOW_BOTS = False
            if confirm(f"{prefix}Add whitelisted bots? (y/n): "):
                WHITELIST_BOTS = prompt_str_set(
                    "Whitelisted bot usernames "
                    "(comma or space separated, no @ needed): ",
                    "whitelisted bot usernames",
                    prefix,
                )
            else:
                WHITELIST_BOTS = set()

        prefix = Q.label("")
        if confirm(f"\n{prefix}Add blacklisted sticker emojis? (y/n): "):
            BLACKLIST_STICKER_EMOJIS = prompt_emoji_set(
                "Blacklisted sticker emojis "
                "(space or comma separated, e.g. 🌟,⭐): ",
                "blacklisted sticker emojis",
                prefix,
            )
        else:
            BLACKLIST_STICKER_EMOJIS = set()

        prefix = Q.label("")
        if confirm(f"\n{prefix}Add blacklisted keywords? (y/n): "):
            keywords = prompt_keywords(
                "Blacklisted keywords to flag (comma separated only): ",
                "blacklisted keywords",
                prefix,
            )
        else:
            keywords = set()

        prefix = Q.label("")
        FLAG_CONTACTS = confirm(
            f"\n{prefix}Flag contact-sharing messages? (y/n): "
        )

        prefix = Q.label("")
        FLAG_LANGUAGES = prompt_language_choice(prefix)

        prefix = Q.label("")
        FLAG_NO_PROFILE_PHOTO = confirm(
            f"\n{prefix}Flag users without a profile picture? (y/n): "
        )

        prefix = Q.label("")
        REPORT_ONCE = confirm(
            f"\n{prefix}Report each violating user only once? "
            "(y = report once and skip future violations, n = report every violation): "
        )

        prefix = Q.label("")
        REPORT_REPLY = prompt_reply_message(prefix)

        prefix = Q.label("")
        REPORT_DELAY = prompt_report_delay(prefix)

        prefix = Q.label("")
        if confirm(f"\n{prefix}Do you want to log reports to a file? (y/n): "):
            LOGGING_ENABLED = True
            LOG_FILE = prompt_log_filename(prefix)
        else:
            LOGGING_ENABLED = False
            LOG_FILE = None

        prefix = Q.label("")
        if confirm(
            f"\n{prefix}Save this configuration to '{save_filename}' for next time? (y/n): "
        ):
            try:
                save_config_file(
                    {
                        "api_id": api_id,
                        "api_hash": api_hash,
                        "target_groups": list(TARGET_GROUPS),
                        "whitelist_admins": bool(WHITELIST_ADMINS),
                        "blacklist_ids": sorted(BLACKLIST_IDS),
                        "blacklist_usernames": sorted(BLACKLIST_USERNAMES),
                        "whitelist_ids": sorted(WHITELIST_IDS),
                        "whitelist_usernames": sorted(WHITELIST_USERNAMES),
                        "allow_bots": ALLOW_BOTS,
                        "whitelist_bots": sorted(WHITELIST_BOTS),
                        "blacklist_sticker_emojis": sorted(BLACKLIST_STICKER_EMOJIS),
                        "keywords": sorted(keywords),
                        "flag_contacts": FLAG_CONTACTS,
                        "flag_languages": sorted(FLAG_LANGUAGES),
                        "flag_no_profile_photo": FLAG_NO_PROFILE_PHOTO,
                        "report_once": REPORT_ONCE,
                        "reply_message": REPORT_REPLY,
                        "report_delay": REPORT_DELAY,
                        "logging_enabled": LOGGING_ENABLED,
                        "log_file": os.path.basename(LOG_FILE) if LOG_FILE else None,
                    },
                    filename=save_filename,
                )
                print(
                    f"Configuration saved to: {config_path(save_filename)}"
                )
            except Exception as e:
                print(f"Warning: could not save {save_filename} ({e}).")

    log_lock = asyncio.Lock()
    bot_pattern = re.compile(r'@\w*bot\b', re.IGNORECASE)
    logged_users = set()

    _last_log_date = read_last_log_date()

    print("\n------\n")

    @client.on(events.NewMessage(chats=TARGET_GROUPS))
    async def handler(event):
        asyncio.create_task(process_event(event))

    @client.on(events.MessageEdited(chats=TARGET_GROUPS))
    async def edit_handler(event):
        asyncio.create_task(process_event(event))

    print("Your automated Group Report System is running.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError, asyncio.CancelledError):
        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
    except ApiIdInvalidError:
        print("\nError: The api_id / api_hash / the combination is invalid.")
        print("Try double-checking them at https://my.telegram.org → API development tools.\n")
    except AccessTokenInvalidError:
        print("\nError: The session is invalid or has been revoked.")
        print("Try deleting 'userbot_session.session' and running the script again.\n")
    except PhoneNumberInvalidError:
        print("\nError: The phone number associated with this login is invalid.")
        print("Try checking the number and running the script again.\n")
    except RPCError as e:
        print(f"\nThere's a Telegram API error, but stay cool! {e}\n")
    except Exception as e:
        print(f"\nAn unexpected error occured, but stay cool! {e}\n")
