import requests
import os
import time

token_file = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "data", "telegram_token.txt")
if not os.path.exists(token_file):
    print("Error: Could not find telegram_token.txt")
    exit(1)

with open(token_file, "r") as f:
    token = f.read().strip()

print("[CRAVE] Connecting to Telegram API...")
url = f"https://api.telegram.org/bot{token}/getUpdates"

for attempt in range(3):
    try:
        resp = requests.get(url, timeout=10).json()
        if resp.get("ok"):
            results = resp.get("result", [])
            if not results:
                print("\n❌ No messages found! Please open your Telegram app, search for your CRAVE bot, hit START, and say 'Hello'. Then run this script again.")
            else:
                chat_id = results[-1]["message"]["chat"]["id"]
                name = results[-1]["message"]["chat"].get("first_name", "User")
                text = results[-1]["message"].get("text", "")
                
                print(f"\n✅ SUCCESS! Received '{text}' from {name}")
                print(f"==========================================")
                print(f"YOUR TELEGRAM CHAT ID: {chat_id}")
                print(f"==========================================")
            break
        else:
            print(f"Error from Telegram: {resp}")
            break
    except Exception as e:
        print(f"Attempt {attempt+1} Failed: {e}")
        time.sleep(2)
