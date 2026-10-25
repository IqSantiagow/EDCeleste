from pydantic_ai import ToolReturn

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.exceptions.game_window_exception import (
    GameWindowNotFoundException,
)
from edceleste.services.keybinds_service import KeybindService
from edceleste.services.models.game_stats import GameStatsSnapshot
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.settings_service import SettingsService


class PerformGameAction(ToolProtocol):
    readable_name = "Perform Game Action"  # Its for UI display
    # Its for UI display, Will be used to fetch a specific action from the
    # tool call arguments, to later display it on UI.
    param_name = "action"
    name = "perform_game_action"

    def __init__(
        self,
        keybind_service: KeybindService,
        settings_service: SettingsService,
        game_state_protocol: GameStateProtocol,
    ) -> None:
        """Only stores the dependencies. The game_actions switch is read on
        every execute(), so turning it off works without a reload."""
        self.keybind_service = keybind_service
        self.settings_service = settings_service
        self.game_state_protocol = game_state_protocol

    # pydantic_ai sends the docstring below to the LLM as the tool description,
    # so it is written for the LLM, not for us. How it works: presses the key
    # bound to the action in the game. Four failures come back as a ToolReturn
    # with is_error=True in the metadata, so the LLM can tell the pilot: game
    # actions switched off in the settings, keybindings not loaded (broken or
    # incomplete file), action without a keyboard key, or game window not
    # found (then nothing is pressed). An action the ship
    # cannot do right now (see get_unavailable_reason) comes back with
    # unavailable=True and the reason as the text, nothing is pressed. The
    # LLM tells the pilot the reason in its own words, Instinct says the same
    # text as its reply. Any other error from KeybindService is raised as it is.
    async def execute(self, action: EdAction) -> ToolReturn:
        """Perform a game action based on the provided type of action"""
        if not self.settings_service.get_settings().game_actions.enabled:
            return ToolReturn(
                return_value="Game actions are disabled by the user.",
                metadata={"is_error": True},
            )

        try:
            is_bound = self.keybind_service.is_bound(action)
        except KeyError:
            return ToolReturn(
                return_value="Game actions are not available: the keybindings "
                "are not loaded.",
                metadata={"is_error": True},
            )

        if not is_bound:
            return ToolReturn(
                return_value=f"{action.value} is not bound to a keyboard key.",
                metadata={"is_error": True},
            )

        unavailable_reason = self.get_unavailable_reason(
            action, self.game_state_protocol.get_game_stats()
        )
        if unavailable_reason is not None:
            return ToolReturn(
                return_value=unavailable_reason,
                metadata={"is_error": False, "unavailable": True},
            )

        try:
            await self.keybind_service.press_keys_for_action(action)
        except GameWindowNotFoundException:
            return ToolReturn(
                return_value="Game window not found, nothing was pressed.",
                metadata={"is_error": True},
            )

        return ToolReturn(
            return_value=f"Performed game action: {action.value}",
            metadata={"is_error": False},
        )

    def get_unavailable_reason(
        self, action: EdAction, game_stats: GameStatsSnapshot
    ) -> str | None:
        """The table of what the ship cannot do. Decides from game_stats only,
        reads no file, presses nothing and raises nothing.

        The states that block an action come from game_stats and are checked in
        this order: "docked" (navigation.is_docked), "landed" (ship.is_landed),
        "in supercruise" (navigation.is_in_supercruise) and "in a hyperspace
        jump" (navigation.is_in_fsd_jump).
        - Landing gear ("Landing gear") and cargo scoop ("Cargo scoop"): blocked
          by all four states.
        - Hardpoints ("Hardpoints"): blocked by docked, landed and a hyperspace
          jump. In supercruise they are allowed on purpose, as in issue #113.
        - Every other action has no row, so it is always possible.
        A new action that depends on the ship state is a new case in the match
        below.

        Returns None when the action is possible. Otherwise returns one sentence
        for the pilot and the LLM: "<name> unavailable: the ship is <state>.",
        e.g. "Landing gear unavailable: the ship is in supercruise." The first
        state of the order above that is true gives the reason.
        """
        states = {
            "docked": game_stats.navigation.is_docked,
            "landed": game_stats.ship.is_landed,
            "in supercruise": game_stats.navigation.is_in_supercruise,
            "in a hyperspace jump": game_stats.navigation.is_in_fsd_jump,
        }
        match action:
            case EdAction.LANDING_GEAR_TOGGLE:
                action_name = "Landing gear"
                blocking_states = [
                    "docked",
                    "landed",
                    "in supercruise",
                    "in a hyperspace jump",
                ]
            case EdAction.TOGGLE_CARGO_SCOOP:
                action_name = "Cargo scoop"
                blocking_states = [
                    "docked",
                    "landed",
                    "in supercruise",
                    "in a hyperspace jump",
                ]
            case EdAction.DEPLOY_HARDPOINT_TOGGLE:
                action_name = "Hardpoints"
                blocking_states = ["docked", "landed", "in a hyperspace jump"]
            case _:
                return None

        for state_name in blocking_states:
            if states[state_name]:
                return f"{action_name} unavailable: the ship is {state_name}."
        return None
