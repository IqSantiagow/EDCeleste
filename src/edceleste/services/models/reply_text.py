from enum import StrEnum


class ReplyTexts(StrEnum):
    """Every short reply the pilot can hear, one member per text. The value is
    the sentence that is spoken and written to COMMS. Celeste speaks all of them
    ahead of time in the voice of a profile (one wav file per member, see
    build_reply_wav_file_name), so playing one is just opening a file. A member
    added here is missing in the folders of the old profiles, so the app speaks
    it live until the replies are made again."""

    # Toggles: done, already done, unavailable
    FLIGHT_ASSIST_ON = "Flight assist on"
    FLIGHT_ASSIST_OFF = "Flight assist off"
    FLIGHT_ASSIST_ALREADY_ON = "Flight assist already on"
    FLIGHT_ASSIST_ALREADY_OFF = "Flight assist already off"
    HARDPOINTS_DEPLOYED = "Hardpoints deployed"
    HARDPOINTS_RETRACTED = "Hardpoints retracted"
    HARDPOINTS_ALREADY_DEPLOYED = "Hardpoints already deployed"
    HARDPOINTS_ALREADY_RETRACTED = "Hardpoints already retracted"
    HARDPOINTS_UNAVAILABLE = "Hardpoints unavailable"
    LANDING_GEAR_DEPLOYED = "Landing gear deployed"
    LANDING_GEAR_RETRACTED = "Landing gear retracted"
    LANDING_GEAR_ALREADY_DEPLOYED = "Landing gear already deployed"
    LANDING_GEAR_ALREADY_RETRACTED = "Landing gear already retracted"
    LANDING_GEAR_UNAVAILABLE = "Landing gear unavailable"
    CARGO_SCOOP_DEPLOYED = "Cargo scoop deployed"
    CARGO_SCOOP_RETRACTED = "Cargo scoop retracted"
    CARGO_SCOOP_ALREADY_DEPLOYED = "Cargo scoop already deployed"
    CARGO_SCOOP_ALREADY_RETRACTED = "Cargo scoop already retracted"
    CARGO_SCOOP_UNAVAILABLE = "Cargo scoop unavailable"
    LIGHTS_ON = "Lights on"
    LIGHTS_OFF = "Lights off"
    LIGHTS_ALREADY_ON = "Lights already on"
    LIGHTS_ALREADY_OFF = "Lights already off"
    NIGHT_VISION_ON = "Night vision on"
    NIGHT_VISION_OFF = "Night vision off"
    NIGHT_VISION_ALREADY_ON = "Night vision already on"
    NIGHT_VISION_ALREADY_OFF = "Night vision already off"

    # Flight
    BOOSTING = "Boosting"
    ENGAGING_SUPERCRUISE = "Engaging supercruise"
    JUMPING_TO_NEXT_SYSTEM = "Jumping to the next system"
    ENGAGING_FRAME_SHIFT_DRIVE = "Engaging frame shift drive"
    THROTTLE_ZERO = "Throttle zero"
    THROTTLE_FIFTY_PERCENT = "Throttle fifty percent"
    THROTTLE_SEVENTY_FIVE_PERCENT = "Throttle seventy five percent"
    FULL_THROTTLE = "Full throttle"

    # Power distribution
    MORE_POWER_TO_ENGINES = "More power to engines"
    MORE_POWER_TO_WEAPONS = "More power to weapons"
    MORE_POWER_TO_SYSTEMS = "More power to systems"
    POWER_DISTRIBUTION_RESET = "Power distribution reset"

    # Targeting
    TARGET_SELECTED = "Target selected"
    NEXT_TARGET = "Next target"
    PREVIOUS_TARGET = "Previous target"
    HIGHEST_THREAT_TARGETED = "Highest threat targeted"
    NEXT_SUBSYSTEM = "Next subsystem"
    PREVIOUS_SUBSYSTEM = "Previous subsystem"
    NEXT_FIRE_GROUP = "Next fire group"
    PREVIOUS_FIRE_GROUP = "Previous fire group"

    # Defence and utilities
    SHIELD_CELL_USED = "Shield cell used"
    CHAFF_LAUNCHED = "Chaff launched"
    HEAT_SINK_LAUNCHED = "Heat sink launched"
    CARGO_JETTISONED = "Cargo jettisoned"

    # Panels, maps and scanners
    COCKPIT_FOCUSED = "Cockpit focused"
    NAVIGATION_PANEL_OPENED = "Navigation panel opened"
    COMMS_PANEL_OPENED = "Comms panel opened"
    ROLE_PANEL_OPENED = "Role panel opened"
    SYSTEMS_PANEL_OPENED = "Systems panel opened"
    QUICK_COMMS_OPENED = "Quick comms opened"
    GALAXY_MAP_OPENED = "Galaxy map opened"
    SYSTEM_MAP_OPENED = "System map opened"
    FULL_SPECTRUM_SCANNER_READY = "Full spectrum scanner ready"
    RADAR_RANGE_INCREASED = "Radar range increased"
    RADAR_RANGE_DECREASED = "Radar range decreased"

    # Said when the game state changes, see SHIP_FLAG_REPLY_TEXTS and
    # JOURNAL_EVENT_REPLY_TEXTS (the lines the game says itself)
    SHIELDS_ONLINE = "Shields online"
    SHIELDS_OFFLINE = "Shields offline"
    DRIVE_ASSIST_ON = "Drive assist on"
    DRIVE_ASSIST_OFF = "Drive assist off"
    FUEL_SCOOPING = "Fuel scooping"
    FUEL_SCOOP_DISENGAGED = "Fuel scoop disengaged"
    MAIN_FUEL_TANK_LOW = "Main fuel tank low"
    FRAME_SHIFT_DRIVE_CHARGING = "Frame shift drive charging"
    HANDBRAKE_IS_ON = "Handbrake is on"
    FUEL_REPLENISHED = "Fuel replenished"
    DOCKING_SUCCESSFUL = "Docking successful"
    SELF_DESTRUCT_INITIATED = "Self-destruct sequence initiated"
    FIGHTER_DESTROYED = "Fighter destroyed"
    MISSION_FAILED = "Mission failed"
    FIGHTER_DEPLOYED = "Fighter deployed"
    DOCKING_REQUEST_DENIED = "Docking request denied"
    DOCKING_REQUEST_GRANTED = "Docking request granted"

    # Refusals
    GAME_ACTIONS_DISABLED = "Game actions disabled"


# Every text that is spoken ahead of time, in the order of the enum.
REPLY_TEXTS = list(ReplyTexts)
