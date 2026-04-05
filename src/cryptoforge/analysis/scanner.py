"""Market scanner — detects unusual activity across multiple symbols."""

import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger("cryptoforge.scanner")


@dataclass(frozen=True, slots=True)
class MarketAlert:
    symbol: str
    alert_type: str  # volume_spike, breakout, funding_extreme
    message: str
    value: float
    timestamp: float


class MarketScanner:
    """Scans multiple symbols for unusual activity."""

    def __init__(self, volume_spike_threshold: float = 3.0, funding_extreme: float = 0.05):
        self.volume_spike_threshold = volume_spike_threshold
        self.funding_extreme = funding_extreme
        self._volume_history: dict[str, deque] = {}
        self._price_history: dict[str, deque] = {}
        self._alerts: list[MarketAlert] = []

    def process_ticker(self, data: dict) -> MarketAlert | None:
        """Process a ticker update and check for alerts."""
        symbol = data.get("symbol", "")
        volume = float(data.get("volume", 0))
        price = float(data.get("close", data.get("mark_price", 0)))
        funding = float(data.get("funding_rate", 0))

        if not symbol or price == 0:
            return None

        # Track history
        if symbol not in self._volume_history:
            self._volume_history[symbol] = deque(maxlen=100)
            self._price_history[symbol] = deque(maxlen=100)

        self._volume_history[symbol].append(volume)
        self._price_history[symbol].append(price)

        # Check volume spike
        vol_hist = self._volume_history[symbol]
        if len(vol_hist) >= 20:
            avg_vol = sum(list(vol_hist)[-20:]) / 20
            if avg_vol > 0 and volume > avg_vol * self.volume_spike_threshold:
                alert = MarketAlert(
                    symbol=symbol, alert_type="volume_spike",
                    message=f"{symbol}: Volume {volume/avg_vol:.1f}x average",
                    value=volume / avg_vol, timestamp=time.time(),
                )
                self._alerts.append(alert)
                logger.info("ALERT: %s", alert.message)
                return alert

        # Check funding rate extreme
        if abs(funding) > self.funding_extreme:
            direction = "positive" if funding > 0 else "negative"
            annualized = funding * 3 * 365 * 100  # 3 payments/day × 365 days
            alert = MarketAlert(
                symbol=symbol, alert_type="funding_extreme",
                message=f"{symbol}: Funding {direction} {annualized:.1f}% annualized",
                value=annualized, timestamp=time.time(),
            )
            self._alerts.append(alert)
            return alert

        # Check price breakout (20-period high/low)
        prices = self._price_history[symbol]
        if len(prices) >= 20:
            recent = list(prices)[-20:]
            high = max(recent[:-1])
            low = min(recent[:-1])
            if price > high:
                alert = MarketAlert(
                    symbol=symbol, alert_type="breakout_high",
                    message=f"{symbol}: New 20-period HIGH @ {price:,.2f}",
                    value=price, timestamp=time.time(),
                )
                self._alerts.append(alert)
                return alert
            if price < low:
                alert = MarketAlert(
                    symbol=symbol, alert_type="breakout_low",
                    message=f"{symbol}: New 20-period LOW @ {price:,.2f}",
                    value=price, timestamp=time.time(),
                )
                self._alerts.append(alert)
                return alert

        return None

    @property
    def recent_alerts(self) -> list[MarketAlert]:
        return self._alerts[-50:]
