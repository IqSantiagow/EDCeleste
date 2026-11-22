import unittest
from unittest.mock import Mock, patch

from textual.app import App
from textual.containers import Grid
from textual.widgets import Footer, Input, Static, TabbedContent
from textual.widgets._footer import FooterKey

from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen
from edceleste.ui.screens.dashboard.widgets.ship_log.ship_log_tabs import (
    SHIP_LOG_TAB_LOG,
    SHIP_LOG_TAB_STATION,
)
from edceleste.ui.screens.dashboard.widgets.ship_log.widget_station_market import (
    WidgetStationMarket,
)

TAB_SHIP = "ship-log-tab-ship"
TAB_ENG = "ship-log-tab-eng"
TAB_LDG = "ship-log-tab-ldg"


class FakeDashboardRepository:
    """Every stream ends at once, so the dashboard shows no data."""

    def __getattr__(self, name: str):
        if name.startswith("stream_"):

            async def empty_stream():
                return
                yield

            return empty_stream
        return Mock()


class DashboardApp(App):
    def on_mount(self) -> None:
        self.push_screen(
            DashboardScreen(
                dashboard_repository=FakeDashboardRepository(),
                settings_repository=Mock(),
                game_watcher_service=Mock(),
            )
        )


class DashboardCardKeysTest(unittest.IsolatedAsyncioTestCase):
    def run_dashboard(self):
        """Runs the dashboard without the DI container: the header becomes an
        empty Static and the station card does not stream."""
        header_patch = patch(
            "edceleste.ui.screens.dashboard.dashboard_screen.AppHeader", Static
        )
        station_patch = patch.object(WidgetStationMarket, "stream_station_market")
        self.addCleanup(header_patch.stop)
        self.addCleanup(station_patch.stop)
        header_patch.start()
        station_patch.start()
        return DashboardApp().run_test(size=(200, 50))

    def open_card_id(self, screen: DashboardScreen) -> str:
        return screen.active_ship_log_tab()

    def grid_is_expanded(self, screen: DashboardScreen) -> bool:
        return screen.query_one("#app-container", Grid).has_class("-ship-log-expanded")

    async def test_f4_opens_station_expanded_and_f1_goes_back_to_log(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            await pilot.press("f4")
            await pilot.pause()

            self.assertEqual(SHIP_LOG_TAB_STATION, self.open_card_id(screen))
            self.assertTrue(self.grid_is_expanded(screen))

            await pilot.press("f1")
            await pilot.pause()

            self.assertEqual(SHIP_LOG_TAB_LOG, self.open_card_id(screen))

    async def test_f3_opens_eng_card_with_no_data(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            await pilot.press("f3")
            await pilot.pause()

            self.assertEqual(TAB_ENG, self.open_card_id(screen))
            no_data_labels = screen.query(f"#{TAB_ENG} .ship-log-no-data")
            self.assertEqual(2, len(no_data_labels))

    async def test_every_f_key_opens_its_card_in_both_panels(self):
        expected_cards = {
            "f1": SHIP_LOG_TAB_LOG,
            "f2": TAB_SHIP,
            "f3": TAB_ENG,
            "f4": SHIP_LOG_TAB_STATION,
            "f5": "ship-log-tab-sys",
            "f6": "ship-log-tab-nav",
            "f7": TAB_LDG,
        }
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            for key, card_id in expected_cards.items():
                with self.subTest(key=key):
                    await pilot.press(key)
                    await pilot.pause()

                    for tabs in screen.query(TabbedContent):
                        self.assertEqual(card_id, tabs.active)

    async def test_a_card_key_keeps_the_typed_text_and_the_focus_in_the_input(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen
            comms_input = screen.query_one("#comms-input", Input)
            comms_input.focus()
            await pilot.press(*"jump to")

            await pilot.press("f2")
            await pilot.press(*" sol")
            await pilot.pause()

            self.assertEqual(TAB_SHIP, self.open_card_id(screen))
            self.assertIs(comms_input, screen.focused)
            self.assertEqual("jump to sol", comms_input.value)

    async def test_footer_shows_one_cards_entry_for_all_seven_keys(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            footer_entries = [
                (footer_key.key_display, footer_key.description)
                for footer_key in screen.query_one(Footer).query(FooterKey)
            ]

            self.assertIn(("f1–f7", "Cards"), footer_entries)
            shown_f_keys = [key for key, _ in footer_entries if key.startswith("f")]
            self.assertEqual(["f1–f7"], shown_f_keys)

    async def test_a_card_key_keeps_the_log_expanded_when_the_pilot_expanded_it(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            await pilot.press("ctrl+e")
            await pilot.press("f2")
            await pilot.pause()

            self.assertEqual(TAB_SHIP, self.open_card_id(screen))
            self.assertTrue(self.grid_is_expanded(screen))

    async def test_leaving_the_station_card_keeps_the_log_expanded_until_ctrl_e(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            await pilot.press("f4")
            await pilot.press("f2")
            await pilot.pause()

            self.assertTrue(self.grid_is_expanded(screen))

            await pilot.press("ctrl+e")
            await pilot.pause()

            self.assertFalse(self.grid_is_expanded(screen))

    async def test_ctrl_e_still_toggles_the_expanded_log(self):
        async with self.run_dashboard() as pilot:
            await pilot.pause()
            screen = pilot.app.screen

            await pilot.press("ctrl+e")
            await pilot.pause()

            self.assertTrue(self.grid_is_expanded(screen))


if __name__ == "__main__":
    unittest.main()
