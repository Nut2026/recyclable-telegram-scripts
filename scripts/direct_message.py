"""
This is a simple script to Telegram your friends right in your terminal.

How to use:
1. Please install the telethon module.
2. When prompted, enter your Telegram api_id and api_hash.
3. Enter your friend's ID. Enter your message. Hit Enter. 
4. Your friend receives your DM!

That's basically it. Don't forget to follow Telegram's ToS at all times. Enjoy!
"""

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ApiIdInvalidError,
    AccessTokenInvalidError,
    PhoneNumberInvalidError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    PeerIdInvalidError,
    UserPrivacyRestrictedError,
    ChatWriteForbiddenError,
    RPCError,
)
import asyncio
import sys

session_name = "userbot_session"

async def main():
    print("\nWelcome to the Simple Script to Telegram Your Friends.")
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
            print("Loading...")
            print("\n------")

            while True:
                try:
                    try:
                        target = input(
                            "\nPlease enter your friend's username or user ID: ").strip()
                    except KeyboardInterrupt:
                        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                        return
                    if not target:
                        print("Error: Target cannot be empty. Please try again.")
                        continue
                    if target.lower() == "exit":
                        break

                    try:
                        message = input("Message to send: ").strip()
                    except KeyboardInterrupt:
                        print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                        return
                    if not message:
                        print("Error: Message cannot be empty.")
                        continue

                    try:
                        entity = await client.get_entity(target)
                    except UsernameInvalidError:
                        print(f"Error: '{target}' is not a valid username.")
                        continue
                    except UsernameNotOccupiedError:
                        print(f"Error: The username '{target}' does not exist on Telegram.")
                        continue
                    except PeerIdInvalidError:
                        print(
                            f"Error: Could not find a user with ID '{target}'. "
                            "Please check the ID, or make sure you've interacted with them before."
                        )
                        continue
                    except ValueError:
                        print(
                            f"Error: '{target}' is not a valid username or user ID. "
                            "Please make sure that the usernames start with @ or be a plain name; IDs must be numeric."
                        )
                        continue

                    try:
                        await client.send_message(entity, message)
                        print("Message sent.")
                    except UserPrivacyRestrictedError:
                        print("Error: This user's privacy settings prevent you from messaging them.")
                    except ChatWriteForbiddenError:
                        print("Error: You are not allowed to write in this chat.")
                    except FloodWaitError as e:
                        print(f"Rate limited. Please wait {e.seconds} seconds.")
                        await asyncio.sleep(e.seconds)

                    while True:
                        try:
                            again = input("\nSend another message? (y/n): ").strip().lower()
                        except KeyboardInterrupt:
                            print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                            return
                        if again in ("y", "yes"):
                            break
                        if again in ("n", "no", "exit", "quit", "q"):
                            print("\nSee you!\n")
                            return
                        print("Error: Please enter 'y' or 'n'.")

                except FloodWaitError as e:
                    print(f"Rate limited. Please wait {e.seconds} seconds.")
                    await asyncio.sleep(e.seconds)

                except KeyboardInterrupt:
                    print("\n\nKeyboard interrupt detected. Exiting safely...\n")
                    return

                except Exception as e:
                    print(f"Error: {e}")

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
