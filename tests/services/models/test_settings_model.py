import unittest

from pydantic import ValidationError

from services.models.journal_event import KNOWN_EVENTS
from services.models.settings_model import (
    EventReactionModel,
    LLMModel,
    PathModel,
    SettingsModel,
    TTSModel,
)


def _make_tts_model() -> TTSModel:
    return TTSModel(voice="en-GB-SoniaNeural", volume=1.0)


class TestTTSModel(unittest.TestCase):
    def test_assigning_valid_volume_updates_the_field(self):
        tts_model = _make_tts_model()

        tts_model.volume = 0.5

        self.assertEqual(tts_model.volume, 0.5)

    def test_assigning_out_of_range_volume_raises_validation_error(self):
        tts_model = _make_tts_model()

        with self.assertRaises(ValidationError):
            tts_model.volume = 1.5


def _base_settings_kwargs() -> dict:
    return dict(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="prompt", user_prompt=""),
    )


class TestSettingsModelEventReaction(unittest.TestCase):
    def test_default_event_reaction_only_load_game_enabled(self):
        settings = SettingsModel(**_base_settings_kwargs())
        event_reaction = settings.event_reaction.event_reaction

        self.assertTrue(event_reaction["LoadGame"])
        self.assertEqual(set(event_reaction), {event.value for event in KNOWN_EVENTS})
        other_events = {
            key: value for key, value in event_reaction.items() if key != "LoadGame"
        }
        self.assertTrue(all(value is False for value in other_events.values()))

    def test_explicit_full_mapping_is_preserved_unchanged(self):
        full_mapping = {event.value: event.value == "FSDJump" for event in KNOWN_EVENTS}

        settings = SettingsModel(
            **_base_settings_kwargs(),
            event_reaction={"event_reaction": full_mapping},
        )

        self.assertEqual(settings.event_reaction.event_reaction, full_mapping)

    def test_partial_mapping_fills_missing_known_events_with_false(self):
        settings = SettingsModel(
            **_base_settings_kwargs(),
            event_reaction={"event_reaction": {"FSDJump": True}},
        )
        event_reaction = settings.event_reaction.event_reaction

        self.assertTrue(event_reaction["FSDJump"])
        self.assertFalse(event_reaction["LoadGame"])
        self.assertEqual(set(event_reaction), {event.value for event in KNOWN_EVENTS})

    def test_unknown_event_key_is_stripped_from_event_reaction_mapping(self):
        settings = SettingsModel(
            **_base_settings_kwargs(),
            event_reaction={"event_reaction": {"NotARealEvent": True, "FSDJump": True}},
        )
        event_reaction = settings.event_reaction.event_reaction

        self.assertNotIn("NotARealEvent", event_reaction)
        self.assertTrue(event_reaction["FSDJump"])
        self.assertEqual(set(event_reaction), {event.value for event in KNOWN_EVENTS})

    def test_direct_validator_call_rejects_non_dict_input(self):
        # Pydantic's own dict[str, bool] field-type check rejects non-dict
        # input before this "after" validator ever runs, so the isinstance
        # guard inside it is unreachable through the public SettingsModel(...)
        # constructor. Calling the validator classmethod directly is the only
        # way to exercise that guard clause.
        with self.assertRaises(ValueError) as ctx:
            EventReactionModel.prepare_potentially_malformed_events_and_validate(
                ["not", "a", "dict"]
            )

        self.assertIn("must be a dictionary", str(ctx.exception))

    def test_constructing_with_non_dict_event_reaction_raises_pydantic_validation_error(
        self,
    ):
        with self.assertRaises(ValidationError):
            SettingsModel(
                **_base_settings_kwargs(), event_reaction=["not", "a", "dict"]
            )


if __name__ == "__main__":
    unittest.main()
