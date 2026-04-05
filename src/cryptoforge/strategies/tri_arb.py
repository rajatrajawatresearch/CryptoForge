"""Triangular Arbitrage — exploit pricing inefficiencies across 3 pairs."""

import logging
import time
from dataclasses import dataclass

from ..exchange.client import DeltaClient

logger = logging.getLogger("cryptoforge.tri_arb")


@dataclass(frozen=True, slots=True)
class ArbOpportunity:
    path: str               # e.g., "BTC→ETH→USDT"
    profit_pct: float       # expected profit after fees
    prices: tuple           # (rate1, rate2, rate3)
    timestamp: float


class TriangularArbitrage:
    """Scans for triangular arbitrage opportunities on Delta Exchange.

    Monitors 3 related pairs. When cross-rates don't align (after fees),
    executes all 3 legs to capture the discrepancy.

    Example triangle: BTC/USDT → ETH/BTC → ETH/USDT → USDT
    """

    def __init__(self, client: DeltaClient, fee_pct: float = 0.05):
        self.client = client
        self.fee_pct = fee_pct / 100  # convert to decimal
        self.opportunities_found: list[ArbOpportunity] = []
        self.opportunities_executed: list[ArbOpportunity] = []
        self.total_pnl: float = 0.0
        self._last_scan = 0.0

    def scan_triangle(
        self,
        price_ab: float,  # e.g., BTC/USDT ask
        price_bc: float,  # e.g., ETH/BTC ask
        price_ac: float,  # e.g., ETH/USDT bid
        path: str = "A→B→C",
    ) -> ArbOpportunity | None:
        """Check if a triangular arbitrage opportunity exists.

        Forward path: buy A with C, buy B with A, sell B for C
        profit = (1/price_ab) * (1/price_bc) * price_ac - 1

        Args:
            price_ab: Cost to buy A in terms of C (ask price)
            price_bc: Cost to buy B in terms of A (ask price)
            price_ac: Revenue from selling B in terms of C (bid price)
            path: Human-readable path description

        Returns:
            ArbOpportunity if profitable after 3x fees, None otherwise.
        """
        if price_ab <= 0 or price_bc <= 0 or price_ac <= 0:
            return None

        # Forward arbitrage
        forward_profit = (1 / price_ab) * (1 / price_bc) * price_ac - 1

        # Reverse arbitrage
        reverse_profit = price_ab * price_bc * (1 / price_ac) - 1

        # Need to cover 3 legs of fees (both maker/taker)
        total_fees = self.fee_pct * 3 * 2  # 3 legs × buy+sell

        best_profit = max(forward_profit, reverse_profit)
        direction = "forward" if forward_profit > reverse_profit else "reverse"

        if best_profit > total_fees:
            opp = ArbOpportunity(
                path=f"{path} ({direction})",
                profit_pct=round((best_profit - total_fees) * 100, 4),
                prices=(price_ab, price_bc, price_ac),
                timestamp=time.time(),
            )
            self.opportunities_found.append(opp)
            logger.info("ARB FOUND: %s | Profit: %.4f%% (gross: %.4f%%, fees: %.4f%%)",
                         opp.path, opp.profit_pct, best_profit * 100, total_fees * 100)
            return opp

        return None

    def scan_from_orderbooks(self, books: dict[str, dict]) -> ArbOpportunity | None:
        """Scan using live orderbook data from multiple pairs.

        Args:
            books: dict of symbol → {"best_bid": float, "best_ask": float}
        """
        # Define triangles to check
        triangles = [
            ("BTCUSD", "ETHBTC", "ETHUSD", "BTC→ETH→USD"),
            ("BTCUSD", "SOLBTC", "SOLUSD", "BTC→SOL→USD"),
        ]

        for pair_ab, pair_bc, pair_ac, path in triangles:
            if pair_ab not in books or pair_bc not in books or pair_ac not in books:
                continue

            opp = self.scan_triangle(
                price_ab=books[pair_ab]["best_ask"],
                price_bc=books[pair_bc]["best_ask"],
                price_ac=books[pair_ac]["best_bid"],
                path=path,
            )
            if opp:
                return opp

        return None

    def get_status(self) -> dict:
        return {
            "opportunities_found": len(self.opportunities_found),
            "opportunities_executed": len(self.opportunities_executed),
            "total_pnl": round(self.total_pnl, 4),
            "last_scan": time.strftime("%H:%M:%S", time.localtime(self._last_scan)) if self._last_scan else "never",
        }
