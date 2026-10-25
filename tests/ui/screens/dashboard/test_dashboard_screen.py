import unittest
from unittest.mock import Mock

from lxml import etree  # type: ignore

from edceleste.services.models.keybinds_model import EdAction, MissingKeybindsError
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
