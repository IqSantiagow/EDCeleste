import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.adapters.tools.perform_game_action import PerformGameAction
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.settings_model import GameActionsModel, SettingsModel
from edceleste.services.settings_service import SettingsService


class TestPerformGameAction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The MCP server calls the handler with a single positional dict, so the
        # tool has to accept exactly that shape.
        self.keybind_service = Mock(spec=KeybindService)
        self.keybind_service.perform_action = AsyncMock()
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = Mock(
            spec=SettingsModel,
            game_actions=GameActionsModel(enabled=True),
        )
        self.tool = PerformGameAction(
            keybind_service=self.keybind_service,
            settings_service=self.settings_service,
        )

    async def test_should_perform_action_for_known_action_value(self):
        result = await self.tool.execute({"action": "ToggleFlightAssist"})

        self.keybind_service.perform_action.assert_awaited_once_with(
            EdAction.TOGGLE_FLIGHT_ASSIST
        )
        self.assertFalse(result["is_error"])
        self.assertEqual(
            result["content"][0]["text"],
            "Performed game action: ToggleFlightAssist",
        )

    async def test_should_return_error_when_action_argument_is_missing(self):
        result = await self.tool.execute({})

        self.keybind_service.perform_action.assert_not_awaited()
        self.assertTrue(result["is_error"])

    async def test_should_return_error_for_unknown_action_value(self):
        result = await self.tool.execute({"action": "NotARealAction"})

        self.keybind_service.perform_action.assert_not_awaited()
        self.assertTrue(result["is_error"])

    async def test_should_return_error_when_game_actions_are_disabled(self):
        self.settings_service.get_settings.return_value = Mock(
            spec=SettingsModel,
            game_actions=GameActionsModel(enabled=False),
        )

        result = await self.tool.execute({"action": "ToggleFlightAssist"})

        self.keybind_service.perform_action.assert_not_awaited()
        self.assertTrue(result["is_error"])
        self.assertEqual(
            result["content"][0]["text"],
            "Game actions are disabled by the user.",
        )


if __name__ == "__main__":
    unittest.main()
