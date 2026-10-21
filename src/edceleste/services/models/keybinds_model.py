import re
from enum import StrEnum

from pydantic import BaseModel, Field


class EdAction(StrEnum):
    """
    Used for mapping keybinds from XML
    """

    # Flight & navigation
    TOGGLE_FLIGHT_ASSIST = "ToggleFlightAssist"
    USE_BOOST_JUICE = "UseBoostJuice"
    SUPERCRUISE = "Supercruise"
    HYPERSPACE = "Hyperspace"
    HYPER_SUPER_COMBINATION = "HyperSuperCombination"
    SET_SPEED_ZERO = "SetSpeedZero"
    SET_SPEED_50 = "SetSpeed50"
    SET_SPEED_75 = "SetSpeed75"
    SET_SPEED_100 = "SetSpeed100"
    # Power distribution (pips)
    INCREASE_ENGINES_POWER = "IncreaseEnginesPower"
    INCREASE_WEAPONS_POWER = "IncreaseWeaponsPower"
    INCREASE_SYSTEMS_POWER = "IncreaseSystemsPower"
    RESET_POWER_DISTRIBUTION = "ResetPowerDistribution"
    # Targeting & combat
    SELECT_TARGET = "SelectTarget"
    CYCLE_NEXT_TARGET = "CycleNextTarget"
    CYCLE_PREVIOUS_TARGET = "CyclePreviousTarget"
    SELECT_HIGHEST_THREAT = "SelectHighestThreat"
    CYCLE_NEXT_SUBSYSTEM = "CycleNextSubsystem"
    CYCLE_PREVIOUS_SUBSYSTEM = "CyclePreviousSubsystem"
    CYCLE_FIRE_GROUP_NEXT = "CycleFireGroupNext"
    CYCLE_FIRE_GROUP_PREVIOUS = "CycleFireGroupPrevious"
    DEPLOY_HARDPOINT_TOGGLE = "DeployHardpointToggle"
    # Defence & utilities
    USE_SHIELD_CELL = "UseShieldCell"
    FIRE_CHAFF_LAUNCHER = "FireChaffLauncher"
    DEPLOY_HEAT_SINK = "DeployHeatSink"
    SHIP_SPOT_LIGHT_TOGGLE = "ShipSpotLightToggle"
    NIGHT_VISION_TOGGLE = "NightVisionToggle"
    # Ship systems
    TOGGLE_CARGO_SCOOP = "ToggleCargoScoop"
    LANDING_GEAR_TOGGLE = "LandingGearToggle"
    EJECT_ALL_CARGO = "EjectAllCargo"
    # UI, panels, maps & scanners
    UI_FOCUS = "UIFocus"
    FOCUS_LEFT_PANEL = "FocusLeftPanel"
    FOCUS_COMMS_PANEL = "FocusCommsPanel"
    FOCUS_RADAR_PANEL = "FocusRadarPanel"
    FOCUS_RIGHT_PANEL = "FocusRightPanel"
    QUICK_COMMS_PANEL = "QuickCommsPanel"
    GALAXY_MAP_OPEN = "GalaxyMapOpen"
    SYSTEM_MAP_OPEN = "SystemMapOpen"
    EXPLORATION_FSS_ENTER = "ExplorationFSSEnter"
    RADAR_INCREASE_RANGE = "RadarIncreaseRange"
    RADAR_DECREASE_RANGE = "RadarDecreaseRange"


# TODO: Implement popup to set up required keybinds if they are missing from the XML
# file. This will allow users to customize their keybinds and ensure that all
# necessary actions are mapped to keys.


class MissingKeybindsError(Exception):
    """Raised when a loaded ``.binds`` file does not cover every ``EdAction``."""

    def __init__(self, missing: set[EdAction]) -> None:
        """Keeps the missing actions in self.missing for the caller and puts
        their names, sorted A-Z, into the error message."""
        self.missing = missing
        names = ", ".join(sorted(action.value for action in missing))
        super().__init__(f"Missing required keybinds: {names}")


class Keybind(BaseModel):
    key: str | None = Field(
        default=None,
        description="The keyboard key, None when the action has no keyboard binding",
    )
    action: EdAction = Field(..., description="The action associated with the keybind")
    modifiers: list[str] = Field(
        default_factory=list,
        description="Keys held down while the key is pressed, e.g. LeftShift",
    )


def action_in_plain_words(action: EdAction) -> str:
    """The action's name as words for the pilot, e.g. in a warning. The
    CamelCase value is split into words, only the first word keeps its capital
    letter, a run of capitals stays as it is ("UI", "FSS") and a number is its
    own word. UseShieldCell -> "Use shield cell", UIFocus -> "UI focus",
    SetSpeed50 -> "Set speed 50". Pure function."""
    words = re.findall(r"[A-Z]{2,}(?=[A-Z][a-z]|\d|$)|[A-Z][a-z]*|\d+", action.value)
    first_word, *other_words = words
    other_words = [word if word.isupper() else word.lower() for word in other_words]
    return " ".join([first_word, *other_words])


# pynput names that differ from the game's key names (lowercase, "Key_" cut).
# The generic "shift", "ctrl" and "alt" are the left key.
PYNPUT_TO_GAME_KEY_NAMES = {
    "shift": "leftshift",
    "shift_l": "leftshift",
    "shift_r": "rightshift",
    "ctrl": "leftcontrol",
    "ctrl_l": "leftcontrol",
    "ctrl_r": "rightcontrol",
    "alt": "leftalt",
    "alt_l": "leftalt",
    "alt_r": "rightalt",
    "alt_gr": "rightalt",
    "up": "uparrow",
    "down": "downarrow",
    "left": "leftarrow",
    "right": "rightarrow",
    "esc": "escape",
}


def find_keybind_using_key(
    pynput_key_name: str, keybinds: list[Keybind]
) -> Keybind | None:
    """The first game keybind that uses the key, as its key or as one of its
    modifiers, None when the key is free. pynput_key_name is as pynput prints
    it: "Key.f9", "Key.page_up", "'k'", "Button.x1". The names are compared in
    lowercase without underscores. A mouse button is never found, the game's
    keyboard keybinds do not use one. Keys like "," that the game spells out
    ("Comma") are not matched."""
    name = pynput_key_name.removeprefix("Key.").strip("'").lower()
    game_key_name = PYNPUT_TO_GAME_KEY_NAMES.get(name, name.replace("_", ""))
    for keybind in keybinds:
        used_keys = [keybind.key, *keybind.modifiers]
        if game_key_name in [key.lower() for key in used_keys if key is not None]:
            return keybind
    return None
