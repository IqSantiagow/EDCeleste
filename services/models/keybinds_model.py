from pydantic import BaseModel, Field

REQUIRED_KEYBINDS = (
    # Flight & navigation
    "ToggleFlightAssist",
    "UseBoostJuice",
    "Supercruise",
    "Hyperspace",
    "HyperSuperCombination",
    "SetSpeedZero",
    "SetSpeed50",
    "SetSpeed75",
    "SetSpeed100",
    # Power distribution (pips)
    "IncreaseEnginesPower",
    "IncreaseWeaponsPower",
    "IncreaseSystemsPower",
    "ResetPowerDistribution",
    # Targeting & combat
    "SelectTarget",
    "CycleNextTarget",
    "CyclePreviousTarget",
    "SelectHighestThreat",
    "CycleNextSubsystem",
    "CyclePreviousSubsystem",
    "CycleFireGroupNext",
    "CycleFireGroupPrevious",
    "DeployHardpointToggle",
    # Defence & utilities
    "UseShieldCell",
    "FireChaffLauncher",
    "DeployHeatSink",
    "ShipSpotLightToggle",
    "NightVisionToggle",
    # Ship systems
    "ToggleCargoScoop",
    "LandingGearToggle",
    "EjectAllCargo",
    # UI, panels, maps & scanners
    "UIFocus",
    "FocusLeftPanel",
    "FocusCommsPanel",
    "FocusRadarPanel",
    "FocusRightPanel",
    "QuickCommsPanel",
    "GalaxyMapOpen",
    "SystemMapOpen",
    "ExplorationFSSEnter",
    "RadarIncreaseRange",
    "RadarDecreaseRange",
)

# TODO: Implement popup to set up required keybinds if they are missing from the XML
# file. This will allow users to customize their keybinds and ensure that all
# necessary actions are mapped to keys.


class Keybind(BaseModel):
    key: str = Field(..., description="The key associated with the keybind")
    action: str = Field(..., description="The action associated with the keybind")
    # modifier_key: str = Field(
    #     default="", description="The modifier key associated with the keybind"
    # ) TODO: Implement modifier key support in the future
