"""Builds the EDCeleste training set (v2) for a Jev-style decision model.

Run with the PROJECT venv, once per projection order (PYTHONHASHSEED changes the order
of the
sentences in the game state, exactly as it does between two runs of the app):
    for seed in 0 1 2 3; do PYTHONHASHSEED=$seed .venv/Scripts/python.exe
    model_bench/scripts/build_training_data.py $seed; done
Each run writes model_bench/training_data/part_<seed>.jsonl.

Three kinds of examples, all in the /v1/systemone shape (state + noul questions + gold
yes/no):
  reaction - a Celeste reaction: game event + the pilot's prompt. Should Celeste speak
  now?
  fact     - plain questions about the game state ("Is the ship overheating?")
  command  - what the pilot said: which ship action, and does it need the big LLM?
There is no built-in tactic: what Celeste does is the pilot's prompt, the model only has
to follow it.
"""

import asyncio
import csv
import json
import random
import sys
from pathlib import Path

from pydantic import TypeAdapter

from bench import ACTIONS, command_questions
from build_scenarios import read_all_fixture_events
from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models.game_events import MarketEvent, StatusEvent, StatusFlags
from edceleste.services.models.journal_event import JournalEvent

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "training_data"
RECORDINGS_CSV = Path(__file__).resolve().parents[1] / "recordings" / "recordings.csv"
STATES_PER_RUN = 250
UTTERANCES_PER_RUN = 400
REACTION_QUESTIONS_PER_STATE = 3
FACT_QUESTIONS_PER_STATE = 6

F = StatusFlags
SCOOPABLE_STAR_CLASSES = {"K", "G", "B", "F", "O", "A", "M"}
STAR_CLASSES = [
    "K",
    "G",
    "B",
    "F",
    "O",
    "A",
    "M",
    "TTS",
    "Y",
    "L",
    "T",
    "N",
    "DA",
    "H",
    "W",
    "AeBe",
]
COMMODITY_NAMES = [
    "Gold",
    "Silver",
    "Palladium",
    "Tritium",
    "Painite",
    "Bertrandite",
    "Indite",
    "Gallite",
    "Beryllium",
    "Water",
    "Hydrogen Fuel",
    "Biowaste",
]

# ---------------------------------------------------------------- the game situation

# event shown to the pilot in the reactions list -> where the ship is when it happens
EVENTS = {
    "FSD jump": "supercruise",
    "Docked": "docked",
    "Docking granted": "normal space",
    "Undocked": "normal space",
    "Supercruise exit": "normal space",
    "Approach body": "supercruise",
    "Overheating": "any",
    "Being interdicted": "supercruise",
    "Fuel low": "any",
    "Under attack": "normal space",
}


def sample_facts(rng: random.Random) -> dict:
    """Everything that is true in one moment of the game. The game state text is built
    from these."""
    event = rng.choice(list(EVENTS))
    where = EVENTS[event]
    if where == "any":
        where = rng.choice(["normal space", "supercruise"])
    if event == "Fuel low" or rng.random() < 0.12:
        fuel_tons = round(rng.uniform(0.4, 3.0), 1)
    else:
        fuel_tons = round(rng.uniform(4.0, 32.0), 1)
    danger_chance = 0.4 if event == "Overheating" else 0.15
    in_danger = event == "Under attack" or (
        where == "normal space" and rng.random() < danger_chance
    )
    interdicted = event == "Being interdicted"
    has_route = rng.random() < 0.75
    facts = {
        "event": event,
        "docked": where == "docked",
        "in_supercruise": where == "supercruise",
        "overheating": event == "Overheating" or rng.random() < 0.08,
        "in_danger": in_danger,
        "interdicted": interdicted,
        "shields_down": (in_danger or interdicted) and rng.random() < 0.5,
        "hardpoints_out": (in_danger and rng.random() < 0.7)
        or (where == "normal space" and rng.random() < 0.08),
        "pad_assigned": event == "Docking granted",
        "gear_down": where == "docked"
        or (event == "Docking granted" and rng.random() < 0.4),
        "fuel_tons": fuel_tons,
        "low_fuel": fuel_tons < 3.2,
        "hull_percent": 100 if rng.random() < 0.6 else rng.randint(15, 99),
        "next_star_class": rng.choice(STAR_CLASSES) if has_route else None,
        "jumps_left": (rng.randint(1, 5) if rng.random() < 0.5 else rng.randint(6, 25))
        if has_route
        else None,
        "market_deals": {},
    }
    if facts["docked"] and rng.random() < 0.75:
        names = rng.sample(COMMODITY_NAMES, 5)
        if rng.random() < 0.5 and "Gold" not in names:
            names[0] = "Gold"
        for name in names:
            facts["market_deals"][name] = rng.choice([-1, 1]) * rng.randint(20, 9000)
    return facts


def status_flags(facts: dict) -> int:
    flags = F.InMainShip
    if not facts["shields_down"]:
        flags |= F.ShieldsUp
    checks = [
        ("docked", F.Docked),
        ("in_supercruise", F.Supercruise),
        ("overheating", F.Overheating),
        ("in_danger", F.IsInDanger),
        ("interdicted", F.BeingInterdicted),
        ("hardpoints_out", F.HardpointsDeployed),
        ("gear_down", F.LandingGearDown),
        ("low_fuel", F.LowFuel),
    ]
    for fact_name, flag in checks:
        if facts[fact_name]:
            flags |= flag
    return int(flags)


async def build_game_state(facts: dict) -> str:
    event_bus = EventBus()
    game_state_service = GameStateService(event_bus)
    journal_event_parser = TypeAdapter(JournalEvent)
    fixture_by_name = {event["event"]: event for event in read_all_fixture_events()}
    skipped = {
        "Died",
        "Resurrect",
        "Docked",
        "DockingGranted",
        "FuelScoop",
        "FSDTarget",
        "Loadout",
    }

    raw_events = [
        dict(event)
        for event in read_all_fixture_events()
        if event["event"] not in skipped
    ]
    loadout = dict(fixture_by_name["Loadout"], HullHealth=facts["hull_percent"] / 100)
    raw_events.append(loadout)
    if facts["next_star_class"]:
        raw_events.append(
            dict(
                fixture_by_name["FSDTarget"],
                StarClass=facts["next_star_class"],
                RemainingJumpsInRoute=facts["jumps_left"],
            )
        )
    if facts["pad_assigned"]:
        raw_events.append(fixture_by_name["DockingGranted"])
    if facts["docked"]:
        raw_events.append(fixture_by_name["Docked"])
    for raw_event in raw_events:
        await event_bus.publish(journal_event_parser.validate_python(raw_event))

    if facts["market_deals"]:
        items = []
        for name, difference in facts["market_deals"].items():
            mean_price = random.Random(name).randint(5_000, 60_000)
            items.append(
                {
                    "Name": name,
                    "Category": "Metals",
                    "SellPrice": mean_price + difference,
                    "MeanPrice": mean_price,
                    "BuyPrice": 0,
                }
            )
        docked = fixture_by_name["Docked"]
        await event_bus.publish(
            MarketEvent(
                timestamp="2026-10-05T20:00:00Z",
                event="Market",
                MarketID=docked["MarketID"],
                StationName=docked["StationName"],
                StarSystem=docked["StarSystem"],
                Items=items,
            )
        )

    await event_bus.publish(
        StatusEvent(
            timestamp="2026-10-05T20:00:01Z",
            event="Status",
            Flags=status_flags(facts),
            Pips=[4, 4, 4],
            Fuel={"FuelMain": facts["fuel_tons"], "FuelReservoir": 0.4},
        )
    )
    return game_state_service.get_game_state_projection()


SYSTEM_NAMES = [
    "Kazemlya",
    "Shinrarta Dezhra",
    "Deciat",
    "Maia",
    "Colonia",
    "Jameson",
    "LHS 3447",
    "Eravate",
    "Sothis",
    "Robigo",
    "Wolf 397",
    "Achenar",
]
BODY_NAMES = [
    "Ocainawaka AB 3 a",
    "Eravate 2",
    "Maia A 3 a",
    "Deciat 6 a",
    "Wolf 397 c 1",
    "Sothis A 5",
]
SETTLEMENT_NAMES = [
    "Wu Mineralogic Enterprise",
    "Farseer Inc",
    "Hawking Research Post",
    "Bluford Agricultural Site",
]
STATION_NAMES = [
    "Hammel Terminal",
    "Jameson Memorial",
    "Ackerman Market",
    "Farseer Inc",
    "Robigo Mines",
    "Cleve Hub",
]
SHIP_NAMES = [
    "Cobra Mk III",
    "Krait Mk II",
    "Python",
    "Asp Explorer",
    "Federal Corvette",
    "Type-9 Heavy",
    "Diamondback Explorer",
    "Viper Mk III",
]
COMMANDER_NAMES = ["SANTIAGOW", "JAMESON", "OBSIDIAN", "KESTREL", "NOVA"]


def swap_names(game_state: str, rng: random.Random) -> str:
    """The fixtures are one commander in one place. Swap names so the model cannot learn
    them by heart."""
    replacements = {
        "Kazemlya": rng.choice(SYSTEM_NAMES),
        "Col 285 Sector LH-B a43-1": rng.choice(SYSTEM_NAMES),
        "Ocainawaka AB 3 a": rng.choice(BODY_NAMES),
        "Wu Mineralogic Enterprise": rng.choice(SETTLEMENT_NAMES),
        "Hammel Terminal": rng.choice(STATION_NAMES),
        "Fan Horizons": rng.choice(STATION_NAMES),
        "Cobra Mk III": rng.choice(SHIP_NAMES),
        "SANTIAGOW": rng.choice(COMMANDER_NAMES),
        "575382": str(rng.randint(1_000, 900_000_000)),
    }
    for old_name, new_name in replacements.items():
        game_state = game_state.replace(old_name, new_name)
    return game_state


# ---------------------------------------------------------------- Celeste reactions:
# the pilot's prompt


def best_paying(facts: dict, commodity: str) -> bool:
    return facts["market_deals"].get(commodity, 0) > 0


# (events it fits, or None for any event; the pilot's prompt; is it true in this
# moment?)
REACTION_PROMPTS = [
    (None, "Always tell me.", lambda f: True),
    (None, "Tell me what happened and what to do.", lambda f: True),
    (None, "Only speak if the ship is under attack.", lambda f: f["in_danger"]),
    (None, "Only speak if the ship is overheating.", lambda f: f["overheating"]),
    (None, "Only speak if my shields are down.", lambda f: f["shields_down"]),
    (None, "Only tell me if fuel is low.", lambda f: f["low_fuel"]),
    (
        None,
        "Only tell me if I have less than 5 tons of fuel.",
        lambda f: f["fuel_tons"] < 5,
    ),
    (
        None,
        "Only tell me if the hull is below 50 percent.",
        lambda f: f["hull_percent"] < 50,
    ),
    (None, "Stay quiet unless the hull is damaged.", lambda f: f["hull_percent"] < 100),
    (
        None,
        "Stay quiet unless something is wrong: overheating, shields down or hull "
        "damage.",
        lambda f: f["overheating"] or f["shields_down"] or f["hull_percent"] < 100,
    ),
    (None, "Don't say anything while I'm docked.", lambda f: not f["docked"]),
    (None, "Only speak when I'm in supercruise.", lambda f: f["in_supercruise"]),
    (
        None,
        "Keep quiet if my hardpoints are deployed.",
        lambda f: not f["hardpoints_out"],
    ),
    (
        None,
        "Only if I'm in danger or being interdicted.",
        lambda f: f["in_danger"] or f["interdicted"],
    ),
    (None, "Never talk during combat.", lambda f: not f["in_danger"]),
    (
        ["FSD jump", "Approach body"],
        "Tell me only if the next star on my route can be scooped for fuel.",
        lambda f: f["next_star_class"] in SCOOPABLE_STAR_CLASSES,
    ),
    (
        ["FSD jump", "Approach body"],
        "Warn me only if the next star on my route cannot be scooped.",
        lambda f: (
            f["next_star_class"] is not None
            and f["next_star_class"] not in SCOOPABLE_STAR_CLASSES
        ),
    ),
    (
        ["FSD jump"],
        "Brief me only if I have fewer than 3 jumps left.",
        lambda f: f["jumps_left"] is not None and f["jumps_left"] < 3,
    ),
    (
        ["FSD jump"],
        "Brief me only when I have arrived, meaning no jumps are left on the route.",
        lambda f: f["jumps_left"] is None,
    ),
    (
        ["FSD jump"],
        "Tell me if I'm low on fuel after the jump.",
        lambda f: f["low_fuel"],
    ),
    (
        ["Docked"],
        "Summarize the station only if it pays above average for gold.",
        lambda f: best_paying(f, "Gold"),
    ),
    (
        ["Docked"],
        "Tell me the best trade here, but only if the station has market data.",
        lambda f: bool(f["market_deals"]),
    ),
    (
        ["Docked"],
        "Only speak if the hull needs repair.",
        lambda f: f["hull_percent"] < 100,
    ),
    (
        ["Docked"],
        "Tell me if this station pays well for painite or palladium.",
        lambda f: best_paying(f, "Painite") or best_paying(f, "Palladium"),
    ),
    (
        ["Docking granted"],
        "Remind me about the landing gear only if it is still up.",
        lambda f: not f["gear_down"],
    ),
    (
        ["Docking granted"],
        "Only speak if my hardpoints are still out.",
        lambda f: f["hardpoints_out"],
    ),
    (
        ["Overheating"],
        "Only tell me if it happens during combat.",
        lambda f: f["in_danger"],
    ),
    (
        ["Overheating"],
        "Only tell me if it happens in supercruise.",
        lambda f: f["in_supercruise"],
    ),
    (
        ["Being interdicted"],
        "Only speak if my shields are already down.",
        lambda f: f["shields_down"],
    ),
    (
        ["Being interdicted"],
        "Tell me to submit unless my fuel is low.",
        lambda f: not f["low_fuel"],
    ),
    (
        ["Fuel low"],
        "Only warn me if the next star can't be scooped.",
        lambda f: (
            f["next_star_class"] is not None
            and f["next_star_class"] not in SCOOPABLE_STAR_CLASSES
        ),
    ),
    (
        ["Under attack"],
        "Only speak if my shields are down.",
        lambda f: f["shields_down"],
    ),
    (
        ["Under attack"],
        "Only speak if the hull is below 50 percent.",
        lambda f: f["hull_percent"] < 50,
    ),
]
# every fourth prompt is never trained on, so the test shows if the model follows new
# prompts
TEST_ONLY_PROMPTS = {
    REACTION_PROMPTS[number][1] for number in range(3, len(REACTION_PROMPTS), 4)
}


def reaction_question(event: str, prompt: str) -> dict:
    """The question the app sends for a Celeste reaction. Same shape works for Jev and
    for local models."""
    return {
        "type": "noul",
        "instructions": (
            f'The pilot\'s instruction for the "{event}" event is: "{prompt}" '
            "Should Celeste speak now?"
        ),
        "criteria": {
            "true": "The current game state meets the instruction, or the instruction "
            "has no condition.",
            "false": "The instruction tells Celeste to stay quiet in the current game "
            "state.",
        },
    }


# (question, is it true?)
FACT_QUESTIONS = [
    ("Is the ship overheating?", lambda f: f["overheating"]),
    ("Is the ship in danger or under attack?", lambda f: f["in_danger"]),
    ("Are the ship's shields down?", lambda f: f["shields_down"]),
    ("Is the ship being interdicted?", lambda f: f["interdicted"]),
    ("Is the fuel low?", lambda f: f["low_fuel"]),
    ("Is the hull below 50 percent?", lambda f: f["hull_percent"] < 50),
    ("Is the hull damaged at all?", lambda f: f["hull_percent"] < 100),
    ("Is the ship docked at a station?", lambda f: f["docked"]),
    ("Is the ship in supercruise?", lambda f: f["in_supercruise"]),
    ("Has the ship been assigned a landing pad?", lambda f: f["pad_assigned"]),
    ("Is the landing gear down?", lambda f: f["gear_down"]),
    ("Are the hardpoints deployed?", lambda f: f["hardpoints_out"]),
    (
        "Can the next star on the route be scooped for fuel?",
        lambda f: f["next_star_class"] in SCOOPABLE_STAR_CLASSES,
    ),
    (
        "Are there fewer than 5 jumps left on the route?",
        lambda f: f["jumps_left"] is not None and f["jumps_left"] < 5,
    ),
    (
        "Does the station market pay above the galactic average for any commodity?",
        lambda f: any(value > 0 for value in f["market_deals"].values()),
    ),
]


# ---------------------------------------------------------------- pilot utterances

PHRASINGS = {
    "DeployHeatSink": [
        "deploy a heat sink",
        "heat sink",
        "fire a heat sink",
        "pop a heat sink",
        "launch heat sink",
        "we're too hot, heat sink",
        "drop a heatsink",
        "use a heat sink",
        "heat sink now",
        "cool us down with a heat sink",
    ],
    "UseShieldCell": [
        "use a shield cell",
        "fire a shield cell",
        "shield cell",
        "pop a cell",
        "recharge the shields with a cell",
        "SCB now",
        "shield cell bank",
        "boost shields with a cell",
        "fire the SCB",
        "use the shield cell bank",
    ],
    "FireChaffLauncher": [
        "fire chaff",
        "chaff",
        "launch chaff",
        "deploy chaff",
        "drop chaff",
        "throw some chaff",
        "chaff now",
        "use the chaff launcher",
        "break their lock with chaff",
        "pop chaff",
    ],
    "UseBoostJuice": [
        "boost",
        "hit the boost",
        "boost now",
        "punch it",
        "engage boost",
        "give me a boost",
        "full boost",
        "boost away",
        "boost the engines",
        "kick in the boost",
    ],
    "LandingGearToggle": [
        "lower the landing gear",
        "gear down",
        "deploy landing gear",
        "retract the landing gear",
        "gear up",
        "put the gear down",
        "raise the gear",
        "landing gear",
        "drop the landing gear",
        "toggle the landing gear",
    ],
    "SetSpeedZero": [
        "cut the throttle",
        "full stop",
        "throttle to zero",
        "all stop",
        "set speed to zero",
        "stop the ship",
        "zero throttle",
        "kill our speed",
        "come to a full stop",
        "throttle zero",
    ],
    "SelectHighestThreat": [
        "target the highest threat",
        "who is the biggest threat, target them",
        "select highest threat",
        "lock the most dangerous enemy",
        "target the biggest threat",
        "highest threat",
        "lock onto the main threat",
        "target whoever is most dangerous",
        "select the top threat",
        "lock the highest threat",
    ],
    "IncreaseSystemsPower": [
        "power to systems",
        "more power to shields",
        "pips to systems",
        "divert power to systems",
        "four pips to sys",
        "max systems",
        "power to shields",
        "put power into systems",
        "increase system power",
        "shields power up",
    ],
    "SetSpeed75": [
        "set speed to seventy five percent",
        "three quarter throttle",
        "throttle seventy five",
        "speed seventy five percent",
        "go to seventy five percent",
        "set throttle to 75",
        "75 percent speed",
        "three quarters speed",
        "throttle to three quarters",
        "speed 75",
    ],
    "DeployHardpointToggle": [
        "deploy hardpoints",
        "weapons out",
        "retract hardpoints",
        "hardpoints",
        "guns out",
        "put the weapons away",
        "deploy weapons",
        "stow the hardpoints",
        "hardpoints out",
        "weapons hot",
    ],
    "ToggleCargoScoop": [
        "open the cargo scoop",
        "cargo scoop",
        "deploy the cargo scoop",
        "close the cargo scoop",
        "scoop out",
        "retract the cargo scoop",
        "open the scoop",
        "cargo hatch",
        "toggle cargo scoop",
        "scoop in",
    ],
    "NightVisionToggle": [
        "night vision",
        "turn on night vision",
        "night vision off",
        "toggle night vision",
        "it's too dark, night vision",
        "switch on night vision",
        "night mode",
        "enable night vision",
        "disable night vision",
        "night vision please",
    ],
}
# v3: ways of saying it that the first recording session showed and the list above
# missed
EXTRA_PHRASINGS = {
    "DeployHeatSink": ["engage a heat sink", "launch a heat sink right now"],
    "UseShieldCell": ["engage the shield cell", "use the SCB"],
    "FireChaffLauncher": ["engage chaff", "fire the chaff launcher"],
    "UseBoostJuice": ["engage the boosters", "use the boosters"],
    "LandingGearToggle": ["extend the landing gear", "engage the landing gear"],
    "SetSpeedZero": ["stop the engines", "speed zero"],
    "SelectHighestThreat": [
        "target the most dangerous enemy",
        "target the most dangerous target",
    ],
    "IncreaseSystemsPower": [
        "all pips to shields",
        "pips to shields",
        "all pips to systems",
        "four pips to shields",
    ],
    "SetSpeed75": ["engines to seventy five percent", "thrust to 75 percent"],
    "DeployHardpointToggle": [
        "extend the hardpoints",
        "engage the hardpoints",
        "deploy the weapons",
    ],
    "ToggleCargoScoop": ["extend the cargo scoop", "engage the cargo scoop"],
    "NightVisionToggle": ["engage night vision", "activate night vision"],
}
for action_name, extra_phrasings in EXTRA_PHRASINGS.items():
    PHRASINGS[action_name] += extra_phrasings

# v3: words tiny.en got wrong in the first recording session, plus close relatives
STT_CONFUSIONS = {
    "hardpoints": ["heart points", "hard points", "card points"],
    "landing gear": ["lending gear", "landing year", "lending you"],
    "pips": ["peeps", "pipes"],
    "chaff": ["chuff", "chaf"],
    "heat sink": ["heatsink", "heat think"],
    "night vision": ["right vision", "nite vision"],
    "boosters": ["bowsters", "boasters"],
    "boost": ["boast"],
    "shield cell": ["shield sell", "shield cel"],
    "throttle": ["trottle"],
    "cargo scoop": ["cargo scope"],
}
VERBS_THAT_CAN_FOLLOW_CAN_YOU = {
    "deploy",
    "fire",
    "pop",
    "launch",
    "use",
    "drop",
    "target",
    "select",
    "lock",
    "set",
    "go",
    "cut",
    "stop",
    "raise",
    "lower",
    "put",
    "retract",
    "open",
    "close",
    "toggle",
    "enable",
    "disable",
    "switch",
    "extend",
    "engage",
    "activate",
    "divert",
    "increase",
    "boost",
    "hit",
    "give",
    "throw",
    "recharge",
    "stow",
    "kill",
    "come",
    "turn",
}


def sound_like_speech_to_text(text: str, rng: random.Random) -> str:
    """Make a clean sentence look like what Whisper tiny.en writes: a misheard word now
    and then, often a capital and a full stop."""
    if rng.random() < 0.35:
        for word, misheard_words in STT_CONFUSIONS.items():
            if word in text:
                text = text.replace(word, rng.choice(misheard_words), 1)
                break
    if rng.random() < 0.5:
        text = text[:1].upper() + text[1:]
        if not text.endswith(("?", ".", "!")):
            text += "."
    return text


COMMAND_PREFIXES = [
    "",
    "",
    "",
    "celeste, ",
    "celeste ",
    "please ",
    "quick, ",
    "ok ",
    "hey celeste, ",
]
COMMAND_SUFFIXES = ["", "", "", " now", " please", " right now", ", now"]

# Every one of these goes to Celeste (D3 and D4: questions about the ship and small talk
# too)
TALK_UTTERANCES = [
    "where can I sell {commodity} for the best price",
    "which station near here buys {commodity}",
    "plan a route to {system}",
    "how many jumps to {system}",
    "is {system} a good place to trade",
    "what is happening in the galaxy today",
    "tell me about the {system} system",
    "what should I do next",
    "find me a station with a shipyard",
    "where do I get a better frame shift drive",
    "what engineers can upgrade my thrusters",
    "is it safe to fly through {system}",
    "what's the best way to make money with my ship",
    "explain how fuel scooping works",
    "what does the {commodity} market look like",
    "tell me a joke",
    "how are you today celeste",
    "summarize what happened on this trip",
    "thanks celeste",
    "good job",
    "how much fuel do I have",
    "where am I",
    "what ship am I flying",
    "how many credits do I have",
    "why did the heat sink fire",
    "remind me to lower the landing gear later",
    "don't deploy the hardpoints yet",
    "how many heat sinks do I have left",
    "was it a good idea to boost there",
    "should I fire chaff against torpedoes",
]


def pick_utterance(rng: random.Random) -> dict:
    """-> {text, asked_actions, phrasing_ids}"""
    utterance = pick_clean_utterance(rng)
    utterance["text"] = sound_like_speech_to_text(utterance["text"], rng)
    return utterance


def pick_clean_utterance(rng: random.Random) -> dict:
    roll = rng.random()
    if roll < 0.55:
        action = rng.choice(list(PHRASINGS))
        number = rng.randrange(len(PHRASINGS[action]))
        phrasing = PHRASINGS[action][number]
        if phrasing.split()[0] in VERBS_THAT_CAN_FOLLOW_CAN_YOU and rng.random() < 0.2:
            text = (
                rng.choice(["can you ", "could you ", "celeste, can you "])
                + phrasing
                + "?"
            )
        else:
            text = (
                rng.choice(COMMAND_PREFIXES) + phrasing + rng.choice(COMMAND_SUFFIXES)
            )
        return {
            "text": text,
            "asked_actions": [action],
            "phrasing_ids": [f"{action}#{number}"],
        }
    if roll < 0.70:
        first_action, second_action = rng.sample(list(PHRASINGS), 2)
        first_number = rng.randrange(len(PHRASINGS[first_action]))
        second_number = rng.randrange(len(PHRASINGS[second_action]))
        joiner = rng.choice([" and ", " and then ", ", ", " then "])
        text = (
            PHRASINGS[first_action][first_number]
            + joiner
            + PHRASINGS[second_action][second_number]
        )
        return {
            "text": text,
            "asked_actions": [first_action, second_action],
            "phrasing_ids": [
                f"{first_action}#{first_number}",
                f"{second_action}#{second_number}",
            ],
        }
    number = rng.randrange(len(TALK_UTTERANCES))
    text = TALK_UTTERANCES[number].format(
        commodity=rng.choice(COMMODITY_NAMES).lower(), system=rng.choice(SYSTEM_NAMES)
    )
    return {"text": text, "asked_actions": [], "phrasing_ids": [f"talk#{number}"]}


def held_out_phrasings() -> set:
    """Two phrasings per action, every fifth talk line and the benchmark's exact words
    go only to the test split."""
    rng = random.Random(1234)
    held_out = set()
    for action, phrasings in PHRASINGS.items():
        for number in rng.sample(range(len(phrasings)), 2):
            held_out.add(f"{action}#{number}")
    for number in range(0, len(TALK_UTTERANCES), 5):
        held_out.add(f"talk#{number}")
    held_out.add(
        f"LandingGearToggle#{
            PHRASINGS['LandingGearToggle'].index('lower the landing gear')
        }"
    )
    held_out.add(f"talk#{TALK_UTTERANCES.index('how much fuel do I have')}")
    return held_out


def recorded_utterance_examples(
    game_states: list[str], rng: random.Random
) -> list[dict]:
    """The pilot's own recordings (raw speech-to-text).
    First session (seen while building v3) -> train, twice with different game states.
    Second session (never used to build anything) -> test."""
    if not RECORDINGS_CSV.exists():
        return []
    examples = []
    with RECORDINGS_CSV.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file, delimiter=";"):
            asked_actions = [
                action for action in row["intent"].split(",") if action in ACTIONS
            ]
            gold = {action: action in asked_actions for action in ACTIONS}
            gold["needs_llm"] = not asked_actions
            is_first_session = row["recorded_at"] < FIRST_RECORDING_SESSION_ENDS
            copies = 2 if is_first_session else 1
            for copy_number in range(copies):
                examples.append(
                    {
                        "id": f"recording-{row['prompt_id']}-{copy_number}",
                        "kind": "recording",
                        "split": "train" if is_first_session else "test",
                        "situation": row["category"],
                        "state": {
                            "game_state": rng.choice(game_states),
                            "pilot_said": row["transcription"],
                        },
                        "questions": command_questions(),
                        "gold": gold,
                    }
                )
    return examples


FIRST_RECORDING_SESSION_ENDS = "2026-10-05 21:00:00"


# ---------------------------------------------------------------- main


async def main() -> None:
    hash_seed = int(sys.argv[1])
    rng = random.Random(hash_seed)
    held_out = held_out_phrasings()
    OUTPUT_DIR.mkdir(exist_ok=True)
    examples = []
    game_states = []

    for state_number in range(STATES_PER_RUN):
        facts = sample_facts(rng)
        game_state = swap_names(await build_game_state(facts), rng)
        game_states.append(game_state)
        state_is_test = rng.random() < 0.15

        # prompts written for this event first (they are rarer), then general ones
        event_prompts = [
            prompt
            for prompt in REACTION_PROMPTS
            if prompt[0] and facts["event"] in prompt[0]
        ]
        general_prompts = [prompt for prompt in REACTION_PROMPTS if prompt[0] is None]
        chosen_prompts = rng.sample(event_prompts, min(2, len(event_prompts)))
        chosen_prompts += rng.sample(
            general_prompts, REACTION_QUESTIONS_PER_STATE - len(chosen_prompts)
        )
        for prompt_number, (_, prompt, is_true) in enumerate(chosen_prompts):
            examples.append(
                {
                    "id": f"reaction-{hash_seed}-{state_number}-{prompt_number}",
                    "kind": "reaction",
                    "split": "test"
                    if state_is_test or prompt in TEST_ONLY_PROMPTS
                    else "train",
                    "situation": facts["event"],
                    "prompt": prompt,
                    "state": {"game_state": game_state, "event": facts["event"]},
                    "questions": {"speak": reaction_question(facts["event"], prompt)},
                    "gold": {"speak": bool(is_true(facts))},
                }
            )

        fact_questions = rng.sample(FACT_QUESTIONS, FACT_QUESTIONS_PER_STATE)
        examples.append(
            {
                "id": f"fact-{hash_seed}-{state_number}",
                "kind": "fact",
                "split": "test" if state_is_test else "train",
                "situation": facts["event"],
                "state": {"game_state": game_state},
                "questions": {
                    f"fact_{number}": {"type": "noul", "instructions": question}
                    for number, (question, _) in enumerate(fact_questions)
                },
                "gold": {
                    f"fact_{number}": bool(is_true(facts))
                    for number, (_, is_true) in enumerate(fact_questions)
                },
            }
        )

    for utterance_number in range(UTTERANCES_PER_RUN):
        utterance = pick_utterance(rng)
        gold = {action: action in utterance["asked_actions"] for action in ACTIONS}
        gold["needs_llm"] = not utterance["asked_actions"]
        examples.append(
            {
                "id": f"command-{hash_seed}-{utterance_number}",
                "kind": "command",
                "split": "test"
                if any(phrasing in held_out for phrasing in utterance["phrasing_ids"])
                else "train",
                "situation": "pilot command"
                if utterance["asked_actions"]
                else "pilot talk",
                "state": {
                    "game_state": rng.choice(game_states),
                    "pilot_said": utterance["text"],
                },
                "questions": command_questions(),
                "gold": gold,
            }
        )

    if hash_seed == 0:
        examples += recorded_utterance_examples(game_states, rng)

    output_file = OUTPUT_DIR / f"part_{hash_seed}.jsonl"
    with output_file.open("w", encoding="utf-8") as file:
        for example in examples:
            file.write(json.dumps(example, ensure_ascii=False) + "\n")
    print(f"{output_file}: {len(examples)} examples")


if __name__ == "__main__":
    asyncio.run(main())
