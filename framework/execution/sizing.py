"""
framework/execution/sizing.py
─────────────────────────────────────────────────────────────────────────────
Position sizing utilities.

Position sizing answers: "Given a signal, how MUCH do I trade?"
It's the most underrated edge in systematic trading — correct sizing turns
a mediocre strategy into a profitable one, and wrong sizing bankrupts
even a great strategy.

Three methods in increasing sophistication:
  1. Fixed Fraction — simple, robust, used by most retail prop traders
  2. Kelly Criterion — mathematically optimal, requires accurate win stats
  3. Volatility Targeting — institutional standard for multi-asset portfolios
"""

import numpy as np


# ─── FIXED FRACTION ───────────────────────────────────────────────────────────

def fixed_fraction(
    capital:   float,
    risk_pct:  float,
    stop_pct:  float,
    price:     float,
) -> int:
    """
    Fixed Fraction — risk a fixed % of capital per trade.

    The default method for prop firm challenges. Simple, transparent,
    and easy to control your maximum daily drawdown with.

    Formula:
        risk_amount    = capital × risk_pct
        stop_distance  = price × stop_pct
        shares         = risk_amount / stop_distance

    Example:
        capital = £100,000, risk 1% per trade = £1,000 risk
        price = £50, stop 2% below entry = £1.00 per share
        → buy 1,000 shares
        If stop is hit: 1,000 × £1.00 loss = £1,000 = exactly 1% of capital ✓

    FTMO rule of thumb:
        With a 10% max drawdown limit, risking 1% per trade means you'd
        need 10 consecutive losses to breach the limit. Manageable.
        Risking 2% → only 5 losses needed. Much riskier.

    Args:
        capital:  total trading capital in £/$
        risk_pct: fraction of capital to risk per trade (e.g. 0.01 = 1%)
        stop_pct: stop loss distance as fraction of price (e.g. 0.02 = 2%)
        price:    current asset price

    Returns:
        Number of shares/units to trade (integer, always floored)
    """
    if stop_pct <= 0 or price <= 0:
        return 0
    risk_amount    = capital * risk_pct
    stop_distance  = price * stop_pct
    return int(risk_amount / stop_distance)


# ─── KELLY CRITERION ──────────────────────────────────────────────────────────

def kelly(
    win_rate: float,
    avg_win:  float,
    avg_loss: float,
) -> float:
    """
    Kelly Criterion — the mathematically optimal fraction to bet.

    Formula:
        f* = W/L - (1-W)/W_avg

    Simplified:
        f* = edge / odds
        where edge = win_rate × avg_win - loss_rate × avg_loss
              odds = avg_win

    Why it matters:
        Kelly maximises the LONG-RUN geometric growth rate of your capital.
        Betting MORE than Kelly causes ruin — bankroll will eventually
        hit zero even with a positive-EV strategy.
        Betting LESS than Kelly is safe but suboptimal.

    Practical usage:
        Almost all professionals use "half Kelly" (f* / 2) because:
        - Win rate and avg P&L estimates are noisy
        - Full Kelly has enormous variance (drawdowns of 50%+ are common)
        - Half Kelly retains ~75% of growth rate at much lower risk

    Interpretation:
        f* > 0  → you have an edge, this is how much to bet
        f* = 0  → breakeven, no edge
        f* < 0  → negative edge, don't trade this strategy

    Args:
        win_rate: fraction of trades that are winners (0.0 to 1.0)
        avg_win:  average P&L on winning trades (positive number, e.g. 0.02)
        avg_loss: average P&L on losing trades (positive number, e.g. 0.01)

    Returns:
        Optimal fraction of capital to wager per trade (float)
    """
    if avg_win <= 0 or avg_loss <= 0:
        return 0.0
    loss_rate = 1.0 - win_rate
    return float(win_rate / avg_loss - loss_rate / avg_win)


# ─── VOLATILITY TARGETING ─────────────────────────────────────────────────────

def vol_target(
    capital:    float,
    target_vol: float,
    asset_vol:  float,
    price:      float,
) -> int:
    """
    Volatility Targeting — size positions to achieve a target portfolio vol.

    The institutional standard. Used by every major CTA fund (Man AHL,
    Winton, Two Sigma). Ensures your portfolio has consistent risk
    regardless of which assets you're trading.

    Formula:
        position_value = capital × (target_vol / asset_vol)
        shares         = position_value / price

    Intuition:
        A 20% vol asset gets HALF the position of a 10% vol asset,
        because it contributes twice the risk per £ invested.
        Your total portfolio volatility is approximately target_vol
        regardless of which assets you hold.

    Example:
        capital = £100,000, target_vol = 10% annual
        Asset A: vol = 20% annual → position = £50,000 → 1,000 shares at £50
        Asset B: vol = 5% annual  → position = £200,000 → 4,000 shares at £50
        (Asset B gets 4× more capital because it's 4× less volatile)

    Args:
        capital:    total trading capital
        target_vol: target annualised portfolio volatility (e.g. 0.10 = 10%)
        asset_vol:  estimated annualised volatility of the asset (e.g. 0.20 = 20%)
        price:      current price of the asset

    Returns:
        Number of shares/units to hold (integer, floored)
    """
    if asset_vol <= 0 or price <= 0:
        return 0
    position_value = capital * (target_vol / asset_vol)
    return int(position_value / price)
