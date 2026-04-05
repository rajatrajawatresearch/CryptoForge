"""Configuration loader and schema."""

import os
import re
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ExchangeConfig(BaseModel):
    base_url: str = "https://cdn-ind.testnet.deltaex.org"
    ws_url: str = "wss://socket.india.delta.exchange"
    prod_url: str = "https://api.india.delta.exchange"


class RiskConfig(BaseModel):
    max_capital: float = 10000
    max_leverage: int = 5
    max_position_pct: float = 20.0
    daily_loss_limit_pct: float = 5.0
    max_open_orders: int = 30


class GridConfig(BaseModel):
    enabled: bool = True
    symbol: str = "BTCUSD"
    product_id: int = 84
    upper_price: float = 95000.0
    lower_price: float = 85000.0
    num_grids: int = 10
    quantity_per_grid: float = 0.001
    leverage: int = 3


class ScalperConfig(BaseModel):
    enabled: bool = False
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSD", "ETHUSD"])
    oir_threshold: float = 0.6
    cooldown_seconds: int = 30
    sl_spread_multiplier: float = 3.0
    rr_ratio: float = 1.5


class TriArbConfig(BaseModel):
    enabled: bool = False
    fee_pct: float = 0.05


class FundingConfig(BaseModel):
    enabled: bool = False
    min_annualized_rate: float = 20.0


class TelegramConfig(BaseModel):
    enabled: bool = True
    signals_channel: str = ""


class StrategiesConfig(BaseModel):
    grid: GridConfig = Field(default_factory=GridConfig)
    scalper: ScalperConfig = Field(default_factory=ScalperConfig)
    tri_arb: TriArbConfig = Field(default_factory=TriArbConfig)
    funding: FundingConfig = Field(default_factory=FundingConfig)


class AppConfig(BaseModel):
    mode: str = "testnet"
    log_level: str = "INFO"
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategies: StrategiesConfig = Field(default_factory=StrategiesConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


def _interpolate(obj):
    if isinstance(obj, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _interpolate(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate(i) for i in obj]
    return obj


def load_config(path: str = "config/settings.toml") -> AppConfig:
    load_dotenv()
    p = Path(path)
    if not p.exists():
        return AppConfig()
    with open(p, "rb") as f:
        raw = tomllib.load(f)
    # Flatten: move [app] fields to top level
    flat = {}
    if "app" in raw:
        flat.update(raw.pop("app"))
    flat.update(raw)
    flat = _interpolate(flat)
    return AppConfig.model_validate(flat)
