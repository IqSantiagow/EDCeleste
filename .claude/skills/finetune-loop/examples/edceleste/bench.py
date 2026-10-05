"""Shared benchmark: the same game states, the same questions and the same timing for
every model.

A model runner only has to give one function:
    ask(state: dict, questions: dict) -> {question_id: probability_of_yes}
and call run_benchmark(model_name, ask).
"""

import json
import statistics
import subprocess
import time
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = BENCH_DIR / "results"
SCENARIOS = json.loads((BENCH_DIR / "scenarios.json").read_text(encoding="utf-8"))
SCENARIOS_BY_ID = {scenario["id"]: scenario for scenario in SCENARIOS}

# action -> (question about the ship situation, what the pilot would ask for)
ACTIONS = {
    "DeployHeatSink": (
        "Should a heat sink be deployed right now to cool the ship down?",
        "a heat sink to be deployed",
    ),
    "UseShieldCell": (
        "Should a shield cell bank be fired right now to restore the shields?",
        "a shield cell to be used",
    ),
    "FireChaffLauncher": (
        "Should chaff be launched right now to break enemy weapon locks?",
        "chaff to be launched",
    ),
    "UseBoostJuice": ("Should the ship boost right now?", "the ship to boost"),
    "LandingGearToggle": (
        "Should the landing gear be toggled right now?",
        "the landing gear to be lowered or raised",
    ),
    "SetSpeedZero": (
        "Should the throttle be set to zero right now?",
        "the throttle to be set to zero",
    ),
    "SelectHighestThreat": (
        "Should the highest threat enemy be targeted right now?",
        "the highest threat to be targeted",
    ),
    "IncreaseSystemsPower": (
        "Should more power be sent to ship systems and shields right now?",
        "more power to systems",
    ),
    "SetSpeed75": (
        "Should the throttle be set to 75 percent right now?",
        "the throttle to be set to 75 percent",
    ),
    "DeployHardpointToggle": (
        "Should the hardpoints be deployed or retracted right now?",
        "the hardpoints to be deployed or retracted",
    ),
    "ToggleCargoScoop": (
        "Should the cargo scoop be deployed or retracted right now?",
        "the cargo scoop to be deployed or retracted",
    ),
    "NightVisionToggle": (
        "Should night vision be toggled right now?",
        "night vision to be toggled",
    ),
}

REFLEX_CRITERIA = {
    "true": "The current game state calls for this action immediately.",
    "false": "Nothing in the current game state requires this action now.",
}
COMMAND_CRITERIA = {
    "true": "The pilot's words directly request this action.",
    "false": "The pilot asked for something else or only asked a question.",
}
NEEDS_LLM_QUESTION = {
    "type": "noul",
    "instructions": "Does the pilot's request need a full language model to answer, "
    "such as knowledge, planning or conversation, instead of a ship control action?",
    "criteria": {
        "true": "The request needs knowledge, planning or a spoken answer.",
        "false": "The request is a ship control command.",
    },
}

# utterance, game state it is said in, actions it asks for, does it need the big LLM
# (None = not scored)
UTTERANCES = [
    ("lower the landing gear", "docking_approach", ["LandingGearToggle"], False),
    ("deploy the heat sink, now", "overheat_scooping", ["DeployHeatSink"], False),
    (
        "retract the landing gear and set speed to seventy five percent",
        "docked_market",
        ["LandingGearToggle", "SetSpeed75"],
        False,
    ),
    ("how much fuel do I have", "low_fuel", [], None),
    (
        "where do I get the best price for gold within twenty light years",
        "docked_market",
        [],
        True,
    ),
    ("plan a route to Sol avoiding anarchy systems", "calm_supercruise", [], True),
    ("what is the latest on Galnet", "calm_supercruise", [], True),
]


# action -> (when the game state calls for it, when it does not). Gives the model the
# game knowledge it may lack.
DESCRIBED_CRITERIA = {
    "DeployHeatSink": ("The ship is overheating.", "Ship temperature is normal."),
    "UseShieldCell": (
        "The shields are down while the ship is in danger.",
        "Shields are up or the ship is safe.",
    ),
    "FireChaffLauncher": (
        "The ship is in combat or being interdicted, so enemies can lock weapons on "
        "it.",
        "No enemy is targeting the ship.",
    ),
    "UseBoostJuice": (
        "The ship must get away fast, for example during an interdiction or under "
        "fire with shields down.",
        "There is no threat to escape from.",
    ),
    "LandingGearToggle": (
        "The ship was assigned a landing pad and is approaching it with the landing "
        "gear up.",
        "The ship is not about to land, or the landing gear is already down.",
    ),
    "SetSpeedZero": (
        "The ship is being interdicted and can submit by cutting the throttle.",
        "There is no interdiction.",
    ),
    "SelectHighestThreat": (
        "The ship is in danger in a fight.",
        "No enemies are around.",
    ),
    "IncreaseSystemsPower": (
        "The shields are down or the ship is under fire.",
        "The ship is safe.",
    ),
    "SetSpeed75": (
        "The pilot must slow to the optimal approach speed right before dropping out "
        "at a destination.",
        "No approach is happening.",
    ),
    "DeployHardpointToggle": (
        "Enemies attack while the hardpoints are retracted.",
        "There is no fight starting.",
    ),
    "ToggleCargoScoop": (
        "There is cargo or material floating in space to collect.",
        "There is nothing to collect.",
    ),
    "NightVisionToggle": (
        "The surroundings are too dark to see.",
        "Visibility is fine.",
    ),
}


def reflex_questions(described: bool = False) -> dict:
    questions = {}
    for action, (situation_question, _) in ACTIONS.items():
        criteria = REFLEX_CRITERIA
        if described:
            when_true, when_false = DESCRIBED_CRITERIA[action]
            criteria = {"true": when_true, "false": when_false}
        questions[action] = {
            "type": "noul",
            "instructions": situation_question,
            "criteria": criteria,
        }
    return questions


def command_questions() -> dict:
    questions = {}
    for action, (_, requested_thing) in ACTIONS.items():
        questions[action] = {
            "type": "noul",
            "instructions": f"Did the pilot just ask for {requested_thing}?",
            "criteria": COMMAND_CRITERIA,
        }
    questions["needs_llm"] = NEEDS_LLM_QUESTION
    return questions


def gpu_memory_used_mb() -> int:
    output = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
    ).stdout
    return int(output.strip().splitlines()[0])


def ask_many_times(
    ask, state: dict, questions: dict, repeats: int
) -> tuple[dict, list[float], float]:
    """Returns answers of the last call, all timings in ms and the largest answer change
    between calls."""
    all_answers = []
    timings_ms = []
    for _ in range(repeats):
        start = time.perf_counter()
        answers = ask(state, questions)
        timings_ms.append((time.perf_counter() - start) * 1000)
        all_answers.append(answers)
    largest_change = 0.0
    for question_id in questions:
        values = [answers[question_id] for answers in all_answers]
        largest_change = max(largest_change, max(values) - min(values))
    return all_answers[-1], timings_ms, largest_change


def run_benchmark(
    model_name: str,
    ask,
    gpu_memory_before_load_mb: int,
    repeats: int = 5,
    notes: dict | None = None,
) -> dict:
    results = {
        "model": model_name,
        "notes": notes or {},
        "reflex": [],
        "reflex_described": [],
        "commands": [],
        "latency": {},
    }

    overheat_state = {"game_state": SCENARIOS_BY_ID["overheat_scooping"]["game_state"]}
    start = time.perf_counter()
    ask(overheat_state, reflex_questions())
    results["latency"]["first_call_ms"] = (time.perf_counter() - start) * 1000
    ask(overheat_state, reflex_questions())

    for result_key, described in (("reflex", False), ("reflex_described", True)):
        for scenario in SCENARIOS:
            state = {"game_state": scenario["game_state"]}
            answers, timings_ms, largest_change = ask_many_times(
                ask, state, reflex_questions(described), repeats
            )
            results[result_key].append(
                {
                    "scenario": scenario["id"],
                    "expected": scenario["expected_actions"],
                    "answers": answers,
                    "timings_ms": timings_ms,
                    "largest_change": largest_change,
                }
            )
            median_ms = statistics.median(timings_ms)
            print(f"  {result_key:16} {scenario['id']:22} {median_ms:7.1f} ms")

    for utterance, scenario_id, expected_actions, needs_llm in UTTERANCES:
        state = {
            "game_state": SCENARIOS_BY_ID[scenario_id]["game_state"],
            "pilot_said": utterance,
        }
        answers, timings_ms, largest_change = ask_many_times(
            ask, state, command_questions(), repeats
        )
        results["commands"].append(
            {
                "utterance": utterance,
                "scenario": scenario_id,
                "expected": expected_actions,
                "needs_llm": needs_llm,
                "answers": answers,
                "timings_ms": timings_ms,
                "largest_change": largest_change,
            }
        )
        print(f"  command {utterance[:40]:40} {statistics.median(timings_ms):7.1f} ms")

    for question_count in (1, 3, 6, 12):
        some_questions = dict(list(reflex_questions().items())[:question_count])
        _, timings_ms, _ = ask_many_times(ask, overheat_state, some_questions, repeats)
        results["latency"][f"questions_{question_count}_ms"] = timings_ms
        median_ms = statistics.median(timings_ms)
        print(f"  latency {question_count:2} questions {median_ms:7.1f} ms")

    results["gpu_memory_before_load_mb"] = gpu_memory_before_load_mb
    results["gpu_memory_after_mb"] = gpu_memory_used_mb()
    save_results(results)
    return results


def save_results(results: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    result_file = RESULTS_DIR / f"{results['model']}.json"
    result_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"saved {result_file}")
