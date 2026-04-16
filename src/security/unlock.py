import os
import sys
import smtplib
import random
import getpass
from email.message import EmailMessage
from pathlib import Path

# Fix for ModuleNotFoundError: No module named 'src'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Load encryption manager
from src.security.encryption import crypto_manager, CRAVE_ROOT
from src.security.rbac import get_rbac, LOCKDOWN_FILE

def send_recovery_email() -> str:
    """Sends OTP via real SMTP and returns the OTP code."""
    # Ensure env is loaded into memory to get SMTP credentials
    crypto_manager.decrypt_env_to_memory()
    
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    
    if not gmail_user or not gmail_pass:
        print("CRITICAL: SMTP credentials missing from encrypted environment.")
        return ""
        
    otp_code = str(random.randint(100000, 999999))
    
    msg = EmailMessage()
    msg.set_content(f"""
    🚨 CRAVE SECURITY ALERT 🚨
    
    A Full System Unlock was requested.
    If you initiated this request, please use the following 6-digit confirmation code to un-brick the system:
    
    [ {otp_code} ]
    
    If you did not request this, ignore this email and your system remains securely locked.
    """)
    msg['Subject'] = f"CRAVE Unlock Code: {otp_code}"
    msg['From'] = gmail_user
    msg['To'] = gmail_user  # Send to self
    
    try:
        smtp = smtplib.SMTP('smtp.gmail.com', 587)
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_pass)
        smtp.send_message(msg)
        smtp.quit()
        return otp_code
    except Exception as e:
        print(f"Failed to send recovery email: {e}")
        return ""

def revoke_lockdown():
    if os.path.exists(LOCKDOWN_FILE):
        os.remove(LOCKDOWN_FILE)
    print("\n✅ SYSTEM UNLOCKED ✅")
    print("All restrictions lifted. You can now start CRAVE.")

def manual_terminal_unlock():
    print("="*50)
    print("🛡️ CRAVE MANUAL LOCKDOWN RECOVERY 🛡️")
    print("="*50)
    
    if not os.path.exists(LOCKDOWN_FILE):
        print("System is not in lockdown. No action needed.")
        return
        
    passphrase = getpass.getpass("\nStep 1: Enter your true L4 Passphrase: ")
    # Verify directly via RBAC hidden method
    if not get_rbac()._verify_secret(passphrase, get_rbac().credentials["L4_PHR_HASH"]):
        print("❌ Incorrect Passphrase! Recovery failed.")
        sys.exit(1)
        
    print("\n✅ Passphrase Verified. Initiating Double-Factor Authentication...")
    print("Step 2: Sending secure unlock code to your registered Email via SMTP...")
    
    otp = send_recovery_email()
    if not otp:
        print("❌ SMTP Failure. Cannot complete recovery.")
        sys.exit(1)
        
    print("\nEmail Sent Successfully.")
    user_otp = input("Step 3: Check your email and enter the 6-digit code here: ")
    
    if user_otp.strip() == otp:
        revoke_lockdown()
    else:
        print("❌ Incorrect Code. System remains in Lockdown.")
        sys.exit(1)

if __name__ == "__main__":
    manual_terminal_unlock()
