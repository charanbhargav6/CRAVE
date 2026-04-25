"""
CRAVE v10.1 - Trading Loop
============================
FIXES vs v10.0 (audit-driven):

  🔧 FIX 3 - ML features now complete (26 fields not 10)
             _log_signal() now calls feature_engineering.extract_features()
             Old inline dict only had 10 fields; 16 were missing entirely,
             making regime classifier training data useless.

  🔧 FIX 4 - Paper equity now used for position sizing
             _get_current_equity() now calls paper_engine.get_equity()
             Was always returning $10,000 starting equity regardless of
             compounding, making position sizes wrong after early trades.
             (Depends on FIX 1 in position_tracker_v10_1.py)

  🔧 FIX 6 - Regime filter integrated directly (not monkey-patch)
             _regime_checked_analyse() is a first-class method called
             from _run_cycle(). The monkey-patch in run_bot_final.py
             was fragile - if method names changed it silently failed open.

  🔧 M2 - Session detection now covers Asian (22:00-02:00 UTC)
           Was: "london" if 7<=h<16 else "ny" - missed Asian entirely.

  🔧 M3 - WebSocket data tried first before REST API
           ws.get_live_ohlcv() → DataAgent().get_ohlcv() fallback.
           WebSocket cache is now actually used in the signal pipeline.

  🔧 M4 - Slippage owned by paper_engine.simulate_fill() only
           Deleted duplicate slippage logic from _paper_execute().
           paper_trading.simulate_fill() does asset-class-aware slippage.
           Old code used pip_size * 2 for everything (wrong for crypto/gold).

  🔧 Audit #9 (send_trade_open exists) - confirmed tg.send_trade_open()
             call is correct; method exists in telegram_interface_v10_1.py.

  🔧 signal_id now passed into positions.open() so ML backfill works.
"""

import logging
import time
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional, List

logger = logging.getLogger("crave.trading_loop")


# ── Kill Zone Helper ──────────────────────────────────────────────────────────

def is_in_kill_zone(symbol: str) -> tuple:
    try:
        from Config.config import KILL_ZONES
        now_utc  = datetime.now(timezone.utc)
        now_mins = now_utc.hour * 60 + now_utc.minute

        for zone_name, zone_cfg in KILL_ZONES.items():
            instruments = zone_cfg.get("instruments", "all")
            if instruments != "all" and symbol not in instruments:
                continue

            start_h, start_m = map(int, zone_cfg["start_utc"].split(":"))
            end_h,   end_m   = map(int, zone_cfg["end_utc"].split(":"))
            start_mins = start_h * 60 + start_m
            end_mins   = end_h   * 60 + end_m

            # Handle overnight zones (e.g., Asian 23:00–02:00)
            if start_mins > end_mins:
                in_zone = now_mins >= start_mins or now_mins <= end_mins
            else:
                in_zone = start_mins <= now_mins <= end_mins

            if in_zone:
                return True, zone_name

        return False, ""

    except Exception as e:
        logger.debug(f"[Loop] Kill zone check error: {e}")
        return True, "unknown"


def _get_session_name(hour_utc: int) -> str:
    """
    FIX M2: Now includes Asian session.
    Old: "london" if 7<=h<16 else "ny" - missed 22:00-02:00 UTC entirely.
    """
    if hour_utc >= 22 or hour_utc < 2:
        return "asian"
    if 6 <= hour_utc < 12:
        return "london"
    return "ny"


# ── MTF Confluence Gate ───────────────────────────────────────────────────────

def check_mtf_confluence(symbol: str, direction: str,
                           df_1h, df_4h) -> tuple:
    """
    Multi-timeframe gate using 4H market structure (BOS/CHoCH).

    Logic:
      1. Detect swing highs/lows on 4H chart.
      2. Check if the most recent confirmed close broke a swing level.
      3. Buy signals require 4H bullish structure (BOS/CHoCH bullish).
         Sell signals require 4H bearish structure.
      4. Ranging 4H = fallback to EMA21 trend filter.
    """
    try:
        import pandas as pd
        if df_4h is None or len(df_4h) < 20:
            return True, "4H data unavailable - passing by default"

        # ── Swing detection on 4H ──
        window = 3
        highs, lows = [], []
        for i in range(window, len(df_4h) - window):
            if df_4h['high'].iloc[i] == df_4h['high'].iloc[i - window: i + window + 1].max():
                highs.append((i, df_4h['high'].iloc[i]))
            if df_4h['low'].iloc[i] == df_4h['low'].iloc[i - window: i + window + 1].min():
                lows.append((i, df_4h['low'].iloc[i]))

        if len(highs) < 2 or len(lows) < 2:
            # Not enough structure — fallback to EMA21
            close_4h = df_4h['close'].iloc[-1]
            ema21_4h = df_4h['close'].ewm(span=21, adjust=False).mean().iloc[-1]
            above = close_4h > ema21_4h
            if direction in ("buy", "long"):
                return above, f"4H EMA21 fallback: {'above' if above else 'below'} ({ema21_4h:.5f})"
            else:
                return not above, f"4H EMA21 fallback: {'below' if not above else 'above'} ({ema21_4h:.5f})"

        last_high  = highs[-1][1]
        prev_high  = highs[-2][1]
        last_low   = lows[-1][1]
        prev_low   = lows[-2][1]
        confirmed  = df_4h['close'].iloc[-1]

        # ── Structure break detection ──
        bullish_bos  = confirmed > last_high        # BOS bullish
        bearish_bos  = confirmed < last_low          # BOS bearish
        choch_bull   = confirmed > last_high and prev_high > highs[-1][1]  # CHoCH reversal up
        choch_bear   = confirmed < last_low  and prev_low  < lows[-1][1]   # CHoCH reversal down

        # Higher highs / lower lows trend
        hh = last_high > prev_high  # higher high
        ll = last_low  < prev_low   # lower low
        hl = last_low  > prev_low   # higher low
        lh = last_high < prev_high  # lower high

        structure_bullish = bullish_bos or choch_bull or (hh and hl)
        structure_bearish = bearish_bos or choch_bear or (ll and lh)

        if direction in ("buy", "long"):
            if structure_bullish:
                reason = "4H BOS/CHoCH BULLISH"
                if hh and hl:
                    reason = "4H HH+HL structure BULLISH"
                return True, reason
            if structure_bearish:
                return False, "4H structure BEARISH — conflicts with buy"
            # Ranging — fallback to EMA21
            ema21_4h = df_4h['close'].ewm(span=21, adjust=False).mean().iloc[-1]
            above = confirmed > ema21_4h
            return above, f"4H ranging, EMA21 fallback: {'bullish' if above else 'bearish'}"
        else:
            if structure_bearish:
                reason = "4H BOS/CHoCH BEARISH"
                if ll and lh:
                    reason = "4H LL+LH structure BEARISH"
                return True, reason
            if structure_bullish:
                return False, "4H structure BULLISH — conflicts with sell"
            ema21_4h = df_4h['close'].ewm(span=21, adjust=False).mean().iloc[-1]
            below = confirmed < ema21_4h
            return below, f"4H ranging, EMA21 fallback: {'bearish' if below else 'bullish'}"

    except Exception as e:
        logger.debug(f"[Loop] MTF gate error: {e}")
        return True, "MTF error - passing by default"


def _get_ohlcv_with_ws_fallback(symbol: str,
                                  timeframe: str,
                                  limit: int):
    """FIX S8: Use market_data_router as primary - it handles all sources."""
    try:
        from Sub_Projects.Trading.data.market_data_router import get_data_router
        df = get_data_router().get_ohlcv(symbol, timeframe, limit=limit)
        if df is not None and len(df) >= 20:
            return df
    except Exception as e:
        import logging
        logging.getLogger("crave").debug(f"DataRouter failed {symbol}: {e}")
    # Original fallback chain below remains as safety net

    # Try WebSocket cache first
    try:
        from Sub_Projects.Trading.websocket_manager import get_ws
        ws_df = get_ws().get_live_ohlcv(symbol, timeframe, limit=limit)
        if ws_df is not None and len(ws_df) >= 20:
            return ws_df
    except Exception:
        pass

    # Fall back to database cache
    try:
        from Sub_Projects.Trading.database_manager import db
        cached = db.get_cached_ohlcv(symbol, timeframe, limit=limit)
        if cached is not None and len(cached) >= 20:
            return cached
    except Exception:
        pass

    # Last resort: REST API
    try:
        from Sub_Projects.Trading.data_agent import DataAgent
        return DataAgent().get_ohlcv(symbol, timeframe=timeframe, limit=limit)
    except Exception as e:
        logger.debug(f"[Loop] OHLCV fallback failed {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────

class TradingLoop:

    SCAN_INTERVAL_SECS      = 300
    MAX_INSTRUMENTS_PER_DAY = 2

    def __init__(self):
        self._running         = False
        self._thread: Optional[threading.Thread] = None
        self._watchlist:      List[dict] = []
        self._trades_today    = 0
        self._last_trade_date = ""
        self._volatile_override = False
        self._is_paper          = True

        try:
            from Config.config import PAPER_TRADING
            self._is_paper = PAPER_TRADING.get("enabled", True)
        except Exception:
            self._is_paper = True

        logger.info(
            f"[TradingLoop] Initialised. Mode: "
            f"{'📄 PAPER' if self._is_paper else '💰 LIVE'}"
        )

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True, name="CRAVETradingLoop"
        )
        self._thread.start()
        logger.info(f"[TradingLoop] Started. Scanning every {self.SCAN_INTERVAL_SECS}s.")

    def stop(self):
        self._running = False
        logger.info("[TradingLoop] Stopped.")

    def _loop(self):
        while self._running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"[TradingLoop] Cycle error: {e}")
            time.sleep(self.SCAN_INTERVAL_SECS)

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN CYCLE
    # ─────────────────────────────────────────────────────────────────────────

    def _run_cycle(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_trade_date:
            self._trades_today    = 0
            self._last_trade_date = today

        from Sub_Projects.Trading.streak_state import streak
        can_trade, reason = streak.can_trade()
        if not can_trade:
            logger.debug(f"[TradingLoop] Gate blocked: {reason}")
            return

        try:
            from Sub_Projects.Trading.node_orchestrator import orchestrator
            if not orchestrator.is_active():
                return
        except Exception:
            pass

        from Sub_Projects.Trading.position_tracker import positions
        current_open = positions.count()
        if current_open >= self.MAX_INSTRUMENTS_PER_DAY:
            return

        # ── Gate 5: Portfolio risk engine ─────────────────────────────────
        # Checks total heat, per-market heat, currency exposure.
        # Blocks entry if any limit would be breached.
        # Also triggers emergency SL tightening if heat is elevated.
        try:
            from Sub_Projects.Trading.risk.portfolio_risk_engine import get_portfolio_risk
            pr = get_portfolio_risk()

            # Emergency SL tighten (5-6.5% range)
            pr.tighten_stops_if_overheated()

            # Emergency close (> 6.5%)
            if pr.check_emergency_close():
                logger.warning("[TradingLoop] Emergency close triggered. Skipping new entries.")
                return

        except Exception as e:
            logger.debug(f"[TradingLoop] Portfolio risk check error (non-fatal): {e}")

        self._process_watchlist()

        # ── Gate 4: Filter instruments to enabled markets only ────────────
        # Instruments whose market is disabled in MARKETS config are excluded.
        # This is how you turn US stocks or India on/off without touching
        # individual instrument configs.
        # (Already handled by get_tradeable_symbols() in config.py -
        #  no code change needed here, just documentation.)

        from Sub_Projects.Trading.instrument_scanner import scanner
        tradeable = scanner.get_tradeable_today()
        if not tradeable:
            return

        slots_available = self.MAX_INSTRUMENTS_PER_DAY - current_open
        for inst_data in tradeable[:slots_available * 2]:
            symbol = inst_data["symbol"]
            if positions.has_open_position(symbol):
                continue

            in_kz, kz_name = is_in_kill_zone(symbol)
            if not in_kz:
                self._add_to_watchlist(symbol, inst_data)
                continue

            # FIX 6: Regime check is now a first-class method call,
            # not a monkey-patch in run_bot_final.py.
            result = self._regime_checked_analyse(symbol, kz_name)
            if result and result.get("executed"):
                slots_available -= 1
                if slots_available <= 0:
                    break

        self._run_options_cycle()

    def _run_options_cycle(self):
        """
        Options signal check. Runs after regular SMC signal check.
        Only active when MARKETS["options"]["enabled"] = True.
        """
        from Config.config import is_market_enabled
        if not is_market_enabled("options"):
            return

        from Config.config import get_symbols_for_market
        option_symbols = get_symbols_for_market("options")
        if not option_symbols:
            return

        try:
            from Sub_Projects.Trading.options.options_engine import get_options_engine

            # Use NIFTY and BANKNIFTY as primary options candidates
            for symbol in ["NIFTY_FUT", "BANKNIFTY_FUT"]:
                from Sub_Projects.Trading.data_agent import DataAgent
                df = DataAgent().get_ohlcv(symbol, timeframe="1h", limit=100)
                if df is None or len(df) < 20:
                    continue

                # Get SMC direction if any signal exists
                smc_direction = None
                try:
                    from Sub_Projects.Trading.daily_bias_engine import bias_engine
                    bias = bias_engine.get_bias(symbol)
                    if bias and bias.get("bias") != "NO_TRADE":
                        smc_direction = ("buy"
                                         if bias.get("bias") == "BUY"
                                         else "sell")
                except Exception:
                    pass

                strategy = get_options_engine().select_strategy(
                    symbol, df, smc_direction
                )
                if strategy:
                    logger.info(
                        f"[TradingLoop] Options signal: "
                        f"{strategy['name']} on {strategy['symbol']}"
                    )
                    # Send to Telegram for manual review (options require
                    # human confirmation until auto-execution is validated)
                    self._notify_options_signal(strategy)

        except Exception as e:
            logger.error(f"[TradingLoop] Options cycle error: {e}")

    def _notify_options_signal(self, strategy: dict):
        """Send options signal to Telegram for review."""
        try:
            from Sub_Projects.Trading.telegram_interface import tg
            strikes = strategy.get("strikes", {})
            strike_str = " | ".join(f"{k}={v}" for k, v in strikes.items()
                                     if isinstance(v, (int, float)))
            tg.send(
                f"⚙️ <b>OPTIONS SIGNAL</b>\n"
                f"Strategy : {strategy['name'].upper()}\n"
                f"Symbol   : {strategy['symbol']}\n"
                f"Spot     : {strategy.get('spot', '?')}\n"
                f"Strikes  : {strike_str}\n"
                f"DTE      : {strategy.get('dte', '?')}\n"
                f"IV Rank  : {strategy.get('iv_rank', '?')}\n"
                f"Regime   : {strategy.get('regime', '?')}\n"
                f"Reason   : {strategy.get('reason', '?')}\n\n"
                f"⚠️ Manual confirmation required.\n"
                f"Reply /options_confirm to execute."
            )
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # FIX 6 - Regime check integrated directly
    # ─────────────────────────────────────────────────────────────────────────

    def _regime_checked_analyse(self, symbol: str,
                                  kz_name: str = "") -> Optional[dict]:
        """
        FIX 6: Regime filter is now inside the trading loop, not a monkey-patch.

        Runs regime detection first. If market is RANGING, SMC signals have
        ~40% win rate (below breakeven) - skip entirely.
        If VOLATILE, allow but halve position size.
        If TRENDING_UP or TRENDING_DOWN - full analysis proceeds.
        """
        try:
            from Sub_Projects.Trading.ml.regime_classifier import regime_model
            df = _get_ohlcv_with_ws_fallback(symbol, "1h", 100)
            if df is not None:
                regime = regime_model.predict(symbol, df)
                if not regime_model.is_favourable(regime):
                    logger.info(
                        f"[TradingLoop] {symbol}: Regime={regime} - "
                        f"unfavourable. Skipping."
                    )
                    return None
                self._volatile_override = regime_model.should_reduce_size(regime)
            else:
                self._volatile_override = False
        except Exception as e:
            logger.debug(f"[TradingLoop] Regime check error (non-fatal): {e}")
            self._volatile_override = False

        return self._analyse_and_execute(symbol, kz_name)

    # ─────────────────────────────────────────────────────────────────────────
    # SIGNAL ANALYSIS + EXECUTION
    # ─────────────────────────────────────────────────────────────────────────

    def _analyse_and_execute(self, symbol: str,
                              kz_name: str = "") -> Optional[dict]:
        logger.info(f"[TradingLoop] Analysing {symbol} ({kz_name})...")

        df_15m = _get_ohlcv_with_ws_fallback(symbol, "15m", 250)
        df_1h = _get_ohlcv_with_ws_fallback(symbol, "1h", 250)
        df_4h = _get_ohlcv_with_ws_fallback(symbol, "4h", 60)

        if df_15m is None or len(df_15m) < 60 or df_1h is None or len(df_1h) < 60:
            logger.warning(f"[TradingLoop] Insufficient data for {symbol}")
            return None

        from Sub_Projects.Trading.strategy_agent import StrategyAgent
        strategy = StrategyAgent()
        # Execute SMC analysis on the 15m TF for tighter entries
        context  = strategy.analyze_market_context(symbol, df_15m)

        if "error" in context:
            return None

        confidence   = context.get("Confidence_Pct", 0)
        grade_str    = context.get("Structure_Score", "C")
        macro_trend  = context.get("Macro_Trend", "Unknown")
        current_price = context.get("Current_Price", df_15m['close'].iloc[-1])

        if macro_trend == "Unknown":
            self._log_signal(symbol, "skip", "Unknown macro trend",
                             confidence, grade_str, context, df_1h=df_15m)
            return None

        direction = "buy" if macro_trend == "Bullish" else "sell"

        from Sub_Projects.Trading.daily_bias_engine import bias_engine
        if not bias_engine.is_tradeable_today(symbol, direction):
            bias = bias_engine.get_bias(symbol)
            b    = bias.get("bias", "NO_TRADE") if bias else "NO_BIAS"
            self._log_signal(symbol, "skip",
                             f"Bias conflict: bias={b} signal={direction}",
                             confidence, grade_str, context, df_1h=df_15m)
            return None

        grade = None
        for g in ("A+", "A", "B+", "B"):
            if g in grade_str:
                grade = g
                break
        if grade is None:
            return None

        min_conf = {"A+": 55, "A": 50, "B+": 45, "B": 40}.get(grade, 40)
        if confidence < min_conf:
            return None

        mtf_ok, mtf_reason = check_mtf_confluence(symbol, direction, df_1h, df_4h)
        if not mtf_ok:
            self._log_signal(symbol, "skip", f"MTF conflict: {mtf_reason}",
                             confidence, grade_str, context, df_1h=df_15m)
            return None

        # ── Economic Calendar No-Trade Window ─────────────────────────────
        # Hard-block new entries within 30min of a high-impact event.
        # The EventHedgeManager handles EXISTING positions; this blocks NEW ones.
        try:
            from Sub_Projects.Trading.data_agent import DataAgent
            from Config.config import get_instrument
            da   = DataAgent()
            inst = get_instrument(symbol)
            ccys = inst.get("currencies", ["USD"])

            for ccy in ccys:
                result = da.check_red_folder(
                    currencies=(ccy,), window_mins=30
                )
                if result.get("is_danger"):
                    event_name = result.get("event_name", "Unknown")
                    mins_away  = result.get("time_to_event_mins", 0)
                    logger.info(
                        f"[TradingLoop] {symbol}: NO-TRADE WINDOW — "
                        f"{event_name} ({ccy}) in {mins_away}min"
                    )
                    self._log_signal(
                        symbol, "skip",
                        f"Econ calendar: {event_name} in {mins_away}min",
                        confidence, grade_str, context, df_1h=df_15m
                    )
                    return None
        except Exception as e:
            logger.debug(f"[TradingLoop] Econ calendar check error (non-fatal): {e}")

        corr_ok, corr_reason = self._correlation_check(symbol, direction)
        if not corr_ok:
            return None

        # ── Zone 1: Order Flow Delta Confirmation ─────────────────────────
        # If price is at an OB, check delta confirms the direction.
        # Dead OBs have negative delta at the level — skip them.
        try:
            from Sub_Projects.Trading.intelligence.order_flow import (
                check_delta_confirmation
            )
            obs = context.get("Order_Blocks", [])
            if obs:
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
                                confidence, grade_str, context, df_1h=df_15m
                            )
                            return None
                        if delta_check.get("signal") == "WAIT":
                            logger.debug(
                                f"[TradingLoop] {symbol}: "
                                f"Delta WAIT — {delta_check['reason']}"
                            )
                            self._add_to_watchlist(symbol, {"symbol": symbol, "score": 7})
                            return None
        except Exception as e:
            logger.debug(f"[TradingLoop] Delta check error (non-fatal): {e}")

        # ── Zone 2: Jarvis Sentiment Override ────────────────────────────
        # Check macro narrative before executing signal.
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
                        confidence, grade_str, context, df_1h=df_15m
                    )
                    return None
                if action == "HALF_SIZE":
                    self._jarvis_half_size = True
                    logger.info(
                        f"[TradingLoop] {symbol}: Jarvis half-size — "
                        f"{override['reason']}"
                    )
                else:
                    self._jarvis_half_size = False
        except Exception as e:
            logger.debug(f"[TradingLoop] Jarvis check error (non-fatal): {e}")
            self._jarvis_half_size = False

        # ── Pre-calculate Risk Pct BEFORE the portfolio gate ──────────────
        from Sub_Projects.Trading.risk_agent import RiskAgent
        from Sub_Projects.Trading.streak_state import streak

        risk_pct = streak.get_current_risk_pct(grade)
        
        # If volatile regime → halve size
        if getattr(self, "_volatile_override", False):
            risk_pct = round(risk_pct * 0.5, 4)
            logger.info(
                f"[TradingLoop] {symbol}: Volatile regime - "
                f"size halved to {risk_pct:.2f}%"
            )
        
        # If Jarvis flagged half-size (sentiment conflict)
        if getattr(self, "_jarvis_half_size", False):
            risk_pct = round(risk_pct * 0.5, 4)
            logger.info(
                f"[TradingLoop] {symbol}: Jarvis half-size applied "
                f"-> {risk_pct:.2f}%"
            )

        # ── Portfolio-level risk gate ─────────────────────────────────────
        try:
            from Sub_Projects.Trading.risk.portfolio_risk_engine import get_portfolio_risk
            pr_ok, pr_reason = get_portfolio_risk().can_add_position(
                symbol, risk_pct, direction
            )
            if not pr_ok:
                logger.info(f"[TradingLoop] {symbol}: Portfolio gate - {pr_reason}")
                self._log_signal(symbol, "skip", f"Portfolio: {pr_reason}",
                                 confidence, grade_str, context, df_1h=df_15m)
                return None
        except Exception as e:
            logger.debug(f"[TradingLoop] Portfolio gate error (non-fatal): {e}")

        risk_agent = RiskAgent()
        risk_agent.max_risk_per_trade = risk_pct / 100

        equity = self._get_current_equity()

        signal_dict = {
            "action":          direction,
            "price":           current_price,
            "symbol":          symbol,
            "is_swing_trade":  context.get("Is_Swing_Trade", False),
        }

        validated = risk_agent.validate_trade_signal(
            current_equity = equity,
            signal         = signal_dict,
            df             = df_15m,
            confidence_pct = confidence,
        )

        if not validated.get("approved"):
            return None

        validated["grade"]     = grade
        validated["risk_pct"]  = risk_pct
        validated["is_paper"]  = self._is_paper
        validated["exchange"]  = self._get_exchange_for(symbol)
        validated["node"]      = self._get_node_name()

        # ── Hybrid Execution: OB Limit Order Logic ────────────────────────
        # Detect the nearest Order Block boundary for precise limit entry.
        # Node-aware: AWS uses strict postOnly, local uses standard limits.
        obs = context.get("Order_Blocks", [])
        ob_limit_price = None
        if obs:
            nearest_ob = obs[0]
            ob_zone = nearest_ob.get("zone", [0, 0])
            if ob_zone[0] > 0:
                # BUY: enter at top of OB (demand), SELL: enter at bottom (supply)
                if direction in ("buy", "long"):
                    ob_limit_price = float(ob_zone[1])  # top of demand OB
                else:
                    ob_limit_price = float(ob_zone[0])  # bottom of supply OB

        node_name = self._get_node_name()
        is_cloud = node_name in ("aws", "gcp", "oracle")

        if ob_limit_price and ob_limit_price > 0:
            validated["order_type"]       = "limit"
            validated["limit_price"]      = round(ob_limit_price, 5)
            validated["strict_post_only"] = is_cloud  # True on AWS, False on laptop/phone
            logger.info(
                f"[TradingLoop] {symbol}: Limit @ {ob_limit_price:.5f} "
                f"({'postOnly' if is_cloud else 'standard'})"
            )
        else:
            validated["order_type"]       = "market"
            validated["strict_post_only"] = False

        logger.info(
            f"[TradingLoop] SIGNAL: {symbol} {direction.upper()} "
            f"grade={grade} conf={confidence}% risk={risk_pct:.2f}% "
            f"{'[PAPER]' if self._is_paper else '[LIVE]'}"
        )

        # Generate signal_id BEFORE execution so it can be stored in position
        signal_id = str(uuid.uuid4())[:8].upper()
        validated["signal_id"] = signal_id

        result = self._execute(validated, current_price)

        if result and result.get("status") in ("filled", "paper_filled"):
            self._trades_today += 1
            self._log_signal(symbol, "traded", "Executed",
                             confidence, grade_str, context,
                             validated=validated, df_1h=df_1h,
                             signal_id=signal_id)
            return {"executed": True, "trade_id": result.get("trade_id")}

        self._log_signal(symbol, "failed",
                         result.get("reason", "execution failed") if result else "no result",
                         confidence, grade_str, context, df_1h=df_1h)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # EXECUTION
    # ─────────────────────────────────────────────────────────────────────────

    def _execute(self, validated: dict, current_price: float) -> dict:
        """
        Route to broker_router which handles:
          - Paper mode simulation (all instruments)
          - Exchange routing (Binance / Alpaca / Zerodha)
          - Market-specific pre-checks (earnings, circuit breakers, PDT)
          - Share vs unit sizing (stocks need shares, not lot_size)
        """
        try:
            from Sub_Projects.Trading.brokers.broker_router import get_router
            return get_router().execute(validated, current_price,
                                        is_paper=self._is_paper)
        except Exception as e:
            logger.error(f"[TradingLoop] Router error: {e}")
            # Fallback to original paths
            if self._is_paper:
                return self._paper_execute(validated, current_price)
            return self._live_execute(validated, current_price)

    def _paper_execute(self, validated: dict, current_price: float) -> dict:
        """
        FIX M4: Slippage now owned exclusively by paper_engine.simulate_fill().
        Old code duplicated slippage with a flat pip_size*2 formula for all
        assets. paper_engine uses asset-class-aware slippage (crypto != forex).
        """
        symbol    = validated["symbol"]
        direction = validated["direction"]
        trade_id  = validated.get("trade_id") or str(uuid.uuid4())[:8].upper()
        signal_id = validated.get("signal_id")

        # FIX M4: delegate all slippage logic to paper_engine
        try:
            from Sub_Projects.Trading.paper_trading import get_paper_engine
            fill_data  = get_paper_engine().simulate_fill(validated, current_price)
            fill_price = fill_data["fill_price"]
        except Exception:
            fill_price = current_price   # fallback

        from Sub_Projects.Trading.position_tracker import positions
        positions.open({
            **validated,
            "trade_id":    trade_id,
            "entry":       fill_price,
            "entry_price": fill_price,
            "is_paper":    True,
            "exchange":    "paper",
            "signal_id":   signal_id,   # FIX: enables ML backfill
        })

        try:
            from Sub_Projects.Trading.telegram_interface import tg
            tg.send_trade_open({
                **validated,
                "trade_id":    trade_id,
                "entry_price": fill_price,
                "current_sl":  validated["stop_loss"],
                "tp1_price":   validated.get("take_profit_1"),
                "current_tp":  validated.get("take_profit_2"),
                "is_paper":    True,
            })
        except Exception:
            pass

        logger.info(
            f"[TradingLoop] 📄 PAPER FILLED: {symbol} {direction.upper()} "
            f"@ {fill_price} | ID={trade_id}"
        )
        return {"status": "paper_filled", "trade_id": trade_id,
                "fill_price": fill_price}

    def _live_execute(self, validated: dict, current_price: float) -> dict:
        try:
            from Sub_Projects.Trading.execution_agent import ExecutionAgent
            from Sub_Projects.Trading.data_agent import DataAgent
            exchange = validated.get("exchange", "alpaca")
            ea = ExecutionAgent(data_agent=DataAgent())
            return ea.execute_trade(validated, current_price, exchange=exchange)
        except Exception as e:
            logger.error(f"[TradingLoop] Live execution error: {e}")
            return {"status": "failed", "reason": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # FIX 4 - Paper equity used for sizing
    # ─────────────────────────────────────────────────────────────────────────

    def _get_current_equity(self) -> float:
        """
        FIX 4: Now reads compounded paper equity, not fixed starting equity.
        Without this, position sizes were identical on trade #1 and trade #100
        even if paper equity had grown 20% - no compounding benefit.
        """
        if self._is_paper:
            try:
                from Sub_Projects.Trading.paper_trading import get_paper_engine
                return get_paper_engine().get_equity()
            except Exception:
                from Config.config import PAPER_TRADING
                return float(PAPER_TRADING.get("starting_equity", 10000))

        # Live mode: read from broker
        try:
            from Sub_Projects.Trading.data_agent import DataAgent
            da      = DataAgent()
            account = da.alpaca.get_account() if da.alpaca else None
            if account:
                return float(account.equity)
        except Exception:
            pass

        return 10000.0

    # ─────────────────────────────────────────────────────────────────────────
    # FIX 3 - ML features complete (26 fields)
    # ─────────────────────────────────────────────────────────────────────────

    def _log_signal(self, symbol: str, status: str, reason: str,
                     confidence: int, grade: str, context: dict,
                     validated: dict = None,
                     df_1h=None,
                     signal_id: str = None):
        """
        FIX 3: Now calls feature_engineering.extract_features() for full
        26-field feature set. Old inline dict only had 10 fields.

        Missing fields were: atr_pct, atr_expansion, above_ema21/50/200,
        ema21_above_ema50, dist_to_swing_high/low_atr, pd_position,
        rsi_divergence_type, volume_signal, volume_expanding,
        structure_event, asset_class, funding_rate, day_of_week.

        All 16 missing fields are now captured automatically.
        """
        try:
            from Sub_Projects.Trading.database_manager import db

            # Generate signal_id if not provided
            sid = signal_id or str(uuid.uuid4())[:8].upper()

            # FIX M2: Correct session detection
            h            = datetime.now(timezone.utc).hour
            session_name = _get_session_name(h)

            db.save_signal({
                "signal_id":       sid,
                "symbol":          symbol,
                "direction":       "buy" if context.get("Macro_Trend") == "Bullish" else "sell",
                "confidence":      confidence,
                "grade":           grade,
                "was_traded":      status == "traded",
                "skip_reason":     reason if status != "traded" else None,
                "entry_price":     context.get("Current_Price"),
                "atr":             validated.get("atr") if validated else None,
                "session":         session_name,
                "macro_trend":     context.get("Macro_Trend"),
                "fvg_hit":         any(
                    f.get("price_inside")
                    for f in context.get("Recent_FVGs", [])
                ),
                "ob_hit":          any(
                    ob.get("zone", [0,0])[0] <=
                    context.get("Current_Price", 0) <=
                    ob.get("zone", [0,1])[1]
                    for ob in context.get("Order_Blocks", [])
                ),
                "sweep_detected":  context.get(
                    "Liquidity_Sweep", {}
                ).get("sweep_detected", False),
                "rsi_divergence":  context.get(
                    "RSI_Divergence", {}
                ).get("divergence", "none"),
                "volume_signal":   context.get("Volume_Delta", {}).get("signal", ""),
                "structure_event": context.get(
                    "Market_Structure", {}
                ).get("event", ""),
                "signal_time":     datetime.now(timezone.utc).isoformat(),
            })

            # FIX 3: Use feature_engineering for complete ML feature set
            if df_1h is not None:
                try:
                    from Sub_Projects.Trading.ml.feature_engineering import extract_features
                    features = extract_features(symbol, df_1h, context, session_name)
                except Exception as fe:
                    logger.debug(f"[TradingLoop] Feature extraction failed: {fe}")
                    # Fallback to basic features if extraction fails
                    features = {
                        "confidence":  confidence,
                        "grade":       grade,
                        "macro_trend": context.get("Macro_Trend"),
                        "utc_hour":    h,
                    }
            else:
                features = {"confidence": confidence, "utc_hour": h}

            db.save_ml_features(
                signal_id   = sid,
                symbol      = symbol,
                signal_time = datetime.now(timezone.utc).isoformat(),
                features    = features,
            )

        except Exception as e:
            logger.debug(f"[TradingLoop] Signal log error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # WATCHLIST
    # ─────────────────────────────────────────────────────────────────────────

    def _add_to_watchlist(self, symbol: str, inst_data: dict):
        if any(w["symbol"] == symbol for w in self._watchlist):
            return
        self._watchlist.append({
            "symbol":   symbol,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "score":    inst_data.get("score", 0),
        })
        logger.debug(f"[TradingLoop] Added {symbol} to watchlist (outside KZ)")

    def _process_watchlist(self):
        if not self._watchlist:
            return

        still_pending = []
        for item in self._watchlist:
            symbol = item["symbol"]
            in_kz, kz_name = is_in_kill_zone(symbol)

            if in_kz:
                from Sub_Projects.Trading.position_tracker import positions
                if not positions.has_open_position(symbol):
                    self._regime_checked_analyse(symbol, f"{kz_name} (watchlist)")
            else:
                added = datetime.fromisoformat(item["added_at"])
                age_h = (datetime.now(timezone.utc) - added).total_seconds() / 3600
                if age_h < 4:
                    still_pending.append(item)

        self._watchlist = still_pending

    # ─────────────────────────────────────────────────────────────────────────
    # CORRELATION GUARD - unchanged
    # ─────────────────────────────────────────────────────────────────────────

    def _correlation_check(self, symbol: str, direction: str) -> tuple:
        try:
            from Sub_Projects.Trading.position_tracker import positions
            from Config.config import RISK

            max_corr    = RISK.get("max_correlated_exposure_pct", 2.0)
            usd_long    = {"EURUSD=X", "GBPUSD=X", "AUDUSD=X", "XAUUSD=X", "BTCUSDT", "ETHUSDT"}
            usd_short   = {"USDJPY=X", "USDCAD=X", "USDCHF=X"}
            total_risk  = 0.0

            for pos in positions.get_all():
                same_dir = (
                    pos["direction"] in ("buy","long") and direction in ("buy","long")
                ) or (
                    pos["direction"] in ("sell","short") and direction in ("sell","short")
                )
                if same_dir and pos["symbol"] in (usd_long | usd_short):
                    total_risk += pos.get("risk_pct", 1.0)

            if total_risk >= max_corr:
                return False, f"Correlated {total_risk:.1f}% >= limit {max_corr}%"
            return True, "OK"
        except Exception:
            return True, "OK"

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _get_exchange_for(self, symbol: str) -> str:
        from Config.config import get_instrument
        return get_instrument(symbol).get("exchange", "paper")

    def _get_node_name(self) -> str:
        import socket
        hostname = socket.gethostname().upper()
        from Config.config import NODES
        for name, cfg in NODES.items():
            if any(p.upper() in hostname for p in cfg.get("hostname_patterns", [])):
                return name
        return "unknown"


# ── Singleton ─────────────────────────────────────────────────────────────────
trading_loop = TradingLoop()

