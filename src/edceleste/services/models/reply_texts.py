import re

from edceleste.services.models.game_events import StatusFlags
from edceleste.services.models.game_stats import ShipStats
from edceleste.services.models.keybinds_model import EdAction

# Short replies the pilot hears after a command. They are spoken ahead of time
# in the voice of a profile, so playing one is just opening a file. One text per
# one-shot action, several per toggle (done, already done, unavailable).
# A new text added here is missing in the folders of the old profiles, so the
# app speaks it live until the replies are made again.
GAME_ACTIONS_DISABLED_TEXT = "Game actions disabled"

REPLY_TEXTS = [
    # Toggles
    "Flight assist on",
    "Flight assist off",
    "Flight assist already on",
    "Flight assist already off",
    "Hardpoints deployed",
    "Hardpoints retracted",
    "Hardpoints already deployed",
    "Hardpoints already retracted",
    "Hardpoints unavailable",
    "Landing gear deployed",
    "Landing gear retracted",
    "Landing gear already deployed",
    "Landing gear already retracted",
    "Landing gear unavailable",
    "Cargo scoop deployed",
    "Cargo scoop retracted",
    "Cargo scoop already deployed",
    "Cargo scoop already retracted",
    "Cargo scoop unavailable",
    "Lights on",
    "Lights off",
    "Lights already on",
    "Lights already off",
    "Night vision on",
    "Night vision off",
    "Night vision already on",
    "Night vision already off",
    # Flight
    "Boosting",
    "Engaging supercruise",
    "Jumping to the next system",
    "Engaging frame shift drive",
    "Throttle zero",
    "Throttle fifty percent",
    "Throttle seventy five percent",
    "Full throttle",
    # Power distribution
    "More power to engines",
    "More power to weapons",
    "More power to systems",
    "Power distribution reset",
    # Targeting
    "Target selected",
    "Next target",
    "Previous target",
    "Highest threat targeted",
    "Next subsystem",
    "Previous subsystem",
    "Next fire group",
    "Previous fire group",
    # Defence and utilities
    "Shield cell used",
    "Chaff launched",
    "Heat sink launched",
    "Cargo jettisoned",
    # Panels, maps and scanners
    "Cockpit focused",
    "Navigation panel opened",
    "Comms panel opened",
    "Role panel opened",
    "Systems panel opened",
    "Quick comms opened",
    "Galaxy map opened",
    "System map opened",
    "Full spectrum scanner ready",
    "Radar range increased",
    "Radar range decreased",
    # Said when the game state changes, see SHIP_FLAG_REPLY_TEXTS and
    # JOURNAL_EVENT_REPLY_TEXTS (the lines the game says itself)
    "Shields online",
    "Shields offline",
    "Drive assist on",
    "Drive assist off",
    "Fuel scooping",
    "Fuel scoop disengaged",
    "Main fuel tank low",
    "Frame shift drive charging",
    "Handbrake is on",
    "Fuel replenished",
    "Docking successful",
    "Self-destruct sequence initiated",
    "Fighter destroyed",
    "Mission failed",
    "Fighter deployed",
    "Docking request denied",
    "Docking request granted",
    # Refusals
    GAME_ACTIONS_DISABLED_TEXT,
]

# The reply for every action that has no direction: one press, one text.
# The toggles are not here, their text depends on the ship (see
# pick_reply_text_for_pressed_action).
REPLY_TEXT_OF_ONE_SHOT_ACTION: dict[EdAction, str] = {
    EdAction.USE_BOOST_JUICE: "Boosting",
    EdAction.SUPERCRUISE: "Engaging supercruise",
    EdAction.HYPERSPACE: "Jumping to the next system",
    EdAction.HYPER_SUPER_COMBINATION: "Engaging frame shift drive",
    EdAction.SET_SPEED_ZERO: "Throttle zero",
    EdAction.SET_SPEED_50: "Throttle fifty percent",
    EdAction.SET_SPEED_75: "Throttle seventy five percent",
    EdAction.SET_SPEED_100: "Full throttle",
    EdAction.INCREASE_ENGINES_POWER: "More power to engines",
    EdAction.INCREASE_WEAPONS_POWER: "More power to weapons",
    EdAction.INCREASE_SYSTEMS_POWER: "More power to systems",
    EdAction.RESET_POWER_DISTRIBUTION: "Power distribution reset",
    EdAction.SELECT_TARGET: "Target selected",
    EdAction.CYCLE_NEXT_TARGET: "Next target",
    EdAction.CYCLE_PREVIOUS_TARGET: "Previous target",
    EdAction.SELECT_HIGHEST_THREAT: "Highest threat targeted",
    EdAction.CYCLE_NEXT_SUBSYSTEM: "Next subsystem",
    EdAction.CYCLE_PREVIOUS_SUBSYSTEM: "Previous subsystem",
    EdAction.CYCLE_FIRE_GROUP_NEXT: "Next fire group",
    EdAction.CYCLE_FIRE_GROUP_PREVIOUS: "Previous fire group",
    EdAction.USE_SHIELD_CELL: "Shield cell used",
    EdAction.FIRE_CHAFF_LAUNCHER: "Chaff launched",
    EdAction.DEPLOY_HEAT_SINK: "Heat sink launched",
    EdAction.EJECT_ALL_CARGO: "Cargo jettisoned",
    EdAction.UI_FOCUS: "Cockpit focused",
    EdAction.FOCUS_LEFT_PANEL: "Navigation panel opened",
    EdAction.FOCUS_COMMS_PANEL: "Comms panel opened",
    EdAction.FOCUS_RADAR_PANEL: "Role panel opened",
    EdAction.FOCUS_RIGHT_PANEL: "Systems panel opened",
    EdAction.QUICK_COMMS_PANEL: "Quick comms opened",
    EdAction.GALAXY_MAP_OPEN: "Galaxy map opened",
    EdAction.SYSTEM_MAP_OPEN: "System map opened",
    EdAction.EXPLORATION_FSS_ENTER: "Full spectrum scanner ready",
    EdAction.RADAR_INCREASE_RANGE: "Radar range increased",
    EdAction.RADAR_DECREASE_RANGE: "Radar range decreased",
}


def pick_reply_text_for_pressed_action(
    action: EdAction, ship_before_press: ShipStats
) -> str:
    """The text of REPLY_TEXTS that says what a pressed key did, e.g.
    LANDING_GEAR_TOGGLE with the gear up -> "Landing gear deployed".

    A toggle does the opposite of what the ship is doing before the press, so
    its text is read from ship_before_press: flight assist, hardpoints,
    landing gear, cargo scoop, lights and night vision. Every other action
    has one text in REPLY_TEXT_OF_ONE_SHOT_ACTION. The state is as old as the
    last Status.json (about a second), so a toggle pressed twice within that
    second gets the same text twice. Only the texts of a key that was pressed
    come out of here ("deployed", "on", "Boosting"). The refusals ("Landing
    gear unavailable") are made by InstinctService from the answer of the
    tool, and the texts "already deployed" and the like are not used yet,
    because the model does not know the direction the pilot asked for.
    Touches no disk and raises nothing for an action of EdAction (a unit test
    checks that each one has a text)."""
    ship = ship_before_press
    match action:
        case EdAction.TOGGLE_FLIGHT_ASSIST:
            return (
                "Flight assist on" if ship.is_flight_assist_off else "Flight assist off"
            )
        case EdAction.DEPLOY_HARDPOINT_TOGGLE:
            return (
                "Hardpoints retracted"
                if ship.are_hardpoints_deployed
                else "Hardpoints deployed"
            )
        case EdAction.LANDING_GEAR_TOGGLE:
            return (
                "Landing gear retracted"
                if ship.is_landing_gear_down
                else "Landing gear deployed"
            )
        case EdAction.TOGGLE_CARGO_SCOOP:
            return (
                "Cargo scoop retracted"
                if ship.is_cargo_scoop_deployed
                else "Cargo scoop deployed"
            )
        case EdAction.SHIP_SPOT_LIGHT_TOGGLE:
            return "Lights off" if ship.are_lights_on else "Lights on"
        case EdAction.NIGHT_VISION_TOGGLE:
            return "Night vision off" if ship.is_night_vision_on else "Night vision on"
        case _:
            return REPLY_TEXT_OF_ONE_SHOT_ACTION[action]


# What Celeste says when the game state shows it, whoever caused the change.
#
# The ship switches that Status.json reports as flags: the flag, the text when
# the game sets it, the text when the game clears it. None = nothing is said for
# that direction.
SHIP_FLAG_REPLY_TEXTS: list[tuple[StatusFlags, str | None, str | None]] = [
    (StatusFlags.LandingGearDown, "Landing gear deployed", "Landing gear retracted"),
    (StatusFlags.HardpointsDeployed, "Hardpoints deployed", "Hardpoints retracted"),
    (StatusFlags.CargoScoopDeployed, "Cargo scoop deployed", "Cargo scoop retracted"),
    (StatusFlags.LightsOn, "Lights on", "Lights off"),
    (StatusFlags.FlightAssistOff, "Flight assist off", "Flight assist on"),
    (StatusFlags.NightVision, "Night vision on", "Night vision off"),
    (StatusFlags.ShieldsUp, "Shields online", "Shields offline"),
    (StatusFlags.SrvDriveAssist, "Drive assist on", "Drive assist off"),
    (StatusFlags.ScoopingFuel, "Fuel scooping", "Fuel scoop disengaged"),
    (StatusFlags.LowFuel, "Main fuel tank low", None),
    (StatusFlags.FsdCharging, "Frame shift drive charging", None),
    (StatusFlags.SrvHandbrake, "Handbrake is on", None),
]

# The journal events with a voice line of the game, by the name in the "event"
# field. Only the ones that come once per happening. The ones that repeat in a
# series (UnderAttack, HeatDamage, Scanned, ReceiveText) need a cooldown and
# are not here yet.
JOURNAL_EVENT_REPLY_TEXTS = {
    "RefuelAll": "Fuel replenished",
    "RefuelPartial": "Fuel replenished",
    "Docked": "Docking successful",
    "SelfDestruct": "Self-destruct sequence initiated",
    "FighterDestroyed": "Fighter destroyed",
    "MissionFailed": "Mission failed",
    "LaunchFighter": "Fighter deployed",
    "DockingDenied": "Docking request denied",
    "DockingGranted": "Docking request granted",
}

# The actions whose key press changes something that the game state says by
# itself a moment later (the flags of SHIP_FLAG_REPLY_TEXTS). Instinct still
# puts its reply in COMMS, but does not speak it, or the pilot would hear it
# twice. The three FSD actions are here because the FSD key is a toggle: it
# starts the charge ("Frame shift drive charging" of the FsdCharging flag) and a
# second press cancels it, which Instinct cannot tell apart.
ACTIONS_SAID_BY_GAME_STATE = frozenset(
    {
        EdAction.TOGGLE_FLIGHT_ASSIST,
        EdAction.DEPLOY_HARDPOINT_TOGGLE,
        EdAction.LANDING_GEAR_TOGGLE,
        EdAction.TOGGLE_CARGO_SCOOP,
        EdAction.SHIP_SPOT_LIGHT_TOGGLE,
        EdAction.NIGHT_VISION_TOGGLE,
        EdAction.SUPERCRUISE,
        EdAction.HYPERSPACE,
        EdAction.HYPER_SUPER_COMBINATION,
    }
)


def pick_reply_texts_for_changed_flags(old_flags: int, new_flags: int) -> list[str]:
    """The texts of REPLY_TEXTS that say which ship switches changed between two
    Status.json Flags values, e.g. the landing gear bit going from 0 to 1 ->
    ["Landing gear deployed"]. One text for every switch of SHIP_FLAG_REPLY_TEXTS
    whose bit differs and has a text for that direction (a direction with None
    says nothing, e.g. the low fuel bit going out), in the order of that list.
    Empty when none of them changed (other bits, like docked or supercruise,
    are ignored). Touches no disk and raises nothing."""
    changed_flags = old_flags ^ new_flags
    texts = []
    for flag, text_when_set, text_when_cleared in SHIP_FLAG_REPLY_TEXTS:
        if changed_flags & flag:
            text = text_when_set if new_flags & flag else text_when_cleared
            if text is not None:
                texts.append(text)
    return texts


def build_reply_wav_file_name(text: str) -> str:
    """The name of the wav file of a reply text, e.g. "Landing gear deployed" ->
    "landing_gear_deployed.wav". Only the file name as a str, no folder.

    1. Lower case.
    2. Every run of characters that are not a-z or 0-9 becomes one "_". Letters
       with accents (ą, é) count as such characters.
    3. "_" at the start and at the end is cut, and ".wav" is added.

    Two texts that differ only in case or punctuation get the same name, and a
    text without a-z and 0-9 gives ".wav". REPLY_TEXTS has neither (a unit test
    checks it). Saving the replies and playing them must both use this function,
    or the files are not found. Touches no disk."""
    words = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return f"{words}.wav"
