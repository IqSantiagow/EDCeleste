import re
from collections.abc import Callable
from typing import NamedTuple

from edceleste.services.models.game_events import StatusFlags
from edceleste.services.models.game_stats import ShipStats
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.reply_text import ReplyTexts


class ShipSwitch(NamedTuple):
    """One ship switch that has a key AND a flag in Status.json, all in one row.
    read_flag_from_ship reads the state the flag stands for from ShipStats, e.g. for the
    flag FlightAssistOff it is ship.is_flight_assist_off. text_when_flag_set is
    what is said when the game sets the flag, text_when_flag_cleared when it
    clears it."""

    action: EdAction
    flag: StatusFlags
    read_flag_from_ship: Callable[[ShipStats], bool]
    text_when_flag_set: ReplyTexts
    text_when_flag_cleared: ReplyTexts


SHIP_SWITCHES = [
    ShipSwitch(
        EdAction.LANDING_GEAR_TOGGLE,
        StatusFlags.LandingGearDown,
        lambda ship: ship.is_landing_gear_down,
        ReplyTexts.LANDING_GEAR_DEPLOYED,
        ReplyTexts.LANDING_GEAR_RETRACTED,
    ),
    ShipSwitch(
        EdAction.DEPLOY_HARDPOINT_TOGGLE,
        StatusFlags.HardpointsDeployed,
        lambda ship: ship.are_hardpoints_deployed,
        ReplyTexts.HARDPOINTS_DEPLOYED,
        ReplyTexts.HARDPOINTS_RETRACTED,
    ),
    ShipSwitch(
        EdAction.TOGGLE_CARGO_SCOOP,
        StatusFlags.CargoScoopDeployed,
        lambda ship: ship.is_cargo_scoop_deployed,
        ReplyTexts.CARGO_SCOOP_DEPLOYED,
        ReplyTexts.CARGO_SCOOP_RETRACTED,
    ),
    ShipSwitch(
        EdAction.SHIP_SPOT_LIGHT_TOGGLE,
        StatusFlags.LightsOn,
        lambda ship: ship.are_lights_on,
        ReplyTexts.LIGHTS_ON,
        ReplyTexts.LIGHTS_OFF,
    ),
    ShipSwitch(
        EdAction.TOGGLE_FLIGHT_ASSIST,
        StatusFlags.FlightAssistOff,
        lambda ship: ship.is_flight_assist_off,
        ReplyTexts.FLIGHT_ASSIST_OFF,
        ReplyTexts.FLIGHT_ASSIST_ON,
    ),
    ShipSwitch(
        EdAction.NIGHT_VISION_TOGGLE,
        StatusFlags.NightVision,
        lambda ship: ship.is_night_vision_on,
        ReplyTexts.NIGHT_VISION_ON,
        ReplyTexts.NIGHT_VISION_OFF,
    ),
]


# The reply for every action that has no direction: one press, one text.
# The toggles are not here, their text depends on the ship (see
# pick_reply_text_for_pressed_action).
REPLY_TEXT_OF_ONE_SHOT_ACTION: dict[EdAction, ReplyTexts] = {
    EdAction.USE_BOOST_JUICE: ReplyTexts.BOOSTING,
    EdAction.SUPERCRUISE: ReplyTexts.ENGAGING_SUPERCRUISE,
    EdAction.HYPERSPACE: ReplyTexts.JUMPING_TO_NEXT_SYSTEM,
    EdAction.HYPER_SUPER_COMBINATION: ReplyTexts.ENGAGING_FRAME_SHIFT_DRIVE,
    EdAction.SET_SPEED_ZERO: ReplyTexts.THROTTLE_ZERO,
    EdAction.SET_SPEED_50: ReplyTexts.THROTTLE_FIFTY_PERCENT,
    EdAction.SET_SPEED_75: ReplyTexts.THROTTLE_SEVENTY_FIVE_PERCENT,
    EdAction.SET_SPEED_100: ReplyTexts.FULL_THROTTLE,
    EdAction.INCREASE_ENGINES_POWER: ReplyTexts.MORE_POWER_TO_ENGINES,
    EdAction.INCREASE_WEAPONS_POWER: ReplyTexts.MORE_POWER_TO_WEAPONS,
    EdAction.INCREASE_SYSTEMS_POWER: ReplyTexts.MORE_POWER_TO_SYSTEMS,
    EdAction.RESET_POWER_DISTRIBUTION: ReplyTexts.POWER_DISTRIBUTION_RESET,
    EdAction.SELECT_TARGET: ReplyTexts.TARGET_SELECTED,
    EdAction.CYCLE_NEXT_TARGET: ReplyTexts.NEXT_TARGET,
    EdAction.CYCLE_PREVIOUS_TARGET: ReplyTexts.PREVIOUS_TARGET,
    EdAction.SELECT_HIGHEST_THREAT: ReplyTexts.HIGHEST_THREAT_TARGETED,
    EdAction.CYCLE_NEXT_SUBSYSTEM: ReplyTexts.NEXT_SUBSYSTEM,
    EdAction.CYCLE_PREVIOUS_SUBSYSTEM: ReplyTexts.PREVIOUS_SUBSYSTEM,
    EdAction.CYCLE_FIRE_GROUP_NEXT: ReplyTexts.NEXT_FIRE_GROUP,
    EdAction.CYCLE_FIRE_GROUP_PREVIOUS: ReplyTexts.PREVIOUS_FIRE_GROUP,
    EdAction.USE_SHIELD_CELL: ReplyTexts.SHIELD_CELL_USED,
    EdAction.FIRE_CHAFF_LAUNCHER: ReplyTexts.CHAFF_LAUNCHED,
    EdAction.DEPLOY_HEAT_SINK: ReplyTexts.HEAT_SINK_LAUNCHED,
    EdAction.EJECT_ALL_CARGO: ReplyTexts.CARGO_JETTISONED,
    EdAction.UI_FOCUS: ReplyTexts.COCKPIT_FOCUSED,
    EdAction.FOCUS_LEFT_PANEL: ReplyTexts.NAVIGATION_PANEL_OPENED,
    EdAction.FOCUS_COMMS_PANEL: ReplyTexts.COMMS_PANEL_OPENED,
    EdAction.FOCUS_RADAR_PANEL: ReplyTexts.ROLE_PANEL_OPENED,
    EdAction.FOCUS_RIGHT_PANEL: ReplyTexts.SYSTEMS_PANEL_OPENED,
    EdAction.QUICK_COMMS_PANEL: ReplyTexts.QUICK_COMMS_OPENED,
    EdAction.GALAXY_MAP_OPEN: ReplyTexts.GALAXY_MAP_OPENED,
    EdAction.SYSTEM_MAP_OPEN: ReplyTexts.SYSTEM_MAP_OPENED,
    EdAction.EXPLORATION_FSS_ENTER: ReplyTexts.FULL_SPECTRUM_SCANNER_READY,
    EdAction.RADAR_INCREASE_RANGE: ReplyTexts.RADAR_RANGE_INCREASED,
    EdAction.RADAR_DECREASE_RANGE: ReplyTexts.RADAR_RANGE_DECREASED,
}


def pick_reply_text_for_pressed_action(
    action: EdAction, ship_before_press: ShipStats
) -> ReplyTexts:
    """Returns the one ReplyTexts member that says what a pressed key did, e.g.
    LANDING_GEAR_TOGGLE with the gear up -> ReplyTexts.LANDING_GEAR_DEPLOYED
    (a str, "Landing gear deployed"). Never None.

    1. A toggle (a row of SHIP_SWITCHES) does the opposite of what the ship is
       doing before the press: flight assist, hardpoints, landing gear, cargo
       scoop, lights and night vision. Its text is read from ship_before_press.
    2. Every other action has one fixed text in REPLY_TEXT_OF_ONE_SHOT_ACTION.

    The state is as old as the last Status.json (about a second), so a toggle
    pressed twice within that second gets the same text twice. Only the texts
    of a key that was pressed come out of here ("deployed", "on", "Boosting").
    The refusals ("Landing gear unavailable") are made by InstinctService from
    the answer of the tool, and the texts "already deployed" and the like are
    not used yet, because the model does not know the direction the pilot
    asked for.

    Touches no disk, bus or network. Raises nothing for an action of EdAction
    (a unit test checks that each one has a text), a KeyError for anything else."""
    for switch in SHIP_SWITCHES:
        if switch.action == action:
            if switch.read_flag_from_ship(ship_before_press):
                return switch.text_when_flag_cleared
            return switch.text_when_flag_set
    return REPLY_TEXT_OF_ONE_SHOT_ACTION[action]


# What Celeste says when the game state shows it, whoever caused the change.
#
# The flags of Status.json that have no key: the flag, the text when the game
# sets it, the text when the game clears it. None = nothing is said for that
# direction.
FLAGS_WITHOUT_KEY_REPLY_TEXTS: list[
    tuple[StatusFlags, ReplyTexts | None, ReplyTexts | None]
] = [
    (StatusFlags.ShieldsUp, ReplyTexts.SHIELDS_ONLINE, ReplyTexts.SHIELDS_OFFLINE),
    (
        StatusFlags.SrvDriveAssist,
        ReplyTexts.DRIVE_ASSIST_ON,
        ReplyTexts.DRIVE_ASSIST_OFF,
    ),
    (
        StatusFlags.ScoopingFuel,
        ReplyTexts.FUEL_SCOOPING,
        ReplyTexts.FUEL_SCOOP_DISENGAGED,
    ),
    (StatusFlags.LowFuel, ReplyTexts.MAIN_FUEL_TANK_LOW, None),
    (StatusFlags.FsdCharging, ReplyTexts.FRAME_SHIFT_DRIVE_CHARGING, None),
    (StatusFlags.SrvHandbrake, ReplyTexts.HANDBRAKE_IS_ON, None),
]

# Every flag Celeste speaks about: the ship switches first, then the rest.
SHIP_FLAG_REPLY_TEXTS: list[
    tuple[StatusFlags, ReplyTexts | None, ReplyTexts | None]
] = [
    (switch.flag, switch.text_when_flag_set, switch.text_when_flag_cleared)
    for switch in SHIP_SWITCHES
] + FLAGS_WITHOUT_KEY_REPLY_TEXTS

# The journal events with a voice line of the game, by the name in the "event"
# field. Only the ones that come once per happening. The ones that repeat in a
# series (UnderAttack, HeatDamage, Scanned, ReceiveText) need a cooldown and
# are not here yet.
JOURNAL_EVENT_REPLY_TEXTS: dict[str, ReplyTexts] = {
    "RefuelAll": ReplyTexts.FUEL_REPLENISHED,
    "RefuelPartial": ReplyTexts.FUEL_REPLENISHED,
    "Docked": ReplyTexts.DOCKING_SUCCESSFUL,
    "SelfDestruct": ReplyTexts.SELF_DESTRUCT_INITIATED,
    "FighterDestroyed": ReplyTexts.FIGHTER_DESTROYED,
    "MissionFailed": ReplyTexts.MISSION_FAILED,
    "LaunchFighter": ReplyTexts.FIGHTER_DEPLOYED,
    "DockingDenied": ReplyTexts.DOCKING_REQUEST_DENIED,
    "DockingGranted": ReplyTexts.DOCKING_REQUEST_GRANTED,
}

# The actions whose key press changes something that the game state says by
# itself a moment later (the flags of SHIP_FLAG_REPLY_TEXTS). Instinct still
# puts its reply in COMMS, but does not speak it, or the pilot would hear it
# twice. The three FSD actions are here because the FSD key is a toggle: it
# starts the charge ("Frame shift drive charging" of the FsdCharging flag) and a
# second press cancels it, which Instinct cannot tell apart.
ACTIONS_SAID_BY_GAME_STATE = frozenset(
    {switch.action for switch in SHIP_SWITCHES}
    | {
        EdAction.SUPERCRUISE,
        EdAction.HYPERSPACE,
        EdAction.HYPER_SUPER_COMBINATION,
    }
)


def pick_reply_texts_for_changed_flags(old_flags: int, new_flags: int) -> list[str]:
    """The texts of ReplyTexts that say which ship switches changed between two
    Status.json Flags values, e.g. the landing gear bit going from 0 to 1 ->
    [ReplyTexts.LANDING_GEAR_DEPLOYED]. The list holds the members as plain str
    (the sentences). One text for every switch of SHIP_FLAG_REPLY_TEXTS
    whose bit differs and has a text for that direction (a direction with None
    says nothing, e.g. the low fuel bit going out), in the order of that list.
    Empty when none of them changed (other bits, like docked or supercruise,
    are ignored). Touches no disk and raises nothing."""
    changed_flags = old_flags ^ new_flags
    texts: list[str] = []
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
    text without a-z and 0-9 gives ".wav". ReplyTexts has neither (a unit test
    checks it). Saving the replies and playing them must both use this function,
    or the files are not found. Touches no disk and raises nothing."""
    words = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return f"{words}.wav"
