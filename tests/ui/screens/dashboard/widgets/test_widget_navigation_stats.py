import asyncio
import unittest

from textual.app import App, ComposeResult
from textual.widgets import Label

from edceleste.ui.screens.dashboard.view_models.game_stats_view_model import (
    NavigationStatsViewModel,
)
from edceleste.ui.screens.dashboard.widgets.stats import widget_navigation_stats
from edceleste.ui.screens.dashboard.widgets.stats.widget_navigation_stats import (
    WidgetNavigationStats,
)


WIDGET_LOGGER_NAME = widget_navigation_stats.__name__


def make_navigation_stats(system: str) -> NavigationStatsViewModel:
    """Navigation stats with only the system filled, the rest is empty."""
    return NavigationStatsViewModel(
        system=system,
        security="",
        body="",
        status="",
        allegiance="",
        government="",
        economy="",
        second_economy="",
        population=0,
        route_next_system="",
        route_remaining_jumps=0,
    )


class FakeDashboardRepository:
    """Gives the widget the stats that the test puts into `stats_queue`."""

    def __init__(self) -> None:
        self.stats_queue: asyncio.Queue[NavigationStatsViewModel] = asyncio.Queue()

    async def stream_navigation_stats(self):
        while True:
            yield await self.stats_queue.get()


class NavigationStatsApp(App):
    """Shows only the NAVIGATION card."""

    def __init__(self, repository: FakeDashboardRepository) -> None:
        super().__init__()
        self.repository = repository

    def compose(self) -> ComposeResult:
        yield WidgetNavigationStats(self.repository)


class WidgetNavigationStatsTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_stats_rewrite_the_labels_while_the_card_is_on_screen(
        self,
    ) -> None:
        repository = FakeDashboardRepository()

        async with NavigationStatsApp(repository).run_test() as pilot:
            await repository.stats_queue.put(make_navigation_stats("Sol"))
            await pilot.pause(0.2)
            await repository.stats_queue.put(make_navigation_stats("Colonia"))
            await pilot.pause(0.2)

            system_label = pilot.app.query_one("#navigation-system", Label)
            self.assertEqual(str(system_label.render()), "Colonia")

    async def test_stats_arriving_after_the_card_is_gone_do_not_crash_the_app(
        self,
    ) -> None:
        repository = FakeDashboardRepository()
        app = NavigationStatsApp(repository)

        async with app.run_test() as pilot:
            await repository.stats_queue.put(make_navigation_stats("Sol"))
            await pilot.pause(0.2)

            card = app.query_one(WidgetNavigationStats)
            for label in card.query(Label):
                await label.remove()
            with self.assertLogs(WIDGET_LOGGER_NAME, level="WARNING") as logs:
                await repository.stats_queue.put(make_navigation_stats("Colonia"))
                await pilot.pause(0.2)

            self.assertTrue(app.is_running)
            self.assertIsNone(app._exception)
            self.assertIn("NAVIGATION card is gone", logs.output[0])
