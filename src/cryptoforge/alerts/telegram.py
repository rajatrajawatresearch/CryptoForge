"""Telegram alerting for trade events."""

import logging
import os

import aiohttp

logger = logging.getLogger("cryptoforge.alerts")


class TelegramAlerter:
    """Sends trading alerts via Telegram Bot API. Never raises — alerting must not crash bot."""

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.enabled = bool(self.bot_token and self.chat_id)

    async def send(self, message: str, chat_id: str | None = None) -> None:
        if not self.enabled:
            return
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(self._url, json={
                    "chat_id": chat_id or self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                })
        except Exception as e:
            logger.error("Telegram error: %s", e)

    def send_sync(self, message: str) -> None:
        """Synchronous send for non-async contexts."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.send(message))
            else:
                loop.run_until_complete(self.send(message))
        except RuntimeError:
            asyncio.run(self.send(message))

    async def order_placed(self, side: str, symbol: str, qty: float, price: float, strategy: str) -> None:
        icon = "🟢" if side.upper() == "BUY" else "🔴"
        await self.send(
            f"{icon} <b>{side.upper()} {symbol}</b>\n"
            f"Qty: {qty} @ ₹{price:,.2f}\n"
            f"Strategy: {strategy}"
        )

    async def order_filled(self, side: str, symbol: str, qty: float, price: float, pnl: float = 0) -> None:
        icon = "✅"
        pnl_str = f"\nP&L: ₹{pnl:+,.2f}" if pnl else ""
        await self.send(f"{icon} <b>FILLED: {side.upper()} {symbol}</b>\nQty: {qty} @ ₹{price:,.2f}{pnl_str}")

    async def grid_cycle_complete(self, symbol: str, pnl: float, total_pnl: float, cycles: int) -> None:
        await self.send(
            f"🔄 <b>Grid Cycle Complete</b>\n"
            f"Symbol: {symbol}\n"
            f"Cycle P&L: ₹{pnl:+,.4f}\n"
            f"Total P&L: ₹{total_pnl:+,.4f}\n"
            f"Cycles: {cycles}"
        )

    async def error(self, msg: str) -> None:
        await self.send(f"⚠️ <b>ERROR</b>\n{msg}")

    async def status(self, msg: str) -> None:
        await self.send(f"📊 {msg}")

    async def daily_summary(self, data: dict) -> None:
        await self.send(
            f"📋 <b>DAILY SUMMARY</b>\n"
            f"P&L: ₹{data.get('pnl', 0):+,.4f}\n"
            f"Trades: {data.get('trades', 0)}\n"
            f"Win Rate: {data.get('win_rate', 0):.0f}%\n"
            f"Grid Cycles: {data.get('cycles', 0)}"
        )
