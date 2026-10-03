import ast
import importlib
import inspect
import pkgutil
import unittest

from pydantic import TypeAdapter

from edceleste.projection import event_projections
from edceleste.services.event_bus import EventBus
from edceleste.services.game_state_service import GameStateService
from edceleste.services.models import game_events
from edceleste.services.models.game_events import GameEvent, UnknownCheckedEvent
from edceleste.services.models.journal_event import JournalEvent

from tests import TEST_KNOWN_EVENTS_FILE_LOCATION

PROJECTION_PROTOCOL_MODULE = "projection"


def load_recognized_event_models() -> list[type[GameEvent]]:
    return [
        model
        for _, model in inspect.getmembers(game_events, inspect.isclass)
        if issubclass(model, GameEvent)
        and model not in (GameEvent, UnknownCheckedEvent)
    ]


def load_projection_modules() -> list:
    return [
        importlib.import_module(f"{event_projections.__name__}.{module_info.name}")
        for module_info in pkgutil.iter_modules(event_projections.__path__)
        if module_info.name != PROJECTION_PROTOCOL_MODULE
    ]


def find_event_names_handled_in(module) -> set[str]:
    """Names that the module checks with isinstance(event, SomeEvent)."""
    handled_names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        is_isinstance_call = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
        )
        if is_isinstance_call:
            handled_names.update(
                name.id for name in ast.walk(node.args[1]) if isinstance(name, ast.Name)
            )
    return handled_names


def load_real_sample(event_name: str) -> GameEvent:
    adapter = TypeAdapter(JournalEvent)
    with open(TEST_KNOWN_EVENTS_FILE_LOCATION, mode="r") as known_events_file:
        for line in known_events_file:
            if f'"event":"{event_name}"' in line.replace(" ", ""):
                return adapter.validate_json(line)
    raise AssertionError(f"No {event_name} sample in the known events file")


class EveryRecognizedEventFeedsGameStateTest(unittest.TestCase):
    def test_should_find_all_recognized_event_models(self):
        # A sanity check, so the guard below cannot pass on an empty list.
        recognized_event_names = {
            model.__name__ for model in load_recognized_event_models()
        }

        self.assertGreater(len(recognized_event_names), 20)
        self.assertIn("DockingGrantedEvent", recognized_event_names)
        self.assertNotIn("UnknownCheckedEvent", recognized_event_names)

    def test_should_have_a_projection_for_every_recognized_event(self):
        handled_names = set()
        for projection_module in load_projection_modules():
            handled_names |= find_event_names_handled_in(projection_module)

        events_feeding_nothing = sorted(
            model.__name__
            for model in load_recognized_event_models()
            if model.__name__ not in handled_names
        )

        self.assertEqual(
            [],
            events_feeding_nothing,
            "These recognized events are not handled by any projection. "
            "Handle them in a projection or stop recognizing them.",
        )


class RealEventsReachGameStateTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.event_bus = EventBus()
        self.game_state = GameStateService(self.event_bus)

    async def test_should_tell_assigned_pad_after_docking_granted(self):
        await self.event_bus.publish(load_real_sample("DockingGranted"))

        self.assertIn(
            "Player was assigned landing pad 44 at station Hammel Terminal.",
            self.game_state.get_game_state_projection(),
        )

    async def test_should_forget_assigned_pad_after_undocked(self):
        await self.event_bus.publish(load_real_sample("DockingGranted"))
        await self.event_bus.publish(load_real_sample("Undocked"))

        self.assertNotIn("landing pad", self.game_state.get_game_state_projection())

    async def test_should_tell_credits_and_game_mode_after_load_game(self):
        await self.event_bus.publish(load_real_sample("LoadGame"))

        game_state_projection = self.game_state.get_game_state_projection()

        self.assertIn("Commander name is SANTIAGOW", game_state_projection)
        self.assertIn("Commander has 575382 of credits", game_state_projection)
        self.assertIn("Commander ship is Cobra Mk III", game_state_projection)
        self.assertIn("Commander plays in Open game mode.", game_state_projection)

    async def test_should_tell_where_ship_dropped_out_of_supercruise(self):
        await self.event_bus.publish(load_real_sample("SupercruiseDestinationDrop"))

        self.assertIn(
            "Player dropped out of supercruise at Resource Extraction Site [Low].",
            self.game_state.get_game_state_projection(),
        )
