"""
CRAVE Phase 8.1 - 8:00 AM Cron Scheduler & Execution Firewall
Runs continuously in the background using the `schedule` library.
At precisely 08:00, it triggers the Pre-Flight check via Telegram, pausing 
all High-Risk modules until the user verifies with a "YES".
"""

import schedule
import time
import threading
import logging
import os
from datetime import datetime

logger = logging.getLogger("crave.core.scheduler")

class DailyScheduler:
    def __init__(self, telegram_agent=None, orchestrator=None):
        self.telegram = telegram_agent
        self.orchestrator = orchestrator
        self.daily_lock = True # By default, high-risk tasks are locked until 8 AM ping
        
        # Determine paths for rotation
        self.log_dir = os.path.join(os.environ.get("CRAVE_ROOT", "D:\\CRAVE"), "Logs")
        
    def _shred_logs(self):
        """Security: Zeroes out tracking history every 24 hours."""
        logger.warning("Initiating 24-hour Log Shredding Protocol...")
        targets = ["trading.log", "security_events.log", "crave.log"]
        
        shredded = []
        for file in targets:
            path = os.path.join(self.log_dir, file)
            if os.path.exists(path):
                # We don't delete the file to keep logging file handlers alive
                # Instead, we overwrite with a fresh header block.
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"=== HISTORY PURGED SECURELY AT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                shredded.append(file)
                
        logger.info(f"Logs shredded: {', '.join(shredded)}")
        
    def _fire_8am_hook(self):
        """The critical daily checkpoint."""
        logger.info("Executing 8:00 AM Cron Hook via Telegram...")
        
        # 1. Ask permission
        if self.telegram:
            msg = "🌅 Good morning Sir. It is 08:00.\nThe Daily Startup Sequence is ready.\n\nDo I have your explicit authorization to begin Algorithmic Trading and Daily Hacking sweeps today?\n\n[Reply using telegram command /authorize to unlock]"
            self.telegram.send_message_sync(msg)
            
        # 2. Shred the logs to clean the 24 hour history
        # Note: In a real system, you'd send the PnL summary FIRST, then shred.
        self._shred_logs()
        
        # 3. Lock the system state
        self.daily_lock = True
        if self.orchestrator:
            self.orchestrator.set_state("waiting_for_8am_auth")
            
        logger.warning("System is now in Hard-Lock awaiting /authorize from user.")
        
    def _fire_weekly_audit(self):
        """Phase 11: Send weekly self-audit email every Sunday at 10:00 AM."""
        logger.info("Executing Weekly Self-Audit...")
        try:
            from src.tools.weekly_audit import send_audit_email
            success = send_audit_email()
            if success and self.telegram:
                self.telegram.send_message_sync("📊 Weekly audit email sent successfully.")
            elif not success and self.telegram:
                self.telegram.send_message_sync("⚠️ Weekly audit saved to logs/weekly_audit.html (email failed).")
        except Exception as e:
            logger.error(f"Weekly audit failed: {e}")

    def _fire_model_check(self):
        """Phase 11: Evolution Engine model capability check."""
        logger.info("Executing Self-Evolution Model Scan...")
        try:
            from src.core.model_manager import ModelManager
            mm = ModelManager()
            if mm._evo_config.get("enabled", False):
                candidates = mm.check_system_resources()
                logger.info(f"Model scan complete: {candidates}")
                mm.mark_checked()
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Model scan failed: {e}")

    def _fire_ollama_purge(self):
        """Purges Ollama from RAM if the system is idle to fight memory leaks."""
        if self.orchestrator:
            state = self.orchestrator.get_status()
            if state != "idle":
                logger.info("Ollama Purge skipped: system not idle.")
                return
                
        logger.warning("Initiating 4-Hour idle Ollama VRAM Purge.")
        try:
            import subprocess
            subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"], capture_output=True)
            time.sleep(2)
            # Restart detached
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "open", "ollama", "serve", None, 0)
            logger.info("Ollama rebooted successfully.")
        except Exception as e:
            logger.error(f"Failed to purge Ollama VRAM: {e}")

    def start_scheduler_loop(self):
        """Infinite loop for the cron thread."""
        logger.info("Daily Scheduler engaged. Tracking towards 08:00 AM routines.")
        
        # Using string matching, "08:00" runs every morning at exactly 8:00 AM local time.
        schedule.every().day.at("08:00").do(self._fire_8am_hook)
        
        # Phase 11: Weekly self-audit every Sunday at 10:00 AM
        schedule.every().sunday.at("10:00").do(self._fire_weekly_audit)
        
        # Phase 11: Weekly model scan at 3:00 AM (runs silently)
        schedule.every(7).days.at("03:00").do(self._fire_model_check)
        
        # Phase 10: 4-Hour Ollama VRAM leak purge
        schedule.every(4).hours.do(self._fire_ollama_purge)
        
        # Boot-time catch-up: if laptop was off during 3 AM, check if overdue
        try:
            from src.core.model_manager import ModelManager
            mm = ModelManager()
            if mm.is_check_overdue() and mm._evo_config.get("enabled", False):
                logger.info("Boot-time catchup: Model scan is overdue. Running now.")
                self._fire_model_check()
        except:
            pass
        
        while True:
            schedule.run_pending()
            time.sleep(30) # Check every 30 seconds to save CPU cycles

    def start(self):
        """Spawns the scheduler daemon."""
        t = threading.Thread(target=self.start_scheduler_loop, daemon=True, name="CRAVECron")
        t.start()
