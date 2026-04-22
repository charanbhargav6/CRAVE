"""
CRAVE v10.1 — Main Entry Point (Session 4 Complete)
=====================================================
All modules wired. Bot is now fully operational in paper mode.
Session 4 fixes: paper equity compounding, ML outcome backfill,
regime filter, WebSocket fallback, lazy singletons.

Run:  python run_bot.py
      python run_bot.py --status
      python run_bot.py --backtest
      python run_bot.py --readiness
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



def _paper_status_msg() -> str:
    try:
        from Sub_Projects.Trading.paper_trading import get_paper_engine
        return get_paper_engine().get_status_message()
    except Exception as e:
        return f"📄 Paper engine not loaded: {e}"

def _regime_available() -> bool:
    try:
        from Sub_Projects.Trading.ml.regime_classifier import regime_model
        return regime_model._trained
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# FULL BOT
# ─────────────────────────────────────────────────────────────────────────────

def run_full_bot(node: str, mode: str):
    """
    Full bot — all modules from Sessions 1-4.
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

    # Dashboard pusher (Session 10)
    try:
        from Sub_Projects.Trading.dashboard.supabase_pusher import get_pusher
        get_pusher().start()
        logger.info("[Main] Dashboard pusher started.")
    except Exception as e:
        logger.warning(f"[Main] Dashboard pusher failed: {e}")

    # ── Session 6: Options Engine ─────────────────────────────────────────
    from Config.config import is_market_enabled
    if is_market_enabled("options"):
        try:
            from Sub_Projects.Trading.options.greeks_monitor import get_greeks_monitor
            get_greeks_monitor().start()
            logger.info("[Main] Greeks monitor started.")
        except Exception as e:
            logger.warning(f"[Main] Greeks monitor failed to start: {e}")

    # ── Session 7: Portfolio Risk Engine ──────────────────────────────────
    # Runs inline checks — no background thread needed.
    # Wired into trading_loop._run_cycle() via Gate 5.
    try:
        from Sub_Projects.Trading.risk.portfolio_risk_engine import get_portfolio_risk
        pr_status = get_portfolio_risk().get_summary()
        logger.info(
            f"[Main] Portfolio risk engine ready. "
            f"Current heat: {pr_status['total_heat']:.2f}%"
        )
    except Exception as e:
        logger.warning(f"[Main] Portfolio risk engine init failed: {e}")

    # ── New Telegram commands for S6+S7 ───────────────────────────────────
    tg.register_command("/portfolio", lambda args: tg.send(
        get_portfolio_risk().get_status_message()
    ))
    tg.register_command("/greeks", lambda args: tg.send(
        get_greeks_monitor().get_status_message()
    ))
    try:
        from Sub_Projects.Trading.options.options_engine import get_options_engine
        tg.register_command("/options", lambda args: tg.send(
            get_options_engine().get_status_message()
        ))
        
        from Sub_Projects.Trading.options.options_engine import iv_calculator
        def _handle_iv_cmd(args: str):
            symbol = (args.strip().upper() or "NIFTY")
            iv_data = iv_calculator.get_iv_rank(symbol)
            if not iv_data.get("available"):
                tg.send(f"📊 IV data unavailable for {symbol}. "
                        f"Builds after 20+ days of market data.")
                return
            tg.send(
                f"📊 <b>IV RANK: {symbol}</b>\n"
                f"IV Rank  : {iv_data['iv_rank']:.0f}%\n"
                f"Signal   : {iv_data['signal']}\n"
                f"Current IV: {iv_data['current_iv']:.1f}%\n"
                f"52W High  : {iv_data['high_52w']:.1f}%\n"
                f"52W Low   : {iv_data['low_52w']:.1f}%\n"
                f"Reason    : {iv_data['reason']}"
            )
        tg.register_command("/iv", _handle_iv_cmd)
    except Exception as e:
        logger.warning(f"[Main] Options Telegram commands skip: {e}")

    tg.register_command("/heat", lambda args: tg.send(
        get_portfolio_risk().get_status_message()
    ))

    # ── Session 4: Wire commands via register_command() ───────────────────
    # FIX M6: Use public API instead of tg._handlers[x] = y

    def _tp_check_handler(args: str):
        result = dynamic_tp.force_check()
        tg.send(f"🔍 <b>TP Check Results</b>\n{result}")

    tg.register_command("/tp_check", _tp_check_handler)

    # Paper trading status + readiness gate
    def _readiness_cmd(args):
        from Sub_Projects.Trading.paper_trading import get_paper_engine
        ready, report = get_paper_engine().check_readiness()
        for chunk in [report[i:i+3000] for i in range(0, len(report), 3000)]:
            tg.send(f"<pre>{chunk}</pre>")

    tg.register_command("/readiness", _readiness_cmd)
    tg.register_command("/paper", lambda args: (
        tg.send(_paper_status_msg())
    ))

    # ML regime status
    def _ml_cmd(args):
        try:
            from Sub_Projects.Trading.ml.regime_classifier import regime_model
            status = regime_model.get_status()
            lines = "\n".join(f"{k}: {v}" for k, v in status.items())
            tg.send(f"🤖 <b>ML STATUS</b>\n{lines}")
        except Exception as e:
            tg.send(f"🤖 ML not active: {e}")

    tg.register_command("/ml", _ml_cmd)

    # WebSocket status
    def _ws_cmd(args):
        try:
            from Sub_Projects.Trading.websocket_manager import get_ws
            tg.send(get_ws().get_status_message())
        except Exception as e:
            tg.send(f"📡 WS not active: {e}")

    tg.register_command("/ws", _ws_cmd)

    # AWS control
    def _aws_start_cmd(args):
        try:
            from Sub_Projects.Trading.aws_manager import get_aws
            get_aws().start_instance()
            tg.send("☁️ AWS instance starting...")
        except Exception as e:
            tg.send(f"☁️ AWS error: {e}")

    def _aws_stop_cmd(args):
        try:
            from Sub_Projects.Trading.aws_manager import get_aws
            get_aws().stop_instance()
            tg.send("☁️ AWS instance stopping...")
        except Exception as e:
            tg.send(f"☁️ AWS error: {e}")

    tg.register_command("/aws_start", _aws_start_cmd)
    tg.register_command("/aws_stop",  _aws_stop_cmd)

    # ── Schedule daily pre-market at 06:30 UTC ────────────────────────────
    def daily_premarket():
        logger.info("[Main] Daily pre-market analysis starting...")
        bias_engine.run_daily_analysis()
        scanner.run_daily_scan()

        # Session 8: Fetch India-specific data for bias engine
        from Config.config import is_market_enabled
        if is_market_enabled("india"):
            try:
                from Sub_Projects.Trading.data.nse_bhavcopy import get_bhavcopy
                bc = get_bhavcopy()

                # Max pain calculation
                for symbol in ("NIFTY", "BANKNIFTY"):
                    mp = bc.calculate_max_pain(symbol)
                    if mp:
                        logger.info(
                            f"[Main] {symbol} Max Pain: "
                            f"{mp['max_pain_strike']} | {mp['interpretation']}"
                        )
                        try:
                            from Sub_Projects.Trading.telegram_interface import tg
                            tg.send(
                                f"📊 <b>{symbol} MAX PAIN</b>\n"
                                f"Strike : {mp['max_pain_strike']}\n"
                                f"Spot   : {mp['current_spot']}\n"
                                f"{mp['interpretation']}"
                            )
                        except Exception:
                            pass

                # FII/DII
                fii_df = bc.get_fii_history(days=1)
                if not fii_df.empty:
                    latest = fii_df.iloc[-1]
                    logger.info(
                        f"[Main] FII: {latest['fii_net']:+,.0f} Cr | "
                        f"DII: {latest['dii_net']:+,.0f} Cr | "
                        f"Bias: {latest['bias']}"
                    )
            except Exception as e:
                logger.debug(f"[Main] India data fetch failed: {e}")

        # Record daily IV snapshot for IV rank history (Options S6)
        from Config.config import is_market_enabled
        if is_market_enabled("options"):
            try:
                from Sub_Projects.Trading.options.options_engine import iv_calculator
                for und in ("NIFTY", "BANKNIFTY"):
                    iv = iv_calculator._estimate_iv(und)
                    if iv:
                        iv_calculator.record_daily_iv(und, iv)
                        logger.info(f"[Main] Daily IV recorded: {und}={iv:.2f}")
            except Exception as e:
                logger.debug(f"[Main] IV snapshot failed: {e}")

        # PRIORITY 7: Sunday automated readiness report + weekly maintenance
        if datetime.now(timezone.utc).weekday() == 6:
            # DB maintenance
            db.prune_old_ohlcv(keep_days=90)
            db.vacuum()
            logger.info("[Main] Weekly DB maintenance done.")

            # Automated readiness gate report — sent every Sunday
            # You always know exactly where you stand without running --readiness
            try:
                from Sub_Projects.Trading.paper_trading import get_paper_engine
                pe           = get_paper_engine()
                ready, report = pe.check_readiness()
                stats        = pe.get_stats()
                total_trades = stats.get("total_trades", 0)
                min_trades   = pe._cfg.get("min_trades_for_live", 30)

                # Send compact weekly progress first
                tg.send(
                    f"📊 <b>WEEKLY READINESS UPDATE</b>\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"Paper Trades : {total_trades} / {min_trades} needed\n"
                    f"Win Rate     : {stats.get('win_rate', 'N/A')}\n"
                    f"Expectancy   : {stats.get('expectancy_r', 'N/A')}\n"
                    f"Sharpe       : {stats.get('sharpe_ratio', 'N/A')}\n"
                    f"Max DD       : {stats.get('max_drawdown', 'N/A')}\n"
                    f"Return       : {stats.get('total_return', 'N/A')}\n"
                    f"Gate Status  : {'✅ PASSED' if ready else '❌ NOT YET'}\n"
                    f"━━━━━━━━━━━━━━━\n"
                    + (
                        "🎉 Ready for live! Run /readiness for full report."
                        if ready else
                        f"⏳ {max(0, min_trades - total_trades)} more trades to minimum."
                    )
                )

                # If passed, send full detailed report
                if ready:
                    for chunk in [report[i:i+3000]
                                  for i in range(0, len(report), 3000)]:
                        tg.send(f"<pre>{chunk}</pre>")

                logger.info(
                    f"[Main] Weekly readiness report sent. "
                    f"Gate: {'PASSED' if ready else 'not yet'} | "
                    f"Trades: {total_trades}/{min_trades}"
                )
            except Exception as e:
                logger.warning(f"[Main] Weekly readiness report failed: {e}")

    schedule.every().day.at("06:30").do(daily_premarket)

    # Run immediately on startup if already past 06:30
    if datetime.now(timezone.utc).hour >= 6:
        daily_premarket()

    # ── Schedule Zerodha daily token refresh at 03:30 UTC ─────────────────
    # Zerodha tokens expire at midnight IST. Must refresh before 04:00 UTC
    # (NSE open). Bot sends login URL to Telegram and waits for /zerodha_token.
    def zerodha_daily_login():
        from Config.config import INDIA, is_market_enabled
        if not is_market_enabled("india"):
            return
        try:
            from Sub_Projects.Trading.brokers.zerodha_agent import get_zerodha
            get_zerodha().daily_login()
        except Exception as e:
            logger.warning(f"[Main] Zerodha daily login failed: {e}")

    schedule.every().day.at("03:30").do(zerodha_daily_login)

    # ── Schedule US stocks pre-close gap risk check at 19:45 UTC ──────────
    # 15 minutes before US market close: evaluate all open stock positions.
    # Close drawdown positions, tighten SL on profitable ones.
    def us_pre_close_check():
        from Config.config import is_market_enabled, get_symbols_for_market
        if not is_market_enabled("us_stocks"):
            return
        try:
            from Sub_Projects.Trading.position_tracker import positions
            from Sub_Projects.Trading.brokers.alpaca_stocks_agent import get_alpaca_stocks
            from Sub_Projects.Trading.data_agent import DataAgent
            da = DataAgent()
            for pos in positions.get_all():
                if pos.get("exchange") != "alpaca":
                    continue
                from Config.config import get_asset_class
                if get_asset_class(pos["symbol"]) not in ("stocks", "indices"):
                    continue
                # Get current price
                df = da.get_ohlcv(pos["symbol"], timeframe="1m", limit=2)
                if df is None or df.empty:
                    continue
                live_price = df["close"].iloc[-1]
                agent      = get_alpaca_stocks()
                should_close, reason = agent.should_close_before_overnight(
                    entry_price   = pos["entry_price"],
                    current_price = live_price,
                    stop_loss     = pos["current_sl"],
                    direction     = pos["direction"],
                )
                if should_close:
                    logger.warning(
                        f"[Main] Pre-close: closing {pos['symbol']}: {reason}"
                    )
                    agent.close_position(pos["symbol"])
                    tg.send(
                        f"⏰ <b>PRE-CLOSE</b>: {pos['symbol']}\n"
                        f"Reason: {reason}"
                    )
                else:
                    # Tighten SL to breakeven
                    logger.info(
                        f"[Main] Pre-close: tightening SL for "
                        f"{pos['symbol']}: {reason}"
                    )
                    positions.update_sl(
                        pos["trade_id"],
                        pos["entry_price"],
                        reason="pre-close gap protection"
                    )
        except Exception as e:
            logger.error(f"[Main] US pre-close check failed: {e}")

    schedule.every().day.at("19:45").do(us_pre_close_check)

    # ── Startup notification ──────────────────────────────────────────────
    mode_str  = "📄 PAPER" if mode == "PAPER" else "💰 LIVE"
    open_pos  = positions.count()

    # Paper equity info
    paper_eq = "$10,000"
    try:
        from Sub_Projects.Trading.paper_trading import get_paper_engine
        pe = get_paper_engine()
        paper_eq = f"${pe.get_equity():,.2f}"
    except Exception:
        pass

    tg.send(
        f"🚀 <b>CRAVE v10.1 Online</b>\n"
        f"Node     : {node}\n"
        f"Mode     : {mode_str}\n"
        f"Equity   : {paper_eq}\n"
        f"Open pos : {open_pos}\n"
        f"Can trade: {'✅' if streak.can_trade()[0] else '❌'}\n"
        f"Risk(A+) : {streak.get_current_risk_pct('A+'):.2f}%\n"
        f"DB size  : {db.get_db_size_mb()}MB"
    )

    logger.info(
        f"[Main] ✅ All modules running (v10.1).\n"
        f"       Trading loop: scanning every 5 min\n"
        f"       Dynamic TP:   checking every 15 min\n"
        f"       Event hedge:  checking every 5 min\n"
        f"       Daily bias:   runs at 06:30 UTC\n"
        f"       Regime filter: {'active (ML)' if _regime_available() else 'active (rules)'}\n"
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
    parser = argparse.ArgumentParser(description="CRAVE v10.1")
    parser.add_argument("--paper",      action="store_true")
    parser.add_argument("--live",       action="store_true")
    parser.add_argument("--backtest",   action="store_true")
    parser.add_argument("--status",     action="store_true")
    parser.add_argument("--setup",      action="store_true")
    parser.add_argument("--readiness",  action="store_true")
    parser.add_argument("--node",       type=str)
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

    if args.readiness:
        from Sub_Projects.Trading.paper_trading import get_paper_engine
        ready, report = get_paper_engine().check_readiness()
        print(report)
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
        from Sub_Projects.Trading.backtest_agent_v10 import BacktestAgentV10
        bt = BacktestAgentV10()

        print("\n1. Standard backtest with fees")
        report = bt.run_backtest(symbol, days=days, min_confidence=conf)
        print(bt.format_report(report))

        if input("\nRun walk-forward validation? (y/n): ").strip().lower() == "y":
            total = int(input("Total days (e.g. 365): ").strip() or "365")
            print(f"\nWalk-forward: {total}d total, 180d train, 30d test...")
            wf = bt.run_walk_forward(symbol, total_days=total,
                                      min_confidence=conf)
            print(bt.format_walk_forward(wf))

        if input("\nRun multi-market comparison? (y/n): ").strip().lower() == "y":
            print("\nRunning on all markets...")
            multi = bt.run_multi_market(days=days, min_confidence=conf)
            print(bt.format_multi_market(multi))

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
