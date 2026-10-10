import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import numpy as np
import soundfile as sf

from edceleste.services.event_bus import EventBus
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.llm_service import SYSTEM_PROMPT
from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    EdgeParamsModel,
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
    TtsProviderParams,
)
from edceleste.services.models.voice_cloning_models import VoiceCloningState
from edceleste.services.settings_service import SettingsService
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_service import (
    DEFAULT_VOICE_SAMPLE_TEXT,
    SILENCE_FLOOR_DBFS,
    TTSEvent,
    TTSService,
    calculate_noise_floor_dbfs,
    find_voices_directory,
    calculate_peak_dbfs,
    calculate_waveform_envelope,
)
from edceleste.services.voice_lab_service import VoiceLabService

VOICE = "en-US-AriaNeural"
SAVED_VOLUME = 0.6
SAMPLE_RATE = 1000


def _make_edge_params(voice: str = VOICE) -> EdgeParamsModel:
    return EdgeParamsModel(type="edge", voice=voice)


def _make_chatterbox_params(profile: str = "celeste") -> ChatterboxParamsModel:
    return ChatterboxParamsModel(type="chatterbox", profile=profile)


def _make_settings(
    params: TtsProviderParams | None = None, voice_lab_enabled: bool = False
) -> SettingsModel:
    params = params or _make_edge_params()
    settings = SettingsModel(
        paths=PathModel(journal_path="C:/j", keybindings_path="C:/k"),
        tts=TTSModel(provider=params.type, params=params, volume=SAVED_VOLUME),
        llm=LLMModel(
            api_key="sk-ant-test", system_prompt=SYSTEM_PROMPT, user_prompt=""
        ),
        stt=SttModel(model="tiny.en"),
    )
    settings.tts.voice_lab.enabled = voice_lab_enabled
    return settings


def _make_fake_cloning_provider() -> ChatterboxTTSProvider:
    """A real Chatterbox provider object whose work is replaced by mocks, so
    no model, GPU or network is used."""
    provider = ChatterboxTTSProvider()
    provider.synthesize = AsyncMock(return_value=(np.full(20, 0.25), SAMPLE_RATE))
    provider.create_voice_profile = AsyncMock()
    provider.get_available_device = Mock(return_value="cuda")
    return provider


def _write_wav(path: Path, seconds: float, amplitude: float = 0.5) -> None:
    sample_count = int(seconds * SAMPLE_RATE)
    sf.write(str(path), np.full(sample_count, amplitude), SAMPLE_RATE)


class TTSServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = _make_settings()

        self.voice_lab_service = Mock(spec=VoiceLabService)
        self.service = TTSService(
            event_bus=EventBus(),
            settings_service=self.settings_service,
            voice_lab_service=self.voice_lab_service,
        )
        self.service.reload_service()

        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        self.voices_dir = Path(temp_directory.name) / "voices"
        voices_dir_patch = patch(
            "edceleste.services.tts_service.VOICES_DIR", self.voices_dir
        )
        voices_dir_patch.start()
        self.addCleanup(voices_dir_patch.stop)

        self.sounddevice = Mock()
        sounddevice_patch = patch.dict(sys.modules, {"sounddevice": self.sounddevice})
        sounddevice_patch.start()
        self.addCleanup(sounddevice_patch.stop)

        self.input_dir = Path(temp_directory.name) / "input"
        self.input_dir.mkdir()

    def _use_saved_chatterbox(self) -> ChatterboxTTSProvider:
        """Saved settings are Chatterbox, the active provider is a fake."""
        self.settings_service.get_settings.return_value = _make_settings(
            _make_chatterbox_params()
        )
        self.service.reload_service()
        fake_provider = _make_fake_cloning_provider()
        self.service.provider = fake_provider
        return fake_provider

    def _make_profile_files(self, name: str, with_sample: bool = True) -> None:
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        (self.voices_dir / f"{name}.pt").write_bytes(b"profile")
        if with_sample:
            (self.voices_dir / f"{name}_sample.wav").write_bytes(b"sample")

    async def _collect_clone_states(self, audio_path, name, params):
        return [
            state async for state in self.service.clone_voice(audio_path, name, params)
        ]

    # --- event bus ---

    async def test_event_bus_publish_of_tts_event_triggers_synthesize_and_play(self):
        event_bus = EventBus()
        service = TTSService(
            event_bus=event_bus,
            settings_service=self.settings_service,
            voice_lab_service=self.voice_lab_service,
        )
        service.synthesize_and_play = AsyncMock()

        await event_bus.publish(TTSEvent("Hello Commander"))

        service.synthesize_and_play.assert_called_once_with("Hello Commander")

    async def test_speak_text_from_tts_event_calls_synthesize_and_play_with_event_text(
        self,
    ):
        self.service.synthesize_and_play = AsyncMock()

        await self.service.speak_text_from_tts_event(TTSEvent("Fuel level low"))

        self.service.synthesize_and_play.assert_called_once_with("Fuel level low")

    # --- build_provider ---

    def test_build_provider_builds_edge_provider(self):
        self.assertIsInstance(self.service.build_provider("edge"), EdgeTTSProvider)

    def test_build_provider_builds_chatterbox_provider(self):
        self.assertIsInstance(
            self.service.build_provider("chatterbox"), ChatterboxTTSProvider
        )

    def test_build_provider_raises_key_error_for_unknown_type(self):
        with self.assertRaises(KeyError):
            self.service.build_provider("unknown")

    def test_build_provider_builds_a_new_object_every_time(self):
        self.assertIsNot(
            self.service.build_provider("edge"), self.service.build_provider("edge")
        )

    # --- synthesize_and_play ---

    async def test_synthesize_and_play_raises_runtime_error_when_provider_not_built(
        self,
    ):
        self.service.provider = None

        with self.assertRaises(RuntimeError):
            await self.service.synthesize_and_play("Hello")

    async def test_synthesize_and_play_passes_saved_params_to_the_edge_provider(self):
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(return_value=(np.zeros(10), SAMPLE_RATE))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello Commander")

        provider.synthesize.assert_awaited_once_with(
            "Hello Commander", _make_edge_params(), None
        )

    async def test_synthesize_and_play_passes_the_profile_path_to_cloning_provider(
        self,
    ):
        provider = self._use_saved_chatterbox()
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        provider.synthesize.assert_awaited_once_with(
            "Hello", _make_chatterbox_params(), self.voices_dir / "celeste.pt"
        )

    async def test_synthesize_and_play_plays_at_the_saved_volume(self):
        samples = np.zeros(10)
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(return_value=(samples, SAMPLE_RATE))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.service.play_samples.assert_awaited_once_with(
            samples, SAMPLE_RATE, SAVED_VOLUME, apply_voice_lab_effects=False
        )

    async def test_synthesize_and_play_applies_voice_lab_effects_when_enabled(self):
        self.settings_service.get_settings.return_value = _make_settings(
            voice_lab_enabled=True
        )
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(return_value=(np.zeros(10), SAMPLE_RATE))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.assertTrue(
            self.service.play_samples.await_args.kwargs["apply_voice_lab_effects"]
        )

    async def test_synthesize_and_play_propagates_error_raised_by_the_provider(self):
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(side_effect=RuntimeError("network down"))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        with self.assertRaises(RuntimeError):
            await self.service.synthesize_and_play("Hello")

        self.service.play_samples.assert_not_awaited()

    # --- playback ---

    async def test_play_samples_plays_at_volume_without_effects_when_not_asked(self):
        samples = np.full(10, 0.5)

        await self.service.play_samples(
            samples, SAMPLE_RATE, 0.5, apply_voice_lab_effects=False
        )

        self.voice_lab_service.apply_effects.assert_not_called()
        played_samples, played_rate = self.sounddevice.play.call_args.args
        np.testing.assert_allclose(played_samples, np.full(10, 0.25))
        self.assertEqual(played_rate, SAMPLE_RATE)

    async def test_play_samples_applies_voice_lab_effects_when_asked(self):
        samples = np.full(10, 0.5)
        with_effects = np.full(30, 1.0)
        self.voice_lab_service.apply_effects.return_value = with_effects

        await self.service.play_samples(
            samples, SAMPLE_RATE, 0.5, apply_voice_lab_effects=True
        )

        self.voice_lab_service.apply_effects.assert_called_once_with(
            samples, SAMPLE_RATE
        )
        played_samples, _ = self.sounddevice.play.call_args.args
        np.testing.assert_allclose(played_samples, np.full(30, 0.5))

    async def test_play_audio_file_plays_the_file_at_saved_volume_without_effects(
        self,
    ):
        audio_path = self.input_dir / "clip.wav"
        _write_wav(audio_path, 0.01, amplitude=0.5)

        await self.service.play_audio_file(str(audio_path))

        self.voice_lab_service.apply_effects.assert_not_called()
        played_samples, played_rate = self.sounddevice.play.call_args.args
        np.testing.assert_allclose(
            played_samples, np.full(10, 0.5 * SAVED_VOLUME), atol=1e-3
        )
        self.assertEqual(played_rate, SAMPLE_RATE)

    async def test_play_audio_file_turns_voice_lab_effects_off_explicitly(self):
        audio_path = self.input_dir / "clip.wav"
        _write_wav(audio_path, 0.01)
        self.service.play_samples = AsyncMock()

        await self.service.play_audio_file(str(audio_path))

        self.assertIs(
            self.service.play_samples.await_args.kwargs["apply_voice_lab_effects"],
            False,
        )

    async def test_play_audio_file_raises_when_file_is_missing(self):
        with self.assertRaises(Exception):
            await self.service.play_audio_file(str(self.input_dir / "nope.wav"))

        self.sounddevice.play.assert_not_called()

    async def test_play_sample_voice_plays_the_saved_sample_file(self):
        self.voices_dir.mkdir(parents=True)
        _write_wav(self.voices_dir / "celeste_sample.wav", 0.01)
        self.service.play_audio_file = AsyncMock()

        await self.service.play_sample_voice("celeste")

        self.service.play_audio_file.assert_awaited_once_with(
            str(self.voices_dir / "celeste_sample.wav")
        )

    async def test_play_sample_voice_raises_file_not_found_without_the_sample(self):
        self.service.play_audio_file = AsyncMock()

        with self.assertRaises(FileNotFoundError):
            await self.service.play_sample_voice("celeste")

        self.service.play_audio_file.assert_not_awaited()

    # --- validate_settings / reload_service ---

    def test_validate_settings_reports_issue_when_edge_voice_missing(self):
        new_settings = _make_settings()
        new_settings.tts.params.voice = ""

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "voice")

    def test_validate_settings_returns_no_issues_when_edge_voice_present(self):
        self.assertIsNone(self.service.validate_settings(_make_settings()))

    def test_validate_settings_uses_the_provider_the_user_is_switching_to(self):
        new_settings = _make_settings(_make_chatterbox_params(profile=""))

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual(issue.field, "profile")

    def test_validate_settings_reports_a_chatterbox_profile_missing_on_disk(self):
        new_settings = _make_settings(_make_chatterbox_params(profile="ghost"))

        issue = self.service.validate_settings(new_settings)

        self.assertIsNotNone(issue)
        self.assertEqual((issue.section, issue.field), ("tts", "profile"))
        self.assertEqual(issue.message, "Profile 'ghost' does not exist.")

    def test_validate_settings_returns_none_for_an_existing_chatterbox_profile(self):
        self._make_profile_files("celeste")
        new_settings = _make_settings(_make_chatterbox_params(profile="celeste"))

        self.assertIsNone(self.service.validate_settings(new_settings))

    def test_validate_settings_does_not_touch_the_active_provider(self):
        active_provider = self.service.provider

        self.service.validate_settings(_make_settings(_make_chatterbox_params()))

        self.assertIs(self.service.provider, active_provider)

    def test_reload_service_builds_edge_provider_for_edge_settings(self):
        self.assertEqual(self.service.provider_type, "edge")
        self.assertIsInstance(self.service.provider, EdgeTTSProvider)

    def test_reload_service_builds_new_provider_when_the_type_changed(self):
        old_provider = self.service.provider
        self.settings_service.get_settings.return_value = _make_settings(
            _make_chatterbox_params()
        )

        self.service.reload_service()

        self.assertEqual(self.service.provider_type, "chatterbox")
        self.assertIsInstance(self.service.provider, ChatterboxTTSProvider)
        self.assertIsNot(self.service.provider, old_provider)

    def test_reload_service_keeps_the_same_provider_when_the_type_is_the_same(self):
        old_provider = self.service.provider
        self.settings_service.get_settings.return_value = _make_settings(
            _make_edge_params("en-US-GuyNeural")
        )

        self.service.reload_service()

        self.assertIs(self.service.provider, old_provider)

    # --- cold_start ---

    async def test_cold_start_yields_pending_status_first(self):
        self.service.reload_service = Mock()

        # ColdStartStatus is mutated in place and re-yielded on completion, so
        # the pending status must be inspected right after this first yield -
        # collecting every yield into a list first would show the mutated,
        # already-completed object instead.
        first_status = await self.service.cold_start().__anext__()

        self.assertEqual(first_status.service, "tts")
        self.assertFalse(first_status.is_critical)
        self.assertFalse(first_status.completed)
        self.assertIsNone(first_status.message)

    async def test_cold_start_pending_status_has_real_booleans_not_none(self):
        self.service.reload_service = Mock()

        first_status = await self.service.cold_start().__anext__()

        self.assertIs(first_status.is_critical, False)
        self.assertIs(first_status.completed, False)

    async def test_cold_start_yields_completed_status_when_reload_service_succeeds(
        self,
    ):
        self.service.reload_service = Mock()

        statuses = [status async for status in self.service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertIsNone(last_status.message)

    async def test_cold_start_yields_error_message_when_reload_service_fails(self):
        self.service.reload_service = Mock(side_effect=RuntimeError("provider down"))

        statuses = [status async for status in self.service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertEqual(last_status.message, "provider down")

    # --- fetch_edge_tts_voice_names ---

    async def test_fetch_edge_tts_voice_names_returns_short_names_from_list_voices(
        self,
    ):
        available_voices = [
            {"ShortName": "en-US-AriaNeural", "Locale": "en-US"},
            {"ShortName": "en-GB-SoniaNeural", "Locale": "en-GB"},
        ]
        with patch(
            "edceleste.services.tts_service.edge_tts.list_voices",
            new=AsyncMock(return_value=available_voices),
        ):
            result = await self.service.fetch_edge_tts_voice_names()

        self.assertEqual(result, ["en-US-AriaNeural", "en-GB-SoniaNeural"])

    async def test_fetch_edge_tts_voice_names_returns_empty_list_when_no_voices(
        self,
    ):
        with patch(
            "edceleste.services.tts_service.edge_tts.list_voices",
            new=AsyncMock(return_value=[]),
        ):
            result = await self.service.fetch_edge_tts_voice_names()

        self.assertEqual(result, [])

    async def test_fetch_edge_tts_voice_names_propagates_error_when_list_voices_fails(
        self,
    ):
        with patch(
            "edceleste.services.tts_service.edge_tts.list_voices",
            new=AsyncMock(side_effect=RuntimeError("network down")),
        ):
            with self.assertRaises(RuntimeError):
                await self.service.fetch_edge_tts_voice_names()

    # --- profile paths ---

    def test_build_profile_path_puts_the_file_in_the_voices_folder(self):
        self.assertEqual(
            self.service.build_profile_path("celeste", ".pt"),
            self.voices_dir / "celeste.pt",
        )

    def test_build_profile_path_drops_folder_parts_of_the_name(self):
        self.assertEqual(
            self.service.build_profile_path("../x", ".pt"), self.voices_dir / "x.pt"
        )

    def test_find_profile_path_is_none_for_the_edge_provider(self):
        self.assertIsNone(
            self.service.find_profile_path(EdgeTTSProvider(), _make_edge_params())
        )

    def test_find_profile_path_returns_the_profile_file_for_cloning_provider(self):
        path = self.service.find_profile_path(
            _make_fake_cloning_provider(), _make_chatterbox_params("nova")
        )

        self.assertEqual(path, self.voices_dir / "nova.pt")

    # --- get_cloning_provider_for ---

    def test_get_cloning_provider_for_returns_the_active_provider_of_the_same_type(
        self,
    ):
        fake_provider = self._use_saved_chatterbox()

        result = self.service.get_cloning_provider_for(_make_chatterbox_params())

        self.assertIs(result, fake_provider)

    def test_get_cloning_provider_for_builds_a_throwaway_for_another_type(self):
        active_provider = self.service.provider

        result = self.service.get_cloning_provider_for(_make_chatterbox_params())

        self.assertIsInstance(result, ChatterboxTTSProvider)
        self.assertIs(self.service.provider, active_provider)
        self.assertEqual(self.service.provider_type, "edge")

    def test_get_cloning_provider_for_raises_when_the_provider_cannot_clone(self):
        with self.assertRaises(VoiceCloningException):
            self.service.get_cloning_provider_for(_make_edge_params())

    # --- clone_voice ---

    async def test_clone_voice_yields_the_states_in_order(self):
        self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        states = await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(
            states,
            [
                VoiceCloningState.DIRECTORY_CREATED,
                VoiceCloningState.AUDIO_PROCESSED,
                VoiceCloningState.COMPLETED,
                VoiceCloningState.SAMPLE_CREATED,
            ],
        )

    async def test_clone_voice_passes_the_screen_params_to_the_provider(self):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)
        screen_params = _make_chatterbox_params("screen")
        screen_params.exaggeration = 1.5

        await self._collect_clone_states(str(audio_path), "nova", screen_params)

        create_args = provider.create_voice_profile.await_args.args
        self.assertEqual(create_args[1], self.voices_dir / "nova.pt")
        self.assertIs(create_args[2], screen_params)
        synthesize_args = provider.synthesize.await_args.args
        self.assertEqual(synthesize_args[0], DEFAULT_VOICE_SAMPLE_TEXT)
        self.assertEqual(synthesize_args[1].exaggeration, 1.5)

    async def test_clone_voice_synthesizes_the_sample_for_the_new_profile_name(self):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params("old")
        )

        synthesize_args = provider.synthesize.await_args.args
        self.assertEqual(synthesize_args[1].profile, "nova")
        self.assertEqual(synthesize_args[2], self.voices_dir / "nova.pt")

    async def test_clone_voice_writes_the_sample_next_to_the_profile(self):
        self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        sample, rate = sf.read(str(self.voices_dir / "nova_sample.wav"))
        self.assertEqual(rate, SAMPLE_RATE)
        self.assertEqual(len(sample), 20)

    async def test_clone_voice_uses_a_throwaway_provider_for_an_unsaved_engine(self):
        active_provider = self.service.provider
        throwaway_provider = _make_fake_cloning_provider()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with patch.object(
            self.service, "build_provider", return_value=throwaway_provider
        ) as build_provider:
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        build_provider.assert_called_once_with("chatterbox")
        throwaway_provider.create_voice_profile.assert_awaited_once()
        self.assertIs(self.service.provider, active_provider)
        self.assertEqual(self.service.provider_type, "edge")

    async def test_clone_voice_raises_voice_cloning_exception_for_edge_params(self):
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(VoiceCloningException):
            await self._collect_clone_states(
                str(audio_path), "nova", _make_edge_params()
            )

    async def test_clone_voice_raises_file_not_found_for_missing_audio(self):
        self._use_saved_chatterbox()

        with self.assertRaises(FileNotFoundError):
            await self._collect_clone_states(
                str(self.input_dir / "nope.wav"), "nova", _make_chatterbox_params()
            )

    async def test_clone_voice_raises_value_error_for_a_too_short_clip(self):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "short.wav"
        _write_wav(audio_path, 5)

        with self.assertRaises(ValueError):
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        provider.create_voice_profile.assert_not_awaited()

    async def test_clone_voice_accepts_a_clip_exactly_as_long_as_reference_seconds(
        self,
    ):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "exact.wav"
        _write_wav(audio_path, provider.reference_seconds)

        states = await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(states[-1], VoiceCloningState.SAMPLE_CREATED)

    async def test_clone_voice_creates_missing_parent_folders_of_the_voices_folder(
        self,
    ):
        provider = self._use_saved_chatterbox()
        nested_voices_dir = self.voices_dir / "deeper" / "voices"
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, provider.reference_seconds)

        with patch("edceleste.services.tts_service.VOICES_DIR", nested_voices_dir):
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        self.assertTrue(nested_voices_dir.is_dir())

    async def test_clone_voice_works_when_the_voices_folder_already_exists(self):
        provider = self._use_saved_chatterbox()
        self.voices_dir.mkdir(parents=True)
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, provider.reference_seconds)

        states = await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(states[-1], VoiceCloningState.SAMPLE_CREATED)

    async def test_clone_voice_wraps_a_provider_error_in_runtime_error(self):
        provider = self._use_saved_chatterbox()
        provider.create_voice_profile.side_effect = OSError("disk full")
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(RuntimeError) as context:
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        self.assertIsInstance(context.exception.__cause__, OSError)

    async def test_clone_voice_deletes_the_trimmed_clip_when_it_fails(self):
        provider = self._use_saved_chatterbox()
        provider.create_voice_profile.side_effect = OSError("disk full")
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(RuntimeError):
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        self.assertFalse((self.voices_dir / "nova_reference.wav").exists())

    async def test_clone_voice_deletes_the_trimmed_clip_after_success(self):
        self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertFalse((self.voices_dir / "nova_reference.wav").exists())
        self.assertTrue(audio_path.exists())

    async def test_clone_voice_gives_the_provider_only_reference_seconds_of_audio(
        self,
    ):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 15)
        seen_frames = []

        async def remember_clip_length(clip_path, profile_path, params):
            seen_frames.append(sf.info(clip_path).frames)

        provider.create_voice_profile.side_effect = remember_clip_length

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(seen_frames, [int(provider.reference_seconds * SAMPLE_RATE)])

    async def test_clone_voice_refuses_the_name_of_an_existing_profile(self):
        provider = self._use_saved_chatterbox()
        self._make_profile_files("nova")
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(FileExistsError):
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        self.assertEqual((self.voices_dir / "nova.pt").read_bytes(), b"profile")
        self.assertEqual((self.voices_dir / "nova_sample.wav").read_bytes(), b"sample")
        provider.create_voice_profile.assert_not_awaited()

    async def test_clone_voice_writes_the_trimmed_clip_under_the_new_profile_name(
        self,
    ):
        provider = self._use_saved_chatterbox()
        self._make_profile_files("narrator")
        audio_path = self.input_dir / "narrator_sample.wav"
        _write_wav(audio_path, 12)
        seen_clip_names = []

        async def remember_clip_name(clip_path, profile_path, params):
            seen_clip_names.append(Path(clip_path).name)

        provider.create_voice_profile.side_effect = remember_clip_name

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(seen_clip_names, ["nova_reference.wav"])
        self.assertEqual(
            (self.voices_dir / "narrator_sample.wav").read_bytes(), b"sample"
        )

    # --- profiles: regression, saved engine is Edge, screen is Chatterbox ---

    def test_profiles_can_be_managed_on_the_screen_while_the_saved_engine_is_edge(
        self,
    ):
        active_provider = self.service.provider
        self._make_profile_files("celeste")
        screen_params = _make_chatterbox_params()

        listed = self.service.get_available_profiles(screen_params)
        self.service.rename_profile("celeste", "nova", screen_params)
        self.service.remove_profile("nova", screen_params)

        self.assertEqual(listed, ["celeste"])
        self.assertEqual(list(self.voices_dir.iterdir()), [])
        self.assertIs(self.service.provider, active_provider)
        self.assertEqual(self.service.provider_type, "edge")

    # --- get_available_profiles ---

    def test_get_available_profiles_lists_profile_names_without_extension(self):
        self._make_profile_files("celeste")
        self._make_profile_files("nova", with_sample=False)

        result = self.service.get_available_profiles(_make_chatterbox_params())

        self.assertCountEqual(result, ["celeste", "nova"])

    def test_get_available_profiles_returns_empty_list_for_edge_params(self):
        self._make_profile_files("celeste")

        self.assertEqual(self.service.get_available_profiles(_make_edge_params()), [])

    def test_get_available_profiles_returns_empty_list_when_folder_is_missing(self):
        self.assertEqual(
            self.service.get_available_profiles(_make_chatterbox_params()), []
        )

    # --- remove_profile ---

    def test_remove_profile_removes_the_profile_and_its_sample(self):
        self._make_profile_files("celeste")
        self._make_profile_files("nova")

        self.service.remove_profile("celeste", _make_chatterbox_params())

        self.assertEqual(
            sorted(path.name for path in self.voices_dir.iterdir()),
            ["nova.pt", "nova_sample.wav"],
        )

    def test_remove_profile_does_not_fail_when_the_files_are_missing(self):
        self.voices_dir.mkdir(parents=True)

        self.service.remove_profile("ghost", _make_chatterbox_params())

    def test_remove_profile_raises_voice_cloning_exception_for_edge_params(self):
        self._make_profile_files("celeste")

        with self.assertRaises(VoiceCloningException):
            self.service.remove_profile("celeste", _make_edge_params())

        self.assertTrue((self.voices_dir / "celeste.pt").exists())

    # --- rename_profile ---

    def test_rename_profile_renames_the_profile_and_its_sample(self):
        self._make_profile_files("celeste")

        self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertEqual(
            sorted(path.name for path in self.voices_dir.iterdir()),
            ["nova.pt", "nova_sample.wav"],
        )

    def test_rename_profile_raises_file_exists_error_when_target_is_taken(self):
        self._make_profile_files("celeste")
        self._make_profile_files("nova")

        with self.assertRaises(FileExistsError):
            self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertTrue((self.voices_dir / "celeste.pt").exists())

    def test_rename_profile_raises_file_not_found_when_the_old_profile_is_missing(
        self,
    ):
        self.voices_dir.mkdir(parents=True)

        with self.assertRaises(FileNotFoundError):
            self.service.rename_profile("ghost", "nova", _make_chatterbox_params())

    def test_rename_profile_skips_a_missing_sample(self):
        self._make_profile_files("celeste", with_sample=False)

        self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertEqual([path.name for path in self.voices_dir.iterdir()], ["nova.pt"])

    def test_rename_profile_raises_voice_cloning_exception_for_edge_params(self):
        with self.assertRaises(VoiceCloningException):
            self.service.rename_profile("celeste", "nova", _make_edge_params())

    # --- preview_voice_sample ---

    async def test_preview_voice_sample_synthesizes_for_the_given_profile(self):
        provider = self._use_saved_chatterbox()
        self.service.play_samples = AsyncMock()
        screen_params = _make_chatterbox_params("other")
        screen_params.exaggeration = 1.2

        await self.service.preview_voice_sample("nova", "Hi there", screen_params)

        text, used_params, profile_path = provider.synthesize.await_args.args
        self.assertEqual(text, "Hi there")
        self.assertEqual(used_params.profile, "nova")
        self.assertEqual(used_params.exaggeration, 1.2)
        self.assertEqual(profile_path, self.voices_dir / "nova.pt")

    async def test_preview_voice_sample_plays_without_effects_at_saved_volume(self):
        provider = self._use_saved_chatterbox()
        samples = np.zeros(5)
        provider.synthesize.return_value = (samples, SAMPLE_RATE)
        self.service.play_samples = AsyncMock()

        await self.service.preview_voice_sample("nova", "Hi", _make_chatterbox_params())

        self.service.play_samples.assert_awaited_once_with(
            samples, SAMPLE_RATE, SAVED_VOLUME, apply_voice_lab_effects=False
        )

    async def test_preview_voice_sample_writes_nothing_to_disk(self):
        self._use_saved_chatterbox()
        self.service.play_samples = AsyncMock()

        await self.service.preview_voice_sample("nova", "Hi", _make_chatterbox_params())

        self.assertFalse(self.voices_dir.exists())

    async def test_preview_voice_sample_raises_voice_cloning_exception_for_edge(self):
        with self.assertRaises(VoiceCloningException):
            await self.service.preview_voice_sample("nova", "Hi", _make_edge_params())

    # --- get_available_device ---

    def test_get_available_device_returns_the_answer_of_the_cloning_provider(self):
        self._use_saved_chatterbox().get_available_device.return_value = "cuda"

        self.assertEqual(
            self.service.get_available_device(_make_chatterbox_params()), "cuda"
        )

    def test_get_available_device_returns_cpu_for_edge_params(self):
        self.assertEqual(self.service.get_available_device(_make_edge_params()), "cpu")

    # --- analysis ---

    def test_analysis_marks_a_clip_shorter_than_reference_seconds_invalid(self):
        audio_path = self.input_dir / "short.wav"
        _write_wav(audio_path, 5)

        result = self.service.perform_sample_voice_analysis_and_validate(
            str(audio_path), _make_chatterbox_params()
        )

        self.assertFalse(result["is_valid"])
        self.assertEqual(
            result["validation_error_message"],
            "Too short - minimum 10s, recommended 10-30s",
        )

    def test_analysis_accepts_a_clip_exactly_as_long_as_reference_seconds(self):
        audio_path = self.input_dir / "exact.wav"
        _write_wav(audio_path, ChatterboxTTSProvider.reference_seconds)

        result = self.service.perform_sample_voice_analysis_and_validate(
            str(audio_path), _make_chatterbox_params()
        )

        self.assertTrue(result["is_valid"])
        self.assertIsNone(result["validation_error_message"])

    def test_analysis_returns_measurements_for_a_valid_clip(self):
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12, amplitude=0.5)

        result = self.service.perform_sample_voice_analysis_and_validate(
            str(audio_path), _make_chatterbox_params()
        )

        self.assertTrue(result["is_valid"])
        self.assertIsNone(result["validation_error_message"])
        self.assertEqual(result["file_name"], "voice.wav")
        self.assertAlmostEqual(result["duration_seconds"], 12.0)
        self.assertEqual(result["sample_rate"], SAMPLE_RATE)
        self.assertEqual(result["channels"], 1)
        self.assertTrue(result["is_mono"])
        self.assertFalse(result["has_clipping"])
        self.assertAlmostEqual(result["peak_dbfs"], -6.02, places=1)
        self.assertEqual(len(result["waveform_envelope"]), 120)

    def test_analysis_detects_clipping(self):
        audio_path = self.input_dir / "loud.wav"
        # FLOAT keeps the exact 1.0, 16 bit PCM would store it just below it
        sf.write(
            str(audio_path),
            np.full(12 * SAMPLE_RATE, 1.0),
            SAMPLE_RATE,
            subtype="FLOAT",
        )

        result = self.service.perform_sample_voice_analysis_and_validate(
            str(audio_path), _make_chatterbox_params()
        )

        self.assertTrue(result["has_clipping"])

    def test_analysis_reports_stereo_clip_as_not_mono(self):
        audio_path = self.input_dir / "stereo.wav"
        sf.write(str(audio_path), np.full((12 * SAMPLE_RATE, 2), 0.5), SAMPLE_RATE)

        result = self.service.perform_sample_voice_analysis_and_validate(
            str(audio_path), _make_chatterbox_params()
        )

        self.assertEqual(result["channels"], 2)
        self.assertFalse(result["is_mono"])
        self.assertTrue(result["is_valid"])

    def test_analysis_raises_voice_cloning_exception_for_edge_params(self):
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(VoiceCloningException):
            self.service.perform_sample_voice_analysis_and_validate(
                str(audio_path), _make_edge_params()
            )

    # --- calculate_peak_dbfs ---

    def test_calculate_peak_dbfs_of_silence_is_the_silence_floor(self):
        self.assertEqual(calculate_peak_dbfs(np.zeros(100)), SILENCE_FLOOR_DBFS)

    def test_calculate_peak_dbfs_of_full_scale_is_zero(self):
        self.assertAlmostEqual(calculate_peak_dbfs(np.array([0.1, -1.0, 0.5])), 0.0)

    def test_calculate_peak_dbfs_of_half_scale_is_minus_six(self):
        self.assertAlmostEqual(
            calculate_peak_dbfs(np.array([0.5, -0.5])), -6.0206, places=3
        )

    # --- calculate_noise_floor_dbfs ---

    def test_calculate_noise_floor_dbfs_of_silence_is_the_silence_floor(self):
        self.assertEqual(
            calculate_noise_floor_dbfs(np.zeros(SAMPLE_RATE), SAMPLE_RATE),
            SILENCE_FLOOR_DBFS,
        )

    def test_calculate_noise_floor_dbfs_uses_the_quietest_window(self):
        # 100ms windows: one loud (0.5) and one quiet (0.1)
        samples = np.concatenate([np.full(100, 0.5), np.full(100, 0.1)])

        result = calculate_noise_floor_dbfs(samples, SAMPLE_RATE)

        self.assertAlmostEqual(result, -20.0, places=3)

    def test_calculate_noise_floor_dbfs_mixes_stereo_to_mono(self):
        left = np.full(100, 0.2)
        right = np.full(100, 0.0)
        stereo = np.stack([left, right], axis=1)

        result = calculate_noise_floor_dbfs(stereo, SAMPLE_RATE)

        self.assertAlmostEqual(result, -20.0, places=3)

    def test_calculate_noise_floor_dbfs_is_twenty_times_the_log_of_the_rms(self):
        # RMS 0.1 gives -20 for both 20 * log10 and 20 / log10, 0.01 does not
        result = calculate_noise_floor_dbfs(np.full(200, 0.01), SAMPLE_RATE)

        self.assertAlmostEqual(result, -40.0, places=3)

    def test_calculate_noise_floor_dbfs_handles_clip_shorter_than_one_window(self):
        result = calculate_noise_floor_dbfs(np.full(10, 0.1), SAMPLE_RATE)

        self.assertAlmostEqual(result, -20.0, places=3)

    # --- calculate_waveform_envelope ---

    def test_calculate_waveform_envelope_gives_peak_per_window(self):
        samples = np.concatenate([np.full(100, 0.2), np.full(100, -0.8)])

        result = calculate_waveform_envelope(samples, SAMPLE_RATE)

        self.assertEqual(result, [0.2, 0.8])

    def test_calculate_waveform_envelope_mixes_stereo_to_mono(self):
        stereo = np.stack([np.full(100, 0.4), np.full(100, 0.0)], axis=1)

        result = calculate_waveform_envelope(stereo, SAMPLE_RATE)

        self.assertEqual(result, [0.2])

    def test_calculate_waveform_envelope_drops_the_last_partial_window(self):
        samples = np.concatenate([np.full(100, 0.2), np.full(50, 0.9)])

        result = calculate_waveform_envelope(samples, SAMPLE_RATE)

        self.assertEqual(result, [0.2])

    def test_calculate_waveform_envelope_respects_the_window_length(self):
        samples = np.concatenate([np.full(50, 0.1), np.full(50, 0.3)])

        result = calculate_waveform_envelope(samples, SAMPLE_RATE, window_seconds=0.05)

        self.assertEqual(result, [0.1, 0.3])


if __name__ == "__main__":
    unittest.main()


class FindVoicesDirectoryTest(unittest.TestCase):
    def test_windows_uses_the_local_app_data_folder(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/pilot/AppData/Local"}):
            voices_dir = find_voices_directory("nt")

        self.assertEqual(
            voices_dir, Path("C:/Users/pilot/AppData/Local") / "EDCeleste" / "voices"
        )

    def test_windows_raises_when_local_app_data_is_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError):
                find_voices_directory("nt")

    def test_other_systems_use_the_local_share_folder_of_the_home(self):
        with patch.object(Path, "home", return_value=Path("/home/pilot")):
            voices_dir = find_voices_directory("posix")

        self.assertEqual(
            voices_dir,
            Path("/home/pilot") / ".local" / "share" / "EDCeleste" / "voices",
        )
