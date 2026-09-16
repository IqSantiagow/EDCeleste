from datetime import datetime
from typing import get_args
import unittest

from edceleste.services.models.game_events import (
    DiedEvent,
    FSDJumpEvent,
    FSDTargetEvent,
    FuelScoopEvent,
    PromotionEvent,
    RankEvent,
    RefuelAllEvent,
    StartJumpEvent,
    StatusEvent,
    UndockedEvent,
    UnknownCheckedEvent,
)
from edceleste.services.models.journal_event import JournalEvent
from edceleste.ui.screens.dashboard.view_models.journal_log_view_model import (
    CATEGORY_COMBAT,
    CATEGORY_NAV,
    CATEGORY_OTHER,
    CATEGORY_TOOLS,
    _CATEGORIES,
    JournalLogViewModel,
)


def make_fsd_jump(star_system: str = "LHS 3447", jump_dist: float = 8.61):
    return FSDJumpEvent(
        event="FSDJump",
        timestamp=datetime.now(),
        StarSystem=star_system,
        SystemAddress=1,
        StarPos=[0.0, 0.0, 0.0],
        SystemAllegiance="Independent",
        SystemEconomy_Localised="Extraction",
        SystemSecondEconomy_Localised="Refinery",
        SystemGovernment_Localised="Anarchy",
        SystemSecurity_Localised="Low Security",
        Population=12704,
        JumpDist=jump_dist,
        FuelUsed=1.2,
        FuelLevel=19.1,
    )


class TestJournalLogViewModelDetails(unittest.TestCase):
    def test_fsd_jump_details_show_distance_travelled(self):
        view_model = JournalLogViewModel.from_event(make_fsd_jump())

        self.assertEqual(view_model.details, "Arrived · 8.61 ly travelled")

    def test_fuel_scoop_details_show_scooped_and_total(self):
        event = FuelScoopEvent(
            event="FuelScoop", timestamp=datetime.now(), Scooped=2.41, Total=31.2
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "+2.41 T scooped · total 31.2 T")

    def test_refuel_all_details_show_cost_with_space_separator(self):
        event = RefuelAllEvent(
            event="RefuelAll", timestamp=datetime.now(), Cost=1284, Amount=32.0
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "Topped off · 1 284 CR")

    def test_promotion_details_translate_rank_number_to_name(self):
        event = PromotionEvent(event="Promotion", timestamp=datetime.now(), Explore=5)

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "Explore rank → Pathfinder")

    def test_promotion_details_join_multiple_promoted_ranks(self):
        event = PromotionEvent(
            event="Promotion", timestamp=datetime.now(), Combat=3, Trade=4
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(
            view_model.details, "Combat rank → Competent · Trade rank → Merchant"
        )

    def test_promotion_details_fall_back_to_number_for_ladderless_rank(self):
        event = PromotionEvent(event="Promotion", timestamp=datetime.now(), Empire=5)

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "Empire rank → rank 5")

    def test_start_jump_hyperspace_details_show_target_system(self):
        event = StartJumpEvent(
            event="StartJump",
            timestamp=datetime.now(),
            JumpType="Hyperspace",
            Taxi=False,
            StarSystem="LHS 3447",
            SystemAddress=123456789,
            StarClass="K",
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "Hyperspace charging → LHS 3447 · class K")

    def test_start_jump_supercruise_details_have_no_system(self):
        event = StartJumpEvent(
            event="StartJump",
            timestamp=datetime.now(),
            JumpType="Supercruise",
            Taxi=False,
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "Supercruise charging")
        self.assertNotIn("None", view_model.details)

    def test_died_details_without_killer_name(self):
        event = DiedEvent(event="Died", timestamp=datetime.now())

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "Destroyed")


class TestJournalLogViewModelSystemColumn(unittest.TestCase):
    def test_fsd_jump_fills_system_column(self):
        view_model = JournalLogViewModel.from_event(make_fsd_jump("Cemiess"))

        self.assertEqual(view_model.system, "Cemiess")

    def test_fsd_target_fills_system_column_from_name_field(self):
        event = FSDTargetEvent(
            event="FSDTarget",
            timestamp=datetime.now(),
            Name="Wolf 1301",
            SystemAddress=1,
            StarClass="M",
            RemainingJumpsInRoute=4,
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.system, "Wolf 1301")

    def test_undocked_leaves_system_column_empty(self):
        event = UndockedEvent(
            event="Undocked", timestamp=datetime.now(), StationName="Mengoli Hub"
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.system, "")

    def test_supercruise_start_jump_leaves_system_column_empty(self):
        event = StartJumpEvent(
            event="StartJump",
            timestamp=datetime.now(),
            JumpType="Supercruise",
            Taxi=False,
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.system, "")


class TestJournalLogViewModelCategories(unittest.TestCase):
    def test_fsd_jump_is_nav_category(self):
        self.assertEqual(
            JournalLogViewModel.from_event(make_fsd_jump()).category, CATEGORY_NAV
        )

    def test_fuel_scoop_is_tools_category(self):
        event = FuelScoopEvent(
            event="FuelScoop", timestamp=datetime.now(), Scooped=2.41, Total=31.2
        )

        self.assertEqual(JournalLogViewModel.from_event(event).category, CATEGORY_TOOLS)

    def test_died_is_combat_category(self):
        event = DiedEvent(event="Died", timestamp=datetime.now())

        self.assertEqual(
            JournalLogViewModel.from_event(event).category, CATEGORY_COMBAT
        )

    def test_rank_is_other_category(self):
        event = RankEvent(event="Rank", timestamp=datetime.now(), Explore=5)

        self.assertEqual(JournalLogViewModel.from_event(event).category, CATEGORY_OTHER)

    def test_unknown_event_gets_other_category_and_empty_details(self):
        event = UnknownCheckedEvent(event="SomeBrandNewEvent", timestamp=datetime.now())

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.category, CATEGORY_OTHER)
        self.assertEqual(view_model.details, "")
        self.assertEqual(view_model.event, "SomeBrandNewEvent")

    def test_every_known_event_class_has_a_category(self):
        """Stops anyone adding a new event without giving it a category."""
        event_classes_without_category = [
            event_class.__name__
            for event_class in _known_journal_event_classes()
            if event_class not in _CATEGORIES
        ]

        self.assertEqual(event_classes_without_category, [])


def _known_journal_event_classes() -> list[type]:
    """Model classes for every event in the JournalEvent union.

    StatusEvent is left out - it does not come from the journal file and
    never reaches the stream shown in the log.
    """
    event_union = get_args(JournalEvent)[0]
    event_classes = [get_args(variant)[0] for variant in get_args(event_union)]
    return [
        event_class for event_class in event_classes if event_class is not StatusEvent
    ]


if __name__ == "__main__":
    unittest.main()
