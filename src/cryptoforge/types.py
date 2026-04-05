"""Shared data types."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(StrEnum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Ticker:
    symbol: str
    product_id: int
    last_price: float
    mark_price: float
    volume_24h: float
    funding_rate: float
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    price: float
    size: float


@dataclass(frozen=True, slots=True)
class OrderBook:
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    timestamp: datetime

    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0

    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0

    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread_bps(self) -> float:
        if self.mid_price == 0:
            return 0
        return (self.best_ask - self.best_bid) / self.mid_price * 10000


@dataclass(frozen=True, slots=True)
class Signal:
    strategy: str
    symbol: str
    side: Side
    price: float
    quantity: float
    stop_loss: float
    target: float
    confidence: float
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(slots=True)
class GridLevel:
    price: float
    side: Side
    order_id: str | None = None
    filled: bool = False
    fill_price: float = 0.0


@dataclass(slots=True)
class TradeRecord:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float = 0.0
    pnl: float = 0.0
    strategy: str = ""
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: datetime | None = None
    fees: float = 0.0
