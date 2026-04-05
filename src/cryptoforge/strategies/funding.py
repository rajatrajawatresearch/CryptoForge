"""Funding Rate Harvester — delta-neutral income from funding payments."""

import logging
import time
from dataclasses import dataclass

from ..exchange.client import DeltaClient

logger = logging.getLogger("cryptoforge.funding")


@dataclass(slots=True)
class FundingPosition:
    symbol: str
    product_id: int
    side: str           # "short" (we short perps when funding is positive)
    size: float
    entry_price: float
    funding_collected: float
    entry_time: float
    last_funding_time: float


class FundingRateHarvester:
    """Collects funding payments by holding delta-neutral positions.

    When funding rate is highly positive: longs pay shorts.
    → Short the perpetual, earn funding every 8 hours.

    When funding rate is highly negative: shorts pay longs.
    → Long the perpetual, earn funding every 8 hours.

    Delta-neutral: the position doesn't care about price direction.
    Profit comes purely from funding payments.
    """

    def __init__(self, client: DeltaClient, min_annualized_rate: float = 20.0):
        self.client = client
        self.min_annualized_rate = min_annualized_rate
        self.positions: dict[str, FundingPosition] = {}
        self.total_funding_collected: float = 0.0
        self._funding_history: list[dict] = []

    def evaluate_funding(self, symbol: str, product_id: int, funding_rate: float, price: float) -> str | None:
        """Evaluate if funding rate warrants a position.

        Args:
            symbol: Trading pair symbol
            product_id: Delta Exchange product ID
            funding_rate: Current funding rate (per 8h, as decimal e.g., 0.001 = 0.1%)
            price: Current mark price

        Returns:
            "enter_short" if should short (positive funding),
            "enter_long" if should long (negative funding),
            "exit" if should close existing position,
            None if no action needed.
        """
        # Annualized rate = funding_rate × 3 payments/day × 365 days × 100%
        annualized = abs(funding_rate) * 3 * 365 * 100

        # Log all funding data
        self._funding_history.append({
            "symbol": symbol, "rate": funding_rate,
            "annualized": annualized, "time": time.time(),
        })

        # Check existing position
        if symbol in self.positions:
            # Exit if funding rate normalized
            if annualized < self.min_annualized_rate * 0.5:
                logger.info("Funding normalized for %s (%.1f%% ann.) — exit signal", symbol, annualized)
                return "exit"
            return None

        # Enter new position
        if annualized >= self.min_annualized_rate:
            if funding_rate > 0:
                logger.info("High positive funding on %s: %.4f (%.1f%% ann.) — SHORT to collect",
                             symbol, funding_rate, annualized)
                return "enter_short"
            else:
                logger.info("High negative funding on %s: %.4f (%.1f%% ann.) — LONG to collect",
                             symbol, funding_rate, annualized)
                return "enter_long"

        return None

    def open_position(self, symbol: str, product_id: int, side: str, size: float, price: float) -> None:
        """Record an opened funding harvest position."""
        self.positions[symbol] = FundingPosition(
            symbol=symbol, product_id=product_id, side=side,
            size=size, entry_price=price, funding_collected=0.0,
            entry_time=time.time(), last_funding_time=time.time(),
        )
        logger.info("Funding position opened: %s %s %s @ %.2f", side, size, symbol, price)

    def record_funding_payment(self, symbol: str, amount: float) -> None:
        """Record a funding payment received."""
        if symbol in self.positions:
            self.positions[symbol].funding_collected += amount
            self.positions[symbol].last_funding_time = time.time()
            self.total_funding_collected += amount
            logger.info("Funding received: %s ₹%.4f (total: ₹%.4f)", symbol, amount, self.total_funding_collected)

    def close_position(self, symbol: str) -> float:
        """Close a funding harvest position. Returns total funding collected."""
        pos = self.positions.pop(symbol, None)
        if not pos:
            return 0.0
        logger.info("Funding position closed: %s | Collected: ₹%.4f", symbol, pos.funding_collected)
        return pos.funding_collected

    def get_status(self) -> dict:
        return {
            "active_positions": len(self.positions),
            "symbols": list(self.positions.keys()),
            "total_funding_collected": round(self.total_funding_collected, 4),
            "recent_rates": [
                {"symbol": h["symbol"], "annualized": f"{h['annualized']:.1f}%"}
                for h in self._funding_history[-5:]
            ],
        }
