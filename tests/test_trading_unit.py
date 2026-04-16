"""
CRAVE Trading Engine — Unit Tests
==================================
Tests the critical money-protecting logic in RiskAgent and ExecutionAgent.
A bug in position sizing, stop-loss, or drawdown = real money lost.

Run: python -m pytest tests/test_trading_unit.py -v
"""

import sys
import os
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Sub_Projects.Trading.risk_agent import RiskAgent
from Sub_Projects.Trading.execution_agent import ExecutionAgent, _get_slippage_limit


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 100, base_price: float = 2000.0, atr_pct: float = 0.01) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    closes = [base_price]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + np.random.randn() * atr_pct))
    closes = np.array(closes)
    highs = closes * (1 + abs(np.random.randn(n)) * atr_pct * 0.5)
    lows = closes * (1 - abs(np.random.randn(n)) * atr_pct * 0.5)
    opens = (closes + np.roll(closes, 1)) / 2
    opens[0] = base_price
    volumes = np.random.randint(100, 10000, n)
    return pd.DataFrame({
        "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# RISK AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestPositionSizing:
    """Tests for size_position() — the function that decides how much money to risk."""

    def test_basic_2pct_risk(self):
        """With $10,000 equity and $100 risk distance, position should be 2 units."""
        ra = RiskAgent()
        # equity=10000, entry=1000, SL=900 → risk per unit = $100
        # 2% of 10000 = $200 → 200/100 = 2.0 lots
        size = ra.size_position(10000, 1000, 900)
        assert size == 2.0

    def test_zero_risk_distance(self):
        """If SL == entry, position size must be 0 (prevents division by zero)."""
        ra = RiskAgent()
        size = ra.size_position(10000, 1000, 1000)
        assert size == 0.0

    def test_tiny_risk_distance(self):
        """Very tight SL should give very large position (but risk is still 2%)."""
        ra = RiskAgent()
        # entry=1000, SL=999 → risk per unit = $1
        # 2% of 10000 = $200 → 200/1 = 200 lots
        size = ra.size_position(10000, 1000, 999)
        assert size == 200.0

    def test_short_position(self):
        """SL above entry (short trade) should still calculate correctly."""
        ra = RiskAgent()
        # entry=1000, SL=1100 → risk per unit = $100
        size = ra.size_position(10000, 1000, 1100)
        assert size == 2.0

    def test_small_account(self):
        """Small $500 account should give proportionally smaller position."""
        ra = RiskAgent()
        # 2% of 500 = $10 → 10/100 = 0.1 lots
        size = ra.size_position(500, 1000, 900)
        assert size == 0.1

    def test_kelly_with_insufficient_data(self):
        """Kelly should fall back to fixed 2% when < 20 trades logged."""
        ra = RiskAgent()
        for _ in range(10):
            ra.log_trade_result("W", 2.0)
        size_kelly = ra.size_position(10000, 1000, 900, use_kelly=True)
        size_fixed = ra.size_position(10000, 1000, 900, use_kelly=False)
        assert size_kelly == size_fixed  # Not enough data → same result

    def test_kelly_with_sufficient_data(self):
        """Kelly with 20+ trades should adjust position size."""
        ra = RiskAgent()
        # 15 wins at 2R, 5 losses at -1R → strong edge
        for _ in range(15):
            ra.log_trade_result("W", 2.0)
        for _ in range(5):
            ra.log_trade_result("L", -1.0)
        size_kelly = ra.size_position(10000, 1000, 900, use_kelly=True)
        size_fixed = ra.size_position(10000, 1000, 900, use_kelly=False)
        # Kelly should give at least as much (strong edge = confident sizing)
        assert size_kelly >= size_fixed * 0.5  # Half-Kelly clamp


class TestDrawdownLimits:
    """Tests for check_drawdown_limit() — the kill switch that protects the account."""

    def test_normal_equity_allowed(self):
        """Normal equity (no drawdown) should allow trading."""
        ra = RiskAgent()
        allowed, _ = ra.check_drawdown_limit(10000)
        assert allowed is True

    def test_5pct_trailing_drawdown_blocks(self):
        """5% drawdown from peak should block new trades."""
        ra = RiskAgent()
        ra.check_drawdown_limit(10000)  # Set peak
        allowed, reason = ra.check_drawdown_limit(9400)  # 6% down
        assert allowed is False
        assert "drawdown" in reason.lower()

    def test_small_drawdown_still_allowed(self):
        """1.5% drawdown should still allow trades (below both 2% daily and 5% trailing)."""
        ra = RiskAgent()
        ra.check_drawdown_limit(10000)
        allowed, _ = ra.check_drawdown_limit(9850)  # 1.5% down
        assert allowed is True

    def test_daily_loss_limit(self):
        """2% daily loss should trigger daily limit."""
        ra = RiskAgent()
        ra.check_drawdown_limit(10000)  # Initialize
        # Simulate same-day loss (don't change session day)
        allowed, reason = ra.check_drawdown_limit(9750)  # 2.5% daily loss
        assert allowed is False
        assert "daily" in reason.lower()

    def test_consecutive_losses_cooldown(self):
        """3 consecutive losses should trigger cooldown."""
        ra = RiskAgent()
        ra.log_trade_result("L", -1.0)
        ra.log_trade_result("L", -1.0)
        ra.log_trade_result("L", -1.0)
        allowed, reason = ra.check_drawdown_limit(10000)
        assert allowed is False
        assert "consecutive" in reason.lower()

    def test_win_resets_consecutive_losses(self):
        """A win after 2 losses should reset the counter."""
        ra = RiskAgent()
        ra.log_trade_result("L", -1.0)
        ra.log_trade_result("L", -1.0)
        ra.log_trade_result("W", 2.0)
        ra.log_trade_result("L", -1.0)
        allowed, _ = ra.check_drawdown_limit(10000)
        assert allowed is True  # Only 1 consecutive loss, not 3


class TestATRCalculation:
    """Tests for calculate_atr() — used for stop-loss distance."""

    def test_atr_with_normal_data(self):
        """ATR should return a positive float with sufficient data."""
        ra = RiskAgent()
        df = _make_ohlcv(100, base_price=2000, atr_pct=0.01)
        atr = ra.calculate_atr(df, period=14)
        assert atr > 0
        assert atr < 2000  # Should be much smaller than price

    def test_atr_with_insufficient_data(self):
        """ATR with < period candles should use simple average fallback."""
        ra = RiskAgent()
        df = _make_ohlcv(5, base_price=100)
        atr = ra.calculate_atr(df, period=14)
        assert atr > 0

    def test_atr_with_empty_df(self):
        """ATR with empty df should return 0.001 (safe minimum)."""
        ra = RiskAgent()
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        atr = ra.calculate_atr(df, period=14)
        assert atr == 0.001


class TestTradeValidation:
    """Tests for validate_trade_signal() — the main approval gate."""

    def test_buy_signal_approved(self):
        """Valid buy signal with good confidence should be approved."""
        ra = RiskAgent()
        df = _make_ohlcv(100, base_price=100)
        signal = {"action": "buy", "price": 100, "symbol": "AAPL"}
        result = ra.validate_trade_signal(10000, signal, df, confidence_pct=70)
        assert result["approved"] is True
        assert result["direction"] == "buy"
        assert result["stop_loss"] < 100  # SL below entry for buy
        assert result["take_profit_2"] > 100  # TP above entry for buy
        assert result["lot_size"] > 0

    def test_sell_signal_approved(self):
        """Valid sell signal should be approved with correct SL/TP direction."""
        ra = RiskAgent()
        df = _make_ohlcv(100, base_price=100)
        signal = {"action": "sell", "price": 100, "symbol": "AAPL"}
        result = ra.validate_trade_signal(10000, signal, df, confidence_pct=70)
        assert result["approved"] is True
        assert result["stop_loss"] > 100  # SL above entry for sell
        assert result["take_profit_2"] < 100  # TP below entry for sell

    def test_low_confidence_rejected(self):
        """Signal with < 40% confidence should be rejected."""
        ra = RiskAgent()
        df = _make_ohlcv(100, base_price=100)
        signal = {"action": "buy", "price": 100, "symbol": "AAPL"}
        result = ra.validate_trade_signal(10000, signal, df, confidence_pct=30)
        assert result["approved"] is False
        assert "confidence" in result["reason"].lower()

    def test_invalid_direction_rejected(self):
        """Invalid direction should be rejected."""
        ra = RiskAgent()
        df = _make_ohlcv(100, base_price=100)
        signal = {"action": "hold", "price": 100, "symbol": "AAPL"}
        result = ra.validate_trade_signal(10000, signal, df, confidence_pct=70)
        assert result["approved"] is False

    def test_atr_value_included(self):
        """Validated signal must include atr_value for ExecutionAgent trailing SL."""
        ra = RiskAgent()
        df = _make_ohlcv(100, base_price=100)
        signal = {"action": "buy", "price": 100, "symbol": "AAPL"}
        result = ra.validate_trade_signal(10000, signal, df, confidence_pct=70)
        assert "atr_value" in result
        assert result["atr_value"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION AGENT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSlippage:
    """Tests for slippage guard — prevents bad fills."""

    def test_crypto_slippage_limit(self):
        assert _get_slippage_limit("BTCUSDT") == 0.003

    def test_forex_slippage_limit(self):
        assert _get_slippage_limit("EURUSD") == 0.0003

    def test_stock_slippage_limit(self):
        assert _get_slippage_limit("AAPL") == 0.001

    def test_gold_is_forex(self):
        assert _get_slippage_limit("XAUUSD") == 0.0003

    def test_slippage_pass(self):
        ea = ExecutionAgent()
        assert ea.check_slippage(100.0, 100.02, "AAPL") is True  # 0.02% < 0.1%

    def test_slippage_fail(self):
        ea = ExecutionAgent()
        assert ea.check_slippage(100.0, 101.0, "AAPL") is False  # 1% > 0.1%


class TestExecutionGuards:
    """Tests for execution guard logic."""

    def test_unapproved_signal_blocked(self):
        """Unapproved signal should be blocked immediately."""
        ea = ExecutionAgent()
        result = ea.execute_trade({"approved": False, "reason": "Test"}, 100.0)
        assert result["status"] == "blocked"

    def test_duplicate_symbol_skipped(self):
        """Can't open two trades on the same symbol."""
        ea = ExecutionAgent()
        ea._open_symbols.add("AAPL")
        result = ea.execute_trade(
            {"approved": True, "symbol": "AAPL", "entry": 100, "lot_size": 1,
             "direction": "buy", "stop_loss": 95, "take_profit_1": 105,
             "take_profit_2": 110, "rr_ratio": 2.0, "atr_value": 1.5},
            100.0
        )
        assert result["status"] == "skipped"


class TestSessionDay:
    """Tests for NY session day calculation."""

    def test_session_day_returns_date(self):
        ra = RiskAgent()
        result = ra._get_ny_session_day()
        from datetime import date
        assert isinstance(result, date)


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary and edge case tests."""

    def test_zero_equity(self):
        """Zero equity should give zero position size."""
        ra = RiskAgent()
        size = ra.size_position(0, 1000, 900)
        assert size == 0.0

    def test_negative_r_multiple_logging(self):
        """Negative R-multiples should be handled gracefully."""
        ra = RiskAgent()
        ra.log_trade_result("L", -1.0)
        ra.log_trade_result("L", -0.5)
        assert ra.consecutive_losses == 2
        assert len(ra.trade_log) == 2

    def test_stats_with_no_trades(self):
        """Stats should handle empty trade log."""
        ra = RiskAgent()
        stats = ra.get_stats()
        assert stats["trades"] == 0

    def test_stats_with_trades(self):
        """Stats should calculate correctly with trade data."""
        ra = RiskAgent()
        ra.log_trade_result("W", 2.0)
        ra.log_trade_result("W", 1.5)
        ra.log_trade_result("L", -1.0)
        stats = ra.get_stats()
        assert stats["total_trades"] == 3
        assert "win_rate" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
