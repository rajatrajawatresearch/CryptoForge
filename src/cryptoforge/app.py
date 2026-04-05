"""CryptoForge main application — orchestrates all components."""

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path

from .alerts.telegram import TelegramAlerter
from .config import load_config
from .exchange.client import DeltaClient
from .exchange.ws import DeltaWebSocket
from .strategies.grid import GridBot

logger = logging.getLogger("cryptoforge")


def setup_logging(level: str = "INFO"):
    fmt = "%(asctime)s [%(levelname)8s] %(name)s: %(message)s"
    logging.basicConfig(level=getattr(logging, level), format=fmt, datefmt="%H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CryptoForge Trading Bot")
    parser.add_argument("--mode", choices=["testnet", "paper", "live"], default=None)
    parser.add_argument("--strategy", choices=["grid", "scalper", "all"], default="grid")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--config", default="config/settings.toml")
    return parser.parse_args()


async def run_grid_bot(config, client: DeltaClient, alerter: TelegramAlerter, ws: DeltaWebSocket):
    """Run the grid trading strategy."""
    grid_config = config.strategies.grid
    bot = GridBot(grid_config, client)

    # Get current price
    try:
        ticker = client.get_ticker(grid_config.symbol)
        current_price = float(ticker.get("mark_price", 0) or ticker.get("close", 0))
        if current_price == 0:
            current_price = (grid_config.upper_price + grid_config.lower_price) / 2
        logger.info("Current %s price: %.2f", grid_config.symbol, current_price)
    except Exception as e:
        logger.warning("Could not fetch price, using midpoint: %s", e)
        current_price = (grid_config.upper_price + grid_config.lower_price) / 2

    # Compute and place grid
    bot.compute_grid(current_price)
    placed = bot.place_grid_orders()

    await alerter.status(
        f"Grid Bot Started: {grid_config.symbol}\n"
        f"Range: {grid_config.lower_price}-{grid_config.upper_price}\n"
        f"Grids: {grid_config.num_grids} | Leverage: {grid_config.leverage}x\n"
        f"Orders placed: {placed}"
    )

    # Listen for order fills via WebSocket
    fill_queue = asyncio.Queue()

    def on_order_update(data):
        """WebSocket callback for order updates."""
        if data.get("type") == "orders":
            for order in data.get("data", [data]):
                status = order.get("state", "")
                if status == "closed" and order.get("meta", {}).get("reason") == "filled":
                    asyncio.get_event_loop().call_soon_threadsafe(
                        fill_queue.put_nowait,
                        {"id": str(order.get("id", "")), "price": float(order.get("average_fill_price", 0))}
                    )

    ws.on_order_update(on_order_update)

    # Subscribe to private channels for order updates
    ws.subscribe_private(["orders"])

    # Main loop: process fills and maintain grid
    logger.info("Grid bot running. Waiting for fills...")
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown.set)

    status_interval = 60  # Print status every 60 seconds
    last_status = time.monotonic()

    while not shutdown.is_set():
        # Check for fills
        try:
            fill = await asyncio.wait_for(fill_queue.get(), timeout=5.0)
            order_id = fill["id"]
            fill_price = fill["price"]

            result = bot.handle_fill(order_id, fill_price)
            if result:
                status = bot.get_status()
                await alerter.grid_cycle_complete(
                    grid_config.symbol,
                    bot.completed_trades[-1].pnl if bot.completed_trades else 0,
                    bot.total_pnl,
                    status["completed_cycles"],
                )
                logger.info("Grid status: %s", status)

        except asyncio.TimeoutError:
            pass

        # Periodic status log
        now = time.monotonic()
        if now - last_status > status_interval:
            status = bot.get_status()
            logger.info("Grid status: %s", status)
            last_status = now

    # Shutdown
    logger.info("Shutting down grid bot...")
    bot.cancel_all_orders()
    final = bot.get_status()
    await alerter.status(f"Grid Bot Stopped\nFinal P&L: ₹{bot.total_pnl:+,.4f}\nCycles: {final['completed_cycles']}")
    logger.info("Final: %s", final)


def main():
    args = parse_args()

    project_root = Path(__file__).resolve().parent.parent.parent
    if project_root.exists():
        os.chdir(project_root)

    config = load_config(args.config)
    mode = args.mode or config.mode
    setup_logging(config.log_level)

    print()
    print("  ╔═══════════════════════════════════╗")
    print("  ║       CRYPTOFORGE TRADING BOT      ║")
    print("  ║   Delta Exchange India • Crypto     ║")
    print("  ╚═══════════════════════════════════╝")
    print()

    # Select base URL
    if mode == "live":
        base_url = config.exchange.prod_url
        logger.warning("LIVE MODE — Real money trading!")
    else:
        base_url = config.exchange.base_url
        logger.info("Mode: %s | URL: %s", mode.upper(), base_url)

    # Initialize components
    client = DeltaClient(base_url=base_url)
    alerter = TelegramAlerter()
    ws = DeltaWebSocket(
        ws_url=config.exchange.ws_url,
        api_key=os.environ.get("DELTA_API_KEY", ""),
        api_secret=os.environ.get("DELTA_API_SECRET", ""),
    )

    # Connect WebSocket
    ws.start()

    # Subscribe to public data
    symbols = [config.strategies.grid.symbol]
    ws.subscribe_public(symbols, ["v2/ticker", "l2_orderbook"])

    logger.info("Capital: ₹%.0f | Max leverage: %dx", config.risk.max_capital, config.risk.max_leverage)

    # Run strategy
    try:
        if args.strategy == "grid":
            asyncio.run(run_grid_bot(config, client, alerter, ws))
        else:
            logger.info("Strategy '%s' not yet implemented", args.strategy)
    except KeyboardInterrupt:
        print("\n  CryptoForge stopped.\n")
    finally:
        ws.stop()


if __name__ == "__main__":
    main()
