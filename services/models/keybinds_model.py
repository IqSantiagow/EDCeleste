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
        self.missing = missing
        names = ", ".join(sorted(action.value for action in missing))
        super().__init__(f"Missing required keybinds: {names}")


class Keybind(BaseModel):
    key: str = Field(..., description="The key associated with the keybind")
    action: EdAction = Field(..., description="The action associated with the keybind")
    # modifier_key: str = Field(
    #     default="", description="The modifier key associated with the keybind"
    # ) TODO: Implement modifier key support in the future
