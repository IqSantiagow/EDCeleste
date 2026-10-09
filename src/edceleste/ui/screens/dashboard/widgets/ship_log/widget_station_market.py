from dependency_injector.wiring import Provide, inject
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Label

from edceleste.containers.main_container import Container
from edceleste.ui.screens.dashboard.ed_dashboard_repository import EdDashboardRepository
from edceleste.ui.screens.dashboard.view_models.station_market_view_model import (
    MAX_BLOCKS,
    StationMarketViewModel,
)

TABLE_ID = "station-market-table"
HEADER_ID = "station-market-header"
MESSAGE_ID = "station-market-message"

# (heading, width). The bar column fits ten blocks either side of the zero axis.
STATION_MARKET_COLUMNS = (
    ("COMMODITY", 24),
    ("CATEGORY", 14),
    ("BUY", 9),
    ("SELL", 10),
    ("STOCK", 9),
    ("DEMAND", 9),
    ("GAL AVG", 10),
    ("VS GALACTIC AVG", MAX_BLOCKS * 2 + 1),
    ("DELTA / T", 9),
    ("NOTE", 20),
)


class WidgetStationMarket(Vertical):
    @inject
    def __init__(
        self,
        ed_dashboard_repository: EdDashboardRepository = Provide[
            Container.ed_dashboard_repository
        ],
        **kwargs,
    ) -> None:
        """The repository comes from the DI container, because the ship log
        panel creates this widget without arguments."""
        super().__init__(**kwargs)
        self.ed_dashboard_repository = ed_dashboard_repository

    def compose(self) -> ComposeResult:
        """Empty station header, empty message label and an empty table. The
        columns are added in on_mount(), the content in show_market()."""
        yield Label("", id=HEADER_ID)
        yield Label("", id=MESSAGE_ID, classes="ship-log-no-data")
        yield DataTable(id=TABLE_ID, cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        """Adds the STATION_MARKET_COLUMNS to the table and starts the worker
        that keeps the market up to date."""
        table = self.query_one(f"#{TABLE_ID}", DataTable)
        for column_heading, column_width in STATION_MARKET_COLUMNS:
            table.add_column(column_heading, width=column_width)
        self.stream_station_market()

    @work
    async def stream_station_market(self) -> None:
        """Textual worker that runs as long as the widget lives. Every new
        market from the repository is drawn at once by show_market()."""
        async for market in self.ed_dashboard_repository.stream_station_market():
            self.show_market(market)

    def show_market(self, market: StationMarketViewModel) -> None:
        """Puts the market header (station name, commodity count) on top. A
        market with a message (not docked, no commodities market, old market
        data) shows only the message and hides the table. Without a message
        the table is shown and all its rows are replaced with the new ones."""
        self.query_one(f"#{HEADER_ID}", Label).update(market.header)

        message_label = self.query_one(f"#{MESSAGE_ID}", Label)
        message_label.update(market.message)
        message_label.display = bool(market.message)

        table = self.query_one(f"#{TABLE_ID}", DataTable)
        table.display = not market.message
        # clear() keeps the columns added on mount.
        table.clear()
        for row in market.rows:
            table.add_row(
                row.commodity,
                row.category,
                row.buy,
                row.sell,
                row.stock,
                row.demand,
                row.galactic_average,
                row.vs_galactic_average,
                row.delta,
                row.note,
            )
