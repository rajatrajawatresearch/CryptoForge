"""Order book analysis — OIR, spread, wall detection, aggressor classification."""

import logging
from collections import deque
from dataclasses import dataclass

from ..types import OrderBook

logger = logging.getLogger("cryptoforge.analysis")


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    oir: float                  # -1.0 to 1.0 (Order Imbalance Ratio)
    oir_ema: float              # EMA of OIR
    bid_total: float            # total bid volume (all levels)
    ask_total: float            # total ask volume (all levels)
    spread_bps: float           # bid-ask spread in basis points
    mid_price: float
    best_bid: float
    best_ask: float
    bid_wall: bool              # large bid wall detected
    ask_wall: bool              # large ask wall detected
    wall_price: float           # price of detected wall (0 if none)
    buy_pressure: float         # 0-1, derived from bid/ask ratio


class OrderBookAnalyzer:
    """Real-time order book analysis for trading signals."""

    def __init__(self, oir_window: int = 100, ema_alpha: float = 0.1, wall_threshold: float = 5.0):
        self.oir_window = oir_window
        self.ema_alpha = ema_alpha
        self.wall_threshold = wall_threshold
        self._oir_history: dict[str, deque] = {}
        self._oir_ema: dict[str, float] = {}

    def analyze(self, book: OrderBook) -> OrderBookSnapshot:
        """Analyze an orderbook snapshot and return metrics."""
        symbol = book.symbol

        # Total volumes
        bid_total = sum(level.size for level in book.bids) if book.bids else 0
        ask_total = sum(level.size for level in book.asks) if book.asks else 0

        # OIR = (bid - ask) / (bid + ask)
        total = bid_total + ask_total
        oir = (bid_total - ask_total) / total if total > 0 else 0

        # Track OIR history
        if symbol not in self._oir_history:
            self._oir_history[symbol] = deque(maxlen=self.oir_window)
            self._oir_ema[symbol] = 0.0

        self._oir_history[symbol].append(oir)

        # EMA of OIR
        prev_ema = self._oir_ema[symbol]
        oir_ema = self.ema_alpha * oir + (1 - self.ema_alpha) * prev_ema
        self._oir_ema[symbol] = oir_ema

        # Wall detection: any single level > threshold × average level size
        bid_wall, ask_wall, wall_price = self._detect_walls(book, bid_total, ask_total)

        # Buy pressure: normalized bid/ask ratio
        buy_pressure = bid_total / total if total > 0 else 0.5

        return OrderBookSnapshot(
            oir=round(oir, 4),
            oir_ema=round(oir_ema, 4),
            bid_total=bid_total,
            ask_total=ask_total,
            spread_bps=round(book.spread_bps, 2),
            mid_price=round(book.mid_price, 2),
            best_bid=book.best_bid,
            best_ask=book.best_ask,
            bid_wall=bid_wall,
            ask_wall=ask_wall,
            wall_price=wall_price,
            buy_pressure=round(buy_pressure, 4),
        )

    def _detect_walls(self, book: OrderBook, bid_total: float, ask_total: float) -> tuple[bool, bool, float]:
        """Detect large order walls in the book."""
        bid_wall = False
        ask_wall = False
        wall_price = 0.0

        if book.bids:
            avg_bid = bid_total / len(book.bids)
            for level in book.bids:
                if level.size > avg_bid * self.wall_threshold:
                    bid_wall = True
                    wall_price = level.price
                    break

        if book.asks:
            avg_ask = ask_total / len(book.asks)
            for level in book.asks:
                if level.size > avg_ask * self.wall_threshold:
                    ask_wall = True
                    wall_price = level.price
                    break

        return bid_wall, ask_wall, wall_price

    def get_oir_trend(self, symbol: str, lookback: int = 20) -> float:
        """Get OIR trend direction. Positive = increasing bid pressure."""
        history = self._oir_history.get(symbol, deque())
        if len(history) < lookback:
            return 0.0
        recent = list(history)[-lookback:]
        first_half = sum(recent[:lookback // 2]) / (lookback // 2)
        second_half = sum(recent[lookback // 2:]) / (lookback // 2)
        return second_half - first_half
