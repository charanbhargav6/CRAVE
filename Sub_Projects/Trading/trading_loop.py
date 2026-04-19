"""
CRAVE v10.0 — Trading Loop
============================
The main signal detection and execution loop.
This is the heart of the bot — it ties every module together.

FLOW PER KILL ZONE CYCLE (every 5 minutes during KZ):

  1. GATE CHECKS
     ├── streak.can_trade()              → circuit breaker / daily loss
     ├── orchestrator.is_active()        → is this node the active one?
     └── event_hedge.active_hedges == 0  → no live event blocking trades

  2. INSTRUMENT SELECTION
     ├── scanner.get_tradeable_today()   → ranked list of instruments
     └── Take top 1-2 only (Scenario B)

  3. PER INSTRUMENT
     ├── bias_engine.is_tradeable_today(symbol, direction)
     ├── kill_zone_filter.is_active()    → are we in London/NY KZ right now?
     ├── data_agent.get_ohlcv(1H + 4H)  → fresh candles
     ├── strategy_agent.analyze_market_context()  → SMC signal
     ├── MTF gate: 4H structure must align with 1H signal
     ├── Grade filter: A+/A/B+/B → get lot multiplier
     ├── risk_agent.validate_trade_signal()  → SL/TP calculation
     └── Execute (paper or live)

  4. POST-EXECUTION
     ├── position_tracker.open()         → persist position
     ├── database_manager.save_signal()  → log everything
     ├── database_manager.save_ml_features() → for future ML
     └── Telegram alert

WATCHLIST:
  Signals that form outside kill zones go to a watchlist.
  On next kill zone open, valid watchlist signals fire first.
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
    """
    Check if current time is inside a kill zone for this symbol.
    Returns (in_kz: bool, zone_name: str).
    """
    try:
        from zoneinfo import ZoneInfo
        from Config.config import KILL_ZONES

        now_utc = datetime.now(timezone.utc)

        for zone_name, zone_cfg in KILL_ZONES.items():
            # Check instrument eligibility
            instruments = zone_cfg.get("instruments", "all")
            if instruments != "all" and symbol not in instruments:
                continue

            # Parse zone times (UTC)
            start_h, start_m = map(int, zone_cfg["start_utc"].split(":"))
            end_h,   end_m   = map(int, zone_cfg["end_utc"].split(":"))

            now_mins   = now_utc.hour * 60 + now_utc.minute
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
        return True, "unknown"   # Fail open — don't block on error


# ── MTF Confluence Gate ───────────────────────────────────────────────────────

def check_mtf_confluence(symbol: str, direction: str,
                           df_1h, df_4h) -> tuple:
    """
    4H structure must agree with 1H signal direction.
    Returns (aligned: bool, reason: str).
    """
    try:
        import pandas as pd
        if df_4h is None or len(df_4h) < 10:
            return True, "4H data unavailable — passing by default"

        close_4h  = df_4h['close'].iloc[-1]
        ema21_4h  = df_4h['close'].ewm(span=21, adjust=False).mean().iloc[-1]
        ema50_4h  = df_4h['close'].rolling(50).mean().iloc[-1]

        above_ema21 = close_4h > ema21_4h
        ema21_above_ema50 = (
            ema21_4h > ema50_4h
            if not pd.isna(ema50_4h) else None
        )

        if direction in ("buy", "long"):
            if above_ema21:
                return True, f"4H bullish: price above EMA21 ({ema21_4h:.5f})"
            else:
                return False, f"4H bearish: price below EMA21 ({ema21_4h:.5f})"
        else:
            if not above_ema21:
                return True, f"4H bearish: price below EMA21 ({ema21_4h:.5f})"
            else:
                return False, f"4H bullish: conflicts with short signal"

    except Exception as e:
        logger.debug(f"[Loop] MTF gate error: {e}")
        return True, "MTF error — passing by default"


# ── Grade to Lot Multiplier ───────────────────────────────────────────────────

def grade_to_risk_multiplier(grade: str) -> float:
    """Map signal grade to risk multiplier. B gets 0.25×, A+ gets 1.0×."""
    from Config.config import RISK
    return RISK["grade_multipliers"].get(grade, 0.25)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TRADING LOOP
# ─────────────────────────────────────────────────────────────────────────────

class TradingLoop:

    SCAN_INTERVAL_SECS      = 300    # Check every 5 minutes
    MAX_INSTRUMENTS_PER_DAY = 2      # Scenario B: focus on top 1-2

    def __init__(self):
        self._running        = False
        self._thread: Optional[threading.Thread] = None
        self._watchlist:     List[dict] = []   # pending signals for next KZ
        self._trades_today   = 0
        self._last_trade_date = ""
        self._is_paper        = True

        # Load paper mode setting
        try:
            from Config.config import PAPER_TRADING
            self._is_paper = PAPER_TRADING.get("enabled", True)
        except Exception:
            self._is_paper = True

        logger.info(
            f"[TradingLoop] Initialised. Mode: "
            f"{'📄 PAPER' if self._is_paper else '💰 LIVE'}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # START / STOP
    # ─────────────────────────────────────────────────────────────────────────

    def start(self):
        """Start trading loop in background thread."""
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop,
            daemon=True,
            name="CRAVETradingLoop"
        )
        self._thread.start()
        logger.info(
            f"[TradingLoop] Started. "
            f"Scanning every {self.SCAN_INTERVAL_SECS}s."
        )

    def stop(self):
        self._running = False
        logger.info("[TradingLoop] Stopped.")

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"[TradingLoop] Cycle error: {e}")
            time.sleep(self.SCAN_INTERVAL_SECS)

    def _run_cycle(self):
        """One full scan cycle."""

        # ── Reset daily trade count at session boundary ───────────────────
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._last_trade_date:
            self._trades_today    = 0
            self._last_trade_date = today

        # ── Gate 1: Circuit breaker + daily loss ──────────────────────────
        from Sub_Projects.Trading.streak_state import streak
        can_trade, reason = streak.can_trade()
        if not can_trade:
            logger.debug(f"[TradingLoop] Gate blocked: {reason}")
            return

        # ── Gate 2: Is this node active? ──────────────────────────────────
        try:
            from Sub_Projects.Trading.node_orchestrator import orchestrator
            if not orchestrator.is_active():
                return   # Standby node — don't trade
        except Exception:
            pass

        # ── Gate 3: Already at max positions for today? ───────────────────
        from Sub_Projects.Trading.position_tracker import positions
        current_open = positions.count()

        if current_open >= self.MAX_INSTRUMENTS_PER_DAY:
            logger.debug(
                f"[TradingLoop] Max positions reached "
                f"({current_open}/{self.MAX_INSTRUMENTS_PER_DAY})"
            )
            return

        # ── Check watchlist first (pending signals) ───────────────────────
        self._process_watchlist()

        # ── Instrument selection ──────────────────────────────────────────
        from Sub_Projects.Trading.instrument_scanner import scanner
        tradeable = scanner.get_tradeable_today()

        if not tradeable:
            logger.debug("[TradingLoop] No tradeable instruments today.")
            return

        # Scan top instruments (limit to MAX_INSTRUMENTS_PER_DAY)
        slots_available = self.MAX_INSTRUMENTS_PER_DAY - current_open
        for inst_data in tradeable[:slots_available * 2]:   # check 2× slots
            symbol = inst_data["symbol"]

            # Skip if already in a position on this symbol
            if positions.has_open_position(symbol):
                continue

            # Check kill zone
            in_kz, kz_name = is_in_kill_zone(symbol)
            if not in_kz:
                # Add to watchlist for next kill zone
                self._add_to_watchlist(symbol, inst_data)
                continue

            # Run signal analysis
            result = self._analyse_and_execute(symbol, kz_name)

            if result and result.get("executed"):
                slots_available -= 1
                if slots_available <= 0:
                    break

    # ─────────────────────────────────────────────────────────────────────────
    # SIGNAL ANALYSIS AND EXECUTION
    # ─────────────────────────────────────────────────────────────────────────

    def _analyse_and_execute(self, symbol: str,
                              kz_name: str = "") -> Optional[dict]:
        """
        Full signal pipeline for one instrument.
        Returns execution result or None.
        """
        logger.info(f"[TradingLoop] Analysing {symbol} ({kz_name})...")

        # ── Fetch data ────────────────────────────────────────────────────
        from Sub_Projects.Trading.data_agent import DataAgent
        da = DataAgent()

        df_1h = da.get_ohlcv(symbol, timeframe="1h", limit=250)
        df_4h = da.get_ohlcv(symbol, timeframe="4h", limit=60)

        if df_1h is None or len(df_1h) < 60:
            logger.warning(f"[TradingLoop] Insufficient data for {symbol}")
            return None

        # ── SMC analysis ──────────────────────────────────────────────────
        from Sub_Projects.Trading.strategy_agent import StrategyAgent
        strategy = StrategyAgent()
        context  = strategy.analyze_market_context(symbol, df_1h)

        if "error" in context:
            logger.debug(f"[TradingLoop] Strategy error: {context['error']}")
            return None

        confidence   = context.get("Confidence_Pct", 0)
        grade_str    = context.get("Structure_Score", "C")
        macro_trend  = context.get("Macro_Trend", "Unknown")
        current_price = context.get("Current_Price", df_1h['close'].iloc[-1])

        # ── Unknown trend → skip (never default to SELL) ──────────────────
        if macro_trend == "Unknown":
            logger.debug(f"[TradingLoop] {symbol}: Unknown trend — skipping")
            self._log_signal(symbol, "skip", "Unknown macro trend",
                             confidence, grade_str, context)
            return None

        direction = "buy" if macro_trend == "Bullish" else "sell"

        # ── Daily bias gate ───────────────────────────────────────────────
        from Sub_Projects.Trading.daily_bias_engine import bias_engine
        if not bias_engine.is_tradeable_today(symbol, direction):
            bias = bias_engine.get_bias(symbol)
            bias_str = bias.get("bias", "NO_TRADE") if bias else "NO_BIAS"
            logger.debug(
                f"[TradingLoop] {symbol}: Daily bias={bias_str}, "
                f"signal={direction} — conflict, skipping"
            )
            self._log_signal(symbol, "skip",
                             f"Bias conflict: bias={bias_str} signal={direction}",
                             confidence, grade_str, context)
            return None

        # ── Grade filter (B and above trade) ─────────────────────────────
        grade = None
        for g in ("A+", "A", "B+", "B"):
            if g in grade_str:
                grade = g
                break

        if grade is None:
            logger.debug(f"[TradingLoop] {symbol}: Grade C — skip")
            return None

        # ── Minimum confidence (40% for B, 55% for A+) ───────────────────
        min_conf = {"A+": 55, "A": 50, "B+": 45, "B": 40}.get(grade, 40)
        if confidence < min_conf:
            logger.debug(
                f"[TradingLoop] {symbol}: Confidence {confidence}% < "
                f"{min_conf}% for grade {grade}"
            )
            return None

        # ── MTF confluence gate ───────────────────────────────────────────
        mtf_ok, mtf_reason = check_mtf_confluence(symbol, direction,
                                                    df_1h, df_4h)
        if not mtf_ok:
            logger.debug(f"[TradingLoop] {symbol}: MTF failed — {mtf_reason}")
            self._log_signal(symbol, "skip",
                             f"MTF conflict: {mtf_reason}",
                             confidence, grade_str, context)
            return None

        # ── Correlation guard ─────────────────────────────────────────────
        corr_ok, corr_reason = self._correlation_check(symbol, direction)
        if not corr_ok:
            logger.debug(f"[TradingLoop] {symbol}: Correlation block — {corr_reason}")
            return None

        # ── Risk validation ───────────────────────────────────────────────
        from Sub_Projects.Trading.risk_agent import RiskAgent
        from Sub_Projects.Trading.streak_state import streak

        risk_pct   = streak.get_current_risk_pct(grade)
        risk_agent = RiskAgent()

        # Override risk_agent base risk with streak-adjusted value
        risk_agent.max_risk_per_trade = risk_pct / 100

        # Get equity — use paper equity or broker equity
        equity = self._get_current_equity()

        signal_dict = {
            "action":  direction,
            "price":   current_price,
            "symbol":  symbol,
            "is_swing_trade": context.get("Is_Swing_Trade", False),
        }

        validated = risk_agent.validate_trade_signal(
            current_equity  = equity,
            signal          = signal_dict,
            df              = df_1h,
            confidence_pct  = confidence,
        )

        if not validated.get("approved"):
            logger.debug(
                f"[TradingLoop] {symbol}: Risk veto — "
                f"{validated.get('reason')}"
            )
            return None

        # Enrich validated signal
        validated["grade"]     = grade
        validated["risk_pct"]  = risk_pct
        validated["is_paper"]  = self._is_paper
        validated["exchange"]  = self._get_exchange_for(symbol)
        validated["node"]      = self._get_node_name()

        # ── Execute ───────────────────────────────────────────────────────
        logger.info(
            f"[TradingLoop] SIGNAL: {symbol} {direction.upper()} "
            f"grade={grade} conf={confidence}% risk={risk_pct:.2f}% "
            f"{'[PAPER]' if self._is_paper else '[LIVE]'}"
        )

        result = self._execute(validated, current_price)

        if result and result.get("status") in ("filled", "paper_filled"):
            self._trades_today += 1
            self._log_signal(symbol, "traded", "Executed",
                             confidence, grade_str, context, validated)
            return {"executed": True, "trade_id": result.get("trade_id")}

        self._log_signal(symbol, "failed",
                         result.get("reason", "execution failed"),
                         confidence, grade_str, context)
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # EXECUTION (paper or live)
    # ─────────────────────────────────────────────────────────────────────────

    def _execute(self, validated: dict, current_price: float) -> dict:
        """Execute validated signal — paper or live."""
        if self._is_paper:
            return self._paper_execute(validated, current_price)
        else:
            return self._live_execute(validated, current_price)

    def _paper_execute(self, validated: dict, current_price: float) -> dict:
        """
        Simulate order fill in paper trading mode.
        Adds realistic slippage simulation.
        """
        symbol    = validated["symbol"]
        direction = validated["direction"]
        entry     = validated["entry"]

        # Simulate slippage
        from Config.config import get_instrument
        inst      = get_instrument(symbol)
        pip_size  = inst.get("pip_size", 0.0001)
        slippage  = pip_size * 2   # 2 pips slippage simulation

        if direction in ("buy", "long"):
            fill_price = round(current_price + slippage, 5)
        else:
            fill_price = round(current_price - slippage, 5)

        trade_id = str(uuid.uuid4())[:8].upper()

        # Register in position tracker
        from Sub_Projects.Trading.position_tracker import positions
        positions.open({
            **validated,
            "trade_id":    trade_id,
            "entry":       fill_price,
            "entry_price": fill_price,
            "is_paper":    True,
            "exchange":    "paper",
        })

        # Telegram alert
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
        """Execute on live broker."""
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
    # WATCHLIST
    # ─────────────────────────────────────────────────────────────────────────

    def _add_to_watchlist(self, symbol: str, inst_data: dict):
        """Add a symbol to the watchlist for next kill zone."""
        # Avoid duplicates
        if any(w["symbol"] == symbol for w in self._watchlist):
            return

        self._watchlist.append({
            "symbol":    symbol,
            "added_at":  datetime.now(timezone.utc).isoformat(),
            "score":     inst_data.get("score", 0),
        })
        logger.debug(f"[TradingLoop] Added {symbol} to watchlist (outside KZ)")

    def _process_watchlist(self):
        """Check watchlist — fire signals that are now in a kill zone."""
        if not self._watchlist:
            return

        still_pending = []
        for item in self._watchlist:
            symbol = item["symbol"]
            in_kz, kz_name = is_in_kill_zone(symbol)

            if in_kz:
                logger.info(
                    f"[TradingLoop] Watchlist: {symbol} now in KZ "
                    f"{kz_name} — checking signal validity"
                )
                # Re-validate signal is still good before executing
                from Sub_Projects.Trading.position_tracker import positions
                if not positions.has_open_position(symbol):
                    self._analyse_and_execute(symbol, f"{kz_name} (watchlist)")
            else:
                # Expire watchlist entries older than 4 hours
                added  = datetime.fromisoformat(item["added_at"])
                age_h  = (datetime.now(timezone.utc) - added).total_seconds() / 3600
                if age_h < 4:
                    still_pending.append(item)

        self._watchlist = still_pending

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _correlation_check(self, symbol: str, direction: str) -> tuple:
        """
        Check if adding this position would create correlated overexposure.
        Max 2% total risk on correlated pairs.
        """
        try:
            from Sub_Projects.Trading.position_tracker import positions
            from Config.config import RISK, get_instrument

            max_corr_exposure = RISK.get("max_correlated_exposure_pct", 2.0)
            corr_threshold    = RISK.get("correlation_threshold", 0.70)

            # Pairs considered correlated (same-direction = same USD exposure)
            usd_long_pairs  = {"EURUSD=X", "GBPUSD=X", "AUDUSD=X",
                                "XAUUSD=X", "BTCUSDT", "ETHUSDT"}
            usd_short_pairs = {"USDJPY=X", "USDCAD=X", "USDCHF=X"}

            open_positions = positions.get_all()
            total_corr_risk = 0.0

            for pos in open_positions:
                pos_sym  = pos["symbol"]
                pos_dir  = pos["direction"]
                pos_risk = pos.get("risk_pct", 1.0)

                # Check if this open position is correlated with proposed trade
                same_dir = (
                    pos_dir in ("buy", "long") and direction in ("buy", "long")
                ) or (
                    pos_dir in ("sell", "short") and direction in ("sell", "short")
                )

                if same_dir and (pos_sym in usd_long_pairs or
                                  pos_sym in usd_short_pairs):
                    total_corr_risk += pos_risk

            if total_corr_risk >= max_corr_exposure:
                return (
                    False,
                    f"Correlated exposure {total_corr_risk:.1f}% >= "
                    f"{max_corr_exposure}% limit"
                )

            return True, "OK"

        except Exception as e:
            logger.debug(f"[TradingLoop] Correlation check error: {e}")
            return True, "OK"   # Fail open

    def _get_current_equity(self) -> float:
        """Get current account equity."""
        if self._is_paper:
            from Config.config import PAPER_TRADING
            # In real implementation, track paper equity dynamically
            # For now use starting equity
            return float(PAPER_TRADING.get("starting_equity", 10000))

        try:
            from Sub_Projects.Trading.data_agent import DataAgent
            da      = DataAgent()
            account = da.alpaca.get_account() if da.alpaca else None
            if account:
                return float(account.equity)
        except Exception:
            pass

        return 10000.0   # Fallback

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

    def _log_signal(self, symbol: str, status: str, reason: str,
                     confidence: int, grade: str, context: dict,
                     validated: dict = None):
        """Log every signal to database for ML feature collection."""
        try:
            from Sub_Projects.Trading.database_manager import db
            signal_id = str(uuid.uuid4())[:8].upper()

            db.save_signal({
                "signal_id":       signal_id,
                "symbol":          symbol,
                "direction":       "buy" if context.get("Macro_Trend") == "Bullish" else "sell",
                "confidence":      confidence,
                "grade":           grade,
                "was_traded":      status == "traded",
                "skip_reason":     reason if status != "traded" else None,
                "entry_price":     context.get("Current_Price"),
                "atr":             validated.get("atr") if validated else None,
                "session":         "london" if 7 <= datetime.now(timezone.utc).hour < 16 else "ny",
                "macro_trend":     context.get("Macro_Trend"),
                "fvg_hit":         any(f.get("price_inside") for f in context.get("Recent_FVGs", [])),
                "ob_hit":          any(ob.get("zone", [0,0])[0] <= context.get("Current_Price", 0) <=
                                       ob.get("zone", [0,1])[1] for ob in context.get("Order_Blocks", [])),
                "sweep_detected":  context.get("Liquidity_Sweep", {}).get("sweep_detected", False),
                "rsi_divergence":  context.get("RSI_Divergence", {}).get("divergence", "none"),
                "volume_signal":   context.get("Volume_Delta", {}).get("signal", ""),
                "structure_event": context.get("Market_Structure", {}).get("event", ""),
                "signal_time":     datetime.now(timezone.utc).isoformat(),
            })

            # Save ML features snapshot
            db.save_ml_features(
                signal_id   = signal_id,
                symbol      = symbol,
                signal_time = datetime.now(timezone.utc).isoformat(),
                features    = {
                    "confidence":      confidence,
                    "grade":           grade,
                    "macro_trend":     context.get("Macro_Trend"),
                    "fvg_hit":         bool(context.get("Recent_FVGs")),
                    "ob_hit":          bool(context.get("Order_Blocks")),
                    "sweep":           context.get("Liquidity_Sweep", {}).get("sweep_detected"),
                    "rsi_div":         context.get("RSI_Divergence", {}).get("divergence"),
                    "vol_signal":      context.get("Volume_Delta", {}).get("signal"),
                    "structure":       context.get("Market_Structure", {}).get("event"),
                    "premium_discount": context.get("Premium_Discount", {}).get("zone"),
                    "utc_hour":        datetime.now(timezone.utc).hour,
                }
            )

        except Exception as e:
            logger.debug(f"[TradingLoop] Signal log error: {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
trading_loop = TradingLoop()
