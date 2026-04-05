"""Grid Trading Bot — profits from sideways/ranging markets."""

import logging
from datetime import datetime

from ..config import GridConfig
from ..exchange.client import DeltaClient
from ..types import GridLevel, Side, TradeRecord

logger = logging.getLogger("cryptoforge.grid")


class GridBot:
    """Grid trading strategy for Delta Exchange.

    Places a ladder of buy/sell limit orders across a price range.
    Profits from price oscillating within the grid — each completed
    buy-then-sell cycle captures one grid spacing as profit.
    """

    def __init__(self, config: GridConfig, client: DeltaClient):
        self.config = config
        self.client = client
        self.grid_levels: list[GridLevel] = []
        self.completed_trades: list[TradeRecord] = []
        self.total_pnl: float = 0.0
        self._active = False

    def compute_grid(self, current_price: float | None = None) -> list[GridLevel]:
        """Compute grid levels between upper and lower bounds."""
        spacing = (self.config.upper_price - self.config.lower_price) / self.config.num_grids
        levels = []

        for i in range(self.config.num_grids + 1):
            price = round(self.config.lower_price + i * spacing, 2)
            # Levels below current price → BUY, above → SELL
            if current_price:
                side = Side.BUY if price < current_price else Side.SELL
            else:
                mid = (self.config.upper_price + self.config.lower_price) / 2
                side = Side.BUY if price < mid else Side.SELL

            levels.append(GridLevel(price=price, side=side))

        self.grid_levels = levels
        logger.info("Grid computed: %d levels from %.2f to %.2f (spacing: %.2f)",
                     len(levels), self.config.lower_price, self.config.upper_price, spacing)
        return levels

    def place_grid_orders(self) -> int:
        """Place all grid orders on the exchange. Returns count placed."""
        # Set leverage first
        try:
            self.client.set_leverage(self.config.product_id, self.config.leverage)
        except Exception as e:
            logger.warning("Set leverage failed (may already be set): %s", e)

        placed = 0
        for level in self.grid_levels:
            if level.order_id:
                continue  # Already placed

            try:
                result = self.client.place_limit_order(
                    product_id=self.config.product_id,
                    side=level.side.value,
                    size=self.config.quantity_per_grid,
                    price=str(level.price),
                )
                level.order_id = str(result.get("id", ""))
                placed += 1
                logger.info("Grid order: %s %.4f @ %.2f (id: %s)",
                             level.side, self.config.quantity_per_grid, level.price, level.order_id)
            except Exception as e:
                logger.error("Failed to place grid order at %.2f: %s", level.price, e)

        logger.info("Placed %d/%d grid orders", placed, len(self.grid_levels))
        return placed

    def handle_fill(self, filled_order_id: str, fill_price: float) -> GridLevel | None:
        """Handle a filled order — place the opposite order one grid away.

        When a BUY fills → place SELL one grid above.
        When a SELL fills → place BUY one grid below.
        """
        filled_level = None
        for level in self.grid_levels:
            if level.order_id == filled_order_id:
                filled_level = level
                break

        if not filled_level:
            return None

        filled_level.filled = True
        filled_level.fill_price = fill_price

        # Find the grid spacing
        spacing = (self.config.upper_price - self.config.lower_price) / self.config.num_grids

        if filled_level.side == Side.BUY:
            # BUY filled → place SELL one grid above
            new_price = round(filled_level.price + spacing, 2)
            new_side = Side.SELL
            logger.info("BUY filled @ %.2f → placing SELL @ %.2f", fill_price, new_price)
        else:
            # SELL filled → place BUY one grid below
            new_price = round(filled_level.price - spacing, 2)
            new_side = Side.BUY
            # Record profit from completed cycle
            pnl = spacing * self.config.quantity_per_grid
            fee = fill_price * self.config.quantity_per_grid * 0.0002 * 2  # maker fee both sides
            net_pnl = pnl - fee
            self.total_pnl += net_pnl
            self.completed_trades.append(TradeRecord(
                symbol=self.config.symbol,
                side="SELL",
                quantity=self.config.quantity_per_grid,
                entry_price=filled_level.price - spacing,
                exit_price=fill_price,
                pnl=net_pnl,
                strategy="grid",
                fees=fee,
            ))
            logger.info("SELL filled @ %.2f → placing BUY @ %.2f (cycle P&L: %.2f)",
                         fill_price, new_price, net_pnl)

        # Place the new order
        if self.config.lower_price <= new_price <= self.config.upper_price:
            try:
                result = self.client.place_limit_order(
                    product_id=self.config.product_id,
                    side=new_side.value,
                    size=self.config.quantity_per_grid,
                    price=str(new_price),
                )
                # Update the level
                filled_level.order_id = str(result.get("id", ""))
                filled_level.price = new_price
                filled_level.side = new_side
                filled_level.filled = False
                return filled_level
            except Exception as e:
                logger.error("Failed to place replacement order: %s", e)

        return None

    def cancel_all_orders(self) -> None:
        """Cancel all grid orders."""
        try:
            self.client.cancel_all(self.config.product_id)
            for level in self.grid_levels:
                level.order_id = None
            logger.info("All grid orders cancelled")
        except Exception as e:
            logger.error("Cancel all failed: %s", e)

    def get_status(self) -> dict:
        """Get current grid status."""
        active_buys = sum(1 for l in self.grid_levels if l.side == Side.BUY and l.order_id and not l.filled)
        active_sells = sum(1 for l in self.grid_levels if l.side == Side.SELL and l.order_id and not l.filled)
        return {
            "total_levels": len(self.grid_levels),
            "active_buys": active_buys,
            "active_sells": active_sells,
            "completed_cycles": len(self.completed_trades),
            "total_pnl": round(self.total_pnl, 4),
            "grid_range": f"{self.config.lower_price}-{self.config.upper_price}",
            "spacing": round((self.config.upper_price - self.config.lower_price) / self.config.num_grids, 2),
        }

    def is_price_in_range(self, price: float) -> bool:
        """Check if current price is within grid range."""
        return self.config.lower_price <= price <= self.config.upper_price
