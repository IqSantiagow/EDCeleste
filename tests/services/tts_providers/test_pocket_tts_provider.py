import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import huggingface_hub
import numpy as np
import soundfile as sf
from huggingface_hub.errors import LocalEntryNotFoundError

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    PocketParamsModel,
)
from edceleste.services.tts_providers.pocket_tts_provider import (
    DECODE_STEPS,
    FIRST_PIECE_FRAMES,
    MODEL_FILE,
    MODEL_REPO,
    MODEL_REVISION,
    NEXT_PIECE_FRAMES,
    ONNX_THREADS,
    PocketTTSProvider,
    find_or_download_model_file,
    take_frames,
)
from edceleste.services.tts_providers.tts_provider_protocol import (
    CloningTTSProviderProtocol,
    StreamingTTSProviderProtocol,
)

PROVIDER_MODULE = "edceleste.services.tts_providers.pocket_tts_provider"
FRAME_SAMPLES = 1920  # 80 ms at 24 kHz, what the real model gives
SAMPLE_RATE = 24000
ONE_FRAME_SECONDS = FRAME_SAMPLES / SAMPLE_RATE


def _make_pocket_params(profile: str = "celeste") -> PocketParamsModel:
    return PocketParamsModel(type="pocket", profile=profile)


def _make_chatterbox_params() -> ChatterboxParamsModel:
    return ChatterboxParamsModel(type="chatterbox", profile="celeste")


class FakeClock:
    """A clock the fake model moves: every frame it makes takes the time set by
    the test, and the test can move the clock itself (the caller's work)."""

    def __init__(self) -> None:
        self.now = 0.0

    def perf_counter(self) -> float:
        return self.now


class FakePocketTTS:
    """Stands in for pocket_tts_onnx.PocketTTS: no model file, no ONNX Runtime.
    Its frames are FRAME_SAMPLES long and filled with the number of the frame."""

    sample_rate = SAMPLE_RATE

    def __init__(self, model_path, num_threads, clock: FakeClock) -> None:
        self.model_path = model_path
        self.num_threads = num_threads
        self.clock = clock
        self.seconds_per_frame = 0.0
        self.frame_count = 20
        self.frames_made = 0
        self.clone_calls: list[tuple] = []
        self.clone_result = np.full((1, 4, 8), 0.5, dtype=np.float32)
        self.stream_calls: list[dict] = []

    def clone_voice(self, samples, sample_rate=None):
        self.clone_calls.append((samples, sample_rate))
        return self.clone_result

    def stream(self, text, voice=None, decode_steps=None):
        self.stream_calls.append(
            {"text": text, "voice": voice, "decode_steps": decode_steps}
        )
        for number in range(self.frame_count):
            self.frames_made += 1
            self.clock.now += self.seconds_per_frame
            yield np.full(FRAME_SAMPLES, number, dtype=np.float32)


class PocketProviderTestCase(unittest.IsolatedAsyncioTestCase):
    """The provider with the vendored PocketTTS and the model download replaced,
    and a temporary folder for the voice profiles."""

    def setUp(self):
        self.clock = FakeClock()
        self.engines: list[FakePocketTTS] = []
        self.frame_count = 20
        self.seconds_per_frame = 0.0

        def make_engine(model_path, num_threads):
            engine = FakePocketTTS(model_path, num_threads, self.clock)
            engine.frame_count = self.frame_count
            engine.seconds_per_frame = self.seconds_per_frame
            self.engines.append(engine)
            return engine

        for target, replacement in (
            (f"{PROVIDER_MODULE}.PocketTTS", make_engine),
            (
                f"{PROVIDER_MODULE}.find_or_download_model_file",
                lambda: Path("fake-model.onnx"),
            ),
            (
                f"{PROVIDER_MODULE}.time",
                SimpleNamespace(perf_counter=self.clock.perf_counter),
            ),
        ):
            patcher = patch(target, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.profile_path = self._save_profile("celeste", 1.0)
        self.provider = PocketTTSProvider()

    def _save_profile(self, name: str, value: float) -> Path:
        path = self.folder / f"{name}.npy"
        np.save(path, np.full((1, 4, 8), value, dtype=np.float16))
        return path

    async def _read_pieces(self, text="Hello Commander") -> list[np.ndarray]:
        return [
            piece
            async for piece in self.provider.synthesize_stream(
                text, _make_pocket_params(), self.profile_path
            )
        ]

    def _set_model(self, frame_count: int, seconds_per_frame: float = 0.0) -> None:
        """Sets how many frames the fake model makes for a text and how long
        each takes, for the model that is loaded and for one that is loaded
        later."""
        self.frame_count = frame_count
        self.seconds_per_frame = seconds_per_frame
        for engine in self.engines:
            engine.frame_count = frame_count
            engine.seconds_per_frame = seconds_per_frame


class FindModelFileTest(unittest.TestCase):
    def test_uses_the_cache_without_downloading(self):
        with patch.object(
            huggingface_hub, "hf_hub_download", return_value="C:/cache/model.onnx"
        ) as download:
            path = find_or_download_model_file()

        self.assertEqual(path, Path("C:/cache/model.onnx"))
        download.assert_called_once()
        self.assertTrue(download.call_args.kwargs["local_files_only"])

    def test_downloads_when_the_cache_has_no_model(self):
        with patch.object(
            huggingface_hub,
            "hf_hub_download",
            side_effect=[LocalEntryNotFoundError("not cached"), "C:/new/model.onnx"],
        ) as download:
            path = find_or_download_model_file()

        self.assertEqual(path, Path("C:/new/model.onnx"))
        self.assertEqual(download.call_count, 2)
        self.assertFalse(download.call_args.kwargs.get("local_files_only", False))

    def test_asks_for_the_pinned_revision_without_a_token(self):
        with patch.object(
            huggingface_hub,
            "hf_hub_download",
            side_effect=[LocalEntryNotFoundError("not cached"), "model.onnx"],
        ) as download:
            find_or_download_model_file()

        for call in download.call_args_list:
            self.assertEqual(call.args, (MODEL_REPO, MODEL_FILE))
            self.assertEqual(call.kwargs["revision"], MODEL_REVISION)
            self.assertIs(call.kwargs["token"], False)


class TakeFramesTest(unittest.TestCase):
    def test_gives_the_next_frames_only(self):
        frames = iter([np.full(2, number) for number in range(5)])

        first = take_frames(frames, 3)
        second = take_frames(frames, 3)

        self.assertEqual([frame[0] for frame in first], [0, 1, 2])
        self.assertEqual([frame[0] for frame in second], [3, 4])

    def test_gives_fewer_frames_when_the_speech_ends(self):
        frames = iter([np.zeros(2), np.zeros(2)])

        self.assertEqual(len(take_frames(frames, 10)), 2)
        self.assertEqual(take_frames(frames, 10), [])


class PocketTTSProviderClassTest(unittest.TestCase):
    def test_is_a_cloning_and_a_streaming_provider(self):
        provider = PocketTTSProvider()

        self.assertIsInstance(provider, CloningTTSProviderProtocol)
        self.assertIsInstance(provider, StreamingTTSProviderProtocol)

    def test_profiles_are_npy_files_in_the_pocket_folder(self):
        self.assertEqual(PocketTTSProvider.profile_file_extension, ".npy")
        self.assertEqual(PocketTTSProvider.profile_folder_name, "pocket")

    def test_learns_a_voice_from_ten_seconds_and_speaks_at_24_khz(self):
        self.assertEqual(PocketTTSProvider.reference_seconds, 10.0)
        self.assertEqual(PocketTTSProvider.stream_sample_rate, 24000)


class SynthesizeTest(PocketProviderTestCase):
    async def test_raises_type_error_for_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.synthesize(
                "Hello", _make_chatterbox_params(), self.profile_path
            )

    async def test_raises_value_error_without_a_profile(self):
        with self.assertRaises(ValueError):
            await self.provider.synthesize("Hello", _make_pocket_params(), None)

    async def test_raises_file_not_found_for_a_missing_profile(self):
        with self.assertRaises(FileNotFoundError):
            await self.provider.synthesize(
                "Hello", _make_pocket_params(), self.folder / "ghost.npy"
            )

    async def test_joins_the_frames_and_gives_the_sample_rate(self):
        self._set_model(frame_count=3)

        samples, sample_rate = await self.provider.synthesize(
            "Hello", _make_pocket_params(), self.profile_path
        )

        self.assertEqual(sample_rate, SAMPLE_RATE)
        self.assertEqual(len(samples), 3 * FRAME_SAMPLES)
        self.assertEqual(
            [samples[number * FRAME_SAMPLES] for number in range(3)], [0, 1, 2]
        )

    async def test_gives_no_samples_for_a_blank_text_without_loading_the_model(self):
        samples, sample_rate = await self.provider.synthesize(
            "   ", _make_pocket_params(), self.profile_path
        )

        self.assertEqual(len(samples), 0)
        self.assertEqual(sample_rate, SAMPLE_RATE)
        self.assertEqual(self.engines, [])

    async def test_gives_no_samples_when_the_model_makes_no_frame(self):
        self._set_model(frame_count=0)

        samples, _ = await self.provider.synthesize(
            "Hello", _make_pocket_params(), self.profile_path
        )

        self.assertEqual(len(samples), 0)

    async def test_loads_the_model_once_with_four_threads(self):
        params = _make_pocket_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, self.profile_path)

        self.assertEqual(len(self.engines), 1)
        self.assertEqual(self.engines[0].num_threads, ONNX_THREADS)
        self.assertEqual(ONNX_THREADS, 4)
        self.assertEqual(self.engines[0].model_path, Path("fake-model.onnx"))

    async def test_loads_a_profile_once_and_again_for_another_profile(self):
        params = _make_pocket_params()
        other_profile = self._save_profile("wingman", 3.0)

        await self.provider.synthesize("One", params, self.profile_path)
        self._save_profile("celeste", 2.0)  # changed on disk, same path
        await self.provider.synthesize("Two", params, self.profile_path)
        await self.provider.synthesize("Three", params, other_profile)

        voices = [call["voice"] for call in self.engines[0].stream_calls]
        self.assertEqual([float(voice[0, 0, 0]) for voice in voices], [1.0, 1.0, 3.0])

    async def test_gives_the_text_the_voice_and_four_decode_steps_to_the_model(self):
        await self.provider.synthesize(
            "Shields are up", _make_pocket_params(), self.profile_path
        )

        call = self.engines[0].stream_calls[0]
        self.assertEqual(call["text"], "Shields are up")
        self.assertEqual(call["decode_steps"], DECODE_STEPS)
        self.assertEqual(DECODE_STEPS, 4)
        self.assertEqual(call["voice"].shape, (1, 4, 8))
        self.assertEqual(float(call["voice"][0, 0, 0]), 1.0)


class SynthesizeStreamTest(PocketProviderTestCase):
    async def test_gives_four_frames_first_then_six_then_the_rest(self):
        self._set_model(frame_count=15)

        pieces = await self._read_pieces()

        self.assertEqual([len(piece) // FRAME_SAMPLES for piece in pieces], [4, 6, 5])
        self.assertEqual((FIRST_PIECE_FRAMES, NEXT_PIECE_FRAMES), (4, 6))

    async def test_gives_the_frames_in_order(self):
        self._set_model(frame_count=5)

        pieces = await self._read_pieces()

        self.assertEqual(
            [
                float(piece[number * FRAME_SAMPLES])
                for piece in pieces
                for number in range(len(piece) // FRAME_SAMPLES)
            ],
            [0.0, 1.0, 2.0, 3.0, 4.0],
        )

    async def test_raises_errors_about_params_and_profile_before_the_first_piece(self):
        for params, profile_path, error in (
            (_make_chatterbox_params(), self.profile_path, TypeError),
            (_make_pocket_params(), None, ValueError),
            (_make_pocket_params(), self.folder / "ghost.npy", FileNotFoundError),
        ):
            with self.subTest(error=error.__name__):
                with self.assertRaises(error):
                    async for _ in self.provider.synthesize_stream(
                        "Hello", params, profile_path
                    ):
                        self.fail("no piece may come before the error")

    async def test_gives_no_pieces_for_a_blank_text_without_loading_the_model(self):
        pieces = await self._read_pieces("  \n ")

        self.assertEqual(pieces, [])
        self.assertEqual(self.engines, [])

    async def test_gives_no_pieces_when_the_model_makes_no_frame(self):
        self._set_model(frame_count=0)

        self.assertEqual(await self._read_pieces(), [])

    async def test_makes_frames_only_as_the_caller_reads_them(self):
        self._set_model(frame_count=30)
        pieces = self.provider.synthesize_stream(
            "Hello", _make_pocket_params(), self.profile_path
        )

        await anext(pieces)

        self.assertEqual(self.engines[0].frames_made, FIRST_PIECE_FRAMES)
        await pieces.aclose()

    async def test_gives_the_text_the_voice_and_four_decode_steps_to_the_model(self):
        await self._read_pieces("Shields are up")

        call = self.engines[0].stream_calls[0]
        self.assertEqual(call["text"], "Shields are up")
        self.assertEqual(call["decode_steps"], DECODE_STEPS)
        self.assertEqual(float(call["voice"][0, 0, 0]), 1.0)

    async def test_loads_the_model_once_for_two_speeches(self):
        await self._read_pieces("One")
        await self._read_pieces("Two")

        self.assertEqual(len(self.engines), 1)


class SpeedVerdictTest(PocketProviderTestCase):
    """The provider decides from what the model made, whether the pieces can
    be played as they come. 30 frames are 2.4 s of speech."""

    async def _speak_at(self, times_faster_than_played: float, frames=30):
        self._set_model(
            frame_count=frames,
            seconds_per_frame=ONE_FRAME_SECONDS / times_faster_than_played,
        )
        await self._read_pieces()

    async def test_is_true_before_any_speech(self):
        self.assertTrue(self.provider.can_stream(_make_pocket_params()))

    async def test_a_slow_speech_makes_can_stream_false(self):
        await self._speak_at(1.0)

        self.assertTrue(self.provider.is_too_slow)
        self.assertFalse(self.provider.can_stream(_make_pocket_params()))

    async def test_a_fast_speech_keeps_can_stream_true(self):
        await self._speak_at(4.0)

        self.assertFalse(self.provider.is_too_slow)
        self.assertTrue(self.provider.can_stream(_make_pocket_params()))

    async def test_a_speech_just_under_the_required_speed_is_too_slow(self):
        await self._speak_at(1.25)

        self.assertTrue(self.provider.is_too_slow)

    async def test_a_speech_just_over_the_required_speed_is_fine(self):
        await self._speak_at(1.35)

        self.assertFalse(self.provider.is_too_slow)

    async def test_a_short_speech_gives_no_verdict(self):
        await self._speak_at(0.5, frames=20)  # 1.6 s, slow but too short to judge

        self.assertFalse(self.provider.is_too_slow)

    async def test_a_speech_of_exactly_two_seconds_is_judged(self):
        await self._speak_at(0.5, frames=25)  # 25 frames are 2.0 s

        self.assertTrue(self.provider.is_too_slow)

    async def test_a_later_fast_speech_takes_the_verdict_back(self):
        await self._speak_at(1.0)
        await self._speak_at(4.0)

        self.assertFalse(self.provider.is_too_slow)

    async def test_counts_only_the_time_inside_the_model(self):
        self._set_model(frame_count=30, seconds_per_frame=ONE_FRAME_SECONDS / 4)

        async for _ in self.provider.synthesize_stream(
            "Hello", _make_pocket_params(), self.profile_path
        ):
            self.clock.now += 5.0  # the caller is slow, the model is not

        self.assertFalse(self.provider.is_too_slow)

    async def test_a_caller_that_stops_early_gets_no_verdict(self):
        self._set_model(frame_count=30, seconds_per_frame=ONE_FRAME_SECONDS)
        pieces = self.provider.synthesize_stream(
            "Hello", _make_pocket_params(), self.profile_path
        )

        await anext(pieces)
        await pieces.aclose()

        self.assertFalse(self.provider.is_too_slow)

    async def test_can_stream_raises_type_error_for_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            self.provider.can_stream(_make_chatterbox_params())


class CreateVoiceProfileTest(PocketProviderTestCase):
    def _write_clip(self, name="clip.wav", sample_rate=16000, channels=1):
        path = self.folder / name
        samples = np.full((sample_rate, channels), 0.5, dtype=np.float32)
        if channels == 2:
            samples[:, 1] = 0.1
        sf.write(path, samples, sample_rate, subtype="FLOAT")
        return path

    async def test_raises_type_error_for_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.create_voice_profile(
                str(self._write_clip()),
                self.folder / "new.npy",
                _make_chatterbox_params(),
            )

        self.assertEqual(self.engines, [])

    async def test_saves_the_voice_as_float16_npy(self):
        new_profile = self.folder / "new.npy"

        await self.provider.create_voice_profile(
            str(self._write_clip()), new_profile, _make_pocket_params()
        )

        saved = np.load(new_profile, allow_pickle=False)
        self.assertEqual(saved.dtype, np.float16)
        self.assertEqual(saved.shape, (1, 4, 8))
        np.testing.assert_allclose(saved, 0.5)

    async def test_gives_the_clip_to_the_model_with_its_sample_rate(self):
        await self.provider.create_voice_profile(
            str(self._write_clip(sample_rate=16000)),
            self.folder / "new.npy",
            _make_pocket_params(),
        )

        samples, sample_rate = self.engines[0].clone_calls[0]
        self.assertEqual(sample_rate, 16000)
        self.assertEqual(len(samples), 16000)

    async def test_mixes_a_stereo_clip_down_to_mono(self):
        await self.provider.create_voice_profile(
            str(self._write_clip(channels=2)),
            self.folder / "new.npy",
            _make_pocket_params(),
        )

        samples, _ = self.engines[0].clone_calls[0]
        self.assertEqual(samples.ndim, 1)
        np.testing.assert_allclose(samples, 0.3, atol=1e-6)

    async def test_makes_the_next_speech_read_the_profile_file_again(self):
        params = _make_pocket_params()
        await self.provider.synthesize("One", params, self.profile_path)
        self.engines[0].clone_result = np.full((1, 4, 8), 7.0, dtype=np.float32)

        await self.provider.create_voice_profile(
            str(self._write_clip()), self.profile_path, params
        )
        await self.provider.synthesize("Two", params, self.profile_path)

        voices = [call["voice"] for call in self.engines[0].stream_calls]
        self.assertEqual([float(voice[0, 0, 0]) for voice in voices], [1.0, 7.0])

    async def test_loads_the_model_once_for_the_profile_and_the_speech(self):
        params = _make_pocket_params()

        await self.provider.create_voice_profile(
            str(self._write_clip()), self.folder / "new.npy", params
        )
        await self.provider.synthesize("Hello", params, self.profile_path)

        self.assertEqual(len(self.engines), 1)


class ValidateParamsTest(unittest.TestCase):
    def test_reports_an_empty_profile(self):
        issue = PocketTTSProvider().validate_params(_make_pocket_params(profile=""))

        self.assertIsNotNone(issue)
        self.assertEqual((issue.section, issue.field), ("tts", "profile"))

    def test_accepts_a_set_profile(self):
        self.assertIsNone(PocketTTSProvider().validate_params(_make_pocket_params()))

    def test_raises_type_error_for_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            PocketTTSProvider().validate_params(_make_chatterbox_params())

    def test_pocket_tts_always_runs_on_the_cpu(self):
        self.assertEqual(PocketTTSProvider().get_available_device(), "cpu")


if __name__ == "__main__":
    unittest.main()
