import unittest
from unittest.mock import AsyncMock, Mock

from pydantic_ai import Tool

from edceleste.adapters.tools.perform_game_action import PerformGameAction
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.settings_model import GameActionsModel, SettingsModel
from edceleste.services.settings_service import SettingsService


class TestPerformGameAction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # pydantic_ai validates the arguments against the signature, so the tool
        # is called with a real EdAction instead of a raw dict.
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
        result = await self.tool.execute(EdAction.TOGGLE_FLIGHT_ASSIST)

        self.keybind_service.perform_action.assert_awaited_once_with(
            EdAction.TOGGLE_FLIGHT_ASSIST
        )
        self.assertFalse(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            "Performed game action: ToggleFlightAssist",
        )

    async def test_should_return_error_when_game_actions_are_disabled(self):
        self.settings_service.get_settings.return_value = Mock(
            spec=SettingsModel,
            game_actions=GameActionsModel(enabled=False),
        )

        result = await self.tool.execute(EdAction.TOGGLE_FLIGHT_ASSIST)

        self.keybind_service.perform_action.assert_not_awaited()
        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            "Game actions are disabled by the user.",
        )


class TestPerformGameActionSchema(unittest.TestCase):
    """The tool no longer hand writes a JSON schema, pydantic_ai builds it."""

    def setUp(self):
        self.tool = PerformGameAction(
            keybind_service=Mock(spec=KeybindService),
            settings_service=Mock(spec=SettingsService),
        )
        self.pydantic_tool = Tool(self.tool.execute, name=self.tool.name)

    def test_should_take_description_from_the_docstring(self):
        self.assertEqual(
            self.pydantic_tool.description,
            "Perform a game action based on the provided type of action",
        )

    def test_should_require_action_argument(self):
        schema = self.pydantic_tool.function_schema.json_schema

        self.assertEqual(schema["required"], ["action"])

    def test_should_list_every_ed_action_in_the_schema(self):
        schema = self.pydantic_tool.function_schema.json_schema

        self.assertEqual(
            schema["$defs"]["EdAction"]["enum"],
            [action.value for action in EdAction],
        )


if __name__ == "__main__":
    unittest.main()
