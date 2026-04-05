"""Utility math functions for trading calculations."""


def position_size(capital: float, risk_pct: float, sl_distance: float, price: float) -> float:
    """Compute position size based on risk.

    Args:
        capital: Total available capital
        risk_pct: Max risk per trade (e.g., 2.0 for 2%)
        sl_distance: Stop-loss distance in price units
        price: Current price

    Returns:
        Position size in base currency units.
    """
    if sl_distance <= 0 or price <= 0:
        return 0.0
    risk_amount = capital * (risk_pct / 100.0)
    return round(risk_amount / sl_distance, 6)


def fee_cost(price: float, quantity: float, fee_pct: float = 0.02) -> float:
    """Calculate fee for a trade. fee_pct in percentage (0.02 = 0.02%)."""
    return price * quantity * (fee_pct / 100.0)


def pnl(entry: float, exit_price: float, quantity: float, side: str) -> float:
    """Calculate P&L for a trade."""
    if side.lower() == "buy":
        return (exit_price - entry) * quantity
    return (entry - exit_price) * quantity


def annualized_funding(rate: float) -> float:
    """Convert per-8h funding rate to annualized percentage."""
    return rate * 3 * 365 * 100


def grid_profit_per_cycle(spacing: float, quantity: float, fee_pct: float = 0.02) -> float:
    """Net profit per grid cycle (buy-sell or sell-buy)."""
    gross = spacing * quantity
    fees = fee_cost(spacing, quantity, fee_pct) * 2  # both legs
    return gross - fees
