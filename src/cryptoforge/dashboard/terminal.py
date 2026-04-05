"""Rich terminal dashboard — lightweight live monitoring."""

import logging
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger("cryptoforge.dashboard")


class TerminalDashboard:
    """Live terminal dashboard using Rich library."""

    def __init__(self):
        self.console = Console()
        self._data = {
            "mode": "testnet",
            "grid_status": {},
            "scalper_status": {},
            "positions": [],
            "recent_trades": [],
            "pnl": 0.0,
            "alerts": [],
            "balance": 0.0,
        }

    def update(self, key: str, value) -> None:
        self._data[key] = value

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._header(), size=3),
            Layout(name="body"),
        )
        layout["body"].split_row(
            Layout(self._grid_panel(), ratio=1),
            Layout(self._trades_panel(), ratio=1),
        )
        return layout

    def _header(self) -> Panel:
        mode = self._data.get("mode", "testnet").upper()
        pnl = self._data.get("pnl", 0)
        balance = self._data.get("balance", 0)
        color = "green" if pnl >= 0 else "red"
        text = Text()
        text.append("CRYPTOFORGE", style="bold cyan")
        text.append(f" | {mode}", style="dim")
        text.append(f" | P&L: ", style="dim")
        text.append(f"₹{pnl:+,.4f}", style=f"bold {color}")
        text.append(f" | Balance: ₹{balance:,.2f}", style="dim")
        text.append(f" | {datetime.now().strftime('%H:%M:%S')}", style="dim")
        return Panel(text, style="blue")

    def _grid_panel(self) -> Panel:
        status = self._data.get("grid_status", {})
        table = Table(title="Grid Bot", show_header=True, header_style="bold cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value", justify="right")

        for key, val in status.items():
            table.add_row(key, str(val))

        # Add alerts
        alerts = self._data.get("alerts", [])
        for alert in alerts[-5:]:
            table.add_row(f"[yellow]ALERT[/yellow]", str(alert))

        return Panel(table, title="Strategies", border_style="blue")

    def _trades_panel(self) -> Panel:
        trades = self._data.get("recent_trades", [])
        table = Table(title="Recent Trades", show_header=True, header_style="bold cyan")
        table.add_column("Time", style="dim", width=8)
        table.add_column("Side", width=4)
        table.add_column("Symbol", width=8)
        table.add_column("P&L", justify="right", width=10)

        for trade in trades[-10:]:
            pnl = trade.pnl if hasattr(trade, "pnl") else trade.get("pnl", 0)
            side = trade.side if hasattr(trade, "side") else trade.get("side", "")
            symbol = trade.symbol if hasattr(trade, "symbol") else trade.get("symbol", "")
            color = "green" if pnl >= 0 else "red"
            side_color = "green" if side.upper() == "BUY" else "red"

            t = trade.entry_time if hasattr(trade, "entry_time") else datetime.now()
            time_str = t.strftime("%H:%M:%S") if hasattr(t, "strftime") else str(t)[:8]

            table.add_row(
                time_str,
                f"[{side_color}]{side.upper()[:4]}[/{side_color}]",
                symbol[:8],
                f"[{color}]{pnl:+,.4f}[/{color}]",
            )

        return Panel(table, title="Trade Log", border_style="blue")

    def print_status(self) -> None:
        """Print a one-shot status update."""
        self.console.print(self.render())
