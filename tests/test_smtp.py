import os
import sys
import smtplib
from email.message import EmailMessage

# Path fix
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.security.encryption import crypto_manager
from src.security.rbac import rbac

def test_smtp():
    print("[Crave] Verifying SMTP Email Connection...")
    
    # 1. Decrypt keys into memory (Needs L3)
    if not rbac.authenticate_l3():
        print("❌ L3 Auth Failed. Cannot access Gmail credentials.")
        return

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_pass:
        print("❌ Error: Gmail credentials missing from encrypted environment.")
        return

    msg = EmailMessage()
    msg.set_content("🛡️ CRAVE SECURITY TEST: Your SMTP Email protocol is active and functional!")
    msg['Subject'] = "Crave Verification: SMTP Protocol Online"
    msg['From'] = gmail_user
    msg['To'] = gmail_user

    try:
        print(f"Connecting to SSL port 465...")
        # Port 465 is more reliable on some networks than 587
        smtp = smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=15)
        smtp.login(gmail_user, gmail_pass)
        smtp.send_message(msg)
        smtp.quit()
        print(f"\n✅ SUCCESS! Check your inbox for {gmail_user}. You should have a verification email.")
    except Exception as e:
        print(f"\n❌ FAILED to send email: {e}")
        print("\nFix checklist:")
        print("1. Ensure your Google 'App Password' is the 16-letter code (no spaces).")
        print("2. Check if your ISP blocks SMTP ports (Common in some regions).")
        print("3. Try a VPN if the error persists.")

if __name__ == "__main__":
    test_smtp()
