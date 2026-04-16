import os
import sys
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from src.security.encryption import crypto_manager
from src.security.rbac import get_rbac, LOCKDOWN_FILE
from src.security.unlock import send_recovery_email, revoke_lockdown

logger = logging.getLogger("crave.security.telegram_gate")

pending_unlocks = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ CRAVE Telegram Security Gate Online.")

async def handle_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    allowed_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if chat_id != str(allowed_chat_id):
        await update.message.reply_text("🚨 UNAUTHORIZED USER.")
        return
        
    if not os.path.exists(LOCKDOWN_FILE):
        await update.message.reply_text("System is not currently locked down.")
        return
        
    try:
        passphrase = context.args[0]
    except IndexError:
        await update.message.reply_text("Usage: /unlock <passphrase>")
        return
        
    if not get_rbac()._verify_secret(passphrase, get_rbac().credentials["L4_PHR_HASH"]):
        await update.message.reply_text("❌ Incorrect Passphrase. Attempt Logged.")
        return
        
    await update.message.reply_text("✅ Passphrase Verified. Triggering 2FA SMTP Email...")
    
    otp = send_recovery_email()
    if not otp:
        await update.message.reply_text("❌ Failed to send SMTP email. Cannot unbrick system remotely.")
        return
        
    pending_unlocks[chat_id] = otp
    await update.message.reply_text("Email sent! Reply with the 6-digit code to conclude the unlocking process.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    text = update.message.text.strip()
    
    if chat_id in pending_unlocks:
        if text == pending_unlocks[chat_id]:
            revoke_lockdown()
            del pending_unlocks[chat_id]
            await update.message.reply_text("✅ SYSTEM UNLOCKED OVERRIDE COMPLETE. You may now start CRAVE locally.")
        else:
            await update.message.reply_text("❌ Incorrect OTP Code.")
            
def start_telegram_gate_daemon():
    # Only load keys into the global scope here
    crypto_manager.decrypt_env_to_memory()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("No Telegram token found. Cannot start daemon.")
        return
        
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unlock", handle_unlock))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("\n[Telegram Gate] Daemonic listener starting in background...")
    # This will strictly block if run directly.
    app.run_polling()

if __name__ == "__main__":
    start_telegram_gate_daemon()
