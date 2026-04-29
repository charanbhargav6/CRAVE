"""Diagnostics script — checks face_id, email, telegram modules."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("=" * 60)
print("  CRAVE MODULE DIAGNOSTICS")
print("=" * 60)

# 1. Vault
print("\n--- 1. VAULT & CREDENTIALS ---")
from src.security.encryption import crypto_manager
ok = crypto_manager.decrypt_env_to_memory()
print(f"  Vault decrypt to memory: {ok}")
print(f"  TELEGRAM_BOT_TOKEN present: {bool(os.environ.get('TELEGRAM_BOT_TOKEN', ''))}")
print(f"  TELEGRAM_CHAT_ID present: {bool(os.environ.get('TELEGRAM_CHAT_ID', ''))}")
print(f"  SMTP_USER present: {bool(os.environ.get('SMTP_USER', ''))}")
print(f"  SMTP_PASS present: {bool(os.environ.get('SMTP_PASS', ''))}")
print(f"  OWNER_EMAIL present: {bool(os.environ.get('OWNER_EMAIL', ''))}")

# 2. Face ID
print("\n--- 2. FACE ID ---")
from src.security.face_id import _CV2, MODEL_PATH
print(f"  OpenCV (cv2) available: {_CV2}")
print(f"  Model file exists: {os.path.exists(MODEL_PATH)}")
if _CV2:
    import cv2
    print(f"  cv2.face module (LBPH): {hasattr(cv2, 'face')}")
    # Check camera
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    print(f"  Camera accessible: {cap.isOpened()}")
    cap.release()

# 3. Telegram
print("\n--- 3. TELEGRAM ---")
token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
if token:
    import requests
    try:
        resp = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()
        print(f"  API /getMe: {data.get('ok', False)}")
        if data.get("ok"):
            print(f"  Bot name: {data['result']['first_name']}")
            print(f"  Bot username: @{data['result']['username']}")
        # Send a test message
        test_resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "CRAVE Diagnostics: Telegram connection OK."},
            timeout=10,
        )
        tdata = test_resp.json()
        print(f"  Test message sent: {tdata.get('ok', False)}")
        if not tdata.get("ok"):
            print(f"  Error: {tdata.get('description', 'unknown')}")
    except Exception as e:
        print(f"  Telegram error: {e}")
else:
    print("  SKIPPED (no token)")

# 4. Email / SMTP
print("\n--- 4. EMAIL / SMTP ---")
smtp_user = os.environ.get("SMTP_EMAIL", os.environ.get("SMTP_USER", ""))
smtp_pass = os.environ.get("SMTP_PASSWORD", os.environ.get("SMTP_PASS", ""))
owner_email = os.environ.get("OWNER_EMAIL", "")
if smtp_user and smtp_pass:
    import smtplib
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        print(f"  SMTP login: SUCCESS (user={smtp_user})")
        server.quit()
    except smtplib.SMTPAuthenticationError as e:
        print(f"  SMTP login: FAILED (auth error) - {e}")
    except Exception as e:
        print(f"  SMTP login: FAILED - {e}")
else:
    print(f"  SMTP_EMAIL set: {bool(smtp_user)}")
    print(f"  SMTP_PASSWORD set: {bool(smtp_pass)}")
    if not smtp_user or not smtp_pass:
        print("  SKIPPED (missing SMTP credentials in vault)")

print("\n" + "=" * 60)
print("  DIAGNOSTICS COMPLETE")
print("=" * 60)
