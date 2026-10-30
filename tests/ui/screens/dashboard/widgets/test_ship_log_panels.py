import unittest
from datetime import datetime
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widget import Widget

from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    CATEGORY_NAV,
    CATEGORY_OTHER,
    JournalLogViewModel,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_extended_panel import (  # noqa: E501
    WidgetShipLogExtendedPanel,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_extended_row import (  # noqa: E501
    WidgetShipLogExtendedRow,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_panel import (
    MAX_ROWS,
    WidgetShipLogPanel,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_row import (
    WidgetShipLogRow,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_station_market import (
    WidgetStationMarket,
)

BURST_SIZE = 210


def make_entry(system: str, category: str = CATEGORY_NAV) -> JournalLogViewModel:
    """One ship log entry whose SYSTEM column is `system`."""
    return JournalLogViewModel(
        timestamp=datetime(2026, 10, 29, 12, 0, 0),
        event="FSDJump",
        system=system,
        details="",
        category=category,
    )


class PanelApp(App):
    """Shows one ship log panel and nothing else."""

    def __init__(self, panel: Widget) -> None:
        super().__init__()
        self.panel = panel

    def compose(self) -> ComposeResult:
        yield self.panel


class ShipLogPanelsBurstTest(unittest.IsolatedAsyncioTestCase):
    async def check_burst_keeps_only_the_newest_rows(self, panel, row_type) -> None:
        """Adds BURST_SIZE jumps in one go, like a journal write with 210 lines,
        and checks that only the newest MAX_ROWS rows are left on screen."""
        async with PanelApp(panel).run_test() as pilot:
            await pilot.pause(0.2)

            for number in range(BURST_SIZE):
                panel.add_entry(make_entry(f"System {number}"))
            await pilot.pause(0.5)

            rows = list(panel.query(row_type))
            self.assertEqual(len(rows), MAX_ROWS)
            self.assertEqual(rows[0].entry.system, f"System {BURST_SIZE - MAX_ROWS}")
            self.assertEqual(rows[-1].entry.system, f"System {BURST_SIZE - 1}")
            self.assertEqual(panel.total_events_count, BURST_SIZE)

    async def test_narrow_panel_keeps_only_the_newest_rows_after_a_burst(self):
        await self.check_burst_keeps_only_the_newest_rows(
            WidgetShipLogPanel(), WidgetShipLogRow
        )

    async def test_extended_panel_keeps_only_the_newest_rows_after_a_burst(self):
        # The station card inside the extended panel streams from the DI
        # container, which this test does not need.
        with patch.object(WidgetStationMarket, "stream_station_market"):
            await self.check_burst_keeps_only_the_newest_rows(
                WidgetShipLogExtendedPanel(), WidgetShipLogExtendedRow
            )

    async def test_dropped_entry_hidden_by_the_filter_does_not_remove_a_row(self):
        """The oldest entry is OTHER, the filter shows only NAV, so no row
        belongs to it and all MAX_ROWS NAV rows have to stay."""
        panel = WidgetShipLogPanel()
        async with PanelApp(panel).run_test() as pilot:
            await pilot.pause(0.2)
            panel.active_filter = CATEGORY_NAV
            panel.add_entry(make_entry("Hidden", CATEGORY_OTHER))
            for number in range(MAX_ROWS):
                panel.add_entry(make_entry(f"System {number}"))
            await pilot.pause(0.5)

            rows = list(panel.query(WidgetShipLogRow))
            self.assertEqual(len(rows), MAX_ROWS)
            self.assertEqual(rows[0].entry.system, "System 0")


if __name__ == "__main__":
    unittest.main()
