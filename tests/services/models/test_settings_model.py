import unittest

from pydantic import ValidationError

from edceleste.services.models.journal_event import KNOWN_EVENTS
from edceleste.services.models.settings_model import (
    ChatterboxTTSProviderModel,
    EdgeTTSProviderModel,
    EventReactionModel,
    GameActionsModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)


def _make_tts_model() -> TTSModel:
    return TTSModel(
        provider=EdgeTTSProviderModel(type="edge", voice="en-GB-SoniaNeural"),
        volume=1.0,
    )


class TestTTSModel(unittest.TestCase):
    def test_assigning_valid_volume_updates_the_field(self):
        tts_model = _make_tts_model()

        tts_model.volume = 0.5

        self.assertEqual(tts_model.volume, 0.5)

    def test_assigning_out_of_range_volume_raises_validation_error(self):
        tts_model = _make_tts_model()

        with self.assertRaises(ValidationError):
            tts_model.volume = 1.5

    def test_provider_defaults_to_edge_when_key_absent(self):
        tts_model = TTSModel(volume=1.0)

        self.assertIsInstance(tts_model.provider, EdgeTTSProviderModel)

    def test_chatterbox_provider_is_picked_by_the_type_discriminator(self):
        tts_model = TTSModel.model_validate(
            {
                "provider": {
                    "type": "chatterbox",
                    "profile": "celeste-v3",
                    "exaggeration": 0.7,
                    "cfg_weight": 0.5,
                    "device": "auto",
                },
                "volume": 1.0,
            }
        )

        self.assertIsInstance(tts_model.provider, ChatterboxTTSProviderModel)
        self.assertEqual(tts_model.provider.profile, "celeste-v3")

    def test_chatterbox_provider_uses_defaults_for_optional_knobs(self):
        provider = ChatterboxTTSProviderModel(type="chatterbox", profile="celeste-v3")

        self.assertEqual(provider.exaggeration, 0.5)
        self.assertEqual(provider.cfg_weight, 0.5)
        self.assertEqual(provider.device, "auto")

    def test_chatterbox_provider_rejects_unknown_device(self):
        with self.assertRaises(ValidationError):
            ChatterboxTTSProviderModel(
                type="chatterbox", profile="celeste-v3", device="tpu"
            )

    def test_chatterbox_provider_rejects_out_of_range_cfg_weight(self):
        with self.assertRaises(ValidationError):
            ChatterboxTTSProviderModel(
                type="chatterbox", profile="celeste-v3", cfg_weight=1.5
            )


class TestSttModel(unittest.TestCase):
    def test_enabled_defaults_to_true_when_key_absent(self):
        stt_model = SttModel(model="tiny.en")

        self.assertTrue(stt_model.enabled)

    def test_enabled_round_trips_through_model_dump(self):
        stt_model = SttModel(model="tiny.en", enabled=False)

        dumped = stt_model.model_dump()

        self.assertEqual(
            dumped, {"enabled": False, "model": "tiny.en", "input_device": None}
        )
        self.assertEqual(SttModel.model_validate(dumped), stt_model)


class TestGameActionsModel(unittest.TestCase):
    def test_enabled_defaults_to_false(self):
        game_actions_model = GameActionsModel()

        self.assertFalse(game_actions_model.enabled)

    def test_enabled_round_trips_through_model_dump(self):
        game_actions_model = GameActionsModel(enabled=True)

        dumped = game_actions_model.model_dump()

        self.assertEqual(dumped, {"enabled": True})
        self.assertEqual(GameActionsModel.model_validate(dumped), game_actions_model)

    def test_settings_model_defaults_game_actions_to_disabled_when_key_absent(self):
        settings = SettingsModel(**_base_settings_kwargs())

        self.assertFalse(settings.game_actions.enabled)


def _base_settings_kwargs() -> dict:
    return dict(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(voice="en-GB-SoniaNeural", volume=1.0),
        llm=LLMModel(api_key="sk-ant-test", system_prompt="prompt", user_prompt=""),
        stt=SttModel(model="tiny.en"),
    )


class TestSettingsModelEventReaction(unittest.TestCase):
    def test_default_event_reaction_only_load_game_enabled(self):
        settings = SettingsModel(**_base_settings_kwargs())
        event_reactions = settings.event_reactions.reactions

        self.assertTrue(event_reactions["LoadGame"])
        self.assertEqual(set(event_reactions), {event.value for event in KNOWN_EVENTS})
        other_events = {
            key: value for key, value in event_reactions.items() if key != "LoadGame"
        }
        self.assertTrue(all(value is False for value in other_events.values()))

    def test_explicit_full_mapping_is_preserved_unchanged(self):
        full_mapping = {event.value: event.value == "FSDJump" for event in KNOWN_EVENTS}

        settings = SettingsModel(
            **_base_settings_kwargs(),
            event_reactions={"reactions": full_mapping},
        )

        self.assertEqual(settings.event_reactions.reactions, full_mapping)

    def test_partial_mapping_fills_missing_known_events_with_false(self):
        settings = SettingsModel(
            **_base_settings_kwargs(),
            event_reactions={"reactions": {"FSDJump": True}},
        )
        event_reactions = settings.event_reactions.reactions

        self.assertTrue(event_reactions["FSDJump"])
        self.assertFalse(event_reactions["LoadGame"])
        self.assertEqual(set(event_reactions), {event.value for event in KNOWN_EVENTS})

    def test_unknown_event_key_is_stripped_from_event_reaction_mapping(self):
        settings = SettingsModel(
            **_base_settings_kwargs(),
            event_reactions={"reactions": {"NotARealEvent": True, "FSDJump": True}},
        )
        event_reactions = settings.event_reactions.reactions

        self.assertNotIn("NotARealEvent", event_reactions)
        self.assertTrue(event_reactions["FSDJump"])
        self.assertEqual(set(event_reactions), {event.value for event in KNOWN_EVENTS})

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
                **_base_settings_kwargs(), event_reactions=["not", "a", "dict"]
            )


if __name__ == "__main__":
    unittest.main()
