import unittest

from edceleste.ui.screens.settings.widgets.tts.voice_clone_modal_screen import (
    pick_free_profile_name,
)


class TestPickFreeProfileName(unittest.TestCase):
    def test_returns_the_wanted_name_when_it_is_free(self):
        self.assertEqual(pick_free_profile_name("celeste", ["narrator"]), "celeste")

    def test_skips_every_taken_number(self):
        taken_names = ["celeste", "celeste_1", "narrator"]

        self.assertEqual(pick_free_profile_name("celeste", taken_names), "celeste_2")


if __name__ == "__main__":
    unittest.main()
