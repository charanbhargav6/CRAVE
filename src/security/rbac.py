import os
import sys
import re
import json
import time
import getpass
import bcrypt
import logging
import threading
from pathlib import Path

# Fix for ModuleNotFoundError: No module named 'src'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Phase 11: Intruder photo on failed auth
try:
    from src.security.intruder_cam import capture_and_alert as _intruder_snap
    _INTRUDER_CAM_AVAILABLE = True
except ImportError:
    _INTRUDER_CAM_AVAILABLE = False

from src.security.encryption import crypto_manager, CREDS_PATH, CREDS_ENC_PATH, CRAVE_ROOT

logger = logging.getLogger("crave.security.rbac")

IDLE_TIMEOUT_SECONDS = 600  # 10 minutes

LOCKDOWN_FILE = os.path.join(CRAVE_ROOT, ".lockdown")

class RBACManager:
    def __init__(self):
        self.auth_level = 1  # Start at L1
        self.retry_counts = {"L2": 3, "L3": 2, "L4": 2}
        self.credentials = {}
        self._last_activity = time.time()
        self._idle_timer = None
        self._idle_lock = threading.Lock()
        self._load_credentials()
        self._start_idle_timer()

    # ── idle timer ────────────────────────────────────────────────────────────

    def touch(self):
        """Call this on every user interaction to reset the idle timer."""
        self._last_activity = time.time()

    def _start_idle_timer(self):
        """Background thread that checks for idle timeout every 30 seconds."""
        def _check_idle():
            while True:
                time.sleep(30)
                with self._idle_lock:
                    elapsed = time.time() - self._last_activity
                    if elapsed >= IDLE_TIMEOUT_SECONDS and self.auth_level > 1:
                        logger.info(f"Idle for {int(elapsed)}s — auto-demoting to L1")
                        self.demote_to_l1()

        self._idle_timer = threading.Thread(target=_check_idle, daemon=True, name="RBACIdleTimer")
        self._idle_timer.start()

    def check_lockdown(self):
        """Called by the Orchestrator/Main CRAVE entry to see if we should even boot."""
        if os.path.exists(LOCKDOWN_FILE):
            print("\n🚨 [SYSTEM LOCKDOWN ACTIVE] 🚨")
            print("CRAVE is completely locked due to unauthorized access attempts.")
            print(f"Run 'python tests/unlock.py' from terminal to recover.")
            sys.exit(1)

    def _hash_secret(self, secret: str) -> str:
        return bcrypt.hashpw(secret.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def _verify_secret(self, secret: str, hashed: str) -> bool:
        return bcrypt.checkpw(secret.encode('utf-8'), hashed.encode('utf-8'))

    def _setup_wizard(self):
        print("\n" + "="*50)
        print("🛡️  INITIALIZING CRAVE SECURITY LAYER 🛡️")
        print("="*50)
        print("This is your first boot. We need to set up your keys.")
        print("WARNING: DO NOT FORGET THESE.")

        # L2 PIN
        while True:
            pin = getpass.getpass("\n[1/3] Enter 6-digit PIN for Level 2 (Apps/Files): ")
            if len(pin) != 6 or not pin.isdigit():
                print("Error: Must be exactly 6 digits.")
                continue
            confirm = getpass.getpass("Confirm 6-digit PIN: ")
            if pin == confirm:
                break
            print("Mismatch! Try again.")

        # L3 Password
        while True:
            pwd = getpass.getpass("\n[2/3] Enter strong Password for Level 3 (API Keys/Trading): ")
            if len(pwd) < 10:
                print("Error: Must be at least 10 characters.")
                continue
            if not re.search(r'[A-Z]', pwd):
                print("Error: Must contain at least 1 uppercase letter.")
                continue
            if not re.search(r'[0-9]', pwd):
                print("Error: Must contain at least 1 number.")
                continue
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', pwd):
                print("Error: Must contain at least 1 symbol.")
                continue
            if pin in pwd:
                print("Error: Password cannot contain your L2 PIN.")
                continue
            confirm = getpass.getpass("Confirm Password: ")
            if pwd == confirm:
                break
            print("Mismatch! Try again.")

        # L4 Passphrase
        while True:
            phrase = getpass.getpass("\n[3/3] Enter 4-word Passphrase for Level 4 (Code/Lockdown): ")
            if len(phrase.split()) < 2:
                print("Error: Recommend at least multiple words separated by spaces.")
                continue
            if pwd in phrase or pin in phrase:
                print("Error: Passphrase must be completely unique from L2/L3.")
                continue
            confirm = getpass.getpass("Confirm Passphrase: ")
            if phrase == confirm:
                break
            print("Mismatch! Try again.")

        self.credentials = {
            "L2_PIN_HASH": self._hash_secret(pin),
            "L3_PWD_HASH": self._hash_secret(pwd),
            "L4_PHR_HASH": self._hash_secret(phrase)
        }
        
        # Save to plain JSON temporarily
        with open(CREDS_PATH, "w") as f:
            json.dump(self.credentials, f)
            
        # Encrypt it
        crypto_manager.encrypt_file(CREDS_PATH, CREDS_ENC_PATH)
        os.remove(CREDS_PATH)
        
        # Also let's encrypt .env if it exists
        crypto_manager.encrypt_env_file()
        
        print("\n✅ Setup Complete! Your credentials and API keys are now securely encrypted.")

    def _load_credentials(self):
        if not os.path.exists(CREDS_ENC_PATH) and not os.path.exists(CREDS_PATH):
            self._setup_wizard()
            return
            
        if os.path.exists(CREDS_ENC_PATH):
            success = crypto_manager.decrypt_file(CREDS_ENC_PATH, CREDS_PATH)
            if not success:
                print("FATAL: Cannot decrypt credentials! Are you missing the master key?")
                sys.exit(1)
                
        with open(CREDS_PATH, "r") as f:
            self.credentials = json.load(f)
            
        # Immediately overwrite and delete plain file for safety
        os.remove(CREDS_PATH)

    def trigger_lockdown(self):
        print("\n🚨 CRITICAL SECURITY BREACH DETECTED 🚨")
        print("Initiating full system lockdown...")
        with open(LOCKDOWN_FILE, "w") as f:
            f.write("LOCKED")
        sys.exit(1)

    def _is_higher_level_password(self, secret: str, target_level: int) -> bool:
        """Check if the entered secret matches a HIGHER level credential.
        This prevents accidental exposure of L3/L4 secrets at lower prompts."""
        try:
            if target_level <= 2 and "L3_PWD_HASH" in self.credentials:
                if self._verify_secret(secret, self.credentials["L3_PWD_HASH"]):
                    return True
            if target_level <= 3 and "L4_PHR_HASH" in self.credentials:
                if self._verify_secret(secret, self.credentials["L4_PHR_HASH"]):
                    return True
        except Exception:
            pass
        return False

    def _fire_intruder_snap(self, level: str, attempt: int):
        """Capture photo and send to Telegram on failed auth attempt."""
        if not _INTRUDER_CAM_AVAILABLE:
            return
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        # ghost_tracker will be set if TelegramAgent is running
        tracker = getattr(self, '_ghost_tracker', None)
        _intruder_snap(level=level, attempt=attempt, token=token, chat_id=chat_id, ghost_tracker=tracker)

    def authenticate_l2(self) -> bool:
        if self.auth_level >= 2: return True
        self.touch()
        
        try:
            from src.core.tts import speak
        except ImportError:
            speak = lambda x: None

        try:
            from src.security.face_id import verify_face
            speak("Verifying biometrics.")
            print("\n[L2 Auth] Checking Face ID...")
            matched, dist = verify_face()
            if matched:
                print(f"✅ Biometric L2 Access Granted (dist: {dist:.1f})")
                speak("Access granted.")
                self.auth_level = max(self.auth_level, 2)
                self.touch()
                return True
            else:
                print("❌ Biometric failed or not recognized.")
                speak("Biometric verification failed. Please type your Level 2 PIN in the terminal.")
        except Exception as e:
            print(f"[Face ID Error]: {e}")
            speak("Camera error. Please enter your code in the terminal.")

        max_attempts = self.retry_counts["L2"]
        attempts = max_attempts
        while attempts > 0:
            pin = getpass.getpass(f"\n[L2 Auth] Enter 6-digit PIN ({attempts} attempts left): ")
            # Reject if user accidentally enters a higher-level password
            if self._is_higher_level_password(pin, 2):
                print("⚠️ That looks like a higher-level credential. Rejected for safety.")
                self._fire_intruder_snap("L2", max_attempts - attempts + 1)
                attempts -= 1
                continue
            if self._verify_secret(pin, self.credentials["L2_PIN_HASH"]):
                print("✅ L2 Access Granted.")
                self.auth_level = max(self.auth_level, 2)
                self.touch()
                return True
            attempts -= 1
            print("❌ Incorrect PIN.")
            self._fire_intruder_snap("L2", max_attempts - attempts)
        
        print("⚠️ L2 Authentication Failed. 60-second cooldown initiated (simulation).")
        return False

    def authenticate_l3(self) -> bool:
        if self.auth_level >= 3: return True
        self.touch()
        
        try:
            from src.core.tts import speak
        except ImportError:
            speak = lambda x: None
            
        print("\n[L3 Auth] Authorization required for API access.")
        speak("Level 3 clearance required. Please enter your password in the terminal.")
        
        max_attempts = self.retry_counts["L3"]
        attempts = max_attempts
        while attempts > 0:
            pwd = getpass.getpass(f"Enter Password ({attempts} attempts left): ")
            # Reject if user accidentally enters L4 passphrase
            if self._is_higher_level_password(pwd, 3):
                print("⚠️ That looks like a higher-level credential. Rejected for safety.")
                self._fire_intruder_snap("L3", max_attempts - attempts + 1)
                attempts -= 1
                continue
                
            if self._verify_secret(pwd, self.credentials["L3_PWD_HASH"]):
                # Password verified. Now check Face ID to avoid SMTP
                print("\n[L3 Auth] Password accepted. Checking Biometrics to bypass OTP...")
                try:
                    from src.security.face_id import verify_face
                    matched, dist = verify_face()
                except Exception:
                    matched = False
                    
                if matched:
                    print(f"✅ L3 Access Granted via Face + Password.")
                    speak("Access granted.")
                else:
                    print("❌ Biometric failed. Resorting to SMTP Email Verification...")
                    speak("Biometric verification failed. Initiating SMTP protocol. Please check your email and type the OTP in the terminal.")
                    
                    import random
                    expected_otp = str(random.randint(100000, 999999))
                    try:
                        from src.agents.email_agent import EmailAgent
                        target_email = os.environ.get("OWNER_EMAIL", "crave.admin@localhost")
                        EmailAgent().send_email(to_address=target_email, subject="CRAVE L3 OTP", body=f"Your OTP code is: {expected_otp}")
                        print(f"[L3 Auth] OTP sent securely to {target_email}.")
                    except Exception as e:
                        print(f"SMTP Error: {e}")
                        speak("SMTP module failed. Locking down.")
                        return False
                        
                    # Custom 5 minute timeout logic inside getpass isn't trivial, so we block.
                    otp_attempt = input("\n[L3 Auth] Enter 6-digit OTP from Email: ")
                    if otp_attempt.strip() != expected_otp:
                        print("❌ Incorrect OTP.")
                        speak("Incorrect security code.")
                        self._fire_intruder_snap("L3", 1)
                        return False
                        
                    print("✅ OTP Verified. L3 Access Granted.")
                    speak("Access granted.")
                
                # Inject keys into memory legally
                crypto_manager.decrypt_env_to_memory()
                self.auth_level = max(self.auth_level, 3)
                self.touch()
                return True
                
            attempts -= 1
            print("❌ Incorrect Password.")
            speak("Incorrect password.")
            self._fire_intruder_snap("L3", max_attempts - attempts)
            
        print("⚠️ L3 Authentication Failed. System securing...")
        self.trigger_lockdown()
        return False

    def authenticate_l4(self) -> bool:
        if self.auth_level >= 4: return True
        self.touch()
        
        try:
            from src.core.tts import speak
        except ImportError:
            speak = lambda x: None
            
        print("\n[L4 Auth] MAXIMUM AUTHORIZATION REQUIRED.")
        speak("Maximum authorization required. Verifying biometrics.")

        # L4 mandates Face ID first
        try:
            from src.security.face_id import verify_face
            matched, dist = verify_face()
            if not matched:
                print("❌ Face ID Failed. Level 4 cannot proceed without physical presence.")
                speak("Biometric presence missing. Level 4 denied.")
                self.trigger_lockdown()
                return False
        except Exception:
            print("❌ Face ID Error. Level 4 denied.")
            self.trigger_lockdown()
            return False

        speak("Biometrics confirmed. Please enter your passphrase in the terminal.")
        max_attempts = self.retry_counts["L4"]
        attempts = max_attempts
        while attempts > 0:
            phrase = getpass.getpass(f"Enter Passphrase ({attempts} attempts left): ")
            if self._verify_secret(phrase, self.credentials["L4_PHR_HASH"]):
                # Phase 2: OTP via Telegram or SMTP
                import random
                expected_otp = str(random.randint(100000, 999999))
                speak("Passphrase accepted. Dispatching multi-factor validation.")
                
                # Try Telegram first
                telegram_sent = False
                target_email = os.environ.get("OWNER_EMAIL", "crave.admin@localhost")
                try:
                    token = os.environ.get("TELEGRAM_BOT_TOKEN")
                    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
                    if token and chat_id:
                        import requests
                        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                            json={"chat_id": chat_id, "text": f"🚨 L4 ACTION REQUESTED on Machine.\nOTP: {expected_otp}"}, timeout=5)
                        telegram_sent = True
                        print("[L4 Auth] Sent Telegram OTP.")
                except Exception:
                    pass

                # Fallback to SMTP
                if not telegram_sent:
                    try:
                        from src.agents.email_agent import EmailAgent
                        EmailAgent().send_email(to_address=target_email, subject="CRAVE L4 OTP", body=f"Your OTP code is: {expected_otp}\n\nWARNING: Level 4 Action Requested.")
                        print("[L4 Auth] Sent SMTP Email OTP.")
                    except Exception as e:
                        print(f"SMTP Error: {e}")
                        speak("Failed to initialize OOB verification.")
                        return False

                otp_attempt = input("\n[L4 Auth] Enter 6-digit OTP from Telegram/Email: ")
                if otp_attempt.strip() != expected_otp:
                    print("❌ Incorrect OTP.")
                    speak("Intruder protocol engaged.")
                    self.trigger_lockdown()
                    return False
                
                print("✅ OTP Verified. L4 Access Granted.")
                self.auth_level = 4
                self.touch()
                return True
                
            attempts -= 1
            print("❌ Incorrect Passphrase.")
            speak("Incorrect passphrase.")
            self._fire_intruder_snap("L4", max_attempts - attempts)
            
        print("⚠️ L4 Authentication Failed. Intruders detected.")
        self.trigger_lockdown()
        return False
        
    def demote_to_l1(self):
        """Removes physical keyboard/UI access and resets auth to 1.
           However, API keys remain active in memory for background Trading."""
        self.auth_level = 1
        print("🔒 Security demoted to L1. Physical keyboard access restricted.")
        # We deliberately DO NOT wipe os.environ here. 
        # This allows the 8:00 AM Telegram unlock to keep background trading APIs alive all day.

# ── Lazy singleton (fixes Bug #5 — no auto-init on import) ───────────────────

_rbac_instance = None

def get_rbac() -> RBACManager:
    """Get or create the RBAC manager singleton. Only initializes on first call."""
    global _rbac_instance
    if _rbac_instance is None:
        _rbac_instance = RBACManager()
    return _rbac_instance
