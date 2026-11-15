import unittest
from unittest.mock import Mock, PropertyMock, patch

from lxml import etree  # type: ignore
from textual.css.query import NoMatches

from edceleste.services.models.keybinds_model import EdAction, MissingKeybindsError
from edceleste.services.models.llm_status import LLMStatus
from edceleste.ui.screens.dashboard.dashboard_screen import DashboardScreen


class TestDashboardScreenLoadKeybinds(unittest.TestCase):
    def setUp(self):
        self.settings_repository = Mock()
        self.screen = DashboardScreen(
            dashboard_repository=Mock(),
            settings_repository=self.settings_repository,
            game_watcher_service=Mock(),
        )

    def load_keybinds(self):
        # The method is private, so Python renames it with the class name
        self.screen._DashboardScreen__load_keybinds()

    def test_should_load_keybinds_from_the_repository(self):
        self.load_keybinds()

        self.settings_repository.load_keybinds.assert_called_once_with()

    def test_should_log_and_not_raise_when_keybinds_file_is_missing(self):
        self.settings_repository.load_keybinds.side_effect = FileNotFoundError("none")

        with self.assertLogs(level="WARNING") as logs:
            self.load_keybinds()

        self.assertIn("none", logs.output[0])

    def test_should_log_and_not_raise_when_keybinds_file_is_broken(self):
        self.settings_repository.load_keybinds.side_effect = etree.XMLSyntaxError(
            "Document is empty", 0, 0, 0
        )

        with self.assertLogs(level="WARNING") as logs:
            self.load_keybinds()

        self.assertIn("Document is empty", logs.output[0])

    def test_should_log_missing_actions_and_not_raise_when_file_is_incomplete(self):
        self.settings_repository.load_keybinds.side_effect = MissingKeybindsError(
            {EdAction.LANDING_GEAR_TOGGLE}
        )

        with self.assertLogs(level="WARNING") as logs:
            self.load_keybinds()

        self.assertIn(EdAction.LANDING_GEAR_TOGGLE.value, logs.output[0])


class TestDashboardScreenShowLlmRepliesAndStatus(unittest.IsolatedAsyncioTestCase):
    def make_screen_with_llm_items(self, llm_items):
        async def stream_llm_items():
            for item in llm_items:
                yield item

        dashboard_repository = Mock()
        dashboard_repository.stream_llm_responses.return_value = stream_llm_items()
        return DashboardScreen(
            dashboard_repository=dashboard_repository,
            settings_repository=Mock(),
            game_watcher_service=Mock(),
        )

    async def show_llm_replies_and_status(self, screen, app_is_running):
        # @work wraps the method, __wrapped__ is the plain coroutine without a worker
        with patch.object(
            DashboardScreen, "app", new_callable=PropertyMock
        ) as app_of_screen:
            app_of_screen.return_value = Mock(is_running=app_is_running)
            await DashboardScreen.show_llm_replies_and_status.__wrapped__(screen)

    async def test_should_send_the_llm_status_to_the_input_row(self):
        screen = self.make_screen_with_llm_items([LLMStatus.THINKING])
        input_row = Mock()

        with patch.object(DashboardScreen, "query_one", return_value=input_row):
            await self.show_llm_replies_and_status(screen, app_is_running=True)

        self.assertEqual(LLMStatus.THINKING, input_row.llm_state)

    async def test_should_stop_without_error_when_the_app_is_closing(self):
        # The last IDLE comes after Textual started removing the widgets
        screen = self.make_screen_with_llm_items([LLMStatus.IDLE])

        with patch.object(
            DashboardScreen, "query_one", side_effect=NoMatches("#input-row")
        ):
            await self.show_llm_replies_and_status(screen, app_is_running=False)

    async def test_should_not_hide_a_missing_widget_while_the_app_is_running(self):
        screen = self.make_screen_with_llm_items([LLMStatus.IDLE])

        with patch.object(
            DashboardScreen, "query_one", side_effect=NoMatches("#input-row")
        ):
            with self.assertRaises(NoMatches):
                await self.show_llm_replies_and_status(screen, app_is_running=True)
