"""Builds the game states for the benchmark with the real EventBus + GameStateService.

Run with the PROJECT venv and PYTHONHASHSEED=0 (projections live in a frozenset):
    PYTHONHASHSEED=0 .venv/Scripts/python.exe model_bench/scripts/build_scenarios.py
Writes model_bench/scenarios.json, which the bench venv reads.
"""

import asyncio
import json
from pathlib import Path

from pydantic import TypeAdapter

from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models.game_events import StatusEvent, StatusFlags
from edceleste.services.models.journal_event import JournalEvent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_FILE = PROJECT_ROOT / "tests" / "resources" / "test_known_events.jsonl"
OUTPUT_FILE = PROJECT_ROOT / "model_bench" / "scenarios.json"

# Fixture events that would contradict a living ship in every scenario
SKIPPED_FIXTURE_EVENTS = {"Died", "Resurrect", "Docked", "DockingGranted", "FuelScoop"}

FLYING = StatusFlags.InMainShip | StatusFlags.ShieldsUp

SCENARIOS = [
    {
        "id": "overheat_scooping",
        "description": "Fuel scooping at a star, temperature rising",
        "extra_events": ["FuelScoop"],
        "flags": FLYING
        | StatusFlags.Supercruise
        | StatusFlags.ScoopingFuel
        | StatusFlags.Overheating,
        "fuel_main": 12.1,
        "expected_actions": ["DeployHeatSink"],
    },
    {
        "id": "interdiction",
        "description": "Someone is pulling the ship out of supercruise",
        "extra_events": [],
        "flags": FLYING | StatusFlags.Supercruise | StatusFlags.BeingInterdicted,
        "fuel_main": 14.0,
        "expected_actions": ["UseBoostJuice", "SetSpeedZero", "FireChaffLauncher"],
    },
    {
        "id": "combat_shields_down",
        "description": "Combat, shields are down, ship under fire",
        "extra_events": [],
        "flags": StatusFlags.InMainShip
        | StatusFlags.IsInDanger
        | StatusFlags.HardpointsDeployed,
        "fuel_main": 14.0,
        "expected_actions": [
            "UseShieldCell",
            "FireChaffLauncher",
            "SelectHighestThreat",
            "IncreaseSystemsPower",
            "UseBoostJuice",
        ],
    },
    {
        "id": "docking_approach",
        "description": "Docking granted, ship flying to the pad, gear still up",
        "extra_events": ["DockingGranted"],
        "flags": FLYING,
        "fuel_main": 14.0,
        "expected_actions": ["LandingGearToggle"],
    },
    {
        "id": "calm_supercruise",
        "description": "Supercruise on the way, nothing happens (negative control)",
        "extra_events": [],
        "flags": FLYING | StatusFlags.Supercruise,
        "fuel_main": 14.0,
        "expected_actions": [],
    },
    {
        "id": "docked_market",
        "description": "Ship stands on the pad, market open (negative control)",
        "extra_events": ["Docked"],
        "flags": FLYING | StatusFlags.Docked | StatusFlags.LandingGearDown,
        "fuel_main": 14.0,
        "expected_actions": [],
    },
    {
        "id": "low_fuel",
        "description": "Fuel on reserve, far from a star (negative control)",
        "extra_events": [],
        "flags": FLYING | StatusFlags.Supercruise | StatusFlags.LowFuel,
        "fuel_main": 1.9,
        "expected_actions": [],
    },
]


def read_all_fixture_events() -> list[dict]:
    lines = FIXTURES_FILE.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def find_fixture_event(event_name: str) -> dict:
    for raw_event in read_all_fixture_events():
        if raw_event["event"] == event_name:
            return raw_event
    raise ValueError(f"No fixture line for event {event_name}")


async def build_game_state(scenario: dict, fixture_events: list[dict]) -> str:
    event_bus = EventBus()
    game_state_service = GameStateService(event_bus)
    journal_event_parser = TypeAdapter(JournalEvent)

    extra_events = [find_fixture_event(name) for name in scenario["extra_events"]]
    for raw_event in fixture_events + extra_events:
        await event_bus.publish(journal_event_parser.validate_python(raw_event))

    status_event = StatusEvent(
        timestamp="2026-10-05T20:00:01Z",
        event="Status",
        Flags=int(scenario["flags"]),
        Pips=[4, 4, 4],
        Fuel={"FuelMain": scenario["fuel_main"], "FuelReservoir": 0.4},
    )
    await event_bus.publish(status_event)
    return game_state_service.get_game_state_projection()


async def main() -> None:
    fixture_events = [
        raw_event
        for raw_event in read_all_fixture_events()
        if raw_event["event"] not in SKIPPED_FIXTURE_EVENTS
    ]
    output = []
    for scenario in SCENARIOS:
        game_state = await build_game_state(scenario, fixture_events)
        output.append(
            {
                "id": scenario["id"],
                "description": scenario["description"],
                "expected_actions": scenario["expected_actions"],
                "game_state": game_state,
            }
        )
        print(f"{scenario['id']:22} {len(game_state):5} chars")
    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())
