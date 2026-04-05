"""Tests for config loading."""

import os

from cryptoforge.config import load_config


def test_load_default_config():
    config = load_config()
    assert config.mode == "testnet"
    assert config.strategies.grid.symbol == "BTCUSD"
    assert config.strategies.grid.num_grids == 10


def test_risk_defaults():
    config = load_config()
    assert config.risk.max_capital == 10000
    assert config.risk.max_leverage == 5
    assert config.risk.daily_loss_limit_pct == 5.0


def test_grid_config():
    config = load_config()
    g = config.strategies.grid
    assert g.lower_price < g.upper_price
    assert g.quantity_per_grid > 0
    assert g.leverage > 0
