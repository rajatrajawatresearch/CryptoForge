"""Delta Exchange India REST client wrapper."""

import logging
import os
import time
from datetime import datetime

from delta_rest_client import DeltaRestClient, OrderType, TimeInForce

from ..types import OrderBook, OrderBookLevel, Ticker

logger = logging.getLogger("cryptoforge.exchange")


class DeltaClient:
    """Wrapper around Delta Exchange REST API with rate limiting."""

    def __init__(self, base_url: str, api_key: str | None = None, api_secret: str | None = None):
        self.api_key = api_key or os.environ.get("DELTA_API_KEY", "")
        self.api_secret = api_secret or os.environ.get("DELTA_API_SECRET", "")
        self.base_url = base_url

        self._client = DeltaRestClient(
            base_url=base_url,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )
        self._last_call = 0.0
        self._call_count = 0
        self._window_start = time.monotonic()

    def _rate_limit(self, weight: int = 1) -> None:
        """Simple rate limiter: 10,000 units / 5 min."""
        now = time.monotonic()
        if now - self._window_start > 300:
            self._call_count = 0
            self._window_start = now
        self._call_count += weight
        if self._call_count > 9500:  # buffer
            sleep_time = 300 - (now - self._window_start)
            if sleep_time > 0:
                logger.warning("Rate limit approaching, sleeping %.1fs", sleep_time)
                time.sleep(sleep_time)
                self._call_count = 0
                self._window_start = time.monotonic()

    # ── Market Data ──

    def get_ticker(self, symbol: str) -> dict:
        self._rate_limit()
        return self._client.get_ticker(symbol)

    def get_orderbook(self, product_id: int) -> OrderBook:
        self._rate_limit()
        data = self._client.get_l2_orderbook(product_id)
        bids = [OrderBookLevel(float(b["price"]), float(b["size"])) for b in data.get("buy", [])]
        asks = [OrderBookLevel(float(a["price"]), float(a["size"])) for a in data.get("sell", [])]
        return OrderBook(symbol=str(product_id), bids=bids, asks=asks, timestamp=datetime.now())

    def get_products(self) -> list:
        self._rate_limit()
        return self._client.get_assets()

    # ── Orders ──

    def place_limit_order(self, product_id: int, side: str, size: float, price: str) -> dict:
        self._rate_limit(5)
        result = self._client.place_order(
            product_id=product_id,
            side=side,
            size=size,
            limit_price=price,
            order_type=OrderType.LIMIT,
        )
        logger.info("Order placed: %s %s @ %s (id: %s)", side, size, price, result.get("id"))
        return result

    def place_market_order(self, product_id: int, side: str, size: float) -> dict:
        self._rate_limit(5)
        result = self._client.place_order(
            product_id=product_id,
            side=side,
            size=size,
            order_type=OrderType.MARKET,
        )
        logger.info("Market order: %s %s (id: %s)", side, size, result.get("id"))
        return result

    def cancel_order(self, product_id: int, order_id: int) -> dict:
        self._rate_limit(5)
        return self._client.cancel_order(product_id, order_id)

    def cancel_all(self, product_id: int) -> dict:
        self._rate_limit(5)
        return self._client.batch_cancel(product_id, [])

    def get_open_orders(self) -> list:
        self._rate_limit()
        return self._client.get_live_orders()

    # ── Positions ──

    def get_position(self, product_id: int) -> dict:
        self._rate_limit()
        return self._client.get_position(product_id)

    def set_leverage(self, product_id: int, leverage: int) -> dict:
        self._rate_limit()
        return self._client.set_leverage(product_id, leverage)

    # ── Account ──

    def get_balance(self, asset_id: int = 5) -> dict:
        """Get wallet balance. asset_id=5 is INR on Delta India."""
        self._rate_limit()
        return self._client.get_balances(asset_id)

    def get_order_history(self, page_size: int = 50) -> list:
        self._rate_limit()
        return self._client.order_history({}, page_size=page_size)
