from datetime import datetime
import unittest

from edceleste.services.models.game_events import StartJumpEvent
from edceleste.ui.widgets.dashboard.view_models.journal_log_view_model import (
    JournalLogViewModel,
)


class TestJournalLogViewModel(unittest.TestCase):
    def test_start_jump_hyperspace_includes_system_details(self):
        event = StartJumpEvent(
            event="StartJump",
            timestamp=datetime.now(),
            JumpType="Hyperspace",
            Taxi=False,
            StarSystem="Test System",
            SystemAddress=123456789,
            StarClass="K",
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(
            view_model.details,
            "JumpType: Hyperspace, StarSystem: Test System, SystemAddress: 123456789",
        )

    def test_start_jump_supercruise_omits_missing_system_details(self):
        event = StartJumpEvent(
            event="StartJump",
            timestamp=datetime.now(),
            JumpType="Supercruise",
            Taxi=False,
        )

        view_model = JournalLogViewModel.from_event(event)

        self.assertEqual(view_model.details, "JumpType: Supercruise")
        self.assertNotIn("None", view_model.details)


if __name__ == "__main__":
    unittest.main()
