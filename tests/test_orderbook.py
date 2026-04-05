"""Tests for OrderBook Analyzer."""

from datetime import datetime

from cryptoforge.analysis.orderbook import OrderBookAnalyzer
from cryptoforge.types import OrderBook, OrderBookLevel


def _make_book(bids_sizes: list[float], asks_sizes: list[float], base_price: float = 90000) -> OrderBook:
    bids = [OrderBookLevel(base_price - i * 10, s) for i, s in enumerate(bids_sizes)]
    asks = [OrderBookLevel(base_price + (i + 1) * 10, s) for i, s in enumerate(asks_sizes)]
    return OrderBook(symbol="BTCUSD", bids=bids, asks=asks, timestamp=datetime.now())


def test_oir_bid_heavy():
    analyzer = OrderBookAnalyzer()
    book = _make_book([10, 10, 10], [1, 1, 1])
    snap = analyzer.analyze(book)
    assert snap.oir > 0.5  # Bid-heavy


def test_oir_ask_heavy():
    analyzer = OrderBookAnalyzer()
    book = _make_book([1, 1, 1], [10, 10, 10])
    snap = analyzer.analyze(book)
    assert snap.oir < -0.5  # Ask-heavy


def test_oir_balanced():
    analyzer = OrderBookAnalyzer()
    book = _make_book([5, 5, 5], [5, 5, 5])
    snap = analyzer.analyze(book)
    assert abs(snap.oir) < 0.01  # Balanced


def test_spread_bps():
    analyzer = OrderBookAnalyzer()
    book = _make_book([5], [5], base_price=90000)
    snap = analyzer.analyze(book)
    assert snap.spread_bps > 0


def test_wall_detection():
    analyzer = OrderBookAnalyzer(wall_threshold=2.0)
    # One bid level much larger than others (50 vs avg=20 → 2.5x avg)
    book = _make_book([50, 5, 5], [5, 5, 5])
    snap = analyzer.analyze(book)
    assert snap.bid_wall is True


def test_no_wall_when_even():
    analyzer = OrderBookAnalyzer(wall_threshold=5.0)
    book = _make_book([5, 5, 5], [5, 5, 5])
    snap = analyzer.analyze(book)
    assert snap.bid_wall is False
    assert snap.ask_wall is False


def test_buy_pressure():
    analyzer = OrderBookAnalyzer()
    book = _make_book([10, 10], [2, 2])
    snap = analyzer.analyze(book)
    assert snap.buy_pressure > 0.7  # Strong buy pressure
