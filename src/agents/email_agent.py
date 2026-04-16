import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import logging
from src.security.encryption import crypto_manager
from src.core.memory_bank import MemoryBank

logger = logging.getLogger("crave.agents.email")

class EmailAgent:
    def __init__(self):
        # Using DPAPI injected env vars
        self.smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.environ.get("SMTP_PORT", 587))
        self.smtp_user = os.environ.get("SMTP_USER", "")
        self.smtp_pass = os.environ.get("SMTP_PASS", "")
        self.memory = MemoryBank()

    def send_email(self, to_address: str, subject: str, body: str) -> str:
        """Sends an email directly via local SMTP."""
        if not self.smtp_user or not self.smtp_pass:
            return "Error: SMTP credentials not injected into environment."
        
        task_id = f"email_{int(time.time() * 1000)}"
        self.memory.log_task_start(task_id, "send_email", {"to": to_address, "subject_len": len(subject)})
        
        try:
            # Check ML Success Probability (just logging it for now, user can see CRAVE's self-awareness)
            prob = self.memory.predict_success_probability("send_email", {"to": to_address})
            logger.info(f"ML predicts {prob * 100}% chance of email success to {to_address}.")

            msg = MIMEMultipart()
            msg['From'] = self.smtp_user
            msg['To'] = to_address
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
                
            self.memory.log_task_end(task_id, success=True)
            return f"Email successfully sent to {to_address}."
            
        except Exception as e:
            self.memory.log_task_end(task_id, success=False, error_msg=str(e))
            logger.error(f"Email failed: {e}")
            return f"Failed to send email: {e}"
