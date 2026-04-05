"""Signal publisher — formats and sends trading signals to Telegram channel."""

import logging
from datetime import datetime

from ..alerts.telegram import TelegramAlerter
from ..types import Signal, Side

logger = logging.getLogger("cryptoforge.signals")


class SignalPublisher:
    """Publishes formatted trading signals to a public Telegram channel."""

    def __init__(self, alerter: TelegramAlerter, channel_id: str = "", delay_seconds: int = 0):
        self.alerter = alerter
        self.channel_id = channel_id
        self.delay_seconds = delay_seconds  # Free tier: 5-min delay
        self._signal_count = 0

    async def publish(self, signal: Signal) -> None:
        """Format and publish a signal to the channel."""
        self._signal_count += 1

        icon = "🟢" if signal.side == Side.BUY else "🔴"
        direction = "BUY" if signal.side == Side.BUY else "SELL"

        # Calculate target/SL percentages
        if signal.price > 0:
            target_pct = abs(signal.target - signal.price) / signal.price * 100
            sl_pct = abs(signal.stop_loss - signal.price) / signal.price * 100
        else:
            target_pct = sl_pct = 0

        msg = (
            f"{icon} <b>{direction} {signal.symbol}</b> @ ₹{signal.price:,.2f}\n"
            f"\n"
            f"🎯 Target: ₹{signal.target:,.2f} (+{target_pct:.2f}%)\n"
            f"🛑 SL: ₹{signal.stop_loss:,.2f} (-{sl_pct:.2f}%)\n"
            f"📊 Confidence: {signal.confidence * 100:.0f}%\n"
            f"⚙️ Strategy: {signal.strategy}\n"
        )

        # Add metadata if available
        meta = signal.metadata
        if meta.get("oir"):
            msg += f"📈 OIR: {meta['oir']:+.2f}\n"
        if meta.get("spread_bps"):
            msg += f"📏 Spread: {meta['spread_bps']:.1f} bps\n"
        if meta.get("buy_pressure"):
            msg += f"💪 Buy Pressure: {meta['buy_pressure']:.0%}\n"

        msg += f"\n#{self._signal_count} | {datetime.now().strftime('%H:%M:%S IST')}"

        chat_id = self.channel_id or self.alerter.chat_id
        await self.alerter.send(msg, chat_id=chat_id)

    async def publish_daily_summary(self, data: dict) -> None:
        """Publish end-of-day performance summary."""
        wins = data.get("wins", 0)
        total = data.get("total_signals", 0)
        win_rate = (wins / total * 100) if total else 0

        msg = (
            f"📋 <b>DAILY SIGNAL REPORT</b>\n"
            f"\n"
            f"Total Signals: {total}\n"
            f"Winners: {wins} | Losers: {total - wins}\n"
            f"Win Rate: {win_rate:.0f}%\n"
            f"Total P&L: ₹{data.get('total_pnl', 0):+,.4f}\n"
            f"Best: ₹{data.get('best', 0):+,.4f}\n"
            f"Worst: ₹{data.get('worst', 0):+,.4f}\n"
            f"\n"
            f"Strategies: Grid={data.get('grid_cycles', 0)} cycles, "
            f"Scalps={data.get('scalp_trades', 0)}\n"
            f"\n"
            f"📢 Join for real-time signals!"
        )

        chat_id = self.channel_id or self.alerter.chat_id
        await self.alerter.send(msg, chat_id=chat_id)


class SignalTracker:
    """Tracks signal performance over time."""

    def __init__(self):
        self._signals: list[dict] = []

    def record(self, signal: Signal) -> None:
        self._signals.append({
            "symbol": signal.symbol,
            "side": signal.side,
            "price": signal.price,
            "target": signal.target,
            "stop_loss": signal.stop_loss,
            "strategy": signal.strategy,
            "confidence": signal.confidence,
            "time": datetime.now(),
            "status": "open",
            "exit_price": 0,
            "pnl": 0,
        })

    def update_price(self, symbol: str, price: float) -> None:
        for s in self._signals:
            if s["symbol"] == symbol and s["status"] == "open":
                if s["side"] == Side.BUY:
                    if price >= s["target"]:
                        s["status"] = "won"
                        s["exit_price"] = price
                        s["pnl"] = price - s["price"]
                    elif price <= s["stop_loss"]:
                        s["status"] = "lost"
                        s["exit_price"] = price
                        s["pnl"] = price - s["price"]
                else:
                    if price <= s["target"]:
                        s["status"] = "won"
                        s["exit_price"] = price
                        s["pnl"] = s["price"] - price
                    elif price >= s["stop_loss"]:
                        s["status"] = "lost"
                        s["exit_price"] = price
                        s["pnl"] = s["price"] - price

    def get_summary(self) -> dict:
        closed = [s for s in self._signals if s["status"] != "open"]
        wins = sum(1 for s in closed if s["pnl"] > 0)
        pnls = [s["pnl"] for s in closed]
        return {
            "total_signals": len(self._signals),
            "open": sum(1 for s in self._signals if s["status"] == "open"),
            "wins": wins,
            "losses": len(closed) - wins,
            "total_pnl": sum(pnls),
            "best": max(pnls) if pnls else 0,
            "worst": min(pnls) if pnls else 0,
        }
