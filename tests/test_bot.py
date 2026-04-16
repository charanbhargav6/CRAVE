import os
import sys
import asyncio
from telegram import Bot

# Path fix
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.security.encryption import crypto_manager
from src.security.rbac import rbac

async def test_bot():
    print("[CRAVE] Verifying Telegram Bot Connection...")
    
    # 1. Decrypt keys into memory (Needs L3)
    if not rbac.authenticate_l3():
        print("❌ L3 Auth Failed. Cannot access Bot token.")
        return

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("❌ Error: Bot info missing from encrypted environment.")
        return

    # Using direct requests instead of the library to prove connectivity
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": "🚀 CRAVE SYSTEM STATUS: Telegram Bot Online and Connected via HTTPS!"}
    
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print("\n✅ SUCCESS! Check your Telegram App. You should have a message from CRAVE.")
        else:
            print(f"\n❌ FAILED: Telegram API returned {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"\n❌ FAILED to send message: {e}")

if __name__ == "__main__":
    asyncio.run(test_bot())
