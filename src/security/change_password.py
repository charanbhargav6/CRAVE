"""
CRAVE — Secure Password Manager
Save to: D:\\CRAVE\\src\\security\\change_password.py

Features:
  - Change L2 PIN, L3 Password, or L4 Passphrase
  - Requires L4 passphrase verification FIRST
  - Requires email OTP (2FA) before any change is applied
  - Validates new passwords against master plan rules
  - Re-encrypts and saves credentials securely

Usage:
  cd D:\\CRAVE
  .venv\\Scripts\\python.exe src\\security\\change_password.py
"""

import os
import sys
import re
import json
import random
import getpass
import bcrypt
import requests

# Fix imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.security.encryption import crypto_manager, CREDS_PATH, CREDS_ENC_PATH
from src.security.unlock import send_recovery_email


# ── Helpers ──────────────────────────────────────────────────────────────────

def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_secret(secret: str, hashed: str) -> bool:
    return bcrypt.checkpw(secret.encode('utf-8'), hashed.encode('utf-8'))


def load_credentials() -> dict:
    """Decrypt and load credentials into memory."""
    if not os.path.exists(CREDS_ENC_PATH):
        print("❌ No credentials found. Run CRAVE first to set up passwords.")
        sys.exit(1)

    success = crypto_manager.decrypt_file(CREDS_ENC_PATH, CREDS_PATH)
    if not success:
        print("❌ FATAL: Cannot decrypt credentials. Master key missing?")
        sys.exit(1)

    with open(CREDS_PATH, "r") as f:
        creds = json.load(f)

    # Immediately delete the plain file
    os.remove(CREDS_PATH)
    return creds


def save_credentials(creds: dict):
    """Encrypt and save credentials."""
    with open(CREDS_PATH, "w") as f:
        json.dump(creds, f)

    crypto_manager.encrypt_file(CREDS_PATH, CREDS_ENC_PATH)
    os.remove(CREDS_PATH)
    print("✅ Credentials encrypted and saved.")


# ── Validation ───────────────────────────────────────────────────────────────

def validate_l2_pin(pin: str, creds: dict) -> str:
    """Validate L2 PIN. Returns error message or empty string if valid."""
    if len(pin) != 6 or not pin.isdigit():
        return "Must be exactly 6 digits."
    return ""


def validate_l3_password(pwd: str, creds: dict) -> str:
    """Validate L3 Password. Returns error message or empty string if valid."""
    if len(pwd) < 10:
        return "Must be at least 10 characters."
    if not re.search(r'[A-Z]', pwd):
        return "Must contain at least 1 uppercase letter."
    if not re.search(r'[0-9]', pwd):
        return "Must contain at least 1 number."
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', pwd):
        return "Must contain at least 1 symbol."
    return ""


def validate_l4_passphrase(phrase: str, creds: dict) -> str:
    """Validate L4 Passphrase. Returns error message or empty string if valid."""
    if len(phrase.split()) < 2:
        return "Must be at least 2 words separated by spaces."
    return ""


# ── Telegram OTP ─────────────────────────────────────────────────────────────

def send_telegram_otp() -> str:
    """Send OTP via Telegram Bot API. Returns OTP string or empty on failure."""
    # Load encrypted env to get bot token + chat ID
    crypto_manager.decrypt_env_to_memory()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("❌ Telegram not configured. Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env.enc")
        return ""

    otp_code = str(random.randint(100000, 999999))

    message = (
        "🔐 *CRAVE PASSWORD CHANGE — 2FA CODE*\n\n"
        f"Your verification code is:\n\n"
        f"```\n{otp_code}\n```\n\n"
        "⏳ Enter this code in the terminal to proceed.\n"
        "🚫 If you did NOT request this, ignore this message."
    )

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)

        if resp.status_code == 200 and resp.json().get("ok"):
            return otp_code
        else:
            print(f"❌ Telegram API error: {resp.text}")
            return ""
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")
        return ""


# ── 2FA Verification (Email OR Telegram) ────────────────────────────────────

def verify_2fa() -> bool:
    """Let user choose Email or Telegram for OTP, then verify. Returns True if verified."""
    print("\n🛡️  Choose 2FA verification method:\n")
    print("  1. 📧 Email (Gmail SMTP)")
    print("  2. 📱 Telegram Bot")
    print("  3. ⏭️  Skip (only if neither is set up yet)\n")

    choice = input("Enter choice (1-3): ").strip()

    otp = ""
    channel_name = ""

    if choice == "1":
        print("\n📧 Sending OTP to your registered email...")
        otp = send_recovery_email()
        channel_name = "email"
        if not otp:
            print("❌ Failed to send email. Check GMAIL_USER / GMAIL_APP_PASSWORD in .env.enc")
    elif choice == "2":
        print("\n📱 Sending OTP to your Telegram...")
        otp = send_telegram_otp()
        channel_name = "Telegram"
        if not otp:
            print("❌ Failed to send Telegram message. Check TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in .env.enc")
    elif choice == "3":
        print("\n⚠️  Skipping 2FA. Set up email or Telegram for proper security.")
        return True
    else:
        print("Invalid choice.")
        return False

    if not otp:
        print("\n   Would you like to try the other method?")
        retry = input("   Type YES to try, or anything else to abort: ").strip().upper()
        if retry == "YES":
            if choice == "1":
                print("\n📱 Trying Telegram instead...")
                otp = send_telegram_otp()
                channel_name = "Telegram"
            else:
                print("\n📧 Trying Email instead...")
                otp = send_recovery_email()
                channel_name = "email"

        if not otp:
            print("❌ Both channels failed. Aborting.")
            return False

    print(f"✅ OTP sent via {channel_name}! Check your {channel_name}.\n")

    for attempt in range(3):
        user_otp = input(f"Enter 6-digit code ({3 - attempt} attempts left): ").strip()
        if user_otp == otp:
            print("✅ 2FA Verified!\n")
            return True
        print("❌ Incorrect code.")

    print("❌ 2FA verification failed. Password change aborted.")
    return False


# ── Password Change Flow ────────────────────────────────────────────────────

def change_l2(creds: dict) -> dict:
    """Change L2 PIN."""
    print("\n─── Change L2 PIN ───")
    while True:
        new_pin = getpass.getpass("Enter new 6-digit PIN: ")
        err = validate_l2_pin(new_pin, creds)
        if err:
            print(f"❌ {err}")
            continue
        confirm = getpass.getpass("Confirm new 6-digit PIN: ")
        if new_pin != confirm:
            print("❌ PINs don't match. Try again.")
            continue
        break

    creds["L2_PIN_HASH"] = hash_secret(new_pin)
    print("✅ L2 PIN updated.")
    return creds


def change_l3(creds: dict) -> dict:
    """Change L3 Password."""
    print("\n─── Change L3 Password ───")
    print("Rules: 10+ chars, 1 uppercase, 1 number, 1 symbol")
    while True:
        new_pwd = getpass.getpass("Enter new password: ")
        err = validate_l3_password(new_pwd, creds)
        if err:
            print(f"❌ {err}")
            continue
        confirm = getpass.getpass("Confirm new password: ")
        if new_pwd != confirm:
            print("❌ Passwords don't match. Try again.")
            continue
        break

    creds["L3_PWD_HASH"] = hash_secret(new_pwd)
    print("✅ L3 Password updated.")
    return creds


def change_l4(creds: dict) -> dict:
    """Change L4 Passphrase."""
    print("\n─── Change L4 Passphrase ───")
    print("Rules: Multiple words separated by spaces")
    while True:
        new_phrase = getpass.getpass("Enter new passphrase: ")
        err = validate_l4_passphrase(new_phrase, creds)
        if err:
            print(f"❌ {err}")
            continue
        confirm = getpass.getpass("Confirm new passphrase: ")
        if new_phrase != confirm:
            print("❌ Passphrases don't match. Try again.")
            continue
        break

    creds["L4_PHR_HASH"] = hash_secret(new_phrase)
    print("✅ L4 Passphrase updated.")
    return creds


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("🔐 CRAVE SECURE PASSWORD MANAGER 🔐")
    print("=" * 50)

    # Step 1: Load credentials
    creds = load_credentials()

    # Step 2: Verify L4 passphrase (proves authority)
    print("\n🛡️  Step 1: Verify your identity")
    print("   Enter your current L4 passphrase to proceed.\n")

    for attempt in range(2):
        phrase = getpass.getpass(f"L4 Passphrase ({2 - attempt} attempts left): ")
        if verify_secret(phrase, creds["L4_PHR_HASH"]):
            print("✅ Identity verified.\n")
            break
        print("❌ Incorrect passphrase.")
    else:
        print("\n🚨 Authentication failed. Aborting.")
        sys.exit(1)

    # Step 3: Email 2FA
    print("🛡️  Step 2: Two-factor authentication")
    if not verify_2fa():
        sys.exit(1)

    # Step 4: Choose what to change
    print("🛡️  Step 3: What would you like to do?\n")
    print("  1. Change L2 PIN (6-digit)")
    print("  2. Change L3 Password")
    print("  3. Change L4 Passphrase")
    print("  4. Change ALL passwords")
    print("  5. Cancel\n")

    choice = input("Enter choice (1-5): ").strip()

    if choice == "1":
        creds = change_l2(creds)
    elif choice == "2":
        creds = change_l3(creds)
    elif choice == "3":
        creds = change_l4(creds)
    elif choice == "4":
        creds = change_l2(creds)
        creds = change_l3(creds)
        creds = change_l4(creds)
    elif choice == "5":
        print("Cancelled. No changes made.")
        sys.exit(0)
    else:
        print("Invalid choice. Aborting.")
        sys.exit(1)

    # Step 5: Save
    print("\n💾 Saving encrypted credentials...")
    save_credentials(creds)

    print("\n" + "=" * 50)
    print("🔐 PASSWORD CHANGE COMPLETE 🔐")
    print("=" * 50)
    print("Your new credentials are securely encrypted.")
    print("Remember them — there is no 'forgot password' option!\n")


if __name__ == "__main__":
    main()
