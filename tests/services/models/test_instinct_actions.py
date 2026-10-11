import unittest

from edceleste.services.models.instinct_actions import (
    ACTION_DESCRIPTIONS,
    NO_ACTION,
    NO_ACTION_DESCRIPTION,
    build_which_action_questions,
)
from edceleste.services.models.keybinds_model import EdAction


class InstinctActionsTest(unittest.TestCase):
    def test_every_ed_action_has_a_description(self):
        self.assertEqual(set(ACTION_DESCRIPTIONS), set(EdAction))

    def test_question_lists_offered_actions_in_order_and_ends_with_none(self):
        offered = [EdAction.LANDING_GEAR_TOGGLE, EdAction.SUPERCRUISE]

        question = build_which_action_questions(offered)["action"]

        self.assertEqual(
            list(question["criteria"]), ["LandingGearToggle", "Supercruise", "none"]
        )
        self.assertEqual(
            question["criteria"]["LandingGearToggle"],
            ACTION_DESCRIPTIONS[EdAction.LANDING_GEAR_TOGGLE],
        )
        self.assertEqual(
            question["criteria"]["Supercruise"],
            ACTION_DESCRIPTIONS[EdAction.SUPERCRUISE],
        )
        self.assertEqual(question["criteria"][NO_ACTION], NO_ACTION_DESCRIPTION)

    def test_question_has_the_trained_name_type_and_instructions(self):
        questions = build_which_action_questions([EdAction.SUPERCRUISE])

        self.assertEqual(list(questions), ["action"])
        self.assertEqual(questions["action"]["type"], "choice")
        self.assertEqual(
            questions["action"]["instructions"],
            "Which ship action did the pilot just ask for?",
        )

    def test_question_contains_only_the_offered_actions(self):
        # The table has 41 actions, so a missing one is not a coincidence
        question = build_which_action_questions([EdAction.SUPERCRUISE])["action"]

        self.assertEqual(list(question["criteria"]), ["Supercruise", "none"])

    def test_question_with_no_offered_actions_has_only_none(self):
        question = build_which_action_questions([])["action"]

        self.assertEqual(question["criteria"], {"none": NO_ACTION_DESCRIPTION})

    def test_trained_texts_are_unchanged(self):
        # The model was trained on these exact words. This was also compared
        # with every "action" question of the training data (4459 of them).
        self.assertEqual(
            ACTION_DESCRIPTIONS[EdAction.LANDING_GEAR_TOGGLE],
            "lower or raise the landing gear",
        )
        self.assertEqual(
            ACTION_DESCRIPTIONS[EdAction.DEPLOY_HARDPOINT_TOGGLE],
            "deploy or retract the hardpoints (weapons)",
        )
        self.assertEqual(
            ACTION_DESCRIPTIONS[EdAction.HYPER_SUPER_COMBINATION],
            "frame shift drive: supercruise or jump, whichever fits",
        )
        self.assertEqual(
            NO_ACTION_DESCRIPTION,
            "no ship action: the pilot is talking, asking or refusing",
        )


if __name__ == "__main__":
    unittest.main()
