"""Delta Exchange WebSocket client for real-time data."""

import hashlib
import hmac
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime

import websocket

from ..types import OrderBook, OrderBookLevel, Ticker

logger = logging.getLogger("cryptoforge.exchange")


class DeltaWebSocket:
    """WebSocket client for Delta Exchange real-time data."""

    def __init__(self, ws_url: str, api_key: str = "", api_secret: str = ""):
        self.ws_url = ws_url
        self.api_key = api_key
        self.api_secret = api_secret
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._connected = False
        self._callbacks: dict[str, list] = defaultdict(list)
        self._last_msg_time = 0.0

    def on_ticker(self, callback) -> None:
        """Register callback for ticker updates. Signature: callback(data: dict)"""
        self._callbacks["v2/ticker"].append(callback)

    def on_orderbook(self, callback) -> None:
        """Register callback for L2 orderbook updates."""
        self._callbacks["l2_orderbook"].append(callback)

    def on_trades(self, callback) -> None:
        """Register callback for trade updates."""
        self._callbacks["all_trades"].append(callback)

    def on_order_update(self, callback) -> None:
        """Register callback for private order updates."""
        self._callbacks["orders"].append(callback)

    def on_position_update(self, callback) -> None:
        """Register callback for private position updates."""
        self._callbacks["positions"].append(callback)

    def on_funding_rate(self, callback) -> None:
        """Register callback for funding rate updates."""
        self._callbacks["funding_rate"].append(callback)

    def _on_message(self, ws, message):
        self._last_msg_time = time.monotonic()
        try:
            data = json.loads(message)
            channel = data.get("type", "")

            # Dispatch to registered callbacks
            for cb_channel, callbacks in self._callbacks.items():
                if cb_channel in channel or channel == cb_channel:
                    for cb in callbacks:
                        try:
                            cb(data)
                        except Exception as e:
                            logger.error("WS callback error: %s", e)
        except json.JSONDecodeError:
            pass

    def _on_open(self, ws):
        logger.info("WebSocket connected")
        self._connected = True

        # Authenticate for private channels
        if self.api_key and self.api_secret:
            self._authenticate(ws)

    def _on_close(self, ws, code, reason):
        logger.warning("WebSocket closed: %s %s", code, reason)
        self._connected = False

    def _on_error(self, ws, error):
        logger.error("WebSocket error: %s", error)

    def _authenticate(self, ws):
        ts = str(int(time.time()))
        sig_data = f"GET{ts}/live"
        sig = hmac.new(self.api_secret.encode(), sig_data.encode(), hashlib.sha256).hexdigest()
        ws.send(json.dumps({
            "type": "auth",
            "payload": {"api-key": self.api_key, "signature": sig, "timestamp": ts}
        }))
        logger.info("WebSocket authenticated")

    def subscribe_public(self, symbols: list[str], channels: list[str] | None = None):
        """Subscribe to public channels."""
        channels = channels or ["v2/ticker", "l2_orderbook"]
        if self._ws and self._connected:
            self._ws.send(json.dumps({
                "type": "subscribe",
                "payload": {"channels": [{"name": ch, "symbols": symbols} for ch in channels]}
            }))
            logger.info("Subscribed to %s for %s", channels, symbols)

    def subscribe_private(self, channels: list[str] | None = None):
        """Subscribe to private channels (requires auth)."""
        channels = channels or ["orders", "positions"]
        if self._ws and self._connected:
            self._ws.send(json.dumps({
                "type": "subscribe",
                "payload": {"channels": [{"name": ch, "symbols": ["all"]} for ch in channels]}
            }))
            logger.info("Subscribed to private: %s", channels)

    def start(self):
        """Start WebSocket in background thread."""
        self._ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self._on_message,
            on_open=self._on_open,
            on_close=self._on_close,
            on_error=self._on_error,
        )
        self._thread = threading.Thread(target=self._ws.run_forever, daemon=True,
                                         kwargs={"ping_interval": 30, "ping_timeout": 10})
        self._thread.start()
        # Wait for connection
        for _ in range(50):
            if self._connected:
                return
            time.sleep(0.1)
        logger.warning("WebSocket connection timeout")

    def stop(self):
        if self._ws:
            self._ws.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def seconds_since_last_message(self) -> float:
        if self._last_msg_time == 0:
            return float("inf")
        return time.monotonic() - self._last_msg_time
