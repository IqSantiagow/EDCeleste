import pytest
from textual.app import App

from edceleste.ui.screens.dashboard.widgets.ship_log.widget_ship_log_row import (
    WidgetShipLogRow,
)

pytestmark = pytest.mark.anyio


def ship_log_events(app: App) -> list[str]:
    # app.query() looks only at the first screen, the dashboard is pushed on top
    rail_rows = app.screen.query_one("#ship-log-rail").query(WidgetShipLogRow)
    return [row.entry.event for row in rail_rows]


async def test_should_show_an_event_written_to_the_journal_in_the_ship_log(edceleste):
    async with edceleste.run_app() as pilot:
        await edceleste.boot_to_dashboard(pilot)

        edceleste.append_journal_event("FSDJump")

        await edceleste.wait_until(
            pilot,
            lambda: "FSDJump" in ship_log_events(pilot.app),
            "FSDJump in the ship log",
        )
