"""
CRAVE v10.0 — Main Entry Point (Session 3 Complete)
=====================================================
All modules wired. Bot is now fully operational in paper mode.

Run:  python run_bot.py
      python run_bot.py --status
      python run_bot.py --backtest
      python run_bot.py --setup
"""

import os
import sys
import socket
import logging
import argparse
import time
import schedule
from pathlib import Path
from datetime import datetime, timezone

# ── Load .env ─────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    print("Run: pip install python-dotenv")

sys.path.insert(0, str(Path(__file__).parent))

# ── Logging ───────────────────────────────────────────────────────────────────
from Config.config import LOGGING as LOG_CFG, LOGS_DIR
import logging.handlers

def setup_logging():
    level    = getattr(logging, LOG_CFG.get("level", "INFO"))
    handlers = []

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    handlers.append(ch)

    log_file = LOGS_DIR / "crave.log"
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=LOG_CFG.get("max_size_mb", 10) * 1024 * 1024,
        backupCount=LOG_CFG.get("backup_count", 5),
    )
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    handlers.append(fh)

    logging.basicConfig(level=level, handlers=handlers, force=True)

setup_logging()
logger = logging.getLogger("crave.main")


# ─────────────────────────────────────────────────────────────────────────────

def detect_node() -> str:
    from Config.config import NODES
    hostname = socket.gethostname().upper()
    for name, cfg in NODES.items():
        if any(p.upper() in hostname for p in cfg.get("hostname_patterns", [])):
            return name
    return "aws"


def print_banner(node: str, mode: str):
    print(f"""
╔══════════════════════════════════════════════════════╗
║                 CRAVE v10.0                          ║
║     Smart Money Concept Trading System               ║
╠══════════════════════════════════════════════════════╣
║  Node     : {node:<42}║
║  Mode     : {mode:<42}║
║  Time     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'):<42}║
╚══════════════════════════════════════════════════════╝""")


def check_env() -> bool:
    missing_req = [k for k in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
                   if not os.environ.get(k)]
    if missing_req:
        logger.warning(f"Missing env vars: {missing_req}. Edit .env")

    return bool(
        os.environ.get("BINANCE_API_KEY") or
        os.environ.get("ALPACA_API_KEY")
    )


# ─────────────────────────────────────────────────────────────────────────────
# FULL BOT
# ─────────────────────────────────────────────────────────────────────────────

def run_full_bot(node: str, mode: str):
    """
    Full bot — all modules from Sessions 1, 2, and 3.
    Paper mode by default. Flip to live after readiness gate passes.
    """
    logger.info(f"[Main] Starting FULL BOT — node={node} mode={mode}")

    # ── Session 1: Infrastructure ─────────────────────────────────────────
    from Sub_Projects.Trading.streak_state       import streak
    from Sub_Projects.Trading.position_tracker   import positions
    from Sub_Projects.Trading.database_manager   import db
    from Sub_Projects.Trading.state_sync         import sync

    # ── Session 2: Intelligence ───────────────────────────────────────────
    from Sub_Projects.Trading.node_orchestrator  import orchestrator
    from Sub_Projects.Trading.telegram_interface import tg
    from Sub_Projects.Trading.daily_bias_engine  import bias_engine
    from Sub_Projects.Trading.instrument_scanner import scanner

    # ── Session 3: Trading ────────────────────────────────────────────────
    from Sub_Projects.Trading.dynamic_tp_engine  import dynamic_tp
    from Sub_Projects.Trading.event_hedge_manager import event_hedge
    from Sub_Projects.Trading.trading_loop        import trading_loop

    # ── Start infrastructure ──────────────────────────────────────────────
    orchestrator.start()
    sync.start(is_active=orchestrator.is_active())
    tg.start()
    tg.start_schedulers()

    # ── Start trading engines ─────────────────────────────────────────────
    dynamic_tp.start()
    event_hedge.start()
    trading_loop.start()

    # ── Wire /tp_check command to DynamicTPEngine ─────────────────────────
    def _tp_check_handler(args: str):
        result = dynamic_tp.force_check()
        tg.send(f"🔍 <b>TP Check Results</b>\n{result}")

    tg._handlers["/tp_check"] = _tp_check_handler

    # ── Schedule daily pre-market at 06:30 UTC ────────────────────────────
    def daily_premarket():
        logger.info("[Main] Daily pre-market analysis starting...")
        bias_engine.run_daily_analysis()
        scanner.run_daily_scan()

        # Weekly DB maintenance (Sundays only)
        if datetime.now(timezone.utc).weekday() == 6:
            db.prune_old_ohlcv(keep_days=90)
            db.vacuum()
            logger.info("[Main] Weekly DB maintenance complete.")

    schedule.every().day.at("06:30").do(daily_premarket)

    # Run immediately on startup if already past 06:30
    if datetime.now(timezone.utc).hour >= 6:
        daily_premarket()

    # ── Startup notification ──────────────────────────────────────────────
    mode_str  = "📄 PAPER" if mode == "PAPER" else "💰 LIVE"
    open_pos  = positions.count()
    tg.send(
        f"🚀 <b>CRAVE v10.0 Online</b>\n"
        f"Node     : {node}\n"
        f"Mode     : {mode_str}\n"
        f"Open pos : {open_pos}\n"
        f"Can trade: {'✅' if streak.can_trade()[0] else '❌'}\n"
        f"Risk(A+) : {streak.get_current_risk_pct('A+'):.2f}%\n"
        f"DB size  : {db.get_db_size_mb()}MB"
    )

    logger.info(
        f"[Main] ✅ All modules running.\n"
        f"       Trading loop: scanning every 5 min\n"
        f"       Dynamic TP:   checking every 15 min\n"
        f"       Event hedge:  checking every 5 min\n"
        f"       Daily bias:   runs at 06:30 UTC\n"
        f"       Use Telegram commands to control the bot."
    )

    # ── Main loop ─────────────────────────────────────────────────────────
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)

    except KeyboardInterrupt:
        logger.info("[Main] Shutting down gracefully...")
        trading_loop.stop()
        dynamic_tp.stop()
        event_hedge.stop()
        sync.stop()
        tg.send("⏹️ CRAVE shutdown.")
        logger.info("[Main] Shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
# LITE BOT (phone / standby)
# ─────────────────────────────────────────────────────────────────────────────

def run_lite_bot(node: str, mode: str):
    """
    Lite bot for phone in standby.
    Monitors positions, syncs state, handles Telegram commands.
    Does NOT generate new signals (that's the active node's job).
    """
    logger.info(f"[Main] Starting LITE BOT on {node}")

    from Sub_Projects.Trading.streak_state       import streak
    from Sub_Projects.Trading.position_tracker   import positions
    from Sub_Projects.Trading.node_orchestrator  import orchestrator
    from Sub_Projects.Trading.telegram_interface import tg
    from Sub_Projects.Trading.thermal_monitor    import thermal
    from Sub_Projects.Trading.state_sync         import sync
    from Sub_Projects.Trading.dynamic_tp_engine  import dynamic_tp
    from Sub_Projects.Trading.event_hedge_manager import event_hedge

    orchestrator.start()
    sync.start(is_active=False)   # Pull only on phone
    tg.start()
    thermal.start()

    # Phone still monitors open positions and handles TP extension
    dynamic_tp.start()
    event_hedge.start()

    tg.send(
        f"📱 <b>CRAVE Phone Node Online</b>\n"
        f"Mode: monitoring + standby\n"
        f"Open positions: {positions.count()}"
    )

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        tg.send("⏹️ Phone node shutdown.")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CRAVE v10.0")
    parser.add_argument("--paper",    action="store_true")
    parser.add_argument("--live",     action="store_true")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--status",   action="store_true")
    parser.add_argument("--setup",    action="store_true")
    parser.add_argument("--node",     type=str)
    args = parser.parse_args()

    node             = args.node or detect_node()
    has_exchange_keys = check_env()
    mode = "LIVE" if (args.live and has_exchange_keys) else "PAPER"

    if args.live and not has_exchange_keys:
        logger.warning("Live requested but no API keys. Defaulting to paper.")

    print_banner(node, mode)

    if args.status:
        from Sub_Projects.Trading.streak_state   import streak
        from Sub_Projects.Trading.position_tracker import positions
        print(streak.get_status_message())
        print()
        print(positions.get_summary_message())
        return

    if args.setup:
        run_setup_wizard()
        return

    if args.backtest:
        run_backtest_mode()
        return

    from Config.config import NODES
    can_run = NODES.get(node, NODES["aws"]).get("can_run", [])

    if "full_bot" in can_run or "signal_detection" in can_run:
        run_full_bot(node, mode)
    else:
        run_lite_bot(node, mode)


def run_backtest_mode():
    print("\n📊 CRAVE v10.0 Backtest Mode")
    print("─────────────────────────────")
    symbol = input("Symbol (e.g. BTCUSD, XAUUSD): ").strip()
    days   = int(input("Days (min 60 for XAUUSD, 30 for BTC): ").strip() or "60")
    conf   = int(input("Min confidence % (recommended 55): ").strip() or "55")
    try:
        from Sub_Projects.Trading.backtest_agent import BacktestAgent
        bt     = BacktestAgent()
        report = bt.run_backtest(symbol, days=days, min_confidence=conf)
        print("\n" + bt.format_report(report))
    except Exception as e:
        print(f"Backtest error: {e}")


def run_setup_wizard():
    print("\n🔧 CRAVE v10.0 Setup Wizard")
    print("─────────────────────────────")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        print("Edit .env and add your full bot token.")
        return

    print("\n1. Getting your Telegram Chat ID:")
    print(f"   Open: https://api.telegram.org/bot{token}/getUpdates")
    print("   Send any message to your bot first, then open that URL.")
    print("   Copy the 'id' number from the 'chat' object.")
    print("   Set TELEGRAM_CHAT_ID=<that number> in .env\n")

    try:
        from Sub_Projects.Trading.database_manager import db
        print(f"2. Database: ✅ OK ({db.get_db_size_mb()}MB at {db.db_path})")
    except Exception as e:
        print(f"2. Database: ❌ {e}")

    try:
        from Sub_Projects.Trading.streak_state import streak
        status = streak.get_status()
        print(f"3. Streak state: ✅ OK — {status['streak_state']}")
    except Exception as e:
        print(f"3. Streak state: ❌ {e}")

    try:
        from Sub_Projects.Trading.position_tracker import positions
        print(f"4. Positions: ✅ OK — {positions.count()} open")
    except Exception as e:
        print(f"4. Positions: ❌ {e}")

    print("\n✅ Setup check complete.")
    print("Next: python run_bot.py  (starts in paper trading mode)")
    print("      python run_bot.py --status  (check state)")


if __name__ == "__main__":
    main()
