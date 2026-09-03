import unittest
from unittest.mock import Mock

from edceleste.ui.screens.settings.settings_screen import SettingsScreen


class TestCompareDictsAndReturnModifiedCount(unittest.TestCase):
    def setUp(self):
        # The method under test is pure (dict in, int out) and doesn't touch
        # anything Textual sets up on mount, so we don't need a running app.
        self.settings_screen = SettingsScreen(settings_repository=Mock())

    def test_returns_zero_for_identical_dicts(self):
        settings = {"model": "claude-haiku-4-5-20251001", "system_prompt": "hi"}

        result = self.settings_screen.compare_dicts_and_return_modified_count(
            settings, settings
        )

        self.assertEqual(result, 0)

    def test_counts_one_change_per_differing_top_level_field(self):
        old = {"model": "claude-haiku-4-5-20251001", "system_prompt": "hi"}
        new = {"model": "claude-sonnet-5", "system_prompt": "hi"}

        result = self.settings_screen.compare_dicts_and_return_modified_count(new, old)

        self.assertEqual(result, 1)

    def test_recurses_into_nested_dicts_on_both_sides(self):
        old = {"provider": {"type": "claude_agent_sdk", "model": "a"}}
        new = {"provider": {"type": "claude_agent_sdk", "model": "b"}}

        result = self.settings_screen.compare_dicts_and_return_modified_count(new, old)

        self.assertEqual(result, 1)

    def test_switching_a_discriminated_union_variant_does_not_raise_key_error(self):
        # Mirrors switching llm.provider from claude_agent_sdk to
        # chat_completions (or tts.provider from edge to chatterbox) - the
        # two variants don't share the same field names.
        old = {"provider": {"type": "claude_agent_sdk", "model": "claude-haiku"}}
        new = {
            "provider": {
                "type": "chat_completions",
                "model": "",
                "base_url": "",
                "bearer_token": "",
            }
        }

        result = self.settings_screen.compare_dicts_and_return_modified_count(new, old)

        # Every key that exists on only one side counts as a change: type,
        # model, base_url, bearer_token = 4.
        self.assertEqual(result, 4)


if __name__ == "__main__":
    unittest.main()
