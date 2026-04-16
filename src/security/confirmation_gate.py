"""
CRAVE Security — Confirmation Gate (Two-Channel Auth)
Save to: D:\\CRAVE\\src\\security\\confirmation_gate.py

Handles approval for dangerous operations (model changes, self-modification).
Two channels:
  LOCAL:  Face ID + L4 passphrase
  REMOTE: OTP via SMTP email → verify reply in Telegram bot

Thread-safe, singleton pattern.
"""

import os
import sys
import time
import random
import string
import logging
import threading
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from typing import Optional, Callable

logger = logging.getLogger("crave.security.confirmation_gate")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


class PendingApproval:
    """Tracks a single pending approval request."""

    def __init__(self, description: str, otp: str, expires_at: datetime):
        self.description = description
        self.otp = otp
        self.expires_at = expires_at
        self.approved = False
        self.denied = False
        self.attempts = 0
        self.max_attempts = 3
        self.event = threading.Event()  # Signals when decision is made


class ConfirmationGate:
    """
    Dual-channel approval system for dangerous operations.
    
    Usage:
        gate = get_confirmation_gate()
        approved = gate.request_approval(
            description="Upgrade primary model to qwen3:14b",
            operation_type="model_upgrade",
        )
        if approved:
            # proceed with operation
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._pending: dict[str, PendingApproval] = {}
        self._otp_expiry_minutes = 5
        self._timeout_minutes = 15
        self._initialized = True

    # ── LOCAL APPROVAL (Face + L4) ────────────────────────────────────────────

    def _approve_local(self, description: str) -> bool:
        """
        At-laptop approval: Face ID scan + L4 passphrase.
        Returns True if both pass.
        """
        print(f"\n{'='*60}")
        print(f"  ⚠️  APPROVAL REQUIRED")
        print(f"{'='*60}")
        print(f"  Action: {description}")
        print(f"{'='*60}")

        # Step 1: Face ID
        try:
            from src.security.face_id import verify_face
            matched, distance = verify_face()
            if not matched:
                print(f"  ❌ Face ID failed (distance: {distance:.3f})")
                logger.warning(f"[ConfirmGate] Face ID rejected for: {description}")
                return False
            print(f"  ✅ Face ID verified (distance: {distance:.3f})")
        except ImportError:
            print("  ⚠️ Face ID not available — skipping biometric check")
        except Exception as e:
            print(f"  ⚠️ Face ID error: {e} — skipping biometric check")

        # Step 2: L4 Passphrase
        try:
            from src.security.rbac import get_rbac
            import getpass

            rbac = get_rbac()
            passphrase = getpass.getpass("  Enter L4 passphrase: ")

            if rbac._verify_secret(passphrase, rbac.credentials.get("L4_PHR_HASH", "")):
                print("  ✅ L4 passphrase verified")
                logger.info(f"[ConfirmGate] LOCAL approval granted for: {description}")
                return True
            else:
                print("  ❌ L4 passphrase incorrect")
                return False
        except Exception as e:
            logger.error(f"[ConfirmGate] L4 auth error: {e}")
            return False

    # ── REMOTE APPROVAL (Email OTP + Telegram verify) ─────────────────────────

    def _generate_otp(self) -> str:
        """Generate a 6-digit one-time password."""
        return ''.join(random.choices(string.digits, k=6))

    def _send_otp_email(self, otp: str, description: str) -> bool:
        """Send OTP via Gmail SMTP."""
        email_user = os.environ.get("GMAIL_USER", "")
        email_pass = os.environ.get("GMAIL_APP_PASSWORD", "")

        if not email_user or not email_pass:
            logger.error("[ConfirmGate] Gmail credentials not configured for OTP delivery.")
            return False

        subject = f"🔐 CRAVE Approval Code: {otp}"
        body = f"""
CRAVE is requesting your approval for a critical operation.

─────────────────────────────────────
ACTION: {description}
TIME:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
CODE:   {otp}
─────────────────────────────────────

This code expires in {self._otp_expiry_minutes} minutes.

To approve: Open Telegram and reply to CRAVE bot with this code.
To deny: Ignore this email or reply "DENY" in Telegram.

⚠️ If you did not trigger this action, someone else may have 
access to your system. Reply "LOCKDOWN" in Telegram immediately.
"""

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email_user
        msg["To"] = email_user

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(email_user, email_pass)
                server.send_message(msg)
            logger.info(f"[ConfirmGate] OTP email sent for: {description}")
            return True
        except Exception as e:
            logger.error(f"[ConfirmGate] Failed to send OTP email: {e}")
            return False

    def _notify_telegram_pending(self, description: str, request_id: str) -> bool:
        """Send Telegram notification about pending approval."""
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            return False

        try:
            import requests
            text = (
                f"⚠️ *APPROVAL REQUIRED*\n\n"
                f"*Action:* {description}\n"
                f"*Time:* {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"📧 An OTP code has been sent to your email.\n"
                f"Reply here with the code to approve.\n"
                f"Reply `DENY` to reject.\n"
                f"Reply `LOCKDOWN` if this wasn't you.\n\n"
                f"_Code expires in {self._otp_expiry_minutes} minutes._"
            )
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            return True
        except:
            return False

    def _approve_remote(self, description: str) -> bool:
        """
        Remote approval flow:
        1. Generate OTP
        2. Send OTP via email (SMTP)
        3. Send Telegram notification
        4. Wait for user to reply with OTP in Telegram
        5. Verify OTP match + expiry
        """
        otp = self._generate_otp()
        request_id = f"req_{int(time.time())}"
        expires_at = datetime.now() + timedelta(minutes=self._otp_expiry_minutes)

        pending = PendingApproval(description, otp, expires_at)
        self._pending[request_id] = pending

        # Send OTP via email
        if not self._send_otp_email(otp, description):
            logger.error("[ConfirmGate] Failed to send OTP email. Denying request.")
            del self._pending[request_id]
            return False

        # Notify Telegram
        self._notify_telegram_pending(description, request_id)

        # Wait for response (blocking with timeout)
        timeout_sec = self._timeout_minutes * 60
        pending.event.wait(timeout=timeout_sec)

        # Check result
        result = pending.approved
        del self._pending[request_id]

        if result:
            logger.info(f"[ConfirmGate] REMOTE approval granted for: {description}")
        else:
            logger.info(f"[ConfirmGate] REMOTE approval denied/timeout for: {description}")

        return result

    def verify_telegram_otp(self, code: str) -> str:
        """
        Called by TelegramAgent when user replies with a code.
        Returns: "approved", "denied", "invalid", "expired", "no_pending"
        """
        for req_id, pending in list(self._pending.items()):
            if datetime.now() > pending.expires_at:
                pending.denied = True
                pending.event.set()
                return "expired"

            pending.attempts += 1

            if code.upper() == "DENY":
                pending.denied = True
                pending.event.set()
                return "denied"

            if code.upper() == "LOCKDOWN":
                pending.denied = True
                pending.event.set()
                # Trigger system lockdown
                try:
                    from src.security.rbac import get_rbac
                    get_rbac().trigger_lockdown()
                except:
                    pass
                return "lockdown"

            if code == pending.otp:
                pending.approved = True
                pending.event.set()
                return "approved"

            if pending.attempts >= pending.max_attempts:
                pending.denied = True
                pending.event.set()
                return "max_attempts"

            return "invalid"

        return "no_pending"

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    def request_approval(
        self,
        description: str,
        operation_type: str = "general",
        force_remote: bool = False,
    ) -> bool:
        """
        Request approval for a dangerous operation.
        
        Auto-detects whether to use local or remote channel:
        - If Face ID camera is available → try local first
        - If camera unavailable or force_remote → use email OTP + Telegram
        
        Args:
            description: Human-readable description of what's being approved
            operation_type: "model_upgrade", "model_delete", "code_modify", "general"
            force_remote: Force remote approval even if local is possible
            
        Returns:
            True if approved, False if denied/timeout
        """
        # Log the attempt
        try:
            from src.core.reasoning_log import get_reasoning_log
            get_reasoning_log().log_action(
                action="APPROVAL_REQUESTED",
                trigger=description,
                reasoning={"type": operation_type, "channel": "pending"},
            )
        except:
            pass

        if force_remote:
            return self._approve_remote(description)

        # Try local first (camera + L4)
        try:
            import cv2
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            camera_available = cap.isOpened()
            cap.release()
        except:
            camera_available = False

        if camera_available:
            result = self._approve_local(description)
        else:
            result = self._approve_remote(description)

        # Log result
        try:
            from src.core.reasoning_log import get_reasoning_log
            get_reasoning_log().log_action(
                action="APPROVAL_RESULT",
                trigger=description,
                reasoning={"approved": result, "type": operation_type},
                result="APPROVED" if result else "DENIED",
            )
        except:
            pass

        return result

    @property
    def has_pending(self) -> bool:
        return len(self._pending) > 0


def get_confirmation_gate() -> ConfirmationGate:
    """Return the global ConfirmationGate singleton."""
    return ConfirmationGate()
