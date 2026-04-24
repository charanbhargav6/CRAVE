"""
CRAVE v10.0 - Instrument Scanner
==================================
Runs daily at 06:45 UTC after DailyBiasEngine completes.
Ranks all instruments and selects the top 1-2 to trade today.

SCORING CRITERIA (max 10 points):
  ATR expansion      +3  current ATR > 20d avg ATR by 20%+ (market is moving)
  Liquidity nearby   +3  equal highs/lows or FVG within 1× ATR (magnet levels)
  Bias strength      +3  from DailyBiasEngine (1/2/3 points)
  Clean structure    +1  no conflicting signals, clear BOS/CHoCH
  Funding neutral     -2  (crypto only) extreme funding = crowded trade

TRADEABLE TODAY:
  Score >= 6 AND bias != NO_TRADE → tradeable
  Score < 6 OR bias == NO_TRADE  → skip today

IF NOTHING SCORES >= 6:
  No trades today. Zero is better than a forced bad trade.

USAGE:
  from Sub_Projects.Trading.instrument_scanner import scanner

  # Run daily ranking
  ranking = scanner.run_daily_scan()

  # Check if specific instrument is tradeable
  ok, reason = scanner.is_tradeable("XAUUSD=X")
  
  # Get top instrument for today
  top = scanner.get_top_instrument()
"""

import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

logger = logging.getLogger("crave.scanner")


class InstrumentScanner:

    MIN_SCORE_TO_TRADE = 6

    def __init__(self):
        self._today_ranking: list = []
        self._last_scan_date: Optional[str] = None

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN SCAN
    # ─────────────────────────────────────────────────────────────────────────

    def run_daily_scan(self, force: bool = False) -> list:
        """
        Score and rank all tradeable instruments.
        Returns sorted list of {symbol, score, tradeable, reason}.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if not force and self._last_scan_date == today and self._today_ranking:
            return self._today_ranking

        logger.info("[Scanner] Running daily instrument scan...")

        from Config.config import get_tradeable_symbols
        from concurrent.futures import ThreadPoolExecutor, as_completed
        symbols = get_tradeable_symbols()
        results = []

        # PRIORITY 4: Parallel scoring — each symbol is independent.
        # ThreadPoolExecutor(4) reduces wall time from ~16s to ~4s.
        # Errors are caught per-symbol; one failure doesn't block others.
        def _score_safe(symbol: str) -> dict:
            try:
                return self._score_instrument(symbol)
            except Exception as e:
                logger.error(f"[Scanner] Scoring failed for {symbol}: {e}")
                return {
                    "symbol":    symbol,
                    "score":     0,
                    "tradeable": False,
                    "reason":    f"Error: {e}",
                    "breakdown": {},
                }

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_score_safe, s): s for s in symbols}
            for future in as_completed(futures):
                results.append(future.result())

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        self._today_ranking  = results
        self._last_scan_date = today

        # Log and notify
        self._log_and_notify(results)

        return results

    def _score_instrument(self, symbol: str) -> dict:
        """Score a single instrument. Returns score dict."""
        from Config.config import get_instrument
        inst_cfg  = get_instrument(symbol)
        score     = 0
        breakdown = {}

        # ── 1. ATR Expansion (+3) ──────────────────────────────────────────
        df = self._get_ohlcv(symbol, "1h", limit=250)
        atr_score = 0
        if df is not None and len(df) >= 50:
            atr     = self._wilder_atr(df, 14)
            atr_20d = self._wilder_atr(df.tail(480), 14)  # 20d avg on 1H = 480 candles

            if not pd.isna(atr) and not pd.isna(atr_20d) and atr_20d > 0:
                expansion = atr / atr_20d
                if expansion >= 1.4:
                    atr_score = 3
                    breakdown["ATR"] = "+3 (strongly expanding)"
                elif expansion >= 1.2:
                    atr_score = 2
                    breakdown["ATR"] = "+2 (expanding)"
                elif expansion >= 1.0:
                    atr_score = 1
                    breakdown["ATR"] = "+1 (normal)"
                else:
                    breakdown["ATR"] = "+0 (contracting - avoid)"
            score += atr_score

        # ── 2. Liquidity Proximity (+3) ────────────────────────────────────
        liq_score = 0
        if df is not None and len(df) >= 20:
            liq_score = self._check_liquidity_proximity(df, symbol)
            score    += liq_score
            breakdown["Liquidity"] = f"+{liq_score}"

        # ── 3. Bias Strength (+3) ──────────────────────────────────────────
        bias_score = 0
        try:
            from Sub_Projects.Trading.daily_bias_engine import bias_engine
            bias = bias_engine.get_bias(symbol)
            if bias:
                bias_val = bias.get("bias", "NO_TRADE")
                strength = bias.get("strength", 0)
                if bias_val != "NO_TRADE":
                    bias_score = min(strength, 3)
                    breakdown["Bias"] = f"+{bias_score} ({bias_val} str={strength})"
                else:
                    breakdown["Bias"] = "+0 (NO_TRADE)"
        except Exception as e:
            breakdown["Bias"] = f"+0 (error: {e})"
        score += bias_score

        # ── 4. Clean structure (+1) ────────────────────────────────────────
        structure_score = 0
        if df is not None and len(df) >= 30:
            # Check that last 3 candles are not high-wick dojis (indecision)
            last3       = df.tail(3)
            bodies      = (last3['close'] - last3['open']).abs()
            ranges      = last3['high'] - last3['low']
            body_ratio  = (bodies / ranges.replace(0, np.nan)).mean()
            if not pd.isna(body_ratio) and body_ratio > 0.4:
                structure_score = 1
                breakdown["Structure"] = "+1 (clean candles)"
            else:
                breakdown["Structure"] = "+0 (doji/indecision)"
        score += structure_score

        # ── 5. Funding rate penalty (crypto, -2) ──────────────────────────
        funding_penalty = 0
        if inst_cfg.get("funding_check"):
            try:
                from Sub_Projects.Trading.data_agent import DataAgent
                da   = DataAgent()
                rate = da.get_funding_rate(symbol)
                if rate.get("available"):
                    r = abs(rate.get("funding_rate_pct", 0))
                    if r > 0.05:
                        funding_penalty = -2
                        breakdown["Funding"] = f"-2 (extreme: {r:.3f}%)"
                    else:
                        breakdown["Funding"] = "+0 (neutral)"
            except Exception:
                pass
        score += funding_penalty

        # ── Final decision ────────────────────────────────────────────────
        tradeable = (
            score >= self.MIN_SCORE_TO_TRADE and
            bias_score > 0   # Must have a clear bias
        )

        if not tradeable:
            if bias_score == 0:
                reason = "No clear daily bias"
            elif score < self.MIN_SCORE_TO_TRADE:
                reason = f"Score {score} < minimum {self.MIN_SCORE_TO_TRADE}"
            else:
                reason = "Below threshold"
        else:
            reason = f"Score {score}/10 - tradeable"

        return {
            "symbol":    symbol,
            "score":     score,
            "tradeable": tradeable,
            "reason":    reason,
            "breakdown": breakdown,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # LIQUIDITY PROXIMITY CHECK
    # ─────────────────────────────────────────────────────────────────────────

    def _check_liquidity_proximity(self, df: pd.DataFrame,
                                    symbol: str) -> int:
        """
        Check if price is near a significant liquidity level.
        Equal highs/lows or unmitigated FVGs = price magnet = high follow-through.
        """
        current = df['close'].iloc[-1]
        atr     = self._wilder_atr(df, 14)
        if atr == 0:
            return 0

        proximity_threshold = atr * 2   # within 2× ATR of a level

        # Equal highs (liquidity pool above)
        recent_highs = df['high'].tail(50).values
        for i in range(len(recent_highs)):
            for j in range(i + 1, len(recent_highs)):
                if abs(recent_highs[i] - recent_highs[j]) / recent_highs[i] <= 0.002:
                    level = (recent_highs[i] + recent_highs[j]) / 2
                    if abs(current - level) <= proximity_threshold:
                        return 3   # Very close to equal highs

        # Equal lows (liquidity pool below)
        recent_lows = df['low'].tail(50).values
        for i in range(len(recent_lows)):
            for j in range(i + 1, len(recent_lows)):
                if abs(recent_lows[i] - recent_lows[j]) / recent_lows[i] <= 0.002:
                    level = (recent_lows[i] + recent_lows[j]) / 2
                    if abs(current - level) <= proximity_threshold:
                        return 3

        # Unmitigated FVG nearby
        for i in range(max(0, len(df)-20), len(df)-2):
            c1_high = df['high'].iloc[i]
            c1_low  = df['low'].iloc[i]
            c3_low  = df['low'].iloc[i + 2]
            c3_high = df['high'].iloc[i + 2]

            if c3_low > c1_high:   # Bullish FVG
                mid = (c1_high + c3_low) / 2
                if abs(current - mid) <= proximity_threshold:
                    return 2

            if c3_high < c1_low:   # Bearish FVG
                mid = (c3_high + c1_low) / 2
                if abs(current - mid) <= proximity_threshold:
                    return 2

        # Swing high/low nearby
        window = 5
        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == df['high'].iloc[i-window:i+window+1].max():
                if abs(current - df['high'].iloc[i]) <= proximity_threshold:
                    return 1
            if df['low'].iloc[i] == df['low'].iloc[i-window:i+window+1].min():
                if abs(current - df['low'].iloc[i]) <= proximity_threshold:
                    return 1

        return 0

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC QUERIES
    # ─────────────────────────────────────────────────────────────────────────

    def is_tradeable(self, symbol: str) -> tuple:
        """Returns (tradeable: bool, reason: str)."""
        ranking = self.run_daily_scan()
        for item in ranking:
            if item["symbol"] == symbol:
                return item["tradeable"], item["reason"]
        return False, f"{symbol} not in instrument list"

    def get_top_instrument(self) -> Optional[dict]:
        """Get the highest-scoring tradeable instrument today."""
        ranking = self.run_daily_scan()
        for item in ranking:
            if item["tradeable"]:
                return item
        return None

    def get_tradeable_today(self) -> list:
        """Get all tradeable instruments today, ranked by score."""
        ranking = self.run_daily_scan()
        return [item for item in ranking if item["tradeable"]]

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _wilder_atr(self, df: pd.DataFrame, period: int) -> float:
        if len(df) < period + 1:
            return 0.0
        tr  = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low']  - df['close'].shift()).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0/period, adjust=False).mean()
        val = atr.iloc[-1]
        return float(val) if not pd.isna(val) else 0.0

    def _get_ohlcv(self, symbol: str, timeframe: str,
                    limit: int) -> Optional[pd.DataFrame]:
        """Fetch OHLCV via data router - handles all markets."""
        try:
            from Sub_Projects.Trading.data.market_data_router import get_data_router
            df = get_data_router().get_ohlcv(symbol, timeframe, limit=limit)
            if df is not None and len(df) >= 10:
                return df
        except Exception:
            pass
        # Original fallback below
        try:
            from Sub_Projects.Trading.database_manager import db
            cached = db.get_cached_ohlcv(symbol, timeframe, limit=limit)
            if cached is not None and len(cached) >= 50:
                return cached
        except Exception:
            pass

        try:
            import yfinance as yf
            tf_map = {"1h": "1h", "4h": "4h", "1d": "1d"}
            tf     = tf_map.get(timeframe, "1h")
            days   = max(limit // 16 + 10, 30)   # rough estimate
            end    = datetime.now()
            start  = end - timedelta(days=days)
            df     = yf.download(symbol, start=start, end=end,
                                  interval=tf, progress=False)
            if df is None or df.empty:
                return None
            df = df.reset_index()
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            col_map = {}
            for col in df.columns:
                cl = str(col).lower()
                if "date" in cl: col_map[col] = "time"
                elif cl == "open":   col_map[col] = "open"
                elif cl == "high":   col_map[col] = "high"
                elif cl == "low":    col_map[col] = "low"
                elif cl == "close":  col_map[col] = "close"
                elif cl == "volume": col_map[col] = "volume"
            df = df.rename(columns=col_map)
            if "volume" not in df.columns:
                df["volume"] = 0
            df["time"] = pd.to_datetime(df["time"])
            df = df[["time","open","high","low","close","volume"]].dropna()
            return df.reset_index(drop=True)
        except Exception as e:
            logger.debug(f"[Scanner] OHLCV fetch failed {symbol}: {e}")
            return None

    def _log_and_notify(self, results: list):
        """Log ranking and send Telegram summary."""
        logger.info("[Scanner] Daily ranking:")
        for item in results:
            status = "✅" if item["tradeable"] else "❌"
            logger.info(
                f"  {status} {item['symbol']:15s} "
                f"score={item['score']:4.1f} {item['reason']}"
            )

        try:
            from Sub_Projects.Trading.telegram_interface import tg
            tradeable = [i for i in results if i["tradeable"]]
            lines     = [
                "🎯 <b>INSTRUMENT SCAN</b>",
                f"Tradeable today: {len(tradeable)}",
                "━━━━━━━━━━━━━━━",
            ]
            for item in results[:6]:   # show top 6
                status = "✅" if item["tradeable"] else "❌"
                short  = item["symbol"].replace("=X", "").replace("-USD", "")
                lines.append(f"{status} {short}: {item['score']}/10 - {item['reason']}")

            if not tradeable:
                lines.append("\n⚠️ No instruments qualify today. No trades.")

            tg.send("\n".join(lines))
        except Exception as e:
            logger.debug(f"[Scanner] Telegram notify failed: {e}")

    def get_summary_message(self) -> str:
        """Formatted ranking for Telegram /scan command."""
        ranking = self.run_daily_scan()
        if not ranking:
            return "📊 No scan results. Run /scan to refresh."
        lines = [f"🎯 <b>INSTRUMENT RANKING - "
                 f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}</b>",
                 "━━━━━━━━━━━━━━━"]
        for item in ranking:
            status = "✅" if item["tradeable"] else "❌"
            short  = item["symbol"].replace("=X","").replace("-USD","")
            lines.append(f"{status} {short}: {item['score']}/10")
        return "\n".join(lines)


# ── Singleton ─────────────────────────────────────────────────────────────────
scanner = InstrumentScanner()

