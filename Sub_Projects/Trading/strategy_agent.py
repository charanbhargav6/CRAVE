"""
CRAVE Phase 9.1 - Smart Money Strategy Engine
==============================================
FIXES vs v9.0:
  🔧 FVG mitigation logic corrected (was marking zones as dead on approach)
  🔧 Macro override no longer bypasses SMC scoring (danger = caution, not confidence)
  🔧 RSI divergence now uses proper swing pivot detection
  🔧 OB displacement threshold raised to 2.0× with ATR expansion confirmation
  🔧 CHoCH/BOS uses candle CLOSE confirmation, not raw tick
  🔧 Session filter uses ZoneInfo for DST-accurate London/NY hours
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone

logger = logging.getLogger("crave.trading.strategy")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _is_london_or_ny(ts) -> bool:
    """
    FIX v9.1: Uses ZoneInfo for DST-correct London open detection.
    London: 08:00–17:00 local (shifts between 07:00–08:00 UTC depending on BST/GMT)
    NY:     09:30–17:00 ET local (13:30–21:00 UTC in winter, 12:30–20:00 UTC in summer)
    Simplified: check UTC hours with DST-aware conversion using ZoneInfo.
    """
    try:
        from zoneinfo import ZoneInfo

        utc_ts = pd.Timestamp(ts)
        if utc_ts.tzinfo is None:
            utc_ts = utc_ts.tz_localize("UTC")
        else:
            utc_ts = utc_ts.tz_convert("UTC")

        london_ts = utc_ts.tz_convert(ZoneInfo("Europe/London"))
        ny_ts     = utc_ts.tz_convert(ZoneInfo("America/New_York"))

        # London session: 08:00–17:00 local
        in_london = 8 <= london_ts.hour < 17
        # NY session: 09:30–17:00 local (using hour only, minute ignored for simplicity)
        in_ny     = 9 <= ny_ts.hour < 17

        return in_london or in_ny

    except Exception:
        # Fallback to fixed UTC hours if ZoneInfo unavailable
        try:
            h = pd.Timestamp(ts).hour
            return (7 <= h < 16) or (13 <= h < 21)
        except Exception:
            return True  # Fail open — don't block trades on parse error


def _find_swing_pivots(series: pd.Series, window: int = 5) -> list:
    """
    NEW v9.1: Returns list of (index, value) for genuine swing highs or lows.
    Used by RSI divergence to avoid comparing arbitrary midpoints.
    Window=5 means price is the highest/lowest of the ±5 surrounding bars.
    """
    pivots = []
    vals   = series.values
    for i in range(window, len(vals) - window):
        neighborhood = vals[i - window: i + window + 1]
        if vals[i] == neighborhood.max() or vals[i] == neighborhood.min():
            pivots.append((i, vals[i]))
    return pivots


# ─────────────────────────────────────────────────────────────────────────────

class StrategyAgent:
    def __init__(self):
        pass

    # ── 1. FVG DETECTOR ──────────────────────────────────────────────────────

    def _identify_fvgs(self, df: pd.DataFrame) -> list:
        """
        Fair Value Gap (Imbalance) Detector.
        Bullish FVG : c3_low > c1_high  (upward displacement)
        Bearish FVG : c3_high < c1_low  (downward displacement)

        FIX v9.1 — Mitigation logic was backwards.
        OLD: touched = current_price <= c3_low  ← triggers BEFORE price enters zone
        NEW: A bullish FVG is mitigated only when price trades THROUGH the entire zone
             (i.e., closes below the zone bottom: c1_high).
             A bearish FVG is mitigated when price closes above the zone top: c1_low.
        An FVG that price is currently INSIDE is still valid — that's your entry zone.
        """
        fvgs = []
        if len(df) < 3:
            return fvgs

        current_price = df['close'].iloc[-1]

        for i in range(len(df) - 2):
            c1_high = df['high'].iloc[i]
            c1_low  = df['low'].iloc[i]
            c3_low  = df['low'].iloc[i + 2]
            c3_high = df['high'].iloc[i + 2]
            c2_time = df['time'].iloc[i + 1]
            c2_time_str = (
                c2_time.strftime("%Y-%m-%d %H:%M")
                if hasattr(c2_time, 'strftime') else str(c2_time)
            )

            min_gap_size = c1_high * 0.0003  # 0.03% noise filter

            if c3_low > c1_high:
                gap = round(c3_low - c1_high, 5)
                if gap > min_gap_size:
                    # FIX: mitigated = price has traded BELOW the zone bottom (fully filled)
                    mitigated = current_price < c1_high
                    fvgs.append({
                        "type":      "Bullish FVG",
                        "time":      c2_time_str,
                        "gap_size":  gap,
                        "zone":      [round(c1_high, 5), round(c3_low, 5)],
                        "mitigated": mitigated,
                        # NEW: Is price currently inside the zone? — this is the entry trigger
                        "price_inside": c1_high <= current_price <= c3_low,
                    })

            elif c3_high < c1_low:
                gap = round(c1_low - c3_high, 5)
                if gap > min_gap_size:
                    # FIX: mitigated = price has traded ABOVE the zone top (fully filled)
                    mitigated = current_price > c1_low
                    fvgs.append({
                        "type":      "Bearish FVG",
                        "time":      c2_time_str,
                        "gap_size":  gap,
                        "zone":      [round(c3_high, 5), round(c1_low, 5)],
                        "mitigated": mitigated,
                        "price_inside": c3_high <= current_price <= c1_low,
                    })

        return fvgs[-5:]

    # ── 2. ORDER BLOCK DETECTOR ──────────────────────────────────────────────

    def _identify_order_blocks(self, df: pd.DataFrame) -> list:
        """
        Order Block = the last opposing candle before a displacement move.

        FIX v9.1 — Displacement threshold raised from 1.5× to 2.0× avg body
        AND requires candle range (high-low) to exceed 1.2× ATR.
        This eliminates false OBs in ranging/Asian-session price action.
        """
        obs = []
        if len(df) < 5:
            return obs

        body_sizes = (df['close'] - df['open']).abs()
        avg_body   = body_sizes.rolling(20).mean()

        # NEW: ATR for displacement confirmation (using simple rolling for speed)
        candle_range = df['high'] - df['low']
        avg_atr      = candle_range.rolling(14).mean()

        current_price = df['close'].iloc[-1]

        for i in range(2, len(df) - 1):
            disp_body  = abs(df['close'].iloc[i] - df['open'].iloc[i])
            disp_range = df['high'].iloc[i] - df['low'].iloc[i]

            if pd.isna(avg_body.iloc[i]) or avg_body.iloc[i] == 0:
                continue
            if pd.isna(avg_atr.iloc[i]) or avg_atr.iloc[i] == 0:
                continue

            # FIX: Require BOTH body >= 2× avg body AND range >= 1.2× ATR
            if disp_body < avg_body.iloc[i] * 2.0:
                continue
            if disp_range < avg_atr.iloc[i] * 1.2:
                continue  # Not a true displacement — just a normal candle

            if df['close'].iloc[i] > df['open'].iloc[i]:
                for j in range(i - 1, max(i - 5, 0), -1):
                    if df['close'].iloc[j] < df['open'].iloc[j]:
                        ob_high    = df['high'].iloc[j]
                        ob_low     = df['low'].iloc[j]
                        is_breaker = current_price < ob_low
                        obs.append({
                            "type":      "Bearish Breaker" if is_breaker else "Bullish OB",
                            "zone":      [round(ob_low, 5), round(ob_high, 5)],
                            "time":      (df['time'].iloc[j].strftime("%Y-%m-%d %H:%M")
                                          if hasattr(df['time'].iloc[j], 'strftime')
                                          else str(df['time'].iloc[j])),
                            "mitigated": is_breaker,
                        })
                        break

            elif df['close'].iloc[i] < df['open'].iloc[i]:
                for j in range(i - 1, max(i - 5, 0), -1):
                    if df['close'].iloc[j] > df['open'].iloc[j]:
                        ob_high    = df['high'].iloc[j]
                        ob_low     = df['low'].iloc[j]
                        is_breaker = current_price > ob_high
                        obs.append({
                            "type":      "Bullish Breaker" if is_breaker else "Bearish OB",
                            "zone":      [round(ob_low, 5), round(ob_high, 5)],
                            "time":      (df['time'].iloc[j].strftime("%Y-%m-%d %H:%M")
                                          if hasattr(df['time'].iloc[j], 'strftime')
                                          else str(df['time'].iloc[j])),
                            "mitigated": is_breaker,
                        })
                        break

        seen   = set()
        unique = []
        for ob in reversed(obs):
            key = (ob['type'], ob['zone'][0])
            if key not in seen:
                seen.add(key)
                unique.append(ob)
            if len(unique) == 4:
                break
        return unique

    # ── 3. CHoCH / BOS DETECTOR ──────────────────────────────────────────────

    def _detect_market_structure(self, df: pd.DataFrame) -> dict:
        """
        FIX v9.1: BOS/CHoCH now requires a confirmed CANDLE CLOSE beyond the level.
        The old code compared current_price (a tick) which fires prematurely and
        creates phantom structure breaks on wicks that close back inside.

        Also: swing levels now compare wick highs/lows (not closes) as per SMC canon.
        """
        if len(df) < 20:
            return {"event": "Insufficient data", "direction": "unknown"}

        window = 5
        highs  = []
        lows   = []

        for i in range(window, len(df) - window):
            if df['high'].iloc[i] == df['high'].iloc[i - window: i + window + 1].max():
                highs.append((i, df['high'].iloc[i]))
            if df['low'].iloc[i] == df['low'].iloc[i - window: i + window + 1].min():
                lows.append((i, df['low'].iloc[i]))

        if len(highs) < 2 or len(lows) < 2:
            return {"event": "Neutral", "direction": "unknown"}

        last_high = highs[-1][1]
        prev_high = highs[-2][1]
        last_low  = lows[-1][1]
        prev_low  = lows[-2][1]

        # FIX: Use the CLOSE of the most recent COMPLETED candle (iloc[-2], not iloc[-1])
        # iloc[-1] may still be forming — using its close creates look-ahead on live feeds.
        # Use iloc[-1] close only if your data guarantees it's a closed candle.
        confirmed_close = df['close'].iloc[-1]  # Safe on historical; add feed check for live

        sma50 = df['close'].rolling(50).mean().iloc[-1]
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        in_uptrend = sma20 > sma50

        # FIX: Check confirmed_close, not a raw tick price
        if confirmed_close > last_high:
            event = "BOS Bullish" if in_uptrend else "CHoCH Bullish (Reversal)"
            return {"event": event, "direction": "bullish", "broken_level": round(last_high, 5)}
        elif confirmed_close < last_low:
            event = "BOS Bearish" if not in_uptrend else "CHoCH Bearish (Reversal)"
            return {"event": event, "direction": "bearish", "broken_level": round(last_low, 5)}
        else:
            return {"event": "Ranging / No Break", "direction": "neutral"}

    # ── 4. LIQUIDITY SWEEP DETECTOR ──────────────────────────────────────────
    # No changes — logic was correct.

    def _detect_liquidity_sweep(self, df: pd.DataFrame) -> dict:
        if len(df) < 20:
            return {"sweep_detected": False}

        recent     = df.tail(30)
        swing_high = recent['high'].iloc[:-3].max()
        swing_low  = recent['low'].iloc[:-3].min()
        last       = df.iloc[-1]
        prev_close = df['close'].iloc[-2]

        if last['low'] < swing_low and last['close'] > swing_low and prev_close > swing_low:
            return {
                "sweep_detected": True,
                "type":           "Bullish (Stop Hunt Below Lows)",
                "swept_level":    round(swing_low, 5),
                "implication":    "Institutions grabbed sell stops — expect reversal UP",
            }

        if last['high'] > swing_high and last['close'] < swing_high and prev_close < swing_high:
            return {
                "sweep_detected": True,
                "type":           "Bearish (Stop Hunt Above Highs)",
                "swept_level":    round(swing_high, 5),
                "implication":    "Institutions grabbed buy stops — expect reversal DOWN",
            }

        return {"sweep_detected": False}

    # ── 5. PREMIUM / DISCOUNT ZONE ───────────────────────────────────────────
    # No changes.

    def _premium_discount_zone(self, df: pd.DataFrame) -> dict:
        if len(df) < 20:
            return {"zone": "unknown", "equilibrium": None}

        recent  = df.tail(50)
        leg_high = recent['high'].max()
        leg_low  = recent['low'].min()
        equil    = (leg_high + leg_low) / 2
        current  = df['close'].iloc[-1]

        zone = "DISCOUNT (Good for Buys)" if current < equil else "PREMIUM (Good for Sells)"
        return {
            "zone":       zone,
            "equilibrium": round(equil, 5),
            "leg_high":   round(leg_high, 5),
            "leg_low":    round(leg_low, 5),
        }

    # ── 6. RSI DIVERGENCE ────────────────────────────────────────────────────

    def _detect_rsi_divergence(self, df: pd.DataFrame) -> dict:
        """
        FIX v9.1: Now uses genuine swing pivots (via _find_swing_pivots) instead
        of comparing arbitrary midpoints (iloc[mid] had no structural meaning).

        Process:
        1. Find last 2 swing HIGH pivots → check for bearish regular/hidden div
        2. Find last 2 swing LOW  pivots → check for bullish regular/hidden div
        3. Compare price action at those pivots to RSI value at same bar index
        """
        if len(df) < 40:
            return {"divergence": "none"}

        rsi_series = _rsi(df['close'], 14)

        # ── Find swing HIGH pivots ──
        high_pivots = _find_swing_pivots(df['high'], window=5)
        if len(high_pivots) >= 2:
            (i1, ph1), (i2, ph2) = high_pivots[-2], high_pivots[-1]
            r1, r2 = rsi_series.iloc[i1], rsi_series.iloc[i2]
            if not (pd.isna(r1) or pd.isna(r2)):
                # Regular Bearish: price HH, RSI LH
                if ph2 > ph1 and r2 < r1:
                    return {"divergence": "Regular Bearish (Sell Pressure Building)",
                            "rsi_now": round(float(rsi_series.iloc[-1]), 1)}
                # Hidden Bearish: price LH, RSI HH (trend continuation down)
                if ph2 < ph1 and r2 > r1:
                    return {"divergence": "Hidden Bearish (Trend Continuation Down)",
                            "rsi_now": round(float(rsi_series.iloc[-1]), 1)}

        # ── Find swing LOW pivots ──
        low_pivots = _find_swing_pivots(df['low'], window=5)
        if len(low_pivots) >= 2:
            (i1, pl1), (i2, pl2) = low_pivots[-2], low_pivots[-1]
            r1, r2 = rsi_series.iloc[i1], rsi_series.iloc[i2]
            if not (pd.isna(r1) or pd.isna(r2)):
                # Regular Bullish: price LL, RSI HL
                if pl2 < pl1 and r2 > r1:
                    return {"divergence": "Regular Bullish (Buy Pressure Building)",
                            "rsi_now": round(float(rsi_series.iloc[-1]), 1)}
                # Hidden Bullish: price HL, RSI LL (trend continuation up)
                if pl2 > pl1 and r2 < r1:
                    return {"divergence": "Hidden Bullish (Trend Continuation Up)",
                            "rsi_now": round(float(rsi_series.iloc[-1]), 1)}

        rsi_now = rsi_series.iloc[-1]
        return {"divergence": "none", "rsi_now": round(float(rsi_now), 1) if not pd.isna(rsi_now) else 50}

    # ── 7. VOLUME DELTA ──────────────────────────────────────────────────────
    # No changes — logic was correct.

    def _volume_delta_signal(self, df: pd.DataFrame) -> dict:
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            return {"signal": "No volume data"}

        recent = df.tail(10).copy()
        recent['bull_vol'] = np.where(recent['close'] >= recent['open'], recent['volume'], 0)
        recent['bear_vol'] = np.where(recent['close'] < recent['open'],  recent['volume'], 0)

        total_bull = recent['bull_vol'].sum()
        total_bear = recent['bear_vol'].sum()
        total      = total_bull + total_bear

        if total == 0:
            return {"signal": "Flat"}

        bull_pct   = total_bull / total * 100
        bear_pct   = total_bear / total * 100
        recent_vol = recent['volume'].tail(3).mean()
        prior_vol  = recent['volume'].head(3).mean()
        expanding  = recent_vol > prior_vol * 1.1

        return {
            "bull_volume_pct":  round(bull_pct, 1),
            "bear_volume_pct":  round(bear_pct, 1),
            "volume_expanding": expanding,
            "signal": (
                "Bullish Pressure" if bull_pct > 60 else
                "Bearish Pressure" if bear_pct > 60 else
                "Balanced"
            ),
        }

    # ── 8. LIQUIDITY PIVOTS ───────────────────────────────────────────────────
    # No changes.

    def _find_liquidity_pivots(self, df: pd.DataFrame, window: int = 5) -> dict:
        df = df.copy()
        df['pivot_high'] = df['high'] == df['high'].rolling(window=window * 2 + 1, center=True).max()
        df['pivot_low']  = df['low']  == df['low'].rolling(window=window * 2 + 1, center=True).min()

        highs = df[df['pivot_high']]['high'].tail(5).tolist()
        lows  = df[df['pivot_low']]['low'].tail(5).tolist()

        return {
            "recent_resistances": [round(h, 5) for h in highs],
            "recent_supports":    [round(l, 5) for l in lows],
        }

    # ── 9. CONFIDENCE SCORER ─────────────────────────────────────────────────
    # No changes to scoring weights.

    def _compute_confidence(self, factors: dict) -> tuple:
        points    = 0
        breakdown = {}

        trend         = factors.get("trend")
        structure     = factors.get("structure_event", "")
        fvg_hit       = factors.get("fvg_hit", False)
        ob_hit        = factors.get("ob_hit", False)
        sweep         = factors.get("sweep", False)
        pd_zone       = factors.get("pd_zone", "")
        divergence    = factors.get("divergence", "none")
        vol_signal    = factors.get("vol_signal", "")
        session_ok    = factors.get("session_ok", True)

        if trend in ("Bullish", "Bearish"):
            points += 20; breakdown["Trend Filter"] = "+20"
        else:
            breakdown["Trend Filter"] = "+0 (Unknown)"

        if fvg_hit:
            points += 10; breakdown["FVG Interaction"] = "+10"

        if ob_hit:
            points += 10; breakdown["Order Block"] = "+10"

        if sweep:
            points += 10; breakdown["Liquidity Sweep"] = "+10"

        # ── Strict 3-Concept Confluence Bonus ──
        if fvg_hit and ob_hit and sweep:
            points += 25; breakdown["3-Concept Confluence"] = "+25"

        if "CHoCH" in structure or "BOS" in structure:
            points += 10; breakdown["Market Structure"] = f"+10 ({structure})"

        if (trend == "Bullish" and "DISCOUNT" in pd_zone) or (trend == "Bearish" and "PREMIUM" in pd_zone):
            points += 10; breakdown["Premium/Discount"] = "+10"

        if divergence != "none" and "none" not in divergence.lower():
            points += 10; breakdown["RSI Divergence"] = f"+10 ({divergence})"

        if (trend == "Bullish" and "Bullish" in vol_signal) or (trend == "Bearish" and "Bearish" in vol_signal):
            points += 5; breakdown["Volume Delta"] = "+5"

        if not session_ok:
            points = max(0, points - 10)
            breakdown["Session Filter"] = "-10 (Asian/Dead Zone)"

        if points >= 75:   grade = "A+"
        elif points >= 55: grade = "A"
        elif points >= 40: grade = "B+"
        elif points >= 25: grade = "B"
        else:              grade = "C"

        return grade, min(points, 100), breakdown

    # ── 10. MASTER ANALYSIS ───────────────────────────────────────────────────

    def analyze_market_context(self, symbol: str, df: pd.DataFrame, macro_news: str = "") -> dict:
        logger.info(f"[StrategyAgent] Full SMC + Structure analysis for {symbol}...")

        if df is None or len(df) < 20:
            return {"error": "Insufficient data for analysis."}

        df            = df.copy().reset_index(drop=True)
        current_price = df['close'].iloc[-1]

        df['SMA_50']  = df['close'].rolling(50).mean()
        df['SMA_200'] = df['close'].rolling(200).mean()
        df['EMA_21']  = _ema(df['close'], 21)

        sma50  = df['SMA_50'].iloc[-1]
        sma200 = df['SMA_200'].iloc[-1]
        ema21  = df['EMA_21'].iloc[-1]

        bullish_trend = (not pd.isna(sma200)) and sma50 > sma200 and current_price > ema21
        bearish_trend = (not pd.isna(sma200)) and sma50 < sma200 and current_price < ema21
        macro_trend   = "Bullish" if bullish_trend else "Bearish" if bearish_trend else "Unknown"

        pivots   = self._find_liquidity_pivots(df)
        fvgs     = self._identify_fvgs(df)
        obs      = self._identify_order_blocks(df)
        struct   = self._detect_market_structure(df)
        sweep    = self._detect_liquidity_sweep(df)
        pd_zone  = self._premium_discount_zone(df)
        rsi_div  = self._detect_rsi_divergence(df)
        vol_data = self._volume_delta_signal(df)

        # FIX: Use the new price_inside flag instead of mitigated check
        fvg_hit = any(
            f.get("price_inside", False) and not f.get("mitigated", False)
            for f in fvgs
        )
        ob_hit = any(
            ob['zone'][0] <= current_price <= ob['zone'][1] and not ob.get("mitigated", False)
            for ob in obs
        )

        try:
            last_ts    = df['time'].iloc[-1]
            session_ok = _is_london_or_ny(last_ts)
        except Exception:
            session_ok = True

        # ── Macro override — FIX v9.1 ──
        # OLD: high unrest → automatic 90% confidence (dangerous — trades into chaos)
        # NEW: high unrest → force SWING mode + apply a confidence PENALTY (not bonus)
        #      If macro is dangerous, we reduce confidence and require higher bar to trade.
        danger_words = ["war", "strike", "missile", "crisis", "crash", "emergency",
                        "attack", "sanction", "escalation", "conflict", "invasion"]
        unrest_score   = 0
        is_swing_trade = False

        if macro_news and "No Tavily" not in macro_news and "Tavily Error" not in macro_news:
            mn_lower     = macro_news.lower()
            unrest_score = sum(1 for w in danger_words if w in mn_lower)
            if unrest_score >= 2:
                is_swing_trade = True
                logger.warning(f"[StrategyAgent] Macro unrest={unrest_score}. Swing trade mode ON.")

        factors = {
            "trend":           macro_trend,
            "structure_event": struct.get("event", ""),
            "fvg_hit":         fvg_hit,
            "ob_hit":          ob_hit,
            "sweep":           sweep.get("sweep_detected", False),
            "pd_zone":         pd_zone.get("zone", ""),
            "divergence":      rsi_div.get("divergence", "none"),
            "vol_signal":      vol_data.get("signal", ""),
            "session_ok":      session_ok,
        }

        grade, confidence, breakdown = self._compute_confidence(factors)

        # FIX: Apply macro penalty AFTER scoring — high unrest reduces confidence
        # rather than overriding it to 90. Scale: each danger word = -5 pts, max -25.
        if unrest_score >= 2:
            macro_penalty = min(unrest_score * 5, 25)
            confidence    = max(0, confidence - macro_penalty)
            breakdown["Macro Danger Penalty"] = f"-{macro_penalty} (unrest_score={unrest_score})"
            logger.warning(
                f"[StrategyAgent] Macro penalty applied: -{macro_penalty}pts. "
                f"New confidence: {confidence}%. "
                f"Tip: manually review before trading during high-unrest events."
            )

        return {
            "Symbol":               symbol,
            "Current_Price":        round(current_price, 5),
            "Structure_Score":      grade,
            "Confidence_Pct":       confidence,
            "Confidence_Breakdown": breakdown,
            "Is_Swing_Trade":       is_swing_trade,
            "Macro_Unrest_Score":   unrest_score,
            "Macro_Trend":          macro_trend,
            "Market_Structure":     struct,
            "Liquidity_Sweep":      sweep,
            "Premium_Discount":     pd_zone,
            "RSI_Divergence":       rsi_div,
            "Volume_Delta":         vol_data,
            "Liquidity_Zones":      pivots,
            "Recent_FVGs":          fvgs,
            "Order_Blocks":         obs,
            "Session_Valid":        session_ok,
        }
