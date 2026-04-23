"""
CRAVE v10.4 — Zone Wiring Guide
================================
Exact changes to plug all 4 zones into the existing bot.
All changes are ADDITIVE — nothing from Sessions 1-9 is removed.

ZONES DELIVERED:
  Zone 1: intelligence/order_flow.py     (delta confirmation + void scanner)
  Zone 2: intelligence/jarvis_llm.py     (sentiment filter + post-mortem)
  Zone 3: security/chaos_monkey.py       (failover stress tests)
  Zone 3: security/api_sentinel.py       (anomalous order detection)
  Zone 4: content/trade_recap.py         (video scripts + public dashboard)
"""

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 1 — trading_loop_v10_1.py
# Wire Zone 1 (delta confirmation) into _analyse_and_execute()
# ADD after the existing corr_ok check, BEFORE risk_agent.validate
# ─────────────────────────────────────────────────────────────────────────────

Z1_DELTA_FIND = """        corr_ok, corr_reason = self._correlation_check(symbol, direction)
        if not corr_ok:
            return None"""

Z1_DELTA_REPLACE = """        corr_ok, corr_reason = self._correlation_check(symbol, direction)
        if not corr_ok:
            return None

        # ── Zone 1: Order Flow Delta Confirmation ─────────────────────────
        # If price is at an OB, check delta confirms the direction.
        # Dead OBs have negative delta at the level — skip them.
        # This is the highest-impact single feature addition.
        try:
            from Sub_Projects.Trading.intelligence.order_flow import (
                check_delta_confirmation
            )
            obs = context.get("Order_Blocks", [])
            if obs:
                # Check the most recent / closest OB
                ob_zone = obs[0].get("zone", [0, 0])
                if ob_zone[0] > 0:
                    df_5m = _get_ohlcv_with_ws_fallback(symbol, "5m", 50)
                    if df_5m is not None and len(df_5m) >= 10:
                        delta_check = check_delta_confirmation(
                            df_5m, ob_zone, direction
                        )
                        if delta_check.get("signal") == "SKIP":
                            logger.info(
                                f"[TradingLoop] {symbol}: "
                                f"DEAD OB — {delta_check['reason']}"
                            )
                            self._log_signal(
                                symbol, "skip",
                                f"Dead OB: {delta_check['reason']}",
                                confidence, grade_str, context, df_1h=df_1h
                            )
                            return None
                        if delta_check.get("signal") == "WAIT":
                            logger.debug(
                                f"[TradingLoop] {symbol}: "
                                f"Delta WAIT — {delta_check['reason']}"
                            )
                            # Add to watchlist instead of executing now
                            self._add_to_watchlist(symbol, {"symbol": symbol, "score": 7})
                            return None
        except Exception as e:
            logger.debug(f"[TradingLoop] Delta check error (non-fatal): {e}")

        # ── Zone 2: Jarvis Sentiment Override ────────────────────────────
        # Check macro narrative before executing signal.
        # HAWKISH + BUY or BLACK_SWAN → HALF_SIZE or NO_TRADE override.
        try:
            from Sub_Projects.Trading.intelligence.jarvis_llm import get_jarvis
            jarvis = get_jarvis()
            if jarvis.is_ready():
                override = jarvis.get_sentiment_override(symbol, direction)
                action   = override.get("action", "PROCEED")
                if action == "NO_TRADE":
                    logger.info(
                        f"[TradingLoop] {symbol}: Jarvis veto — "
                        f"{override['reason']}"
                    )
                    self._log_signal(
                        symbol, "skip",
                        f"Jarvis: {override['reason']}",
                        confidence, grade_str, context, df_1h=df_1h
                    )
                    return None
                if action == "HALF_SIZE":
                    # Will be read by risk_pct calculation below
                    self._jarvis_half_size = True
                    logger.info(
                        f"[TradingLoop] {symbol}: Jarvis half-size — "
                        f"{override['reason']}"
                    )
                else:
                    self._jarvis_half_size = False
        except Exception as e:
            logger.debug(f"[TradingLoop] Jarvis check error (non-fatal): {e}")
            self._jarvis_half_size = False"""

# Also need to apply half-size in risk_pct calculation:
Z1_HALFSIZE_FIND = """        risk_pct = streak.get_current_risk_pct(grade)
        # If volatile regime → halve size
        if self._volatile_override:
            risk_pct = round(risk_pct * 0.5, 4)"""

Z1_HALFSIZE_REPLACE = """        risk_pct = streak.get_current_risk_pct(grade)
        # If volatile regime → halve size
        if self._volatile_override:
            risk_pct = round(risk_pct * 0.5, 4)
        # If Jarvis flagged half-size (sentiment conflict)
        if getattr(self, "_jarvis_half_size", False):
            risk_pct = round(risk_pct * 0.5, 4)
            logger.info(
                f"[TradingLoop] {symbol}: Jarvis half-size applied "
                f"→ {risk_pct:.2f}%"
            )"""


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 2 — position_tracker_v10_2.py
# Wire Zone 2 (post-mortem) and Zone 4 (content) into close()
# ADD after the existing Telegram alert in close()
# ─────────────────────────────────────────────────────────────────────────────

Z2_POSTMORTEM_FIND = """        logger.info(
            f"[Positions] Closed: {pos['symbol']} "
            f"| {outcome} | {r_multiple:+.2f}R "
            f"| held {hold_h:.1f}h"
        )
        return closed_trade"""

Z2_POSTMORTEM_REPLACE = """        logger.info(
            f"[Positions] Closed: {pos['symbol']} "
            f"| {outcome} | {r_multiple:+.2f}R "
            f"| held {hold_h:.1f}h"
        )

        # ── Zone 2: Jarvis post-mortem (async, non-blocking) ──────────────
        try:
            from Sub_Projects.Trading.intelligence.jarvis_llm import get_jarvis
            get_jarvis().write_trade_postmortem(closed_trade, run_async=True)
        except Exception:
            pass

        # ── Zone 4: Content factory (async, A+ trades only) ───────────────
        try:
            from Sub_Projects.Trading.content.trade_recap import get_content_factory
            get_content_factory().generate_trade_recap(
                pos["trade_id"], run_async=True
            )
        except Exception:
            pass

        return closed_trade"""


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 3 — daily_bias_engine.py
# Wire Zone 1 (liquidity void scanner) into analyse_instrument()
# ADD before the bias strength calculation
# ─────────────────────────────────────────────────────────────────────────────

Z1_VOID_FIND = """        # ── Combine weekly + daily → final bias ───────────────────────────
        bias     = self._combine_biases(weekly_bias, daily_bias)"""

Z1_VOID_REPLACE = """        # ── Zone 1: Liquidity Void Scanner ────────────────────────────────
        # Check for unfilled FVGs > 7 days old that act as price magnets.
        # If trade direction points toward a void → add strength bonus.
        void_bonus = 0
        try:
            from Sub_Projects.Trading.intelligence.order_flow import (
                scan_liquidity_voids, get_void_bias_bonus
            )
            voids = scan_liquidity_voids(df_daily, min_age_days=7)
            if voids:
                bias_direction = daily_bias.get("direction", "unknown")
                void_result = get_void_bias_bonus(
                    voids, bias_direction,
                    float(df_daily["close"].iloc[-1])
                )
                void_bonus = void_result.get("bonus", 0)
                if void_bonus > 0:
                    nearest = void_result.get("nearest_void", {})
                    logger.info(
                        f"[Bias] {symbol}: Liquidity void bonus +{void_bonus} — "
                        f"{void_result.get('reason','')}"
                    )
        except Exception as e:
            logger.debug(f"[Bias] Void scanner error (non-fatal): {e}")

        # ── Combine weekly + daily → final bias ───────────────────────────
        bias = self._combine_biases(weekly_bias, daily_bias)
        # Apply void bonus to strength
        if void_bonus > 0:
            bias["strength"] = min(3, bias.get("strength", 1) + void_bonus)
            bias["void_draw"] = True"""


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 4 — run_bot.py run_full_bot()
# Start Zone 3 (sentinel) and wire Zone 4 commands
# ADD after ws.start() and the trading_loop.start() calls
# ─────────────────────────────────────────────────────────────────────────────

Z3_Z4_RUNBOT_FIND = """    logger.info(
        "[Main] ✅ CRAVE v10.0 fully operational.\\n"
        "       All 4 sessions active. Paper trading running.\\n"
        "       Telegram commands available — send /help to your bot."
    )"""

Z3_Z4_RUNBOT_REPLACE = """    # ── Zone 3: API Sentinel ────────────────────────────────────────────
    try:
        from Sub_Projects.Trading.security.api_sentinel import get_sentinel
        get_sentinel().start()
        logger.info("[Main] API Sentinel started.")
    except Exception as e:
        logger.warning(f"[Main] API Sentinel failed to start: {e}")

    # ── Zone 4: Wire content commands ────────────────────────────────────
    def _cmd_export_dashboard(args: str):
        try:
            from Sub_Projects.Trading.content.trade_recap import get_content_factory
            path = get_content_factory().export_public_dashboard()
            tg.send(f"✅ Public dashboard exported: {path}")
        except Exception as e:
            tg.send(f"❌ Export failed: {e}")

    def _cmd_sentinel_status(args: str):
        try:
            from Sub_Projects.Trading.security.api_sentinel import get_sentinel
            s = get_sentinel().get_status()
            tg.send(
                f"🛡️ <b>SENTINEL STATUS</b>\\n"
                + "\\n".join(f"{k}: {v}" for k, v in s.items())
            )
        except Exception as e:
            tg.send(f"❌ Sentinel: {e}")

    def _cmd_run_chaos(args: str):
        test = (args.strip() or "network_lag")
        tg.send(f"🐒 Starting chaos test: {test} (30s)")
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
                f"🐒 Chaos test complete: {test}\\n"
                f"State check: {'✅ ALL OK' if all_ok else '⚠️ Issues detected'}\\n"
                f"Details: {json.dumps(result.get('state_checks', {}))}"
            )
        except Exception as e:
            tg.send(f"❌ Chaos test failed: {e}")

    tg.register_command("/export_dashboard", _cmd_export_dashboard)
    tg.register_command("/sentinel",         _cmd_sentinel_status)
    tg.register_command("/chaos",            _cmd_run_chaos)

    logger.info(
        "[Main] ✅ CRAVE v10.4 fully operational.\\n"
        "       Zones 1-4 active: OrderFlow + Jarvis + Sentinel + Content\\n"
        "       Telegram commands available — send /help to your bot."
    )"""


# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 5 — .env additions for Zone 2
# ─────────────────────────────────────────────────────────────────────────────

ENV_ADDITIONS = """
# ── Zone 2: Jarvis LLM (Gemini) ──
GEMINI_API_KEY=your_key_from_aistudio.google.com     # free tier: 15 RPM

# ── Zone 2: News APIs (optional — RSS fallback works without these) ──
NEWS_API_KEY=your_key_from_newsapi.org               # free: 100 req/day
GNEWS_API_KEY=your_key_from_gnews.io                 # free: 100 req/day

# ── Zone 3: Sentinel thresholds ──
SENTINEL_ALERT_THRESHOLD=3    # anomalies before pausing
SENTINEL_KILL_THRESHOLD=5     # anomalies before kill
"""

# ─────────────────────────────────────────────────────────────────────────────
# CHANGE 6 — telegram_interface.py TELEGRAM_COMMANDS additions
# ─────────────────────────────────────────────────────────────────────────────

NEW_TELEGRAM_COMMANDS = {
    "/chaos":           "Run chaos test: /chaos network_lag|rate_limit|db|telegram",
    "/sentinel":        "API Sentinel status — anomaly count and thresholds",
    "/export_dashboard":"Export public HTML verification dashboard",
    "/postmortems":     "List recent Jarvis trade post-mortems",
    "/recap":           "Generate trade recap: /recap TRADE_ID",
}


# ─────────────────────────────────────────────────────────────────────────────
# NEW DEPENDENCIES
# ─────────────────────────────────────────────────────────────────────────────

NEW_DEPS = """
pip install google-generativeai   # Zone 2 — Jarvis LLM
# All other Zone 1/3/4 features use existing packages
"""


# ─────────────────────────────────────────────────────────────────────────────
# FILE STRUCTURE ADDITIONS
# ─────────────────────────────────────────────────────────────────────────────

NEW_FILES = """
Sub_Projects/Trading/
├── intelligence/
│   ├── __init__.py
│   ├── order_flow.py        Zone 1: delta confirmation + void scanner
│   └── jarvis_llm.py        Zone 2: sentiment filter + post-mortem
├── security/
│   ├── __init__.py
│   ├── chaos_monkey.py      Zone 3: failover stress tests
│   └── api_sentinel.py      Zone 3: anomalous order detection
└── content/
    ├── __init__.py
    └── trade_recap.py       Zone 4: video scripts + public dashboard

State/
├── postmortems/            Zone 2: trade journal markdown files
├── recaps/                 Zone 4: video script markdown files
└── public_dashboard.html   Zone 4: public HTML page
"""


# ─────────────────────────────────────────────────────────────────────────────
# DEPLOY INSTRUCTIONS
# ─────────────────────────────────────────────────────────────────────────────

INSTRUCTIONS = """
═══════════════════════════════════════════════════════════════
CRAVE v10.4 — ZONES 1-4 DEPLOYMENT
═══════════════════════════════════════════════════════════════

1. Copy all new files (see NEW_FILES above)

2. Create __init__.py files:
   touch Sub_Projects/Trading/intelligence/__init__.py
   touch Sub_Projects/Trading/security/__init__.py
   touch Sub_Projects/Trading/content/__init__.py

3. Apply CHANGE 1 to trading_loop_v10_1.py (2 patches)
4. Apply CHANGE 2 to position_tracker_v10_2.py
5. Apply CHANGE 3 to daily_bias_engine.py
6. Apply CHANGE 4 to run_bot.py
7. Add ENV_ADDITIONS to .env
8. Install: pip install google-generativeai

9. Test each zone individually:
   # Zone 1: Check delta on a known dead OB
   python -c "from Sub_Projects.Trading.intelligence.order_flow import *; print('OK')"

   # Zone 2: Test Jarvis connection
   python -c "from Sub_Projects.Trading.intelligence.jarvis_llm import get_jarvis; j=get_jarvis(); print('Ready:', j.is_ready())"

   # Zone 3: Run chaos monkey (30s test)
   python -m Sub_Projects.Trading.security.chaos_monkey --test network_lag --duration 30

   # Zone 4: Generate public dashboard
   python -c "from Sub_Projects.Trading.content.trade_recap import get_content_factory; get_content_factory().export_public_dashboard()"

10. Start bot: python run_bot.py

NEW TELEGRAM COMMANDS:
  /chaos network_lag    → 30-second lag injection test
  /sentinel             → API anomaly detection status
  /export_dashboard     → generate public proof-of-work HTML
═══════════════════════════════════════════════════════════════
"""

if __name__ == "__main__":
    print(INSTRUCTIONS)
