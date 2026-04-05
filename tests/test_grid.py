"""Tests for Grid Trading Bot."""

from unittest.mock import MagicMock

from cryptoforge.config import GridConfig
from cryptoforge.strategies.grid import GridBot
from cryptoforge.types import Side


def _make_bot(grids=5, lower=85000, upper=95000) -> GridBot:
    config = GridConfig(
        symbol="BTCUSD", product_id=84,
        upper_price=upper, lower_price=lower,
        num_grids=grids, quantity_per_grid=0.001, leverage=3,
    )
    return GridBot(config, MagicMock())


def test_grid_levels_count():
    bot = _make_bot(grids=5)
    levels = bot.compute_grid(90000)
    assert len(levels) == 6  # num_grids + 1


def test_grid_spacing():
    bot = _make_bot(grids=10, lower=80000, upper=90000)
    levels = bot.compute_grid(85000)
    spacing = levels[1].price - levels[0].price
    assert spacing == 1000.0


def test_buys_below_sells_above():
    bot = _make_bot(grids=10)
    levels = bot.compute_grid(90000)
    for level in levels:
        if level.price < 90000:
            assert level.side == Side.BUY
        elif level.price > 90000:
            assert level.side == Side.SELL


def test_handle_fill_creates_opposite():
    bot = _make_bot(grids=5)
    levels = bot.compute_grid(90000)
    # Simulate a buy fill
    buy_level = [l for l in levels if l.side == Side.BUY][0]
    buy_level.order_id = "ORDER-1"
    bot.client.place_limit_order = MagicMock(return_value={"id": "ORDER-2"})

    result = bot.handle_fill("ORDER-1", buy_level.price)
    assert result is not None
    # After buy fill, a sell should be placed one grid above
    bot.client.place_limit_order.assert_called_once()
    call_args = bot.client.place_limit_order.call_args
    assert call_args[1]["side"] == "sell" or call_args[0][1] == "sell"


def test_sell_fill_records_pnl():
    bot = _make_bot(grids=5, lower=85000, upper=95000)
    levels = bot.compute_grid(90000)
    # Simulate a sell fill (completes a cycle)
    sell_level = [l for l in levels if l.side == Side.SELL][0]
    sell_level.order_id = "ORDER-1"
    bot.client.place_limit_order = MagicMock(return_value={"id": "ORDER-2"})

    bot.handle_fill("ORDER-1", sell_level.price)
    assert bot.total_pnl != 0  # PnL recorded


def test_is_price_in_range():
    bot = _make_bot(lower=85000, upper=95000)
    assert bot.is_price_in_range(90000) is True
    assert bot.is_price_in_range(80000) is False
    assert bot.is_price_in_range(100000) is False


def test_status():
    bot = _make_bot(grids=5)
    bot.compute_grid(90000)
    status = bot.get_status()
    assert status["total_levels"] == 6
    assert status["completed_cycles"] == 0
    assert "grid_range" in status
