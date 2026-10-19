import unittest
from unittest.mock import AsyncMock, Mock

from pydantic_ai import Tool

from edceleste.adapters.tools.perform_game_action import PerformGameAction
from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.services.exceptions.game_window_exception import (
    GameWindowNotFoundException,
)
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.models.game_stats import GameStatsSnapshot
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.reply_texts import REPLY_TEXTS
from edceleste.services.models.settings_model import GameActionsModel, SettingsModel
from edceleste.services.settings_service import SettingsService
from tests.use_cases.dashboard.game_stats_fixtures import (
    make_game_stats_snapshot,
    make_navigation_stats,
    make_ship_stats,
)


def make_stats(
    is_docked=False, is_landed=False, is_in_supercruise=False, is_in_fsd_jump=False
) -> GameStatsSnapshot:
    """A snapshot where only the four states that block actions can be set."""
    return make_game_stats_snapshot(
        navigation=make_navigation_stats(
            is_docked=is_docked,
            is_in_supercruise=is_in_supercruise,
            is_in_fsd_jump=is_in_fsd_jump,
        ),
        ship=make_ship_stats(is_landed=is_landed),
    )


# The name of a blocking state (as the reason sentence says it) and how to set it
BLOCKING_STATES = {
    "docked": dict(is_docked=True),
    "landed": dict(is_landed=True),
    "in supercruise": dict(is_in_supercruise=True),
    "in a hyperspace jump": dict(is_in_fsd_jump=True),
}


class TestPerformGameAction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # pydantic_ai validates the arguments against the signature, so the tool
        # is called with a real EdAction instead of a raw dict.
        self.keybind_service = Mock(spec=KeybindService)
        self.keybind_service.press_keys_for_action = AsyncMock()
        self.keybind_service.is_bound.return_value = True
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = Mock(
            spec=SettingsModel,
            game_actions=GameActionsModel(enabled=True),
        )
        self.game_state_protocol = Mock(spec=GameStateProtocol)
        self.game_state_protocol.get_game_stats.return_value = make_stats()
        self.tool = PerformGameAction(
            keybind_service=self.keybind_service,
            settings_service=self.settings_service,
            game_state_protocol=self.game_state_protocol,
        )

    async def test_should_press_keys_for_known_action_value(self):
        result = await self.tool.execute(EdAction.TOGGLE_FLIGHT_ASSIST)

        self.keybind_service.press_keys_for_action.assert_awaited_once_with(
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

        self.keybind_service.press_keys_for_action.assert_not_awaited()
        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            "Game actions are disabled by the user.",
        )

    async def test_should_return_error_when_action_has_no_keyboard_key(self):
        self.keybind_service.is_bound.return_value = False

        result = await self.tool.execute(EdAction.USE_SHIELD_CELL)

        self.keybind_service.is_bound.assert_called_once_with(EdAction.USE_SHIELD_CELL)
        self.keybind_service.press_keys_for_action.assert_not_awaited()
        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            "UseShieldCell is not bound to a keyboard key.",
        )

    async def test_should_return_error_when_game_window_not_found(self):
        self.keybind_service.press_keys_for_action.side_effect = (
            GameWindowNotFoundException()
        )

        result = await self.tool.execute(EdAction.LANDING_GEAR_TOGGLE)

        self.assertTrue(result.metadata["is_error"])
        self.assertEqual(
            result.return_value,
            "Game window not found, nothing was pressed.",
        )


class TestPerformGameActionAvailability(unittest.IsolatedAsyncioTestCase):
    """What the ship cannot do right now: nothing is pressed and the tool says
    why, as a normal answer (unavailable), not as an error."""

    def setUp(self):
        self.keybind_service = Mock(spec=KeybindService)
        self.keybind_service.press_keys_for_action = AsyncMock()
        self.keybind_service.is_bound.return_value = True
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = Mock(
            spec=SettingsModel,
            game_actions=GameActionsModel(enabled=True),
        )
        self.game_state_protocol = Mock(spec=GameStateProtocol)
        self.game_state_protocol.get_game_stats.return_value = make_stats()
        self.tool = PerformGameAction(
            keybind_service=self.keybind_service,
            settings_service=self.settings_service,
            game_state_protocol=self.game_state_protocol,
        )

    async def assert_refused_in_each_state(
        self, action: EdAction, action_name: str, state_names: list[str]
    ):
        """Puts the ship in each of the states one by one and checks that the
        tool refuses with the sentence for that state and presses nothing."""
        for state_name in state_names:
            with self.subTest(state=state_name):
                self.game_state_protocol.get_game_stats.return_value = make_stats(
                    **BLOCKING_STATES[state_name]
                )

                result = await self.tool.execute(action)

                self.assertEqual(
                    result.return_value,
                    f"{action_name} unavailable: the ship is {state_name}.",
                )
                self.assertEqual(
                    result.metadata, {"is_error": False, "unavailable": True}
                )
                self.keybind_service.press_keys_for_action.assert_not_awaited()

    async def test_should_have_a_prepared_reply_for_every_refusal(self):
        # Instinct says the part before the colon, so it must be a clip text
        for action in (
            EdAction.LANDING_GEAR_TOGGLE,
            EdAction.TOGGLE_CARGO_SCOOP,
            EdAction.DEPLOY_HARDPOINT_TOGGLE,
        ):
            with self.subTest(action=action):
                self.game_state_protocol.get_game_stats.return_value = make_stats(
                    is_docked=True
                )

                result = await self.tool.execute(action)

                self.assertIn(str(result.return_value).split(":")[0], REPLY_TEXTS)

    async def test_should_refuse_the_landing_gear_in_every_blocking_state(self):
        await self.assert_refused_in_each_state(
            EdAction.LANDING_GEAR_TOGGLE,
            "Landing gear",
            ["docked", "landed", "in supercruise", "in a hyperspace jump"],
        )

    async def test_should_refuse_the_cargo_scoop_in_every_blocking_state(self):
        await self.assert_refused_in_each_state(
            EdAction.TOGGLE_CARGO_SCOOP,
            "Cargo scoop",
            ["docked", "landed", "in supercruise", "in a hyperspace jump"],
        )

    async def test_should_refuse_the_hardpoints_when_docked_landed_or_in_a_hyperspace_jump(  # noqa: E501
        self,
    ):
        await self.assert_refused_in_each_state(
            EdAction.DEPLOY_HARDPOINT_TOGGLE,
            "Hardpoints",
            ["docked", "landed", "in a hyperspace jump"],
        )

    async def test_should_deploy_the_hardpoints_in_supercruise(self):
        self.game_state_protocol.get_game_stats.return_value = make_stats(
            is_in_supercruise=True
        )

        result = await self.tool.execute(EdAction.DEPLOY_HARDPOINT_TOGGLE)

        self.keybind_service.press_keys_for_action.assert_awaited_once_with(
            EdAction.DEPLOY_HARDPOINT_TOGGLE
        )
        self.assertEqual(result.metadata, {"is_error": False})

    async def test_should_press_the_landing_gear_when_no_blocking_state_is_true(self):
        result = await self.tool.execute(EdAction.LANDING_GEAR_TOGGLE)

        self.keybind_service.press_keys_for_action.assert_awaited_once_with(
            EdAction.LANDING_GEAR_TOGGLE
        )
        self.assertEqual(result.metadata, {"is_error": False})
        self.assertEqual(
            result.return_value, "Performed game action: LandingGearToggle"
        )

    async def test_should_press_an_action_that_has_no_row_whatever_the_state(self):
        self.game_state_protocol.get_game_stats.return_value = make_stats(
            is_docked=True,
            is_landed=True,
            is_in_supercruise=True,
            is_in_fsd_jump=True,
        )

        result = await self.tool.execute(EdAction.SET_SPEED_ZERO)

        self.keybind_service.press_keys_for_action.assert_awaited_once_with(
            EdAction.SET_SPEED_ZERO
        )
        self.assertEqual(result.metadata, {"is_error": False})

    async def test_should_name_the_first_true_state_when_several_are_true(self):
        self.game_state_protocol.get_game_stats.return_value = make_stats(
            is_docked=True, is_landed=True
        )

        result = await self.tool.execute(EdAction.LANDING_GEAR_TOGGLE)

        self.assertEqual(
            result.return_value, "Landing gear unavailable: the ship is docked."
        )

    async def test_should_report_disabled_game_actions_before_the_ship_state(self):
        self.settings_service.get_settings.return_value = Mock(
            spec=SettingsModel,
            game_actions=GameActionsModel(enabled=False),
        )
        self.game_state_protocol.get_game_stats.return_value = make_stats(
            is_docked=True
        )

        result = await self.tool.execute(EdAction.LANDING_GEAR_TOGGLE)

        self.assertEqual(result.return_value, "Game actions are disabled by the user.")
        self.assertEqual(result.metadata, {"is_error": True})

    async def test_should_ask_the_game_state_on_every_call(self):
        self.game_state_protocol.get_game_stats.side_effect = [
            make_stats(is_docked=True),
            make_stats(),
        ]

        first_result = await self.tool.execute(EdAction.LANDING_GEAR_TOGGLE)
        second_result = await self.tool.execute(EdAction.LANDING_GEAR_TOGGLE)

        self.assertTrue(first_result.metadata["unavailable"])
        self.assertEqual(second_result.metadata, {"is_error": False})
        self.assertEqual(self.game_state_protocol.get_game_stats.call_count, 2)
        self.keybind_service.press_keys_for_action.assert_awaited_once_with(
            EdAction.LANDING_GEAR_TOGGLE
        )


class TestPerformGameActionSchema(unittest.TestCase):
    """The tool no longer hand writes a JSON schema, pydantic_ai builds it."""

    def setUp(self):
        self.tool = PerformGameAction(
            keybind_service=Mock(spec=KeybindService),
            settings_service=Mock(spec=SettingsService),
            game_state_protocol=Mock(spec=GameStateProtocol),
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
