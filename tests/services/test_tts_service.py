import asyncio
import gc
import os
import queue
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import numpy as np
import soundfile as sf

from edceleste.services import tts_service
from edceleste.services.event_bus import EventBus
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.llm_service import SYSTEM_PROMPT
from edceleste.services.models.reply_texts import REPLY_TEXTS, build_reply_wav_file_name
from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    EdgeParamsModel,
    LLMModel,
    PathModel,
    PocketParamsModel,
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
from edceleste.services.tts_providers.pocket_tts_provider import PocketTTSProvider
from edceleste.services.ship_voice_effect import TAIL_SECONDS
from edceleste.services.tts_service import (
    DEFAULT_VOICE_SAMPLE_TEXT,
    SILENCE_FLOOR_DBFS,
    TTSEvent,
    TTSService,
    VOICE_TEST_TEXT,
    WARM_UP_TEXT,
    calculate_noise_floor_dbfs,
    find_voices_directory,
    calculate_peak_dbfs,
    calculate_waveform_envelope,
)

VOICE = "en-US-AriaNeural"
SAVED_VOLUME = 0.6
SAMPLE_RATE = 1000


def _make_edge_params(voice: str = VOICE) -> EdgeParamsModel:
    return EdgeParamsModel(type="edge", voice=voice)


def _make_chatterbox_params(profile: str = "celeste") -> ChatterboxParamsModel:
    return ChatterboxParamsModel(type="chatterbox", profile=profile)


def _make_settings(
    params: TtsProviderParams | None = None, ship_effect: bool = False
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
    settings.tts.ship_effect = ship_effect
    return settings


def _make_fake_cloning_provider() -> ChatterboxTTSProvider:
    """A real Chatterbox provider object whose work is replaced by mocks, so
    no model, GPU or network is used."""
    provider = ChatterboxTTSProvider()
    provider.synthesize = AsyncMock(return_value=(np.full(20, 0.25), SAMPLE_RATE))
    provider.create_voice_profile = AsyncMock()
    provider.get_available_device = Mock(return_value="cuda")
    # Streaming depends on the GPU of the machine, these tests are about the whole voice
    provider.can_stream = Mock(return_value=False)
    return provider


def _write_wav(path: Path, seconds: float, amplitude: float = 0.5) -> None:
    sample_count = int(seconds * SAMPLE_RATE)
    sf.write(str(path), np.full(sample_count, amplitude), SAMPLE_RATE)


class TTSServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = _make_settings()

        self.service = TTSService(
            event_bus=EventBus(),
            settings_service=self.settings_service,
        )
        self.service.reload_service()

        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        self.voices_dir = Path(temp_directory.name) / "voices"
        self.profiles_dir = self.voices_dir / "chatterbox"
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
        profile_folder = self.profiles_dir / name
        profile_folder.mkdir(parents=True, exist_ok=True)
        (profile_folder / "profile.pt").write_bytes(b"profile")
        if with_sample:
            (profile_folder / "sample.wav").write_bytes(b"sample")

    def _make_replies_files(self, profile_name: str, *names: str) -> Path:
        """Writes small files into the replies folder of a Chatterbox profile
        and returns that folder. The path is spelled out here, so these tests
        do not depend on build_replies_folder()."""
        replies_folder = self.profiles_dir / profile_name / "replies"
        replies_folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            (replies_folder / name).write_bytes(name.encode())
        return replies_folder

    def _file_names_in(self, folder: Path) -> list[str]:
        return sorted(path.name for path in folder.iterdir())

    def _every_reply_file_name(self) -> list[str]:
        return sorted(build_reply_wav_file_name(text) for text in REPLY_TEXTS)

    async def _collect_clone_states(self, audio_path, name, params):
        return [
            state async for state in self.service.clone_voice(audio_path, name, params)
        ]

    def _remember_clip_paths_given_to(self, provider) -> list[Path]:
        """The returned list gets the trimmed clip path of every
        create_voice_profile() call, taken while the clip still exists."""
        seen_clip_paths: list[Path] = []

        async def remember_clip_path(clip_path, profile_path, params):
            seen_clip_paths.append(Path(clip_path))

        provider.create_voice_profile.side_effect = remember_clip_path
        return seen_clip_paths

    # --- event bus ---

    async def test_event_bus_publish_of_tts_event_triggers_synthesize_and_play(self):
        event_bus = EventBus()
        service = TTSService(
            event_bus=event_bus,
            settings_service=self.settings_service,
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

        with self.assertRaises(RuntimeError) as raised:
            await self.service.synthesize_and_play("Hello")

        self.assertEqual(str(raised.exception), "The TTS provider is not built yet.")

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
            "Hello",
            _make_chatterbox_params(),
            self.profiles_dir / "celeste" / "profile.pt",
        )

    async def test_synthesize_and_play_plays_at_the_saved_volume(self):
        samples = np.zeros(10)
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(return_value=(samples, SAMPLE_RATE))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.service.play_samples.assert_awaited_once_with(
            samples, SAMPLE_RATE, SAVED_VOLUME, with_ship_effect=False
        )

    async def test_synthesize_and_play_asks_for_the_ship_effect_when_it_is_switched_on(
        self,
    ):
        self.settings_service.get_settings.return_value = _make_settings(
            ship_effect=True
        )
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(return_value=(np.zeros(10), SAMPLE_RATE))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.assertIs(
            self.service.play_samples.await_args.kwargs["with_ship_effect"], True
        )

    async def test_synthesize_and_play_leaves_the_ship_effect_out_when_switched_off(
        self,
    ):
        self.settings_service.get_settings.return_value = _make_settings(
            ship_effect=False
        )
        provider = Mock(spec=EdgeTTSProvider)
        provider.synthesize = AsyncMock(return_value=(np.zeros(10), SAMPLE_RATE))
        self.service.provider = provider
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.assertIs(
            self.service.play_samples.await_args.kwargs["with_ship_effect"], False
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

    async def test_play_samples_plays_the_plain_samples_by_default(self):
        samples = np.full(10, 0.5)
        self.service.add_ship_effect_to_whole_audio = Mock()

        await self.service.play_samples(samples, SAMPLE_RATE, 0.5)

        self.service.add_ship_effect_to_whole_audio.assert_not_called()
        played_samples, played_rate = self.sounddevice.play.call_args.args
        np.testing.assert_allclose(played_samples, np.full(10, 0.25))
        self.assertEqual(played_rate, SAMPLE_RATE)

    async def test_play_samples_adds_the_ship_effect_to_the_whole_audio_when_asked(
        self,
    ):
        samples = np.full(10, 0.5)
        with_effect = np.full((30, 2), 1.0)
        self.service.add_ship_effect_to_whole_audio = Mock(return_value=with_effect)

        await self.service.play_samples(
            samples, SAMPLE_RATE, 0.5, with_ship_effect=True
        )

        self.service.add_ship_effect_to_whole_audio.assert_called_once_with(
            samples, SAMPLE_RATE
        )
        played_samples, played_rate = self.sounddevice.play.call_args.args
        np.testing.assert_allclose(played_samples, np.full((30, 2), 0.5))
        self.assertEqual(played_rate, SAMPLE_RATE)

    async def test_play_samples_waits_for_the_length_of_the_audio_with_the_tail(self):
        self.service.add_ship_effect_to_whole_audio = Mock(
            return_value=np.zeros((50, 2))
        )

        with patch("edceleste.services.tts_service.asyncio.sleep") as sleep:
            sleep.return_value = None
            await self.service.play_samples(
                np.zeros(10), SAMPLE_RATE, 0.5, with_ship_effect=True
            )

        sleep.assert_called_once_with(50 / SAMPLE_RATE)

    def test_add_ship_effect_to_whole_audio_returns_stereo_longer_by_the_tail(self):
        samples = (np.random.default_rng(1).standard_normal(2400) * 0.1).astype(
            np.float32
        )

        with_effect = self.service.add_ship_effect_to_whole_audio(samples, 24000)

        self.assertEqual(
            with_effect.shape, (len(samples) + int(TAIL_SECONDS * 24000), 2)
        )
        self.assertEqual(with_effect.dtype, np.float32)

    def test_add_ship_effect_to_whole_audio_leaves_the_input_unchanged(self):
        samples = (np.random.default_rng(2).standard_normal(2400) * 0.1).astype(
            np.float32
        )
        copy_of_samples = samples.copy()

        self.service.add_ship_effect_to_whole_audio(samples, 24000)

        np.testing.assert_array_equal(samples, copy_of_samples)

    async def test_play_audio_file_plays_the_file_at_saved_volume_without_effects(
        self,
    ):
        audio_path = self.input_dir / "clip.wav"
        _write_wav(audio_path, 0.01, amplitude=0.5)
        self.service.add_ship_effect_to_whole_audio = Mock()

        await self.service.play_audio_file(str(audio_path))

        self.service.add_ship_effect_to_whole_audio.assert_not_called()
        played_samples, played_rate = self.sounddevice.play.call_args.args
        np.testing.assert_allclose(
            played_samples, np.full(10, 0.5 * SAVED_VOLUME), atol=1e-3
        )
        self.assertEqual(played_rate, SAMPLE_RATE)

    async def test_play_audio_file_never_asks_for_the_ship_effect(self):
        self.settings_service.get_settings.return_value = _make_settings(
            ship_effect=True
        )
        audio_path = self.input_dir / "clip.wav"
        _write_wav(audio_path, 0.01)
        self.service.play_samples = AsyncMock()

        await self.service.play_audio_file(str(audio_path))

        self.assertFalse(
            self.service.play_samples.await_args.kwargs.get("with_ship_effect", False)
        )

    async def test_play_audio_file_raises_when_file_is_missing(self):
        with self.assertRaises(Exception):
            await self.service.play_audio_file(str(self.input_dir / "nope.wav"))

        self.sounddevice.play.assert_not_called()

    async def test_play_sample_voice_plays_the_saved_sample_file(self):
        (self.profiles_dir / "celeste").mkdir(parents=True)
        _write_wav(self.profiles_dir / "celeste" / "sample.wav", 0.01)
        self.service.play_audio_file = AsyncMock()

        await self.service.play_sample_voice("celeste", _make_chatterbox_params())

        self.service.play_audio_file.assert_awaited_once_with(
            str(self.profiles_dir / "celeste" / "sample.wav")
        )

    async def test_play_sample_voice_raises_file_not_found_without_the_sample(self):
        self.service.play_audio_file = AsyncMock()

        with self.assertRaises(FileNotFoundError):
            await self.service.play_sample_voice("celeste", _make_chatterbox_params())

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

    def test_build_profile_folder_is_voices_provider_name_for_every_provider(self):
        for provider_type, name in [
            ("edge", VOICE),
            ("pocket", "celeste"),
            ("chatterbox", "nova"),
        ]:
            with self.subTest(provider_type=provider_type):
                self.assertEqual(
                    self.service.build_profile_folder(provider_type, name),
                    self.voices_dir / provider_type / name,
                )

    def test_build_profile_folder_drops_folder_parts_of_the_name(self):
        folder = self.service.build_profile_folder("pocket", "../x")

        self.assertEqual(folder, self.voices_dir / "pocket" / "x")

    def test_build_profile_folder_raises_value_error_for_a_name_without_a_folder(
        self,
    ):
        for name in ["", "..", "a/.."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.service.build_profile_folder("pocket", name)

    def test_build_profile_path_puts_the_file_in_the_folder_of_the_profile(self):
        self.assertEqual(
            self.service.build_profile_path("chatterbox", "celeste", ".pt"),
            self.profiles_dir / "celeste" / "profile.pt",
        )

    def test_build_profile_path_drops_folder_parts_of_the_name(self):
        self.assertEqual(
            self.service.build_profile_path("chatterbox", "../x", ".pt"),
            self.profiles_dir / "x" / "profile.pt",
        )

    def test_build_sample_path_puts_sample_wav_in_the_folder_of_the_profile(self):
        self.assertEqual(
            self.service.build_sample_path("chatterbox", "celeste"),
            self.profiles_dir / "celeste" / "sample.wav",
        )

    def test_find_profile_path_is_none_for_the_edge_provider(self):
        self.assertIsNone(
            self.service.build_profile_path_named_in_params(
                EdgeTTSProvider(), _make_edge_params()
            )
        )

    def test_find_profile_path_returns_the_profile_file_for_cloning_provider(self):
        path = self.service.build_profile_path_named_in_params(
            _make_fake_cloning_provider(), _make_chatterbox_params("nova")
        )

        self.assertEqual(path, self.profiles_dir / "nova" / "profile.pt")

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

    # --- replies: folder and files ---

    def test_build_replies_folder_is_replies_in_the_folder_of_the_profile(self):
        for provider_type, name in [("edge", VOICE), ("pocket", "celeste")]:
            with self.subTest(provider_type=provider_type):
                self.assertEqual(
                    self.service.build_replies_folder(provider_type, name),
                    self.voices_dir / provider_type / name / "replies",
                )

    async def test_prepare_replies_writes_a_wav_for_every_reply_text(self):
        provider = _make_fake_cloning_provider()
        replies_folder = self.input_dir / "replies"

        await self.service.prepare_replies(
            provider, _make_chatterbox_params(), None, replies_folder
        )

        self.assertEqual(
            self._file_names_in(replies_folder), self._every_reply_file_name()
        )
        samples, sample_rate = sf.read(
            str(replies_folder / build_reply_wav_file_name(REPLY_TEXTS[0]))
        )
        self.assertEqual(sample_rate, SAMPLE_RATE)
        self.assertEqual(len(samples), 20)

    async def test_prepare_replies_gives_the_provider_every_text_with_params_and_path(
        self,
    ):
        provider = _make_fake_cloning_provider()
        params = _make_chatterbox_params("nova")
        profile_path = self.profiles_dir / "nova" / "profile.pt"

        await self.service.prepare_replies(
            provider, params, profile_path, self.input_dir / "replies"
        )

        given_arguments = [call.args for call in provider.synthesize.await_args_list]
        self.assertEqual(
            given_arguments, [(text, params, profile_path) for text in REPLY_TEXTS]
        )

    async def test_prepare_replies_creates_the_missing_folder(self):
        replies_folder = self.input_dir / "deeper" / "replies"

        await self.service.prepare_replies(
            _make_fake_cloning_provider(),
            _make_chatterbox_params(),
            None,
            replies_folder,
        )

        self.assertTrue(replies_folder.is_dir())

    async def test_prepare_replies_replaces_an_existing_file(self):
        replies_folder = self.input_dir / "replies"
        replies_folder.mkdir()
        first_reply = replies_folder / build_reply_wav_file_name(REPLY_TEXTS[0])
        first_reply.write_bytes(b"old")

        await self.service.prepare_replies(
            _make_fake_cloning_provider(),
            _make_chatterbox_params(),
            None,
            replies_folder,
        )

        samples, _ = sf.read(str(first_reply))
        self.assertEqual(len(samples), 20)

    async def test_prepare_replies_works_for_a_remote_provider_without_a_profile(
        self,
    ):
        edge_provider = EdgeTTSProvider()
        edge_provider.synthesize = AsyncMock(
            return_value=(np.full(20, 0.25), SAMPLE_RATE)
        )
        replies_folder = self.service.build_replies_folder("edge", VOICE)

        await self.service.prepare_replies(
            edge_provider, _make_edge_params(), None, replies_folder
        )

        self.assertEqual(
            self._file_names_in(self.voices_dir / "edge" / VOICE / "replies"),
            self._every_reply_file_name(),
        )
        given_profile_paths = {
            call.args[2] for call in edge_provider.synthesize.await_args_list
        }
        self.assertEqual(given_profile_paths, {None})

    async def test_prepare_replies_raises_the_provider_error_and_keeps_the_files_so_far(
        self,
    ):
        provider = _make_fake_cloning_provider()
        provider.synthesize.side_effect = [
            (np.full(20, 0.25), SAMPLE_RATE),
            (np.full(20, 0.25), SAMPLE_RATE),
            OSError("no network"),
        ]
        replies_folder = self.input_dir / "replies"

        with self.assertRaises(OSError):
            await self.service.prepare_replies(
                provider, _make_chatterbox_params(), None, replies_folder
            )

        self.assertEqual(
            self._file_names_in(replies_folder),
            sorted(build_reply_wav_file_name(text) for text in REPLY_TEXTS[:2]),
        )

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
                VoiceCloningState.REPLIES_CREATED,
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
        self.assertEqual(create_args[1], self.profiles_dir / "nova" / "profile.pt")
        self.assertIs(create_args[2], screen_params)
        # The first synthesis is the sample, the later ones are the replies
        synthesize_args = provider.synthesize.await_args_list[0].args
        self.assertEqual(synthesize_args[0], DEFAULT_VOICE_SAMPLE_TEXT)
        self.assertEqual(synthesize_args[1].exaggeration, 1.5)

    async def test_clone_voice_synthesizes_the_sample_for_the_new_profile_name(self):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params("old")
        )

        synthesize_args = provider.synthesize.await_args_list[0].args
        self.assertEqual(synthesize_args[0], DEFAULT_VOICE_SAMPLE_TEXT)
        self.assertEqual(synthesize_args[1].profile, "nova")
        self.assertEqual(synthesize_args[2], self.profiles_dir / "nova" / "profile.pt")

    async def test_clone_voice_writes_the_sample_next_to_the_profile(self):
        self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        sample, rate = sf.read(str(self.profiles_dir / "nova" / "sample.wav"))
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

        self.assertEqual(states[-1], VoiceCloningState.REPLIES_CREATED)

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

        self.assertEqual(states[-1], VoiceCloningState.REPLIES_CREATED)

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
        seen_clip_paths: list[Path] = []

        async def remember_clip_path_and_fail(clip_path, profile_path, params):
            seen_clip_paths.append(Path(clip_path))
            raise OSError("disk full")

        provider.create_voice_profile.side_effect = remember_clip_path_and_fail
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(RuntimeError):
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        self.assertEqual(len(seen_clip_paths), 1)
        self.assertFalse(seen_clip_paths[0].parent.exists())

    async def test_clone_voice_deletes_the_trimmed_clip_after_success(self):
        provider = self._use_saved_chatterbox()
        seen_clip_paths = self._remember_clip_paths_given_to(provider)
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(len(seen_clip_paths), 1)
        self.assertFalse(seen_clip_paths[0].parent.exists())
        self.assertTrue(audio_path.exists())

    async def test_clone_voice_deletes_the_trimmed_clip_when_cancelled(self):
        provider = self._use_saved_chatterbox()
        seen_clip_paths: list[Path] = []
        learning_started = asyncio.Event()

        async def learn_until_cancelled(clip_path, profile_path, params):
            seen_clip_paths.append(Path(clip_path))
            learning_started.set()
            await asyncio.Event().wait()

        provider.create_voice_profile.side_effect = learn_until_cancelled
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        clone_task = asyncio.create_task(
            self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )
        )
        await learning_started.wait()
        clone_task.cancel()

        # The cancel must come out as it is, not wrapped in RuntimeError
        with self.assertRaises(asyncio.CancelledError):
            await clone_task

        self.assertFalse(seen_clip_paths[0].parent.exists())

    async def test_clone_voice_finishes_when_the_trimmed_clip_cannot_be_deleted(self):
        provider = self._use_saved_chatterbox()
        seen_clip_paths = self._remember_clip_paths_given_to(provider)
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        # On Windows a file still open in the model thread cannot be deleted
        with patch("os.unlink", side_effect=PermissionError("file in use")):
            states = await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )
        self.addCleanup(shutil.rmtree, seen_clip_paths[0].parent, ignore_errors=True)

        self.assertEqual(states[-1], VoiceCloningState.REPLIES_CREATED)

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

        self.assertEqual(
            (self.profiles_dir / "nova" / "profile.pt").read_bytes(), b"profile"
        )
        self.assertEqual(
            (self.profiles_dir / "nova" / "sample.wav").read_bytes(), b"sample"
        )
        provider.create_voice_profile.assert_not_awaited()

    async def test_clone_voice_writes_the_trimmed_clip_outside_the_voices_folder(self):
        provider = self._use_saved_chatterbox()
        seen_clip_paths = self._remember_clip_paths_given_to(provider)
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        clip_folder = seen_clip_paths[0].parent
        self.assertNotEqual(clip_folder, self.voices_dir)
        self.assertNotEqual(clip_folder, self.input_dir)

    async def test_clone_voice_never_touches_a_recording_picked_from_the_voices_folder(
        self,
    ):
        self._use_saved_chatterbox()
        self.profiles_dir.mkdir(parents=True)
        # The name the trimmed clip had before, it replaced and deleted this file
        audio_path = self.profiles_dir / "nova_reference.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params()
        )

        self.assertEqual(sf.info(str(audio_path)).frames, 12 * SAMPLE_RATE)

    async def test_clone_voice_prepares_the_replies_in_the_folder_of_the_new_profile(
        self,
    ):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        await self._collect_clone_states(
            str(audio_path), "nova", _make_chatterbox_params("old")
        )

        replies_folder = self.profiles_dir / "nova" / "replies"
        self.assertEqual(
            self._file_names_in(replies_folder), self._every_reply_file_name()
        )
        # The first synthesis is the sample, the rest are the replies
        reply_calls = provider.synthesize.await_args_list[1:]
        self.assertEqual([call.args[0] for call in reply_calls], REPLY_TEXTS)
        for reply_call in reply_calls:
            self.assertEqual(reply_call.args[1].profile, "nova")
            self.assertEqual(
                reply_call.args[2], self.profiles_dir / "nova" / "profile.pt"
            )

    async def test_clone_voice_yields_replies_created_only_after_all_replies_are_made(
        self,
    ):
        self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)
        replies_folder = self.profiles_dir / "nova" / "replies"
        replies_written_at_state = {}

        async for state in self.service.clone_voice(
            str(audio_path), "nova", _make_chatterbox_params()
        ):
            replies_written_at_state[state] = len(list(replies_folder.glob("*.wav")))

        self.assertEqual(replies_written_at_state[VoiceCloningState.SAMPLE_CREATED], 0)
        self.assertEqual(
            replies_written_at_state[VoiceCloningState.REPLIES_CREATED],
            len(REPLY_TEXTS),
        )

    async def test_clone_voice_wraps_a_reply_error_in_runtime_error_and_keeps_sample(
        self,
    ):
        provider = self._use_saved_chatterbox()
        provider.synthesize.side_effect = [
            (np.full(20, 0.25), SAMPLE_RATE),
            OSError("no network"),
        ]
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(RuntimeError) as context:
            await self._collect_clone_states(
                str(audio_path), "nova", _make_chatterbox_params()
            )

        self.assertIsInstance(context.exception.__cause__, OSError)
        self.assertTrue((self.profiles_dir / "nova" / "sample.wav").exists())

    async def test_clone_voice_raises_value_error_for_a_name_without_a_folder_at_once(
        self,
    ):
        provider = self._use_saved_chatterbox()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, 12)

        with self.assertRaises(ValueError):
            await self._collect_clone_states(
                str(audio_path), "..", _make_chatterbox_params()
            )

        self.assertFalse(self.voices_dir.exists())
        provider.create_voice_profile.assert_not_awaited()

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
        self.assertEqual(list(self.profiles_dir.iterdir()), [])
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

    def test_remove_profile_removes_the_whole_folder_of_the_profile(self):
        self._make_profile_files("celeste")
        self._make_replies_files("celeste", "gear.wav")
        self._make_profile_files("nova")

        self.service.remove_profile("celeste", _make_chatterbox_params())

        self.assertEqual(self._file_names_in(self.profiles_dir), ["nova"])

    def test_remove_profile_does_not_fail_when_the_files_are_missing(self):
        self.profiles_dir.mkdir(parents=True)

        self.service.remove_profile("ghost", _make_chatterbox_params())

    def test_remove_profile_raises_voice_cloning_exception_for_edge_params(self):
        self._make_profile_files("celeste")

        with self.assertRaises(VoiceCloningException):
            self.service.remove_profile("celeste", _make_edge_params())

        self.assertTrue((self.profiles_dir / "celeste" / "profile.pt").exists())

    def test_remove_profile_keeps_the_replies_of_other_profiles(self):
        self._make_profile_files("celeste")
        self._make_profile_files("nova")
        self._make_replies_files("celeste", "gear.wav")
        nova_replies_folder = self._make_replies_files("nova", "gear.wav")

        self.service.remove_profile("celeste", _make_chatterbox_params())

        self.assertEqual(self._file_names_in(nova_replies_folder), ["gear.wav"])

    def test_remove_profile_raises_value_error_for_a_name_without_a_folder(self):
        self._make_profile_files("celeste")
        replies_folder = self._make_replies_files("celeste", "gear.wav")

        for name in ["", ".."]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.service.remove_profile(name, _make_chatterbox_params())

        self.assertTrue((replies_folder / "gear.wav").exists())
        self.assertTrue((self.profiles_dir / "celeste" / "profile.pt").exists())

    # --- rename_profile ---

    def test_rename_profile_renames_the_folder_of_the_profile(self):
        self._make_profile_files("celeste")

        self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertEqual(self._file_names_in(self.profiles_dir), ["nova"])
        self.assertEqual(
            self._file_names_in(self.profiles_dir / "nova"),
            ["profile.pt", "sample.wav"],
        )

    def test_rename_profile_raises_file_exists_error_when_target_is_taken(self):
        self._make_profile_files("celeste")
        self._make_profile_files("nova")

        with self.assertRaises(FileExistsError):
            self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertTrue((self.profiles_dir / "celeste" / "profile.pt").exists())

    def test_rename_profile_raises_file_not_found_when_the_old_profile_is_missing(
        self,
    ):
        self.profiles_dir.mkdir(parents=True)

        with self.assertRaises(FileNotFoundError):
            self.service.rename_profile("ghost", "nova", _make_chatterbox_params())

    def test_rename_profile_works_for_a_profile_without_a_sample(self):
        self._make_profile_files("celeste", with_sample=False)

        self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertEqual(
            self._file_names_in(self.profiles_dir / "nova"), ["profile.pt"]
        )

    def test_rename_profile_raises_voice_cloning_exception_for_edge_params(self):
        with self.assertRaises(VoiceCloningException):
            self.service.rename_profile("celeste", "nova", _make_edge_params())

    def test_rename_profile_moves_the_folder_of_replies_with_its_files(self):
        self._make_profile_files("celeste")
        old_replies_folder = self._make_replies_files("celeste", "gear.wav")

        self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        new_replies_folder = self.profiles_dir / "nova" / "replies"
        self.assertEqual(self._file_names_in(new_replies_folder), ["gear.wav"])
        self.assertFalse(old_replies_folder.exists())

    def test_rename_profile_replaces_a_stale_folder_under_the_new_name(self):
        self._make_profile_files("celeste")
        self._make_replies_files("celeste", "gear.wav")
        new_replies_folder = self._make_replies_files("nova", "stale.wav")

        self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertEqual(self._file_names_in(new_replies_folder), ["gear.wav"])

    def test_rename_profile_keeps_the_replies_when_the_new_name_is_taken(self):
        self._make_profile_files("celeste")
        self._make_profile_files("nova")
        old_replies_folder = self._make_replies_files("celeste", "gear.wav")

        with self.assertRaises(FileExistsError):
            self.service.rename_profile("celeste", "nova", _make_chatterbox_params())

        self.assertTrue((old_replies_folder / "gear.wav").exists())
        self.assertFalse((self.profiles_dir / "nova" / "replies").exists())

    def test_rename_profile_raises_value_error_for_a_name_without_a_folder_at_once(
        self,
    ):
        self._make_profile_files("celeste")
        replies_folder = self._make_replies_files("celeste", "gear.wav")

        with self.assertRaises(ValueError):
            self.service.rename_profile("celeste", "..", _make_chatterbox_params())

        self.assertTrue((self.profiles_dir / "celeste" / "profile.pt").exists())
        self.assertTrue((replies_folder / "gear.wav").exists())

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
        self.assertEqual(profile_path, self.profiles_dir / "nova" / "profile.pt")

    async def test_preview_voice_sample_plays_without_effects_at_saved_volume(self):
        provider = self._use_saved_chatterbox()
        self.settings_service.get_settings.return_value = _make_settings(
            _make_chatterbox_params(), ship_effect=True
        )
        samples = np.zeros(5)
        provider.synthesize.return_value = (samples, SAMPLE_RATE)
        self.service.play_samples = AsyncMock()

        await self.service.preview_voice_sample("nova", "Hi", _make_chatterbox_params())

        self.service.play_samples.assert_awaited_once_with(
            samples, SAMPLE_RATE, SAVED_VOLUME
        )

    async def test_preview_voice_sample_writes_nothing_to_disk(self):
        self._use_saved_chatterbox()
        self.service.play_samples = AsyncMock()

        await self.service.preview_voice_sample("nova", "Hi", _make_chatterbox_params())

        self.assertFalse(self.voices_dir.exists())

    async def test_preview_voice_sample_raises_voice_cloning_exception_for_edge(self):
        with self.assertRaises(VoiceCloningException):
            await self.service.preview_voice_sample("nova", "Hi", _make_edge_params())

    # --- get_active_or_new_provider_for ---

    def test_active_or_new_provider_returns_the_active_one_for_its_own_type(self):
        active_provider = Mock(spec=EdgeTTSProvider)
        self.service.provider = active_provider

        provider = self.service.get_active_or_new_provider_for(_make_edge_params())

        self.assertIs(provider, active_provider)

    def test_active_or_new_provider_builds_a_throwaway_one_for_another_type(self):
        active_provider = Mock(spec=EdgeTTSProvider)
        self.service.provider = active_provider

        provider = self.service.get_active_or_new_provider_for(
            _make_chatterbox_params()
        )

        self.assertIsInstance(provider, ChatterboxTTSProvider)
        self.assertIs(self.service.provider, active_provider)

    def test_active_or_new_provider_builds_one_when_none_is_active(self):
        self.service.provider = None

        provider = self.service.get_active_or_new_provider_for(_make_edge_params())

        self.assertIsInstance(provider, EdgeTTSProvider)

    # --- play_voice_test_sentence ---

    def _make_screen_tts(
        self,
        params: TtsProviderParams,
        volume: float = 0.3,
        ship_effect: bool = True,
    ) -> TTSModel:
        """The TTS settings as they are on the screen, not the saved ones."""
        return TTSModel(
            provider=params.type,
            params=params,
            volume=volume,
            ship_effect=ship_effect,
        )

    def _use_working_edge_provider(self) -> Mock:
        """The active provider is an Edge one that finds no problem with the
        params and speaks 10 silent samples."""
        provider = Mock(spec=EdgeTTSProvider)
        provider.validate_params.return_value = None
        provider.synthesize = AsyncMock(return_value=(np.zeros(10), SAMPLE_RATE))
        self.service.provider = provider
        return provider

    async def test_voice_test_speaks_the_test_text_with_the_screen_params(self):
        provider = self._use_working_edge_provider()
        self.service.play_samples = AsyncMock()
        screen_params = _make_edge_params("en-GB-SoniaNeural")

        await self.service.play_voice_test_sentence(
            self._make_screen_tts(screen_params)
        )

        text, used_params, profile_path = provider.synthesize.await_args.args
        self.assertEqual(text, VOICE_TEST_TEXT)
        self.assertIs(used_params, screen_params)
        self.assertIsNone(profile_path)

    async def test_voice_test_uses_the_profile_file_of_the_screen_params(self):
        provider = self._use_saved_chatterbox()
        self.service.play_samples = AsyncMock()

        await self.service.play_voice_test_sentence(
            self._make_screen_tts(_make_chatterbox_params("nova"))
        )

        profile_path = provider.synthesize.await_args.args[2]
        self.assertEqual(profile_path, self.profiles_dir / "nova" / "profile.pt")

    async def test_voice_test_plays_the_voice_at_the_screen_volume(self):
        provider = self._use_working_edge_provider()
        samples = np.full(30, 0.5)
        provider.synthesize.return_value = (samples, SAMPLE_RATE)
        self.service.play_samples = AsyncMock()

        await self.service.play_voice_test_sentence(
            self._make_screen_tts(_make_edge_params(), volume=0.3)
        )

        self.service.play_samples.assert_awaited_once()
        self.assertIs(self.service.play_samples.await_args.args[0], samples)
        self.assertEqual(
            self.service.play_samples.await_args.args[1:], (SAMPLE_RATE, 0.3)
        )

    async def test_voice_test_asks_for_the_ship_effect_from_the_screen_when_on(self):
        self._use_working_edge_provider()
        self.service.play_samples = AsyncMock()

        await self.service.play_voice_test_sentence(
            self._make_screen_tts(_make_edge_params(), ship_effect=True)
        )

        self.assertIs(
            self.service.play_samples.await_args.kwargs["with_ship_effect"], True
        )

    async def test_voice_test_leaves_the_ship_effect_out_when_the_screen_has_it_off(
        self,
    ):
        self.settings_service.get_settings.return_value = _make_settings(
            _make_edge_params(), ship_effect=True
        )
        self._use_working_edge_provider()
        self.service.play_samples = AsyncMock()

        await self.service.play_voice_test_sentence(
            self._make_screen_tts(_make_edge_params(), ship_effect=False)
        )

        self.assertIs(
            self.service.play_samples.await_args.kwargs["with_ship_effect"], False
        )

    async def test_voice_test_uses_a_throwaway_provider_for_an_unsaved_engine(self):
        active_provider = self._use_working_edge_provider()
        throwaway_provider = _make_fake_cloning_provider()
        self.service.build_provider = Mock(return_value=throwaway_provider)
        self.service.play_samples = AsyncMock()

        await self.service.play_voice_test_sentence(
            self._make_screen_tts(_make_chatterbox_params("nova"))
        )

        self.service.build_provider.assert_called_once_with("chatterbox")
        throwaway_provider.synthesize.assert_awaited_once()
        active_provider.synthesize.assert_not_awaited()

    async def test_voice_test_raises_value_error_when_engine_is_not_set_up(self):
        provider = self._use_saved_chatterbox()
        self.service.play_samples = AsyncMock()
        screen_params = _make_chatterbox_params("")
        problem = provider.validate_params(screen_params)
        self.assertIsNotNone(problem)

        with self.assertRaises(ValueError) as raised:
            await self.service.play_voice_test_sentence(
                self._make_screen_tts(screen_params)
            )

        self.assertEqual(str(raised.exception), problem.message)
        provider.synthesize.assert_not_awaited()
        self.service.play_samples.assert_not_awaited()

    async def test_voice_test_propagates_provider_error_and_plays_nothing(self):
        provider = self._use_working_edge_provider()
        provider.synthesize.side_effect = RuntimeError("network down")
        self.service.play_samples = AsyncMock()

        with self.assertRaises(RuntimeError):
            await self.service.play_voice_test_sentence(
                self._make_screen_tts(_make_edge_params())
            )

        self.service.play_samples.assert_not_awaited()

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


class FakePortAudioError(Exception):
    """Stands for sounddevice.PortAudioError, the error of a speaker that cannot be
    opened."""


class TTSServiceStreamingTest(unittest.IsolatedAsyncioTestCase):
    """Speaking in pieces: a Chatterbox provider that can stream, with the work of
    the model and the speaker replaced by fakes."""

    def setUp(self):
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = _make_settings(
            _make_chatterbox_params()
        )
        self.service = TTSService(
            event_bus=EventBus(),
            settings_service=self.settings_service,
        )
        self.service.reload_service()
        self.provider = _make_fake_cloning_provider()
        self.service.provider = self.provider

        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        self.voices_dir = Path(temp_directory.name) / "voices"
        self.profiles_dir = self.voices_dir / "chatterbox"
        voices_dir_patch = patch(
            "edceleste.services.tts_service.VOICES_DIR", self.voices_dir
        )
        voices_dir_patch.start()
        self.addCleanup(voices_dir_patch.stop)

        self.sounddevice = Mock()
        sounddevice_patch = patch.dict(sys.modules, {"sounddevice": self.sounddevice})
        sounddevice_patch.start()
        self.addCleanup(sounddevice_patch.stop)

        self.stream_calls: list[tuple] = []
        self.stream_was_read_to_the_end = False

    def _make_provider_speak(self, pieces, can_stream=True, fail_at_piece=None):
        """The provider makes these pieces, one after another. With
        fail_at_piece it fails instead of making that piece."""
        self.provider.can_stream = Mock(return_value=can_stream)
        self.provider.stream_sample_rate = SAMPLE_RATE

        async def synthesize_stream(text, params, profile_path=None):
            self.stream_calls.append((text, params, profile_path))
            for number, piece in enumerate(pieces):
                if number == fail_at_piece:
                    raise RuntimeError("GPU out of memory")
                yield piece
            self.stream_was_read_to_the_end = True

        self.provider.synthesize_stream = synthesize_stream

    def _use_a_fake_player(self):
        """The real player needs a speaker. This one keeps every piece it gets and
        notes when the end (None) came. It gives up after 2 s without a piece, so
        a missing end fails the test and does not leave a thread waiting."""
        self.played_pieces: list[np.ndarray] = []
        self.player_sample_rates: list[int] = []
        self.player_got_the_end = threading.Event()

        def play_pieces(pieces, sample_rate):
            self.player_sample_rates.append(sample_rate)
            while (piece := pieces.get(timeout=2)) is not None:
                self.played_pieces.append(piece)
            self.player_got_the_end.set()

        self.service.play_pieces = play_pieces

    def _use_a_fake_speaker(self) -> MagicMock:
        speaker = MagicMock()
        speaker.__enter__.return_value = speaker
        self.service.open_speaker = Mock(return_value=speaker)
        return speaker

    def _use_a_fake_ship_effect(self):
        """The ship effect is replaced by a fake, because the real one needs a real
        sample rate. The fake doubles every piece and gives it as two columns,
        keeps the pieces it was given and rings on for 3 samples. Every effect
        made is added to self.made_effects."""
        self.made_effects: list = []
        made_effects = self.made_effects

        class FakeShipVoiceEffect:
            def __init__(self, sample_rate):
                self.sample_rate = sample_rate
                self.pieces_given: list[np.ndarray] = []
                made_effects.append(self)

            def process(self, piece):
                self.pieces_given.append(piece)
                return np.stack([piece * 2, piece * 2], axis=1)

            def finish(self):
                return np.full((3, 2), 0.7, dtype=np.float32)

        effect_patch = patch(
            "edceleste.services.tts_service.ShipVoiceEffect", FakeShipVoiceEffect
        )
        effect_patch.start()
        self.addCleanup(effect_patch.stop)

    async def _speak(self, volume=SAVED_VOLUME, with_ship_effect=False):
        await self.service.speak_while_synthesizing(
            self.provider,
            "Hello",
            _make_chatterbox_params(),
            volume,
            None,
            with_ship_effect,
        )

    # --- synthesize_and_play chooses the way ---

    async def test_synthesize_and_play_streams_when_the_provider_can_stream(self):
        self._make_provider_speak(
            [np.full(10, 0.5, dtype=np.float32), np.full(20, 0.5, dtype=np.float32)]
        )
        self._use_a_fake_player()
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.provider.synthesize.assert_not_awaited()
        self.service.play_samples.assert_not_awaited()
        self.provider.can_stream.assert_called_once_with(_make_chatterbox_params())
        self.assertEqual(
            self.stream_calls,
            [
                (
                    "Hello",
                    _make_chatterbox_params(),
                    self.profiles_dir / "celeste" / "profile.pt",
                )
            ],
        )
        self.assertEqual(self.player_sample_rates, [SAMPLE_RATE])
        np.testing.assert_allclose(
            np.concatenate(self.played_pieces), np.full(30, 0.5 * SAVED_VOLUME)
        )

    async def test_synthesize_and_play_streams_through_the_ship_effect_when_on(
        self,
    ):
        self.settings_service.get_settings.return_value = _make_settings(
            _make_chatterbox_params(), ship_effect=True
        )
        self._use_a_fake_ship_effect()
        self._make_provider_speak([np.full(10, 0.5, dtype=np.float32)])
        self._use_a_fake_player()

        await self.service.synthesize_and_play("Hello")

        self.assertEqual(len(self.made_effects), 1)
        self.assertEqual(self.made_effects[0].sample_rate, SAMPLE_RATE)

    async def test_synthesize_and_play_makes_the_whole_audio_when_it_cannot_stream(
        self,
    ):
        self._make_provider_speak([np.zeros(10, dtype=np.float32)], can_stream=False)
        self.service.play_samples = AsyncMock()

        await self.service.synthesize_and_play("Hello")

        self.provider.synthesize.assert_awaited_once()
        self.service.play_samples.assert_awaited_once()
        self.assertEqual(self.stream_calls, [])

    # --- speak_while_synthesizing ---

    async def test_speak_while_synthesizing_queues_every_sample_once_at_the_volume(
        self,
    ):
        self._make_provider_speak(
            [
                (np.arange(10) / 100).astype(np.float32),
                (np.arange(10, 30) / 100).astype(np.float32),
            ]
        )
        self._use_a_fake_player()

        await self._speak(volume=0.5)

        np.testing.assert_allclose(
            np.concatenate(self.played_pieces), (np.arange(30) / 100) * 0.5, atol=1e-6
        )

    async def test_speak_while_synthesizing_runs_all_pieces_through_one_new_effect(
        self,
    ):
        self._use_a_fake_ship_effect()
        first_piece = np.arange(10, dtype=np.float32) / 100
        second_piece = np.arange(10, 30, dtype=np.float32) / 100
        self._make_provider_speak([first_piece, second_piece])
        self._use_a_fake_player()

        await self._speak(volume=0.5, with_ship_effect=True)

        self.assertEqual(len(self.made_effects), 1)
        effect = self.made_effects[0]
        self.assertEqual(effect.sample_rate, SAMPLE_RATE)
        self.assertEqual([len(piece) for piece in effect.pieces_given], [10, 20])
        np.testing.assert_array_equal(effect.pieces_given[0], first_piece)
        np.testing.assert_array_equal(effect.pieces_given[1], second_piece)
        queued = np.concatenate(self.played_pieces[:2])
        np.testing.assert_allclose(
            queued[:, 0], (np.arange(30) / 100) * 2 * 0.5, atol=1e-6
        )

    async def test_speak_while_synthesizing_starts_no_player_when_the_effect_fails(
        self,
    ):
        class BrokenShipVoiceEffect:
            def __init__(self, sample_rate):
                raise ValueError("sample rate not supported")

        effect_patch = patch(
            "edceleste.services.tts_service.ShipVoiceEffect", BrokenShipVoiceEffect
        )
        effect_patch.start()
        self.addCleanup(effect_patch.stop)
        self._make_provider_speak([np.zeros(10, dtype=np.float32)])
        self._use_a_fake_player()

        with self.assertRaises(ValueError):
            await self._speak(with_ship_effect=True)
        # A player that was started would have run by now
        await asyncio.sleep(0.1)

        self.assertEqual(self.player_sample_rates, [])
        self.assertEqual(self.stream_calls, [])

    async def test_speak_while_synthesizing_queues_the_tail_of_the_effect_at_the_end(
        self,
    ):
        self._use_a_fake_ship_effect()
        self._make_provider_speak(
            [
                (np.arange(10) / 100).astype(np.float32),
                (np.arange(10, 30) / 100).astype(np.float32),
            ]
        )
        self._use_a_fake_player()

        await self._speak(volume=0.5, with_ship_effect=True)

        queued = np.concatenate(self.played_pieces)
        self.assertEqual(queued.shape, (33, 2))
        np.testing.assert_allclose(self.played_pieces[-1], np.full((3, 2), 0.35))

    async def test_speak_while_synthesizing_queues_stereo_pieces_of_the_effect(self):
        self._use_a_fake_ship_effect()
        self._make_provider_speak([(np.arange(10) / 100).astype(np.float32)])
        self._use_a_fake_player()

        await self._speak(with_ship_effect=True)

        self.assertEqual(self.played_pieces[0].shape, (10, 2))
        np.testing.assert_array_equal(
            self.played_pieces[0][:, 0], self.played_pieces[0][:, 1]
        )

    async def test_speak_while_synthesizing_leaves_the_pieces_alone_without_the_effect(
        self,
    ):
        self._use_a_fake_ship_effect()
        self._make_provider_speak(
            [np.full(10, 0.5, dtype=np.float32), np.full(20, 0.5, dtype=np.float32)]
        )
        self._use_a_fake_player()

        await self._speak(volume=0.5, with_ship_effect=False)

        self.assertEqual(self.made_effects, [])
        queued = np.concatenate(self.played_pieces)
        self.assertEqual(queued.shape, (30,))
        np.testing.assert_allclose(queued, np.full(30, 0.25))

    async def test_every_reply_gets_a_new_effect(self):
        self._use_a_fake_ship_effect()
        self._make_provider_speak([np.zeros(10, dtype=np.float32)])
        self._use_a_fake_player()

        await self._speak(with_ship_effect=True)
        self._use_a_fake_player()
        await self._speak(with_ship_effect=True)

        self.assertEqual(len(self.made_effects), 2)
        self.assertIsNot(self.made_effects[0], self.made_effects[1])

    async def test_speak_while_synthesizing_ends_the_player_after_the_last_piece(self):
        self._make_provider_speak([np.zeros(10, dtype=np.float32)])
        self._use_a_fake_player()

        await self._speak()

        self.assertTrue(self.stream_was_read_to_the_end)
        self.assertTrue(self.player_got_the_end.is_set())

    async def test_speak_while_synthesizing_works_on_float32_audio_all_the_way(self):
        self._make_provider_speak(
            [np.zeros(10, dtype=np.float32), np.zeros(20, dtype=np.float32)]
        )
        self._use_a_fake_player()

        await self._speak()

        self.assertEqual(
            {piece.dtype for piece in self.played_pieces}, {np.dtype(np.float32)}
        )

    async def test_speak_while_synthesizing_ends_cleanly_when_there_are_no_pieces(
        self,
    ):
        self._make_provider_speak([])
        self._use_a_fake_player()

        await self._speak()

        self.assertTrue(self.player_got_the_end.is_set())
        self.assertEqual(sum(len(piece) for piece in self.played_pieces), 0)

    async def test_speak_while_synthesizing_stops_the_player_when_the_provider_fails(
        self,
    ):
        self._make_provider_speak(
            [np.zeros(10, dtype=np.float32), np.zeros(10, dtype=np.float32)],
            fail_at_piece=1,
        )
        self._use_a_fake_player()

        with self.assertRaises(RuntimeError):
            await self._speak()

        player_got_the_end = await asyncio.to_thread(self.player_got_the_end.wait, 1)
        self.assertTrue(player_got_the_end)
        self.assertEqual(len(self.played_pieces), 1)

    async def test_speak_while_synthesizing_leaves_no_unread_error_of_the_player(
        self,
    ):
        self._make_provider_speak(
            [np.zeros(10, dtype=np.float32), np.zeros(10, dtype=np.float32)],
            fail_at_piece=1,
        )
        provider_errors = []

        def play_pieces_without_a_speaker(pieces, sample_rate):
            raise FakePortAudioError("no speaker")

        self.service.play_pieces = play_pieces_without_a_speaker
        loop_complaints = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: loop_complaints.append(context["message"])
        )

        try:
            await self._speak()
        except RuntimeError as provider_error:
            provider_errors.append(str(provider_error))
        await asyncio.sleep(0.2)  # the player thread fails and its task ends
        gc.collect()  # asyncio complains when a failed task is collected unread

        self.assertEqual(provider_errors, ["GPU out of memory"])
        self.assertEqual(loop_complaints, [])

    # --- the player and the speaker ---

    def test_play_pieces_plays_a_mono_piece_from_both_speakers(self):
        speaker = self._use_a_fake_speaker()
        pieces: queue.Queue = queue.Queue()
        pieces.put(np.array([0.1, 0.2, 0.3], dtype=np.float32))
        pieces.put(None)

        self.service.play_pieces(pieces, 24000)

        self.service.open_speaker.assert_called_once_with(24000)
        speaker.write.assert_called_once()
        np.testing.assert_allclose(
            speaker.write.call_args.args[0],
            np.array([[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]], dtype=np.float32),
        )

    def test_play_pieces_writes_float32_pieces_until_the_end_and_closes_the_speaker(
        self,
    ):
        speaker = self._use_a_fake_speaker()
        stereo_float64_not_contiguous = np.asfortranarray(
            np.array([[0.1, 0.4], [0.2, 0.5]], dtype=np.float64)
        )
        pieces: queue.Queue = queue.Queue()
        pieces.put(stereo_float64_not_contiguous)
        pieces.put(np.array([0.6], dtype=np.float32))
        pieces.put(None)

        self.service.play_pieces(pieces, 24000)

        self.assertEqual(speaker.write.call_count, 2)  # the end (None) is not written
        first_written = speaker.write.call_args_list[0].args[0]
        self.assertEqual(first_written.dtype, np.float32)
        self.assertTrue(first_written.flags["C_CONTIGUOUS"])
        np.testing.assert_allclose(first_written, [[0.1, 0.4], [0.2, 0.5]])
        speaker.__exit__.assert_called_once()

    def test_play_pieces_skips_an_empty_piece(self):
        speaker = self._use_a_fake_speaker()
        pieces: queue.Queue = queue.Queue()
        pieces.put(np.array([0.1, 0.2], dtype=np.float32))
        pieces.put(np.zeros(0, dtype=np.float32))  # nothing left after the last piece
        pieces.put(np.array([0.3], dtype=np.float32))
        pieces.put(None)

        self.service.play_pieces(pieces, 24000)

        written_lengths = [len(call.args[0]) for call in speaker.write.call_args_list]
        self.assertEqual(written_lengths, [2, 1])

    def _set_up_windows_with_wasapi(self, wasapi_listed=True):
        host_apis = [{"name": "MME", "default_output_device": 1}]
        if wasapi_listed:
            host_apis.append({"name": "Windows WASAPI", "default_output_device": 7})
        self.sounddevice.query_hostapis.return_value = host_apis
        self.sounddevice.PortAudioError = FakePortAudioError

    def test_open_speaker_uses_wasapi_with_low_latency_on_windows(self):
        self._set_up_windows_with_wasapi()

        with (
            patch.object(tts_service.sys, "platform", "win32"),
            patch.object(tts_service, "ctypes") as ctypes,
        ):
            speaker = self.service.open_speaker(24000)

        self.assertIs(speaker, self.sounddevice.OutputStream.return_value)
        self.sounddevice.WasapiSettings.assert_called_once_with(auto_convert=True)
        self.sounddevice.OutputStream.assert_called_once_with(
            samplerate=24000,
            channels=2,
            dtype="float32",
            latency="low",
            device=7,
            extra_settings=self.sounddevice.WasapiSettings.return_value,
        )
        ctypes.windll.ole32.CoInitializeEx.assert_called_once_with(None, 0)

    def test_open_speaker_falls_back_to_the_default_speaker_when_wasapi_fails(self):
        self._set_up_windows_with_wasapi()
        self.sounddevice.OutputStream.side_effect = [
            FakePortAudioError("device busy"),
            "the default speaker",
        ]

        with (
            patch.object(tts_service.sys, "platform", "win32"),
            patch.object(tts_service, "ctypes"),
            self.assertLogs(tts_service.logger, level="WARNING"),
        ):
            speaker = self.service.open_speaker(24000)

        self.assertEqual(speaker, "the default speaker")
        self.assertEqual(
            self.sounddevice.OutputStream.call_args_list[1],
            call(samplerate=24000, channels=2, dtype="float32", latency="low"),
        )

    def test_open_speaker_uses_the_default_speaker_when_windows_has_no_wasapi(self):
        self._set_up_windows_with_wasapi(wasapi_listed=False)

        with (
            patch.object(tts_service.sys, "platform", "win32"),
            patch.object(tts_service, "ctypes") as ctypes,
        ):
            self.service.open_speaker(24000)

        self.sounddevice.OutputStream.assert_called_once_with(
            samplerate=24000, channels=2, dtype="float32", latency="low"
        )
        ctypes.windll.ole32.CoInitializeEx.assert_not_called()

    def test_open_speaker_uses_the_default_speaker_on_other_systems(self):
        # WASAPI is on the list, so only the system tells the code not to use it
        self._set_up_windows_with_wasapi()

        with patch.object(tts_service.sys, "platform", "linux"):
            self.service.open_speaker(24000)

        self.sounddevice.OutputStream.assert_called_once_with(
            samplerate=24000, channels=2, dtype="float32", latency="low"
        )
        self.sounddevice.WasapiSettings.assert_not_called()

    # --- warming up the voice ---

    async def test_warm_up_voice_runs_the_model_on_the_warm_up_text_without_sound(
        self,
    ):
        self._make_provider_speak([np.zeros(10, dtype=np.float32)] * 3)

        await self.service.warm_up_voice(self.provider)

        self.assertEqual(
            self.stream_calls,
            [
                (
                    WARM_UP_TEXT,
                    _make_chatterbox_params(),
                    self.profiles_dir / "celeste" / "profile.pt",
                )
            ],
        )
        self.assertTrue(self.stream_was_read_to_the_end)
        self.sounddevice.play.assert_not_called()
        self.sounddevice.OutputStream.assert_not_called()

    async def _run_cold_start(self) -> list[tuple]:
        """What every status looked like when the service handed it out (it is the
        same object, changed afterwards) and how many warm ups had run by then."""
        statuses = []
        async for status in self.service.cold_start():
            statuses.append(
                (
                    status.completed,
                    status.progress_text,
                    status.message,
                    self.service.warm_up_voice.await_count,
                )
            )
        return statuses

    async def test_cold_start_warms_up_the_voice_when_the_provider_can_stream(self):
        self._make_provider_speak([])
        self.service.warm_up_voice = AsyncMock()

        statuses = await self._run_cold_start()

        self.service.warm_up_voice.assert_awaited_once_with(self.provider)
        self.assertEqual(statuses[-1], (True, None, None, 1))

    async def test_cold_start_shows_the_loading_message_before_the_warm_up_starts(
        self,
    ):
        self._make_provider_speak([])
        self.service.warm_up_voice = AsyncMock()

        statuses = await self._run_cold_start()

        self.assertIn((False, "Loading the voice", None, 0), statuses)

    async def test_cold_start_does_not_load_the_voice_when_it_cannot_stream(self):
        self._make_provider_speak([], can_stream=False)
        self.service.warm_up_voice = AsyncMock()

        statuses = await self._run_cold_start()

        self.service.warm_up_voice.assert_not_awaited()
        self.assertEqual(self.stream_calls, [])
        self.assertEqual(statuses[-1], (True, None, None, 0))

    async def test_cold_start_reports_a_failed_warm_up_in_the_status_message(self):
        self._make_provider_speak([])
        self.service.warm_up_voice = AsyncMock(
            side_effect=FileNotFoundError("Voice profile not found: celeste.pt")
        )

        statuses = await self._run_cold_start()

        completed, _, message, _ = statuses[-1]
        self.assertTrue(completed)
        self.assertEqual(message, "Voice profile not found: celeste.pt")


def _make_pocket_params(profile: str = "celeste") -> PocketParamsModel:
    return PocketParamsModel(type="pocket", profile=profile)


def _make_fake_pocket_provider() -> PocketTTSProvider:
    """A real Pocket TTS provider object whose work is replaced by mocks, so no
    model or network is used."""
    provider = PocketTTSProvider()
    provider.synthesize = AsyncMock(return_value=(np.full(20, 0.25), SAMPLE_RATE))
    provider.create_voice_profile = AsyncMock()
    provider.can_stream = Mock(return_value=False)
    return provider


class TTSServiceProfileFoldersTest(unittest.IsolatedAsyncioTestCase):
    """Every cloning provider keeps its profiles and their samples in its own
    folder inside the voices folder: voices/chatterbox and voices/pocket."""

    def setUp(self):
        self.settings_service = Mock(spec=SettingsService)
        self.settings_service.get_settings.return_value = _make_settings()
        self.service = TTSService(
            event_bus=EventBus(),
            settings_service=self.settings_service,
        )
        self.service.reload_service()

        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        self.voices_dir = Path(temp_directory.name) / "voices"
        self.chatterbox_dir = self.voices_dir / "chatterbox"
        self.pocket_dir = self.voices_dir / "pocket"
        voices_dir_patch = patch(
            "edceleste.services.tts_service.VOICES_DIR", self.voices_dir
        )
        voices_dir_patch.start()
        self.addCleanup(voices_dir_patch.stop)

        self.input_dir = Path(temp_directory.name) / "input"
        self.input_dir.mkdir()

    def _use_saved_pocket(self) -> PocketTTSProvider:
        """Saved settings are Pocket TTS, the active provider is a fake."""
        self.settings_service.get_settings.return_value = _make_settings(
            _make_pocket_params()
        )
        self.service.reload_service()
        fake_provider = _make_fake_pocket_provider()
        self.service.provider = fake_provider
        return fake_provider

    def _write_files(self, folder: Path, *names: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            (folder / name).write_bytes(name.encode())

    def test_build_provider_makes_a_pocket_provider_for_pocket(self):
        self.assertIsInstance(self.service.build_provider("pocket"), PocketTTSProvider)

    def test_find_profile_path_puts_a_pocket_profile_in_the_pocket_folder_as_npy(
        self,
    ):
        path = self.service.build_profile_path_named_in_params(
            PocketTTSProvider(), _make_pocket_params("nova")
        )

        self.assertEqual(path, self.pocket_dir / "nova" / "profile.npy")

    def test_get_available_profiles_lists_only_the_profiles_of_the_provider(self):
        self._write_files(self.chatterbox_dir / "voice_a", "profile.pt")
        self._write_files(self.chatterbox_dir / "wrong_kind", "profile.npy")
        self._write_files(self.pocket_dir / "voice_b", "profile.npy")
        self._write_files(self.pocket_dir / "wrong_kind", "profile.pt")

        self.assertEqual(
            self.service.get_available_profiles(_make_pocket_params()), ["voice_b"]
        )
        self.assertEqual(
            self.service.get_available_profiles(_make_chatterbox_params()), ["voice_a"]
        )

    def test_get_available_profiles_ignores_old_files_and_folders_without_a_profile(
        self,
    ):
        # The old layout kept "nova.pt" and "nova_sample.wav" in the folder of
        # the provider, a clone that stopped early leaves a folder with no profile
        self._write_files(self.chatterbox_dir, "old.pt", "old_sample.wav")
        self._write_files(self.chatterbox_dir / "unfinished", "sample.wav")
        self._write_files(self.chatterbox_dir / "nova", "profile.pt")

        self.assertEqual(
            self.service.get_available_profiles(_make_chatterbox_params()), ["nova"]
        )

    def test_get_available_profiles_ignores_files_in_the_voices_folder_itself(self):
        self._write_files(self.voices_dir, "old.pt", "old.npy")

        self.assertEqual(self.service.get_available_profiles(_make_pocket_params()), [])
        self.assertEqual(
            self.service.get_available_profiles(_make_chatterbox_params()), []
        )

    async def test_clone_voice_for_pocket_writes_into_the_pocket_folder(self):
        provider = self._use_saved_pocket()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, provider.reference_seconds)

        _ = [
            state
            async for state in self.service.clone_voice(
                str(audio_path), "nova", _make_pocket_params()
            )
        ]

        profile_path = provider.create_voice_profile.await_args.args[1]
        self.assertEqual(profile_path, self.pocket_dir / "nova" / "profile.npy")
        self.assertTrue((self.pocket_dir / "nova" / "sample.wav").exists())
        self.assertFalse(self.chatterbox_dir.exists())

    async def test_clone_voice_for_pocket_prepares_the_replies_in_the_pocket_folder(
        self,
    ):
        provider = self._use_saved_pocket()
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, provider.reference_seconds)

        _ = [
            state
            async for state in self.service.clone_voice(
                str(audio_path), "nova", _make_pocket_params()
            )
        ]

        replies_folder = self.pocket_dir / "nova" / "replies"
        self.assertEqual(
            sorted(path.name for path in replies_folder.iterdir()),
            sorted(build_reply_wav_file_name(text) for text in REPLY_TEXTS),
        )
        self.assertFalse(self.chatterbox_dir.exists())

    async def test_clone_voice_accepts_a_name_taken_in_another_provider_folder(self):
        provider = self._use_saved_pocket()
        self._write_files(self.chatterbox_dir / "nova", "profile.pt")
        audio_path = self.input_dir / "voice.wav"
        _write_wav(audio_path, provider.reference_seconds)

        states = [
            state
            async for state in self.service.clone_voice(
                str(audio_path), "nova", _make_pocket_params()
            )
        ]

        self.assertEqual(states[-1], VoiceCloningState.REPLIES_CREATED)

    def test_remove_profile_removes_only_the_profile_of_the_provider_of_the_params(
        self,
    ):
        self._write_files(self.chatterbox_dir / "nova", "profile.pt", "sample.wav")
        self._write_files(self.pocket_dir / "nova", "profile.npy", "sample.wav")

        self.service.remove_profile("nova", _make_pocket_params())

        self.assertEqual(list(self.pocket_dir.iterdir()), [])
        self.assertEqual(
            sorted(path.name for path in (self.chatterbox_dir / "nova").iterdir()),
            ["profile.pt", "sample.wav"],
        )

    def test_rename_profile_renames_inside_the_folder_of_the_provider(self):
        self._write_files(self.chatterbox_dir / "celeste", "profile.pt")
        self._write_files(self.pocket_dir / "celeste", "profile.npy", "sample.wav")

        self.service.rename_profile("celeste", "nova", _make_pocket_params())

        self.assertEqual([path.name for path in self.pocket_dir.iterdir()], ["nova"])
        self.assertEqual(
            sorted(path.name for path in (self.pocket_dir / "nova").iterdir()),
            ["profile.npy", "sample.wav"],
        )
        self.assertEqual(
            [path.name for path in self.chatterbox_dir.iterdir()], ["celeste"]
        )

    async def test_preview_voice_sample_uses_the_profile_in_the_pocket_folder(self):
        provider = self._use_saved_pocket()
        self.service.play_samples = AsyncMock()

        await self.service.preview_voice_sample(
            "nova", "Hi there", _make_pocket_params("other")
        )

        profile_path = provider.synthesize.await_args.args[2]
        self.assertEqual(profile_path, self.pocket_dir / "nova" / "profile.npy")

    async def test_play_sample_voice_plays_the_sample_of_the_provider_of_the_params(
        self,
    ):
        self._write_files(self.chatterbox_dir / "celeste", "sample.wav")
        self._write_files(self.pocket_dir / "celeste", "sample.wav")
        self.service.play_audio_file = AsyncMock()

        await self.service.play_sample_voice("celeste", _make_pocket_params())

        self.service.play_audio_file.assert_awaited_once_with(
            str(self.pocket_dir / "celeste" / "sample.wav")
        )

    async def test_play_sample_voice_raises_voice_cloning_exception_for_edge(self):
        self.service.play_audio_file = AsyncMock()

        with self.assertRaises(VoiceCloningException):
            await self.service.play_sample_voice("celeste", _make_edge_params())

        self.service.play_audio_file.assert_not_awaited()
