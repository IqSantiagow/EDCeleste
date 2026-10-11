"""The question Instinct asks the decision model about a pilot message.

The model was trained on exactly these words (dataset
IqSantiagow/edceleste-decisions, kind "command"). Change a word here and the
model has to be measured again.
"""

from edceleste.services.models.keybinds_model import EdAction

COMMAND_QUESTION_NAME = "action"
COMMAND_QUESTION_INSTRUCTIONS = "Which ship action did the pilot just ask for?"

# The answer when the pilot does not ask for a ship action: talking, asking or
# refusing. It is always the last option of the question.
NO_ACTION = "none"
NO_ACTION_DESCRIPTION = "no ship action: the pilot is talking, asking or refusing"

# Keys are the EdAction values, because the training data names the actions the
# same way ("LandingGearToggle").
ACTION_DESCRIPTIONS: dict[EdAction, str] = {
    EdAction.TOGGLE_FLIGHT_ASSIST: "toggle flight assist on or off",
    EdAction.USE_BOOST_JUICE: "boost the engines",
    EdAction.SUPERCRUISE: "engage supercruise",
    EdAction.HYPERSPACE: "hyperspace jump to the next star system",
    EdAction.HYPER_SUPER_COMBINATION: "frame shift drive: supercruise or jump, whichever fits",  # noqa: E501
    EdAction.SET_SPEED_ZERO: "set the throttle to zero, full stop",
    EdAction.SET_SPEED_50: "set the throttle to 50 percent",
    EdAction.SET_SPEED_75: "set the throttle to 75 percent",
    EdAction.SET_SPEED_100: "set the throttle to 100 percent, full speed",
    EdAction.INCREASE_ENGINES_POWER: "send more power (pips) to engines",
    EdAction.INCREASE_WEAPONS_POWER: "send more power (pips) to weapons",
    EdAction.INCREASE_SYSTEMS_POWER: "send more power (pips) to systems and shields",
    EdAction.RESET_POWER_DISTRIBUTION: "balance the power distribution, reset pips",
    EdAction.SELECT_TARGET: "target what is ahead of the ship",
    EdAction.CYCLE_NEXT_TARGET: "cycle to the next target",
    EdAction.CYCLE_PREVIOUS_TARGET: "cycle to the previous target",
    EdAction.SELECT_HIGHEST_THREAT: "target the highest threat",
    EdAction.CYCLE_NEXT_SUBSYSTEM: "cycle to the next subsystem of the target",
    EdAction.CYCLE_PREVIOUS_SUBSYSTEM: "cycle to the previous subsystem of the target",
    EdAction.CYCLE_FIRE_GROUP_NEXT: "switch to the next fire group",
    EdAction.CYCLE_FIRE_GROUP_PREVIOUS: "switch to the previous fire group",
    EdAction.DEPLOY_HARDPOINT_TOGGLE: "deploy or retract the hardpoints (weapons)",
    EdAction.USE_SHIELD_CELL: "use a shield cell bank",
    EdAction.FIRE_CHAFF_LAUNCHER: "fire the chaff launcher",
    EdAction.DEPLOY_HEAT_SINK: "launch a heat sink",
    EdAction.SHIP_SPOT_LIGHT_TOGGLE: "toggle the ship lights",
    EdAction.NIGHT_VISION_TOGGLE: "toggle night vision",
    EdAction.TOGGLE_CARGO_SCOOP: "deploy or retract the cargo scoop",
    EdAction.LANDING_GEAR_TOGGLE: "lower or raise the landing gear",
    EdAction.EJECT_ALL_CARGO: "jettison all cargo",
    EdAction.UI_FOCUS: "focus the cockpit UI",
    EdAction.FOCUS_LEFT_PANEL: "open the left panel (navigation)",
    EdAction.FOCUS_COMMS_PANEL: "open the comms panel",
    EdAction.FOCUS_RADAR_PANEL: "open the role panel (radar panel)",
    EdAction.FOCUS_RIGHT_PANEL: "open the right panel (ship systems)",
    EdAction.QUICK_COMMS_PANEL: "open quick comms to type a message",
    EdAction.GALAXY_MAP_OPEN: "open the galaxy map",
    EdAction.SYSTEM_MAP_OPEN: "open the system map",
    EdAction.EXPLORATION_FSS_ENTER: "enter the full spectrum system scanner (FSS)",
    EdAction.RADAR_INCREASE_RANGE: "increase the radar range",
    EdAction.RADAR_DECREASE_RANGE: "decrease the radar range",
}


def build_which_action_questions(offered_actions: list[EdAction]) -> dict:
    """The questions argument for InstinctService.ask_decision_model: one
    "choice" question named "action", asking which ship action the pilot just
    asked for. The shape is {"action": {"type": "choice", "instructions": the
    question text, "criteria": {option name: description}}}. The options are
    the offered actions in the given order (named by their EdAction value, each
    with its description from ACTION_DESCRIPTIONS), and "none" always last,
    meaning the pilot is only talking, asking or refusing. An empty list gives
    only "none". Only builds the dictionary, the model is not asked here."""
    options = {action.value: ACTION_DESCRIPTIONS[action] for action in offered_actions}
    options[NO_ACTION] = NO_ACTION_DESCRIPTION
    return {
        COMMAND_QUESTION_NAME: {
            "type": "choice",
            "instructions": COMMAND_QUESTION_INSTRUCTIONS,
            "criteria": options,
        }
    }
