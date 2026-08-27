import unittest
from unittest.mock import AsyncMock, Mock

from adapters.tools.perform_game_action import PerformGameAction
from services.keybinds_service import KeybindService
from services.models.keybinds_model import EdAction


class TestPerformGameAction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The MCP server calls the handler with a single positional dict, so the
        # tool has to accept exactly that shape.
        self.keybind_service = Mock(spec=KeybindService)
        self.keybind_service.perform_action = AsyncMock()
        self.tool = PerformGameAction(keybind_service=self.keybind_service)

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


if __name__ == "__main__":
    unittest.main()
