"""Order Flow Scalper — trades on orderbook imbalance signals."""

import logging
import time
from datetime import datetime

from ..analysis.orderbook import OrderBookAnalyzer, OrderBookSnapshot
from ..config import ScalperConfig
from ..exchange.client import DeltaClient
from ..types import OrderBook, Side, Signal, TradeRecord

logger = logging.getLogger("cryptoforge.scalper")


class OrderFlowScalper:
    """Scalps based on order book imbalance. Enters when OIR extreme, exits quickly."""

    def __init__(self, config: ScalperConfig, client: DeltaClient, product_ids: dict[str, int]):
        self.config = config
        self.client = client
        self.product_ids = product_ids  # symbol → product_id
        self.analyzer = OrderBookAnalyzer()
        self.trades: list[TradeRecord] = []
        self.total_pnl: float = 0.0
        self._last_signal_time: dict[str, float] = {}
        self._open_position: dict[str, dict] = {}

    def process_orderbook(self, book: OrderBook) -> Signal | None:
        """Analyze orderbook and generate scalping signal if conditions met."""
        symbol = book.symbol
        snapshot = self.analyzer.analyze(book)

        # Cooldown check
        now = time.monotonic()
        last = self._last_signal_time.get(symbol, 0)
        if now - last < self.config.cooldown_seconds:
            return None

        # Don't open if already in position for this symbol
        if symbol in self._open_position:
            return self._check_exit(symbol, snapshot)

        # Signal: strong OIR + confirmation from EMA
        if snapshot.oir > self.config.oir_threshold and snapshot.oir_ema > 0.3:
            return self._generate_signal(symbol, snapshot, Side.BUY)

        if snapshot.oir < -self.config.oir_threshold and snapshot.oir_ema < -0.3:
            return self._generate_signal(symbol, snapshot, Side.SELL)

        return None

    def _generate_signal(self, symbol: str, snap: OrderBookSnapshot, side: Side) -> Signal:
        """Generate a scalping signal with tight SL/target."""
        price = snap.best_ask if side == Side.BUY else snap.best_bid
        spread = snap.best_ask - snap.best_bid
        sl_distance = max(spread * self.config.sl_spread_multiplier, price * 0.001)
        target_distance = sl_distance * self.config.rr_ratio

        if side == Side.BUY:
            sl = round(price - sl_distance, 2)
            target = round(price + target_distance, 2)
        else:
            sl = round(price + sl_distance, 2)
            target = round(price - target_distance, 2)

        self._last_signal_time[symbol] = time.monotonic()
        self._open_position[symbol] = {
            "side": side, "entry": price, "sl": sl, "target": target, "time": datetime.now()
        }

        logger.info("Scalp signal: %s %s @ %.2f | OIR: %.2f | Spread: %.1f bps | Wall: %s",
                     side, symbol, price, snap.oir, snap.spread_bps,
                     "BID" if snap.bid_wall else ("ASK" if snap.ask_wall else "none"))

        return Signal(
            strategy="scalper",
            symbol=symbol,
            side=side,
            price=price,
            quantity=0,  # let risk manager decide
            stop_loss=sl,
            target=target,
            confidence=min(abs(snap.oir), 1.0),
            metadata={"oir": snap.oir, "spread_bps": snap.spread_bps, "buy_pressure": snap.buy_pressure},
        )

    def _check_exit(self, symbol: str, snap: OrderBookSnapshot) -> Signal | None:
        """Check if open position should be exited."""
        pos = self._open_position.get(symbol)
        if not pos:
            return None

        current = snap.mid_price
        entry = pos["entry"]
        side = pos["side"]

        # Check SL hit
        if side == Side.BUY and current <= pos["sl"]:
            return self._close_position(symbol, current, "stop_loss")
        if side == Side.SELL and current >= pos["sl"]:
            return self._close_position(symbol, current, "stop_loss")

        # Check target hit
        if side == Side.BUY and current >= pos["target"]:
            return self._close_position(symbol, current, "target")
        if side == Side.SELL and current <= pos["target"]:
            return self._close_position(symbol, current, "target")

        # OIR reversal exit: if imbalance flips strongly against position
        if side == Side.BUY and snap.oir < -0.3:
            return self._close_position(symbol, current, "oir_reversal")
        if side == Side.SELL and snap.oir > 0.3:
            return self._close_position(symbol, current, "oir_reversal")

        return None

    def _close_position(self, symbol: str, exit_price: float, reason: str) -> Signal:
        pos = self._open_position.pop(symbol)
        entry = pos["entry"]
        side = pos["side"]

        if side == Side.BUY:
            pnl = exit_price - entry
        else:
            pnl = entry - exit_price

        self.total_pnl += pnl
        self.trades.append(TradeRecord(
            symbol=symbol, side=side.value, quantity=0,
            entry_price=entry, exit_price=exit_price, pnl=pnl,
            strategy="scalper", entry_time=pos["time"],
        ))

        exit_side = Side.SELL if side == Side.BUY else Side.BUY
        logger.info("Scalp exit: %s %s @ %.2f (reason: %s, P&L: %.4f)", exit_side, symbol, exit_price, reason, pnl)

        return Signal(
            strategy="scalper",
            symbol=symbol,
            side=exit_side,
            price=exit_price,
            quantity=0,
            stop_loss=0,
            target=0,
            confidence=1.0,
            metadata={"reason": reason, "pnl": pnl},
        )

    def get_status(self) -> dict:
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return {
            "total_trades": len(self.trades),
            "win_rate": (wins / len(self.trades) * 100) if self.trades else 0,
            "total_pnl": round(self.total_pnl, 4),
            "open_positions": len(self._open_position),
        }
