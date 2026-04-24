"""
CRAVE Phase 8.1 - Telegram Remote Control (Ghost Protocol)
Provides full remote control of CRAVE from your phone via Telegram Bot.

Commands:
  /status    — System status
  /kill      — Emergency kill switch
  /long      — Force next trade = BUY
  /short     — Force next trade = SELL
  /close     — Close all open positions
  /pause     — Pause autonomous trading
  /resume    — Resume autonomous trading
  /logs      — Trading P&L summary
  /sys_logs  — Last 20 lines of crave.log
  /silent N  — Enter silent mode for N minutes
  /unlock    — Remote lockdown recovery
  /authorize — Approve daily 8AM trading gate
  (free text) — Pipes into Orchestrator directly

Ghost Protocol: ALL messages auto-delete after 30 minutes.
"""

import os
import time
import logging
import asyncio
import threading
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logger = logging.getLogger("crave.agents.telegram")

class TelegramAgent:
    def __init__(self, orchestrator=None):
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.orchestrator = orchestrator
        self.app = None
        self._loop = None
        
        # Ghost Protocol Memory
        self._ghost_queue = []  # [(chat_id, message_id, timestamp)]
        self._ghost_lock = threading.Lock()
        self._ghost_timeout = 1800  # 30 minutes in seconds
        
        if self.token:
            t = threading.Thread(target=self._ghost_worker, daemon=True, name="GhostProtocol")
            t.start()

    # -----------------------------------------------------------------
    # GHOST PROTOCOL — Auto-delete messages after 30 minutes
    # -----------------------------------------------------------------
    def _ghost_worker(self):
        """Background thread that deletes messages older than 30 minutes."""
        while True:
            time.sleep(60)
            now = time.time()
            to_delete = []
            
            with self._ghost_lock:
                for item in self._ghost_queue:
                    chat_id, msg_id, ts = item
                    if now - ts >= self._ghost_timeout:
                        to_delete.append(item)
            
            successfully_deleted = set()
            for item in to_delete:
                chat_id, msg_id, ts = item
                url = f"https://api.telegram.org/bot{self.token}/deleteMessage"
                try:
                    resp = requests.post(url, json={"chat_id": chat_id, "message_id": msg_id}, timeout=5)
                    if resp.status_code == 200 or "message to delete not found" in resp.text.lower() or "message can't be deleted" in resp.text.lower():
                        successfully_deleted.add((chat_id, msg_id))
                except Exception:
                    pass
                    
            with self._ghost_lock:
                self._ghost_queue = [x for x in self._ghost_queue if (x[0], x[1]) not in successfully_deleted]

    def _track_message(self, chat_id, message_id):
        """Log message ID for auto-deletion after 30 mins."""
        with self._ghost_lock:
            self._ghost_queue.append((chat_id, message_id, time.time()))

    def _is_authorized(self, update: Update) -> bool:
        """Security Gate: Ensure the sender is actually the owner."""
        incoming_id = str(update.effective_chat.id).strip()
        if not self.chat_id or (incoming_id != self.chat_id and self.chat_id != ""):
            logger.warning(f"Unauthorized Telegram Access Attempt from Chat ID: {incoming_id}")
            return False
        return True

    # -----------------------------------------------------------------
    # SYSTEM COMMANDS
    # -----------------------------------------------------------------
    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        status_parts = [f"📊 *CRAVE STATUS*"]
        if self.orchestrator:
            st = self.orchestrator.get_status()
            status_parts.append(f"State: {self.orchestrator.state}")
            status_parts.append(f"Running: {st.get('running', False)}")
            status_parts.append(f"Silent: {st.get('silent_mode', False)}")
            status_parts.append(f"Messages: {st.get('msg_count', 0)}")
            status_parts.append(f"Voice: {st.get('voice_running', False)}")
            
            # Trading status
            paused = getattr(self.orchestrator, '_trading_paused', False)
            override = getattr(self.orchestrator, '_trade_direction_override', None)
            status_parts.append(f"Trading: {'PAUSED' if paused else 'ACTIVE'}")
            if override:
                status_parts.append(f"Override: {override.upper()}")
        else:
            status_parts.append("Orchestrator: Offline")
        
        msg = "\n".join(status_parts)
        reply = await update.message.reply_text(msg, parse_mode="Markdown")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_kill(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        reply = await update.message.reply_text("🚨 EMERGENCY KILL SWITCH ENGAGED. Securing systems...")
        self._track_message(reply.chat.id, reply.message_id)
        
        
        if self.orchestrator:
            result = self.orchestrator.handle("kill switch", source="telegram")
            reply = await update.message.reply_text(f"🛑 {result}")
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
        self._track_message(reply.chat.id, reply.message_id)
        logger.critical("Remote /kill command executed via Telegram.")

    # -----------------------------------------------------------------
    # TRADING OVERRIDE COMMANDS
    # -----------------------------------------------------------------
    async def _cmd_long(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        if self.orchestrator:
            self.orchestrator._trade_direction_override = "buy"
            reply = await update.message.reply_text("📈 Override: Next trade = BUY. Auto resumes after.")
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_short(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        if self.orchestrator:
            self.orchestrator._trade_direction_override = "sell"
            reply = await update.message.reply_text("📉 Override: Next trade = SELL. Auto resumes after.")
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        if self.orchestrator:
            result = self.orchestrator.handle("close all positions", source="telegram")
            reply = await update.message.reply_text(f"🔒 {result}")
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        if self.orchestrator:
            self.orchestrator._trading_paused = True
            reply = await update.message.reply_text("⏸ Trading PAUSED. Open positions remain. Use /resume to restart.")
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        if self.orchestrator:
            self.orchestrator._trading_paused = False
            reply = await update.message.reply_text("▶️ Trading RESUMED. Full autonomous execution re-engaged.")
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Trading-specific P&L summary from MemoryBank."""
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        try:
            from src.core.memory_bank import MemoryBank
            mb = MemoryBank()
            stats = mb.analyze_consistency()
            
            if stats.get("status") == "warming_up":
                msg = f"📊 *TRADING LOGS*\n{stats.get('message', 'Insufficient data.')}"
            else:
                msg = (
                    f"📊 *TRADING P&L REPORT*\n"
                    f"Status: {stats.get('status', 'N/A').upper()}\n"
                    f"Sample Size: {stats.get('sample_size', 0)} trades\n"
                    f"Win Rate: {stats.get('win_rate', 0)}%\n"
                    f"Total P&L: ${stats.get('total_pnl', 0)}"
                )
            
            # Also append recent trading log tail
            trading_log = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "Logs", "trading.log")
            if os.path.exists(trading_log):
                with open(trading_log, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    tail = "".join(lines[-10:])
                    if tail.strip():
                        msg += f"\n\n📝 *Recent Activity:*\n```\n{tail}\n```"
        except Exception as e:
            msg = f"❌ Error reading trading logs: {e}"
        
        reply = await update.message.reply_text(msg, parse_mode="Markdown")
        self._track_message(reply.chat.id, reply.message_id)

    # -----------------------------------------------------------------
    # SYSTEM MANAGEMENT COMMANDS
    # -----------------------------------------------------------------
    async def _cmd_sys_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        log_path = os.path.join(os.environ.get("CRAVE_ROOT", r"D:\CRAVE"), "Logs", "crave.log")
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    tail = "".join(lines[-20:])
            except:
                tail = "Error reading log."
        else:
            tail = "Log file not found."
        
        reply = await update.message.reply_text(f"🖥️ SYSTEM LOGS:\n```\n{tail}\n```", parse_mode="Markdown")
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_silent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enter silent mode remotely for N minutes. Usage: /silent 90"""
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        # Parse minutes from args
        args = context.args
        minutes = 30  # Default
        if args and args[0].isdigit():
            minutes = int(args[0])
        
        if self.orchestrator:
            self.orchestrator.set_silent_mode(True)
            reply = await update.message.reply_text(f"🔇 Silent mode ON for {minutes} minutes.")
            self._track_message(reply.chat.id, reply.message_id)
            
            # Schedule auto-resume
            def _auto_resume():
                time.sleep(minutes * 60)
                if self.orchestrator:
                    self.orchestrator.set_silent_mode(False)
                    self.send_message_sync(f"🔊 Silent mode auto-expired after {minutes} minutes.")
            
            threading.Thread(target=_auto_resume, daemon=True, name="SilentTimer").start()
        else:
            reply = await update.message.reply_text("❌ Orchestrator offline.")
            self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_unlock(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remote lockdown recovery. Usage: /unlock <passphrase>"""
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        args = context.args
        if not args:
            reply = await update.message.reply_text("Usage: /unlock <your L4 passphrase>")
            self._track_message(reply.chat.id, reply.message_id)
            return
        
        phrase = " ".join(args)
        
        try:
            from src.security.rbac import get_rbac, LOCKDOWN_FILE
            rbac = get_rbac()
            
            if rbac._verify_secret(phrase, rbac.credentials.get("L4_PHR_HASH", "")):
                # Remove lockdown file
                if os.path.exists(LOCKDOWN_FILE):
                    os.remove(LOCKDOWN_FILE)
                    reply = await update.message.reply_text("🔓 Lockdown file removed. Restart CRAVE to resume.")
                else:
                    reply = await update.message.reply_text("ℹ️ No active lockdown found.")
                
                rbac.auth_level = 4
                rbac.touch()
            else:
                reply = await update.message.reply_text("❌ Passphrase incorrect. Lockdown remains.")
                logger.warning("Remote unlock attempt with wrong passphrase via Telegram.")
        except Exception as e:
            reply = await update.message.reply_text(f"❌ Unlock error: {e}")
        
        self._track_message(reply.chat.id, reply.message_id)

    async def _cmd_authorize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve the daily 8AM trading gate."""
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        if self.orchestrator:
            self.orchestrator._trading_paused = False
            self.orchestrator.set_state("idle")
        
        reply = await update.message.reply_text(
            "✅ DAILY AUTHORIZATION ACCEPTED.\n"
            "Trading & automation systems are now fully online."
        )
        self._track_message(reply.chat.id, reply.message_id)

    # -----------------------------------------------------------------
    # BACKTEST COMMAND
    # -----------------------------------------------------------------
    async def _cmd_backtest(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Run a backtest. Usage: /backtest XAUUSD 1 year"""
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        args = context.args
        if not args:
            reply = await update.message.reply_text(
                "Usage: /backtest <symbol> [period]\n"
                "Examples:\n"
                "  /backtest XAUUSD 1 year\n"
                "  /backtest BTC 3 months\n"
                "  /backtest AAPL 15 days"
            )
            self._track_message(reply.chat.id, reply.message_id)
            return
        
        # Build the command string for the orchestrator
        cmd_text = "backtest " + " ".join(args)
        
        reply = await update.message.reply_text(f"⏳ Running backtest: {cmd_text}...")
        self._track_message(reply.chat.id, reply.message_id)
        
        if self.orchestrator:
            def _runner():
                try:
                    res = self.orchestrator.handle(cmd_text, source="telegram")
                    self.send_message_sync(res or "Backtest produced no output.")
                except Exception as e:
                    self.send_message_sync(f"Backtest error: {str(e)}")
            threading.Thread(target=_runner, daemon=True, name="TelegramBacktest").start()

    # -----------------------------------------------------------------
    # FREE-TEXT PASS-THROUGH (anything not a /command)
    # -----------------------------------------------------------------
    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Pipes natural text commands directly into the Orchestrator."""
        if not self._is_authorized(update): return
        self._track_message(update.effective_chat.id, update.message.message_id)
        
        reply = await update.message.reply_text("⚡ Processing...")
        self._track_message(reply.chat.id, reply.message_id)
        
        if self.orchestrator:
            def _runner(chat_id, msg_id):
                try:
                    res = self.orchestrator.handle(update.message.text, source="telegram")
                    url = f"https://api.telegram.org/bot{self.token}/editMessageText"
                    requests.post(url, json={"chat_id": chat_id, "message_id": msg_id, "text": res, "parse_mode": "Markdown"}, timeout=10)
                except Exception as e:
                    url = f"https://api.telegram.org/bot{self.token}/editMessageText"
                    requests.post(url, json={"chat_id": chat_id, "message_id": msg_id, "text": f"Error: {str(e)}"}, timeout=10)
            threading.Thread(target=_runner, args=(reply.chat.id, reply.message_id), daemon=True).start()

    # -----------------------------------------------------------------
    # OUTBOUND PUSH (called by other modules)
    # -----------------------------------------------------------------
    def send_message_sync(self, text: str):
        """Sends arbitrary updates dynamically. Auto-tracked for Ghost Protocol deletion."""
        if not self.token or not self.chat_id: return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            resp = requests.post(url, json={"chat_id": self.chat_id, "text": text}, timeout=5)
            data = resp.json()
            if data.get("ok"):
                self._track_message(self.chat_id, data["result"]["message_id"])
        except Exception as e:
            logger.error(f"Failed to push telegram notification: {e}")

    # -----------------------------------------------------------------
    # ERROR HANDLER — Suppress stack-trace spam from network issues
    # -----------------------------------------------------------------
    async def _error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Gracefully handle Telegram API errors without flooding logs."""
        import telegram.error
        err = context.error
        if isinstance(err, telegram.error.NetworkError):
            # Single-line warning instead of 100-line stack trace
            logger.warning(f"[Telegram] NetworkError (will auto-retry): {err.__class__.__name__}")
        elif isinstance(err, telegram.error.Conflict):
            logger.error("[Telegram] Bot conflict — another instance may be running.")
        else:
            logger.error(f"[Telegram] Unhandled error: {err}", exc_info=False)

    # -----------------------------------------------------------------
    # BOT STARTUP
    # -----------------------------------------------------------------
    def _run_bot(self):
        """Start Telegram polling with exponential backoff retry."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        max_retries = 10
        backoff = 5  # seconds, grows: 5 → 10 → 30 → 60 (capped)
        
        for attempt in range(1, max_retries + 1):
            try:
                self.app = ApplicationBuilder().token(self.token).build()
                
                # System commands
                self.app.add_handler(CommandHandler("status", self._cmd_status))
                self.app.add_handler(CommandHandler("kill", self._cmd_kill))
                self.app.add_handler(CommandHandler("sys_logs", self._cmd_sys_logs))
                self.app.add_handler(CommandHandler("authorize", self._cmd_authorize))
                
                # Trading override commands
                self.app.add_handler(CommandHandler("long", self._cmd_long))
                self.app.add_handler(CommandHandler("short", self._cmd_short))
                self.app.add_handler(CommandHandler("close", self._cmd_close))
                self.app.add_handler(CommandHandler("pause", self._cmd_pause))
                self.app.add_handler(CommandHandler("resume", self._cmd_resume))
                self.app.add_handler(CommandHandler("logs", self._cmd_logs))
                
                # Remote management commands
                self.app.add_handler(CommandHandler("silent", self._cmd_silent))
                self.app.add_handler(CommandHandler("unlock", self._cmd_unlock))
                
                # Backtest command
                self.app.add_handler(CommandHandler("backtest", self._cmd_backtest))
                
                # Handle all natural text
                self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self._handle_text))
                
                # Register error handler to suppress NetworkError spam
                self.app.add_error_handler(self._error_handler)
                
                logger.info(f"Telegram Agent starting (attempt {attempt}/{max_retries}). 13 commands registered.")
                self.app.run_polling(stop_signals=None)
                break  # Clean exit — don't retry
            except Exception as e:
                logger.warning(f"[Telegram] Polling failed (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    logger.info(f"[Telegram] Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)  # Cap at 60s
                else:
                    logger.error("[Telegram] Max retries reached. Remote control disabled.")

    def start(self):
        if not self.token:
            logger.warning("No TELEGRAM_BOT_TOKEN found. Remote control disabled.")
            return
        t = threading.Thread(target=self._run_bot, daemon=True, name="TelegramListener")
        t.start()
