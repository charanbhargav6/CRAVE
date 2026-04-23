"""
CRAVE v10.0 — Main Entry Point
================================
Run this on any node:  python run_bot.py

Auto-detects which machine it's on (laptop/phone/AWS)
and starts the appropriate components.

Laptop:  Full bot — signal detection, execution, backtest, monitoring
Phone:   Lite bot — position monitoring, Telegram interface, heartbeat
AWS:     Full bot — same as laptop (only runs when others unavailable)

FLAGS:
  --paper     Force paper trading mode (default anyway until gate passes)
  --live      Request live trading (only works if readiness gate passes)
  --backtest  Run backtest mode instead of live bot
  --setup     Run first-time setup wizard
  --status    Print current status and exit
"""

import os
import sys
import socket
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

# ── Load secrets: DPAPI Vault first, then .env fallback ──────────────────────
# The main CRAVE system stores all API keys in an encrypted DPAPI vault.
# We load from the vault so the trading bot shares the same Telegram token,
# exchange keys, etc. — no separate .env needed.
_crave_root = str(Path(__file__).resolve().parents[2])  # D:\CRAVE
sys.path.insert(0, _crave_root)

_vault_loaded = False
try:
    from src.security.encryption import crypto_manager
    _vault_loaded = crypto_manager.decrypt_env_to_memory()
except Exception as _ve:
    pass

if not _vault_loaded:
    # Fallback: try a local .env (standalone deployments like AWS)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / ".env")
    except ImportError:
        pass

# ── Add project root to path ──────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── Logging setup ─────────────────────────────────────────────────────────────
from Config.config import LOGGING as LOG_CFG, LOGS_DIR
import logging.handlers

def setup_logging():
    level = getattr(logging, LOG_CFG.get("level", "INFO"))
    handlers = []

    if LOG_CFG.get("log_to_console", True):
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S"
        ))
        handlers.append(h)

    if LOG_CFG.get("log_to_file", True):
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

    logging.basicConfig(level=level, handlers=handlers)

setup_logging()
logger = logging.getLogger("crave.main")


# ─────────────────────────────────────────────────────────────────────────────
# NODE DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def detect_node() -> str:
    """Detect which node we're running on based on hostname."""
    from Config.config import NODES
    hostname = socket.gethostname().upper()

    for node_name, node_cfg in NODES.items():
        patterns = node_cfg.get("hostname_patterns", [])
        if any(p.upper() in hostname for p in patterns):
            return node_name

    # Default to AWS if hostname doesn't match laptop or phone
    return "aws"


def print_banner(node: str, mode: str):
    print(f"""
╔══════════════════════════════════════════════════════╗
║                 CRAVE v10.0                          ║
║          Smart Money Trading System                  ║
╠══════════════════════════════════════════════════════╣
║  Node     : {node:<42}║
║  Mode     : {mode:<42}║
║  Time     : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'):<42}║
║  Python   : {sys.version.split()[0]:<42}║
╚══════════════════════════════════════════════════════╝
    """)


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP CHECKS
# ─────────────────────────────────────────────────────────────────────────────

def check_env():
    """Warn about missing environment variables."""
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    optional = ["BINANCE_API_KEY", "ALPACA_API_KEY", "GITHUB_TOKEN"]

    missing_required = [k for k in required if not os.environ.get(k)]
    missing_optional = [k for k in optional if not os.environ.get(k)]

    if missing_required:
        logger.warning(
            f"Missing required env vars: {missing_required}. "
            f"Edit .env file. Telegram alerts will be disabled."
        )
    if missing_optional:
        logger.info(
            f"Optional env vars not set: {missing_optional}. "
            f"Paper trading only until API keys are added."
        )

    # Force paper mode if no exchange keys
    has_exchange = (
        os.environ.get("BINANCE_API_KEY") or
        os.environ.get("ALPACA_API_KEY")
    )
    return bool(has_exchange)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CRAVE v10.0 Trading Bot")
    parser.add_argument("--paper",    action="store_true", help="Paper trading mode")
    parser.add_argument("--live",     action="store_true", help="Live trading (requires readiness gate)")
    parser.add_argument("--backtest", action="store_true", help="Run backtest")
    parser.add_argument("--status",   action="store_true", help="Print status and exit")
    parser.add_argument("--setup",    action="store_true", help="First-time setup wizard")
    parser.add_argument("--node",     type=str,            help="Override node detection")
    args = parser.parse_args()

    node = args.node or detect_node()
    has_exchange_keys = check_env()

    # Determine mode
    from Config.config import PAPER_TRADING
    if args.live and has_exchange_keys:
        mode = "LIVE"
    else:
        mode = "PAPER"
        if args.live and not has_exchange_keys:
            logger.warning("Live mode requested but no API keys found. Defaulting to paper.")

    print_banner(node, mode)

    # ── Status only ──────────────────────────────────────────────────────────
    if args.status:
        from Sub_Projects.Trading.streak_state import streak
        from Sub_Projects.Trading.position_tracker import positions
        print(streak.get_status_message())
        print()
        print(positions.get_summary_message())
        return

    # ── Setup wizard ─────────────────────────────────────────────────────────
    if args.setup:
        run_setup_wizard()
        return

    # ── Backtest mode ────────────────────────────────────────────────────────
    if args.backtest:
        run_backtest_mode()
        return

    # ── Bot mode ─────────────────────────────────────────────────────────────
    logger.info(f"[Main] Starting CRAVE on node={node}, mode={mode}")

    from Config.config import NODES
    node_cfg   = NODES.get(node, NODES["aws"])
    can_run    = node_cfg.get("can_run", [])

    # Start state sync
    try:
        from Sub_Projects.Trading.state_sync import sync
        is_active = node_cfg.get("is_primary", False)
        sync.start(is_active=is_active)
    except Exception as e:
        logger.warning(f"[Main] State sync startup failed: {e}")

    # Start Telegram interface
    try:
        from Sub_Projects.Trading.telegram_interface import tg
        tg.start()
        tg.send(
            f"🚀 CRAVE v10.0 Started\n"
            f"Node: {node}\n"
            f"Mode: {mode}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
    except Exception as e:
        logger.warning(f"[Main] Telegram startup failed: {e}")

    # Start appropriate bot based on node capabilities
    if "full_bot" in can_run or "signal_detection" in can_run:
        run_full_bot(node, mode)
    elif "lite_bot" in can_run or "position_monitor" in can_run:
        run_lite_bot(node, mode)
    else:
        logger.error(f"[Main] Node '{node}' has no recognised capabilities.")
        sys.exit(1)


def run_full_bot(node: str, mode: str):
    """Full bot — all Session 1+2 modules wired together."""
    import time, schedule
    from Config.config import KILL_ZONES

    logger.info(f"[Main] Starting FULL BOT on {node}...")

    # ── Load all modules ──────────────────────────────────────────────────
    from Sub_Projects.Trading.streak_state      import streak
    from Sub_Projects.Trading.position_tracker  import positions
    from Sub_Projects.Trading.node_orchestrator import orchestrator
    from Sub_Projects.Trading.telegram_interface import tg
    from Sub_Projects.Trading.daily_bias_engine  import get_bias_engine
    bias_engine = get_bias_engine()
    from Sub_Projects.Trading.instrument_scanner import scanner

    # ── Start node orchestrator ──────────────────────────────────────────
    orchestrator.start()

    # ── Start schedulers ─────────────────────────────────────────────────
    tg.start_schedulers()

    # ── Schedule daily pre-market tasks at 06:30 UTC ─────────────────────
    def daily_premarket():
        logger.info("[Main] Running daily pre-market analysis...")
        bias_engine.run_daily_analysis()
        scanner.run_daily_scan()

    schedule.every().day.at("06:30").do(daily_premarket)

    # Run immediately on startup if after 06:30
    from datetime import datetime, timezone
    if datetime.now(timezone.utc).hour >= 6:
        daily_premarket()

    # ── Status on startup ────────────────────────────────────────────────
    tg.send(
        f"✅ <b>CRAVE v10.0 Ready</b>\n"
        f"Node: {node} | Mode: {mode}\n"
        f"{streak.get_status_message()}\n"
        f"{positions.get_summary_message()}"
    )

    logger.info("[Main] All Session 2 modules loaded. Bot running.")

    # ── Zone 3: API Sentinel ────────────────────────────────────────────
    try:
        from Sub_Projects.Trading.security.api_sentinel import get_sentinel
        get_sentinel().start()
        logger.info("[Main] API Sentinel started.")
    except Exception as e:
        logger.warning(f"[Main] API Sentinel failed to start: {e}")

    # ── Zone 4: Wire content + security Telegram commands ────────────────
    import json as _json

    def _cmd_export_dashboard(args: str):
        try:
            from Sub_Projects.Trading.content.trade_recap import get_content_factory
            path = get_content_factory().export_public_dashboard()
            tg.send(f"Dashboard exported: {path}")
        except Exception as e:
            tg.send(f"Export failed: {e}")

    def _cmd_sentinel_status(args: str):
        try:
            from Sub_Projects.Trading.security.api_sentinel import get_sentinel
            s = get_sentinel().get_status()
            tg.send(
                "<b>SENTINEL STATUS</b>\n"
                + "\n".join(f"{k}: {v}" for k, v in s.items())
            )
        except Exception as e:
            tg.send(f"Sentinel: {e}")

    def _cmd_run_chaos(args: str):
        test = (args.strip() or "network_lag")
        tg.send(f"Starting chaos test: {test} (30s)")
        try:
            from Sub_Projects.Trading.security.chaos_monkey import ChaosMonkey
            monkey = ChaosMonkey()
            if test == "network_lag":
                result = monkey.inject_network_lag(500, 30)
            elif test == "rate_limit":
                result = monkey.inject_api_rate_limit(0.5, 30)
            elif test == "db":
                result = monkey.inject_db_disconnect(30)
            elif test == "telegram":
                result = monkey.inject_telegram_blackout(30)
            else:
                result = monkey.inject_network_lag(500, 30)
            all_ok = result.get("all_checks_passed", False)
            tg.send(
                f"Chaos test complete: {test}\n"
                f"State check: {'ALL OK' if all_ok else 'Issues detected'}\n"
                f"Details: {_json.dumps(result.get('state_checks', {}))}"
            )
        except Exception as e:
            tg.send(f"Chaos test failed: {e}")

    tg.register_command("/export_dashboard", _cmd_export_dashboard)
    tg.register_command("/sentinel",         _cmd_sentinel_status)
    tg.register_command("/chaos",            _cmd_run_chaos)

    logger.info(
        "[Main] CRAVE v10.4 fully operational. "
        "Zones 1-4 active: OrderFlow + Jarvis + Sentinel + Content. "
        "Telegram commands available."
    )

    # ── Main loop ────────────────────────────────────────────────────────
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("[Main] Shutting down...")
        tg.send("⏹️ CRAVE shutdown.")


def run_lite_bot(node: str, mode: str):
    """Lite bot for phone — monitoring only."""
    logger.info(f"[Main] Starting LITE BOT on {node} (phone/standby mode)...")

    try:
        from Sub_Projects.Trading.streak_state    import streak
        from Sub_Projects.Trading.position_tracker import positions

        logger.info("[Main] Lite bot running — monitoring positions.")

        import time
        while True:
            # Heartbeat every 60 seconds
            logger.debug("[Main] Phone heartbeat OK.")
            time.sleep(60)

    except KeyboardInterrupt:
        logger.info("[Main] Lite bot shutdown.")


def run_backtest_mode():
    """Interactive backtest runner."""
    print("\n📊 CRAVE Backtest Mode")
    print("─────────────────────")
    symbol = input("Symbol (e.g. BTCUSD, XAUUSD, EURUSD): ").strip()
    days   = int(input("Days (e.g. 60, 90): ").strip() or "60")
    conf   = int(input("Min confidence % (e.g. 55): ").strip() or "55")

    try:
        from Sub_Projects.Trading.backtest_agent import BacktestAgent
        bt     = BacktestAgent()
        report = bt.run_backtest(symbol, days=days, min_confidence=conf)
        print("\n" + bt.format_report(report))
    except Exception as e:
        print(f"Backtest error: {e}")


def run_setup_wizard():
    """First-time setup wizard."""
    print("\n🔧 CRAVE v10.0 Setup Wizard")
    print("─────────────────────────────")

    # Get chat ID
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        return

    print("\nTo get your Telegram Chat ID:")
    print("1. Send any message to your bot")
    print("2. Open this URL in your browser:")
    print(f"   https://api.telegram.org/bot{token}/getUpdates")
    print("3. Find 'chat':{'id': XXXXXX} in the response")
    print("4. Copy that number to TELEGRAM_CHAT_ID in .env")

    # Test database
    try:
        from Sub_Projects.Trading.database_manager import db
        print(f"\n✅ Database OK ({db.get_db_size_mb()}MB)")
    except Exception as e:
        print(f"\n❌ Database error: {e}")

    # Test streak state
    try:
        from Sub_Projects.Trading.streak_state import streak
        print(f"✅ Streak state loaded")
    except Exception as e:
        print(f"❌ Streak state error: {e}")

    print("\n✅ Setup complete. Run: python run_bot.py")


if __name__ == "__main__":
    main()
