"""
tests/test_execution.py
─────────────────────────────────────────────────────────────────────────────
Run with:  pytest tests/test_execution.py -v

Tests for both sizing.py (pure functions) and oms.py (stateful class).
"""

import pytest
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from framework.execution.sizing import fixed_fraction, kelly, vol_target
from framework.execution.oms import OMS, Order, Position


# ═════════════════════════════════════════════════════════════════════════════
# SIZING TESTS
# ═════════════════════════════════════════════════════════════════════════════

# ─── FIXED FRACTION ───────────────────────────────────────────────────────────

def test_fixed_fraction_known_value():
    """
    £100k capital, 1% risk, 2% stop, £50 price.
    risk = £1,000. stop = £1.00/share. → 1,000 shares.
    """
    result = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.02, price=50.0)
    assert result == 1000

def test_fixed_fraction_scales_with_capital():
    """Doubling capital should double position size."""
    s1 = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.02, price=50.0)
    s2 = fixed_fraction(capital=200_000, risk_pct=0.01, stop_pct=0.02, price=50.0)
    assert s2 == 2 * s1

def test_fixed_fraction_zero_stop_returns_zero():
    """Zero stop distance → undefined → return 0 (avoid division by zero)."""
    result = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.0, price=50.0)
    assert result == 0

def test_fixed_fraction_zero_price_returns_zero():
    """Zero price → undefined → return 0."""
    result = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.02, price=0.0)
    assert result == 0

def test_fixed_fraction_returns_integer():
    """Position size must be a whole number of shares."""
    result = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.03, price=47.0)
    assert isinstance(result, int)

def test_fixed_fraction_wider_stop_smaller_position():
    """Wider stop (more risk per share) → fewer shares for same risk amount."""
    tight = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.01, price=50.0)
    wide  = fixed_fraction(capital=100_000, risk_pct=0.01, stop_pct=0.02, price=50.0)
    assert tight > wide, "Tighter stop should allow more shares"


# ─── KELLY CRITERION ──────────────────────────────────────────────────────────

def test_kelly_positive_for_good_edge():
    """A strategy with 60% win rate and 1:1 R/R should have positive Kelly."""
    result = kelly(win_rate=0.6, avg_win=0.02, avg_loss=0.02)
    assert result > 0, "Should have positive Kelly with positive expectancy"

def test_kelly_zero_for_breakeven():
    """50% win rate with equal avg win and loss → breakeven → Kelly ≈ 0."""
    result = kelly(win_rate=0.5, avg_win=0.01, avg_loss=0.01)
    assert abs(result) < 1e-10, f"Expected ~0.0, got {result}"

def test_kelly_negative_for_no_edge():
    """40% win rate with equal R/R → negative expectancy → Kelly < 0."""
    result = kelly(win_rate=0.4, avg_win=0.01, avg_loss=0.01)
    assert result < 0, "Negative edge should produce negative Kelly"

def test_kelly_zero_avg_win_returns_zero():
    """Zero avg win → undefined → return 0."""
    result = kelly(win_rate=0.6, avg_win=0.0, avg_loss=0.01)
    assert result == 0.0

def test_kelly_returns_float():
    result = kelly(win_rate=0.55, avg_win=0.015, avg_loss=0.01)
    assert isinstance(result, float)

def test_kelly_higher_win_rate_bigger_bet():
    """Better win rate with same R/R → larger Kelly fraction."""
    k1 = kelly(win_rate=0.55, avg_win=0.02, avg_loss=0.02)
    k2 = kelly(win_rate=0.65, avg_win=0.02, avg_loss=0.02)
    assert k2 > k1, "Better win rate should produce larger Kelly"


# ─── VOLATILITY TARGETING ─────────────────────────────────────────────────────

def test_vol_target_known_value():
    """
    £100k capital, 10% target vol, 20% asset vol, £50 price.
    position_value = £100k × (0.10/0.20) = £50k.
    shares = £50k / £50 = 1,000.
    """
    result = vol_target(capital=100_000, target_vol=0.10, asset_vol=0.20, price=50.0)
    assert result == 1000

def test_vol_target_higher_vol_smaller_position():
    """More volatile asset → smaller position for same target vol."""
    low_vol  = vol_target(capital=100_000, target_vol=0.10, asset_vol=0.10, price=50.0)
    high_vol = vol_target(capital=100_000, target_vol=0.10, asset_vol=0.20, price=50.0)
    assert low_vol > high_vol, "Lower vol asset should get larger position"

def test_vol_target_zero_asset_vol_returns_zero():
    """Zero asset vol → undefined → return 0."""
    result = vol_target(capital=100_000, target_vol=0.10, asset_vol=0.0, price=50.0)
    assert result == 0

def test_vol_target_returns_integer():
    result = vol_target(capital=100_000, target_vol=0.10, asset_vol=0.15, price=50.0)
    assert isinstance(result, int)

def test_vol_target_scales_with_capital():
    """Doubling capital should double the position size."""
    s1 = vol_target(capital=100_000, target_vol=0.10, asset_vol=0.20, price=50.0)
    s2 = vol_target(capital=200_000, target_vol=0.10, asset_vol=0.20, price=50.0)
    assert s2 == 2 * s1


# ═════════════════════════════════════════════════════════════════════════════
# OMS TESTS
# ═════════════════════════════════════════════════════════════════════════════

# ─── INITIAL STATE ────────────────────────────────────────────────────────────

def test_oms_initial_equity_equals_capital():
    """Fresh OMS should have equity == starting capital."""
    oms = OMS(starting_capital=100_000)
    assert oms.equity == 100_000

def test_oms_initial_pnl_is_zero():
    """No trades → all P&L values should be zero."""
    oms = OMS()
    assert oms.realised_pnl    == 0.0
    assert oms.unrealised_pnl  == 0.0
    assert oms.total_pnl       == 0.0

def test_oms_initial_drawdown_is_zero():
    """No trades → no drawdown."""
    oms = OMS()
    assert oms.current_drawdown == 0.0

def test_oms_initial_positions_empty():
    oms = OMS()
    assert len(oms.positions) == 0


# ─── OPEN POSITION ────────────────────────────────────────────────────────────

def test_open_position_appears_in_positions():
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    assert "AAPL" in oms.positions

def test_open_position_unrealised_pnl_zero_at_entry():
    """Immediately after opening, unrealised P&L should be zero."""
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    assert oms.unrealised_pnl == 0.0

def test_open_multiple_positions():
    oms = OMS()
    oms.open_position("AAPL", direction=1,  quantity=100, price=150.0)
    oms.open_position("MSFT", direction=-1, quantity=50,  price=400.0)
    assert len(oms.positions) == 2


# ─── MARK TO MARKET ───────────────────────────────────────────────────────────

def test_mark_to_market_updates_unrealised_pnl():
    """Long position + price rise → positive unrealised P&L."""
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    oms.mark_to_market({"AAPL": 155.0})
    assert oms.unrealised_pnl == pytest.approx(500.0)   # 100 × (155 - 150)

def test_mark_to_market_short_position():
    """Short position + price fall → positive unrealised P&L."""
    oms = OMS()
    oms.open_position("AAPL", direction=-1, quantity=100, price=150.0)
    oms.mark_to_market({"AAPL": 145.0})
    assert oms.unrealised_pnl == pytest.approx(500.0)   # -1 × 100 × (145 - 150) = +500

def test_mark_to_market_long_loss():
    """Long position + price fall → negative unrealised P&L."""
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    oms.mark_to_market({"AAPL": 145.0})
    assert oms.unrealised_pnl == pytest.approx(-500.0)

def test_equity_updates_after_mark_to_market():
    """Equity should reflect unrealised gains."""
    oms = OMS(starting_capital=100_000)
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    oms.mark_to_market({"AAPL": 160.0})
    assert oms.equity == pytest.approx(101_000.0)        # 100k + 100 × £10


# ─── CLOSE POSITION ───────────────────────────────────────────────────────────

def test_close_position_realises_pnl():
    """Closing a winning long trade should produce positive realised P&L."""
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    pnl = oms.close_position("AAPL", price=160.0)
    assert pnl == pytest.approx(1000.0)                  # 100 × £10

def test_close_position_removes_from_positions():
    """Closed position must no longer appear in open positions."""
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    oms.close_position("AAPL", price=160.0)
    assert "AAPL" not in oms.positions

def test_close_short_position_profit():
    """Closing a profitable short (price fell) → positive P&L."""
    oms = OMS()
    oms.open_position("AAPL", direction=-1, quantity=100, price=150.0)
    pnl = oms.close_position("AAPL", price=140.0)
    assert pnl == pytest.approx(1000.0)                  # -1 × 100 × (140-150) = +1000

def test_close_nonexistent_position_returns_zero():
    """Trying to close a position that doesn't exist should return 0, not crash."""
    oms = OMS()
    result = oms.close_position("FAKE", price=100.0)
    assert result == 0.0

def test_realised_pnl_accumulates():
    """Multiple trades should accumulate realised P&L."""
    oms = OMS()
    oms.open_position("A", direction=1, quantity=100, price=100.0)
    oms.close_position("A", price=110.0)   # +1000
    oms.open_position("B", direction=1, quantity=50, price=200.0)
    oms.close_position("B", price=210.0)   # +500
    assert oms.realised_pnl == pytest.approx(1500.0)


# ─── DRAWDOWN TESTS ───────────────────────────────────────────────────────────

def test_drawdown_is_zero_at_peak():
    """At peak equity, drawdown should be exactly 0."""
    oms = OMS(starting_capital=100_000)
    assert oms.current_drawdown == 0.0

def test_drawdown_is_negative_after_loss():
    """After a losing trade, drawdown should be negative."""
    oms = OMS(starting_capital=100_000)
    oms.open_position("X", direction=1, quantity=100, price=100.0)
    oms.close_position("X", price=90.0)   # -1000 loss
    assert oms.current_drawdown < 0.0

def test_drawdown_magnitude():
    """£1,000 loss on £100k capital → -1% drawdown."""
    oms = OMS(starting_capital=100_000)
    oms.open_position("X", direction=1, quantity=100, price=100.0)
    oms.close_position("X", price=90.0)   # -1000
    assert abs(oms.current_drawdown - (-0.01)) < 1e-6

def test_drawdown_recovers_after_profit():
    """After making back a loss, drawdown should return to 0."""
    oms = OMS(starting_capital=100_000)
    oms.open_position("X", direction=1, quantity=100, price=100.0)
    oms.close_position("X", price=90.0)    # -1000 (drawdown)
    oms.open_position("X", direction=1, quantity=100, price=90.0)
    oms.close_position("X", price=100.0)   # +1000 (recover)
    assert oms.current_drawdown == 0.0


# ─── TRADE LOG & SUMMARY ──────────────────────────────────────────────────────

def test_trade_log_empty_initially():
    oms = OMS()
    log = oms.trade_log()
    assert isinstance(log, pd.DataFrame)
    assert len(log) == 0

def test_trade_log_records_closed_trades():
    oms = OMS()
    oms.open_position("AAPL", direction=1, quantity=100, price=150.0)
    oms.close_position("AAPL", price=160.0)
    log = oms.trade_log()
    assert len(log) == 1
    assert log.iloc[0]["ticker"] == "AAPL"
    assert log.iloc[0]["pnl"] == pytest.approx(1000.0)

def test_trade_log_has_correct_columns():
    oms = OMS()
    oms.open_position("X", direction=1, quantity=10, price=100.0)
    oms.close_position("X", price=105.0)
    expected = {"ticker", "direction", "quantity", "entry", "exit", "pnl", "timestamp"}
    assert set(oms.trade_log().columns) == expected

def test_summary_returns_dict():
    oms = OMS()
    assert isinstance(oms.summary(), dict)

def test_summary_has_all_keys():
    oms = OMS()
    expected = {
        "capital", "equity", "realised_pnl", "unrealised_pnl",
        "total_pnl", "current_drawdown", "open_positions",
        "total_trades", "win_rate"
    }
    assert set(oms.summary().keys()) == expected

def test_summary_win_rate_correct():
    """2 wins, 1 loss → win rate = 2/3."""
    oms = OMS()
    oms.open_position("A", direction=1, quantity=1, price=100.0)
    oms.close_position("A", price=110.0)   # win
    oms.open_position("B", direction=1, quantity=1, price=100.0)
    oms.close_position("B", price=110.0)   # win
    oms.open_position("C", direction=1, quantity=1, price=100.0)
    oms.close_position("C", price=90.0)    # loss
    assert oms.summary()["win_rate"] == pytest.approx(2/3, abs=0.001)
