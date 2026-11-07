"""
This is a simple script to clean up your own messages in a Telegram group, right in your terminal.

How to use:
1. Please install the telethon module.
2. When prompted, enter your Telegram api_id and api_hash.
3. Pick a group from the list. Your own messages will be shown one by one.
4. Choose whether to delete each message or skip it.
5. Your group is a little tidier.

That sums it up. Don't forget to follow Telegram's ToS at all times. Enjoy!
"""

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ApiIdInvalidError,
    AccessTokenInvalidError,
    PhoneNumberInvalidError,
    ChannelInvalidError,
    ChannelPrivateError,
    MessageDeleteForbiddenError,
    RPCError,
)
import asyncio
import sys

session_name = "userbot_session"

async def main():
    print("\nWelcome to the Simple Script to Clean Up Your Group Messages.")
    print("\n------")

    while True:
        try:
            api_id_raw = input("\nPlease enter your Telegram api_id: ").strip()
        except KeyboardInterrupt:
            print("\n\nKeyboard interrupt detected. Exiting safely...\n")
            return
        try:
            api_id = int(api_id_raw)
            break
        except ValueError:
            print("Error: api_id must be a number. Please try again.")

    while True:
        try:
            api_hash = input("Please enter your Telegram api_hash: ").strip()
        except KeyboardInterrupt:
            print("\n\nKeyboard interrupt detected. Exiting safely...\n")
            return
        if api_hash:
            break
        print("Error: api_hash cannot be empty. Please try again.")

    print("\n------\n")

    try:
        async with TelegramClient(session_name, api_id, api_hash) as client:
            print("Loading...\n")
            print("------")

            try:
                dialogs = await client.get_dialogs()
            except FloodWaitError as e:
                print(f"Rate limited. Please wait {e.seconds} seconds.")
                await asyncio.sleep(e.seconds)
                return
            except RPCError as e:
                print(f"\nThere's a Telegram API error, but stay cool! - {e}\n")
                return

            groups = [d for d in dialogs if d.is_group]

            if not groups:
                print("\nError: You don't seem to be in any groups.")
                print("Try joining one first and running the script again.\n")
                return

            while True:
                print("\nYour groups:")
                for i, g in enumerate(groups):
                    print(f"{i + 1}. {g.name}")

                while True:
                    try:
                        choice_raw = input("\nPlease enter the number of the group: ").strip()
                    except KeyboardInterrupt:
                        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                        return
                    if not choice_raw:
                        print("Error: Choice cannot be empty. Please try again.")
                        continue
                    try:
                        choice = int(choice_raw) - 1
                    except ValueError:
                        print("Error: Choice must be a number. Please try again.")
                        continue
                    if choice < 0 or choice >= len(groups):
                        print("Error: That number is not in the list. Please try again.")
                        continue
                    break
                group = groups[choice]

                try:
                    me = await client.get_me()
                except RPCError as e:
                    print(f"\nThere's a Telegram API error, but stay cool! - {e}\n")
                    return

                messages = []
                try:
                    async for msg in client.iter_messages(group, from_user=me.id):
                        messages.append(msg)
                except ChannelInvalidError:
                    print(f"Error: The group '{group.name}' could not be found. Try running the script again.\n")
                    return
                except ChannelPrivateError:
                    print(f"Error: You no longer have access to '{group.name}'.\n")
                    return
                except FloodWaitError as e:
                    print(f"Rate limited. Please wait {e.seconds} seconds.")
                    await asyncio.sleep(e.seconds)
                    return
                except RPCError as e:
                    print(f"\nThere's a Telegram API error, but stay cool! - {e}\n")
                    return

                if not messages:
                    print("There are no messages found in this group.\n")
                else:
                    for msg in messages:
                        local_time = msg.date.astimezone()
                        print(f"\n[{local_time.strftime('%Y-%m-%d %H:%M:%S')}] {msg.text}")
                        while True:
                            try:
                                action = input("Delete this message? (y/n): ").strip().lower()
                            except KeyboardInterrupt:
                                print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                                return
                            if action in ("y", "yes"):
                                break
                            if action in ("n", "no"):
                                break
                            print("Error: Please enter 'y' or 'n'.")
                        if action in ("y", "yes"):
                            try:
                                await client.delete_messages(group, msg)
                                print("Message deleted.")
                            except MessageDeleteForbiddenError:
                                print("Error: You are not allowed to delete this message.")
                            except FloodWaitError as e:
                                print(f"Rate limited. Please wait {e.seconds} seconds.")
                                await asyncio.sleep(e.seconds)
                            except RPCError as e:
                                print(f"\nThere's a Telegram API error, but stay cool! - {e}")
                        else:
                            print("Message skipped.")

                    print("\nYou've reached the end of your messages.")

                while True:
                    try:
                        again = input("\nClean up another group? (y/n): ").strip().lower()
                    except KeyboardInterrupt:
                        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                        return
                    if again in ("y", "yes"):
                        break
                    if again in ("n", "no", "exit", "quit", "q"):
                        print("\nSee you!\n")
                        return
                    print("Error: Please enter 'y' or 'n'.")

    except ApiIdInvalidError:
        print("\nError: The api_id / api_hash / the combination is invalid.")
        print("Try double-checking them at https://my.telegram.org → API development tools.\n")
    except AccessTokenInvalidError:
        print("\nError: The session is invalid or has been revoked.")
        print(f"Try deleting '{session_name}.session' and running the script again.\n")
    except PhoneNumberInvalidError:
        print("\nError: The phone number associated with this login is invalid.")
        print(f"Try checking the number and running the script again.\n")
    except RPCError as e:
        print(f"\nThere's a Telegram API error, but stay cool! - {e}\n")
    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
    except Exception as e:
        print(f"\nAn unexpected error occured, but stay cool! - {e}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
        sys.exit(0)
