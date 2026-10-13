import itertools
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import torch
import transformers.generation.logits_process  # noqa: F401

# torch and transformers are kept in sys.modules while chatterbox is faked: the
# faking restores sys.modules and so forgets what was imported meanwhile, and
# the Rust part of safetensors (a dependency of transformers) cannot be loaded
# twice in one process (on Linux with Python 3.12 the second import fails).

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    EdgeParamsModel,
)
from edceleste.services.tts_providers import chatterbox_tts_provider
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_providers.tts_provider_protocol import (
    StreamingTTSProviderProtocol,
)

PROFILE_NAME = "celeste"


def _make_chatterbox_params(
    profile: str = PROFILE_NAME,
    device: str = "cpu",
    nano: bool = True,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
) -> ChatterboxParamsModel:
    return ChatterboxParamsModel(
        type="chatterbox",
        profile=profile,
        device=device,
        nano=nano,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )


def _make_edge_params() -> EdgeParamsModel:
    return EdgeParamsModel(type="edge", voice="en-US-AriaNeural")


def _make_model_mock(generated_samples: np.ndarray) -> Mock:
    generated_waveform = Mock()
    generated_waveform.squeeze.return_value.cpu.return_value.numpy.return_value = (
        generated_samples
    )

    model = Mock()
    model.sr = 24000
    model.device = "cpu"
    model.generate.return_value = generated_waveform

    return model


def _install_fake_chatterbox_module(test_case: unittest.TestCase) -> Mock:
    # The real chatterbox package is heavy, so it is replaced by a stub that
    # only records how the model and the voice profile were asked to be built.
    fake_tts_turbo_module = Mock()

    modules_patcher = patch.dict(
        sys.modules,
        {
            "chatterbox": Mock(),
            "chatterbox.tts_turbo": fake_tts_turbo_module,
        },
    )
    modules_patcher.start()
    test_case.addCleanup(modules_patcher.stop)

    return fake_tts_turbo_module


class ChatterboxTTSProviderSynthesizeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        self.from_pretrained = (
            self.fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained
        )
        self.conditionals_load = self.fake_tts_turbo_module.Conditionals.load

        self.generated_samples = np.array([0.1, 0.2, 0.3])
        self.model = _make_model_mock(self.generated_samples)
        self.from_pretrained.return_value = self.model

        self.profiles_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.profiles_directory.cleanup)
        self.profile_path = self._make_profile_file("celeste.pt")

        self.provider = ChatterboxTTSProvider()

    def _make_profile_file(self, file_name: str) -> Path:
        profile_path = Path(self.profiles_directory.name) / file_name
        profile_path.touch()
        return profile_path

    async def test_synthesize_returns_generated_samples_and_model_sample_rate(self):
        samples, sample_rate = await self.provider.synthesize(
            "Hello Commander", _make_chatterbox_params(), self.profile_path
        )

        np.testing.assert_allclose(samples, self.generated_samples)
        self.assertEqual(sample_rate, 24000)

    async def test_synthesize_passes_exaggeration_and_cfg_weight_to_the_model(self):
        params = _make_chatterbox_params(exaggeration=0.8, cfg_weight=0.3)

        await self.provider.synthesize("Hello Commander", params, self.profile_path)

        self.model.generate.assert_called_once_with(
            text="Hello Commander",
            norm_loudness=False,
            exaggeration=0.8,
            cfg_weight=0.3,
        )

    async def test_synthesize_loads_the_model_once_for_the_same_params(self):
        params = _make_chatterbox_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, self.profile_path)

        self.from_pretrained.assert_called_once_with(device="cpu", nano=True)

    async def test_synthesize_loads_the_model_again_when_device_changes(self):
        await self.provider.synthesize(
            "One", _make_chatterbox_params(device="cpu"), self.profile_path
        )
        await self.provider.synthesize(
            "Two", _make_chatterbox_params(device="cuda"), self.profile_path
        )

        self.assertEqual(self.from_pretrained.call_count, 2)
        self.from_pretrained.assert_called_with(device="cuda", nano=True)

    async def test_synthesize_loads_the_model_again_when_nano_changes(self):
        await self.provider.synthesize(
            "One", _make_chatterbox_params(nano=True), self.profile_path
        )
        await self.provider.synthesize(
            "Two", _make_chatterbox_params(nano=False), self.profile_path
        )

        self.assertEqual(self.from_pretrained.call_count, 2)
        self.from_pretrained.assert_called_with(device="cpu", nano=False)

    async def test_synthesize_turns_auto_device_into_the_available_one(self):
        with patch("torch.cuda.is_available", return_value=True):
            await self.provider.synthesize(
                "One", _make_chatterbox_params(device="auto"), self.profile_path
            )

        self.from_pretrained.assert_called_once_with(device="cuda", nano=True)

    async def test_synthesize_loads_the_profile_into_the_model(self):
        loaded_conditionals = Mock()
        self.conditionals_load.return_value = loaded_conditionals

        await self.provider.synthesize(
            "Hello", _make_chatterbox_params(), self.profile_path
        )

        self.conditionals_load.assert_called_once_with(self.profile_path, "cpu")
        self.assertIs(self.model.conds, loaded_conditionals)
        self.assertEqual(self.provider.loaded_profile_path, self.profile_path)

    async def test_synthesize_skips_loading_the_same_profile_again(self):
        params = _make_chatterbox_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, self.profile_path)

        self.conditionals_load.assert_called_once()

    async def test_synthesize_loads_the_profile_again_when_it_differs(self):
        other_profile_path = self._make_profile_file("other.pt")
        params = _make_chatterbox_params()

        await self.provider.synthesize("One", params, self.profile_path)
        await self.provider.synthesize("Two", params, other_profile_path)

        self.assertEqual(self.conditionals_load.call_count, 2)
        self.conditionals_load.assert_called_with(other_profile_path, "cpu")
        self.assertEqual(self.provider.loaded_profile_path, other_profile_path)

    async def test_synthesize_loads_the_profile_again_after_the_model_is_reloaded(
        self,
    ):
        await self.provider.synthesize(
            "One", _make_chatterbox_params(device="cpu"), self.profile_path
        )
        await self.provider.synthesize(
            "Two", _make_chatterbox_params(device="cuda"), self.profile_path
        )

        self.assertEqual(self.conditionals_load.call_count, 2)

    async def test_synthesize_raises_when_the_profile_file_does_not_exist(self):
        missing_profile_path = Path(self.profiles_directory.name) / "missing.pt"

        with self.assertRaises(FileNotFoundError):
            await self.provider.synthesize(
                "Hello", _make_chatterbox_params(), missing_profile_path
            )

        self.model.generate.assert_not_called()
        self.assertIsNone(self.provider.loaded_profile_path)

    async def test_synthesize_raises_when_profile_path_is_none(self):
        with self.assertRaises(ValueError):
            await self.provider.synthesize("Hello", _make_chatterbox_params(), None)

        self.from_pretrained.assert_not_called()

    async def test_synthesize_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.synthesize(
                "Hello", _make_edge_params(), self.profile_path
            )

        self.from_pretrained.assert_not_called()


class ChatterboxTTSProviderCreateVoiceProfileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        self.from_pretrained = (
            self.fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained
        )

        self.model = _make_model_mock(np.array([0.1]))
        self.from_pretrained.return_value = self.model

        self.provider = ChatterboxTTSProvider()
        self.profile_path = Path("voices") / "celeste.pt"

    async def test_create_voice_profile_prepares_conditionals_from_the_reference(self):
        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.model.prepare_conditionals.assert_called_once_with(
            wav_fpath="reference.wav", norm_loudness=False
        )

    async def test_create_voice_profile_saves_conditionals_to_the_profile_path(self):
        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.model.conds.save.assert_called_once_with(self.profile_path)

    async def test_create_voice_profile_clears_the_loaded_profile_path(self):
        self.provider.loaded_profile_path = Path("voices") / "old.pt"

        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.assertIsNone(self.provider.loaded_profile_path)

    def _pretend_the_model_is_loaded(self):
        """Same device and nano as _make_chatterbox_params(), so
        create_voice_profile() does not load the model again. Loading would
        clear loaded_profile_path on its own and hide what is tested."""
        self.provider.model = self.model
        self.provider.loaded_device = "cpu"
        self.provider.loaded_nano = True

    async def test_create_voice_profile_clears_loaded_profile_path_before_learning(
        self,
    ):
        self._pretend_the_model_is_loaded()
        self.provider.loaded_profile_path = Path("voices") / "old.pt"
        loaded_profile_path_while_learning = []

        def remember_loaded_profile_path(**kwargs):
            loaded_profile_path_while_learning.append(self.provider.loaded_profile_path)

        self.model.prepare_conditionals.side_effect = remember_loaded_profile_path

        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params()
        )

        self.from_pretrained.assert_not_called()
        self.assertEqual(loaded_profile_path_while_learning, [None])

    async def test_create_voice_profile_clears_loaded_profile_path_when_learning_fails(
        self,
    ):
        self._pretend_the_model_is_loaded()
        self.provider.loaded_profile_path = Path("voices") / "old.pt"
        self.model.prepare_conditionals.side_effect = RuntimeError("bad audio")

        with self.assertRaises(RuntimeError):
            await self.provider.create_voice_profile(
                "reference.wav", self.profile_path, _make_chatterbox_params()
            )

        self.assertIsNone(self.provider.loaded_profile_path)
        self.model.conds.save.assert_not_called()

    async def test_create_voice_profile_loads_the_model_with_the_given_params(self):
        await self.provider.create_voice_profile(
            "reference.wav", self.profile_path, _make_chatterbox_params(nano=False)
        )

        self.from_pretrained.assert_called_once_with(device="cpu", nano=False)

    async def test_create_voice_profile_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            await self.provider.create_voice_profile(
                "reference.wav", self.profile_path, _make_edge_params()
            )

        self.model.prepare_conditionals.assert_not_called()


class ChatterboxTTSProviderValidateParamsTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider()

    def test_validate_params_reports_issue_when_profile_is_empty(self):
        issue = self.provider.validate_params(_make_chatterbox_params(profile=""))

        self.assertIsNotNone(issue)
        self.assertEqual(issue.section, "tts")
        self.assertEqual(issue.field, "profile")

    def test_validate_params_returns_none_when_profile_is_set(self):
        issue = self.provider.validate_params(_make_chatterbox_params())

        self.assertIsNone(issue)

    def test_validate_params_rejects_params_of_another_provider(self):
        with self.assertRaises(TypeError):
            self.provider.validate_params(_make_edge_params())


class ChatterboxTTSProviderAvailableDeviceTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider()

    def test_get_available_device_returns_cuda_when_a_gpu_is_visible(self):
        with patch("torch.cuda.is_available", return_value=True):
            self.assertEqual(self.provider.get_available_device(), "cuda")

    def test_get_available_device_returns_cpu_without_a_gpu(self):
        with patch("torch.cuda.is_available", return_value=False):
            self.assertEqual(self.provider.get_available_device(), "cpu")

    def test_provider_starts_without_a_loaded_model(self):
        self.assertIsNone(self.provider.model)
        self.assertIsNone(self.provider.loaded_profile_path)


def _mangled(name: str) -> str:
    """The streaming steps of the provider are private (double underscore), so the
    tests reach them by the name Python gives them."""
    return f"_ChatterboxTTSProvider__{name}"


class ChatterboxTTSProviderCanStreamTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider()

    def test_can_stream_is_true_for_the_cuda_device_even_without_a_gpu_here(self):
        params = _make_chatterbox_params(device="cuda")

        with patch("torch.cuda.is_available", return_value=False):
            self.assertTrue(self.provider.can_stream(params))

    def test_can_stream_is_false_for_the_cpu_device_even_with_a_gpu_here(self):
        params = _make_chatterbox_params(device="cpu")

        with patch("torch.cuda.is_available", return_value=True):
            self.assertFalse(self.provider.can_stream(params))

    def test_can_stream_turns_auto_into_the_available_device(self):
        params = _make_chatterbox_params(device="auto")

        with patch("torch.cuda.is_available", return_value=True):
            self.assertTrue(self.provider.can_stream(params))
        with patch("torch.cuda.is_available", return_value=False):
            self.assertFalse(self.provider.can_stream(params))

    def test_can_stream_rejects_params_of_another_provider(self):
        params = _make_edge_params()

        with self.assertRaises(TypeError) as raised:
            self.provider.can_stream(params)

        self.assertEqual(
            str(raised.exception),
            f"Chatterbox needs ChatterboxParamsModel, got {type(params)}",
        )


class ChatterboxTTSProviderStreamingProtocolTest(unittest.TestCase):
    def test_chatterbox_counts_as_a_streaming_provider(self):
        self.assertIsInstance(ChatterboxTTSProvider(), StreamingTTSProviderProtocol)

    def test_edge_does_not_count_as_a_streaming_provider(self):
        self.assertNotIsInstance(EdgeTTSProvider(), StreamingTTSProviderProtocol)


class ChatterboxTTSProviderSynthesizeStreamTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake_tts_turbo_module = _install_fake_chatterbox_module(self)
        self.from_pretrained = (
            self.fake_tts_turbo_module.ChatterboxTurboTTS.from_pretrained
        )
        self.conditionals_load = self.fake_tts_turbo_module.Conditionals.load

        self.model = _make_model_mock(np.zeros(3))
        self.from_pretrained.return_value = self.model

        self.profiles_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.profiles_directory.cleanup)
        self.profile_path = Path(self.profiles_directory.name) / "celeste.pt"
        self.profile_path.touch()

        self.provider = ChatterboxTTSProvider()
        # The model is not run here: the step that makes the pieces is replaced
        self.make_audio_pieces = Mock(return_value=iter([]))
        make_audio_pieces_patch = patch.object(
            self.provider, _mangled("make_audio_pieces"), self.make_audio_pieces
        )
        make_audio_pieces_patch.start()
        self.addCleanup(make_audio_pieces_patch.stop)

    async def _collect_pieces(self, params=None, profile_path=None) -> list:
        return [
            piece
            async for piece in self.provider.synthesize_stream(
                "Hello",
                params or _make_chatterbox_params(),
                profile_path or self.profile_path,
            )
        ]

    async def test_synthesize_stream_gives_every_piece_in_order(self):
        pieces = [
            np.full(3, 0.1, dtype=np.float32),
            np.full(4, 0.2, dtype=np.float32),
            np.full(5, 0.3, dtype=np.float32),
        ]
        self.make_audio_pieces.return_value = iter(pieces)

        collected = await self._collect_pieces()

        self.assertEqual(len(collected), 3)
        for collected_piece, expected_piece in zip(collected, pieces):
            np.testing.assert_array_equal(collected_piece, expected_piece)

    async def test_synthesize_stream_gives_a_piece_before_the_next_one_is_made(self):
        log: list[str] = []

        def make_pieces(model, text):
            for number in (1, 2):
                log.append(f"made {number}")
                yield np.full(2, number, dtype=np.float32)

        self.make_audio_pieces.side_effect = make_pieces

        async for _ in self.provider.synthesize_stream(
            "Hello", _make_chatterbox_params(), self.profile_path
        ):
            log.append("got")

        self.assertEqual(log, ["made 1", "got", "made 2", "got"])

    async def test_synthesize_stream_loads_the_model_and_the_profile_first(self):
        state_when_pieces_were_asked: dict = {}

        def make_pieces(model, text):
            state_when_pieces_were_asked["model_loaded"] = self.from_pretrained.called
            state_when_pieces_were_asked["profile_loaded"] = (
                self.conditionals_load.called
            )
            state_when_pieces_were_asked["asked_with"] = (model, text)
            return iter([])

        self.make_audio_pieces.side_effect = make_pieces

        await self._collect_pieces()

        self.assertEqual(
            state_when_pieces_were_asked,
            {
                "model_loaded": True,
                "profile_loaded": True,
                "asked_with": (self.model, "Hello"),
            },
        )
        self.from_pretrained.assert_called_once_with(device="cpu", nano=True)
        self.conditionals_load.assert_called_once_with(self.profile_path, "cpu")

    async def test_synthesize_stream_raises_when_profile_path_is_none(self):
        with self.assertRaises(ValueError) as raised:
            async for _ in self.provider.synthesize_stream(
                "Hello", _make_chatterbox_params(), None
            ):
                pass

        self.assertEqual(str(raised.exception), "Chatterbox needs a voice profile.")

        self.from_pretrained.assert_not_called()
        self.make_audio_pieces.assert_not_called()

    async def test_synthesize_stream_rejects_params_of_another_provider(self):
        params = _make_edge_params()

        with self.assertRaises(TypeError) as raised:
            async for _ in self.provider.synthesize_stream(
                "Hello", params, self.profile_path
            ):
                pass

        self.assertEqual(
            str(raised.exception),
            f"Chatterbox needs ChatterboxParamsModel, got {type(params)}",
        )

        self.from_pretrained.assert_not_called()
        self.make_audio_pieces.assert_not_called()

    async def test_synthesize_stream_raises_when_the_profile_file_does_not_exist(
        self,
    ):
        missing_profile_path = Path(self.profiles_directory.name) / "missing.pt"

        with self.assertRaises(FileNotFoundError):
            await self._collect_pieces(profile_path=missing_profile_path)

        self.make_audio_pieces.assert_not_called()


class ChatterboxTTSProviderGroupTokensTest(unittest.TestCase):
    def setUp(self):
        self.provider = ChatterboxTTSProvider()

    def _group(self, token_count: int) -> list[tuple[list[int], bool]]:
        """Every piece of a text that makes token_count speech tokens, as
        (all tokens so far, is it the last piece). The tokens are copied at once,
        because the provider hands out the same list again, grown."""
        tokens = list(range(token_count))
        model = Mock()
        make_tokens = Mock(side_effect=lambda model, text: iter(tokens))
        group_tokens = getattr(
            self.provider, _mangled("give_tokens_so_far_for_each_piece")
        )
        with patch.object(self.provider, _mangled("make_speech_tokens"), make_tokens):
            pieces = [
                (list(piece_tokens), is_last_piece)
                for piece_tokens, is_last_piece in group_tokens(model, "Hello")
            ]
        make_tokens.assert_called_once_with(model, "Hello")
        return pieces

    def test_first_piece_comes_after_the_first_twelve_tokens(self):
        pieces = self._group(30)

        self.assertEqual(pieces[0], (list(range(12)), False))

    def test_next_pieces_come_every_twenty_five_tokens_and_hold_all_tokens_so_far(
        self,
    ):
        pieces = self._group(60)

        self.assertEqual(
            [(len(tokens), is_last) for tokens, is_last in pieces],
            [(12, False), (37, False), (60, True)],
        )
        self.assertEqual(pieces[1][0], list(range(37)))

    def test_the_last_piece_has_the_finished_flag_and_all_the_tokens(self):
        pieces = self._group(20)

        self.assertEqual(pieces, [(list(range(12)), False), (list(range(20)), True)])

    def test_last_piece_still_comes_when_the_tokens_end_on_a_border(self):
        pieces = self._group(12)

        self.assertEqual(pieces, [(list(range(12)), False), (list(range(12)), True)])

    def test_no_tokens_give_no_pieces(self):
        self.assertEqual(self._group(0), [])


class ChatterboxTTSProviderMelFramesTest(unittest.TestCase):
    SILENCE_TOKEN = 4299

    def setUp(self):
        self.s3token2mel = Mock()
        self.s3token2mel.forward.return_value = torch.zeros(1, 80, 40)
        modules_patcher = patch.dict(
            sys.modules,
            {
                "chatterbox.models.s3gen.const": SimpleNamespace(
                    S3GEN_SIL=self.SILENCE_TOKEN
                ),
                "chatterbox.models.s3gen.s3gen": SimpleNamespace(
                    S3Token2Mel=self.s3token2mel
                ),
            },
        )
        modules_patcher.start()
        self.addCleanup(modules_patcher.stop)

        self.provider = ChatterboxTTSProvider()
        self.model = Mock()
        self.model.device = "cpu"
        self.noise = torch.arange(200.0).expand(1, 80, 200)

    def _make_mel_frames(self, speech_tokens: list[int], is_last_piece: bool):
        make_mel_frames = getattr(self.provider, _mangled("make_mel_frames"))
        return make_mel_frames(self.model, speech_tokens, is_last_piece, self.noise)

    def _tokens_given_to_s3gen(self) -> list[int]:
        return self.s3token2mel.forward.call_args.args[1].tolist()

    def test_mel_frames_leave_out_tokens_that_are_not_sounds(self):
        self._make_mel_frames([1, 2, 6561, 7000, 3], is_last_piece=False)

        self.assertEqual(self._tokens_given_to_s3gen(), [1, 2, 3])

    def test_mel_frames_of_the_last_piece_get_silence_and_all_the_frames(self):
        mel_frames = self._make_mel_frames([1, 2, 3], is_last_piece=True)

        self.assertEqual(
            self._tokens_given_to_s3gen(), [1, 2, 3] + [self.SILENCE_TOKEN] * 3
        )
        self.assertEqual(mel_frames.shape, (1, 80, 40))

    def test_mel_frames_of_other_pieces_drop_the_six_unsure_frames(self):
        mel_frames = self._make_mel_frames([1, 2, 3], is_last_piece=False)

        self.assertEqual(self._tokens_given_to_s3gen(), [1, 2, 3])
        self.assertEqual(mel_frames.shape, (1, 80, 34))

    def test_mel_frames_run_s3gen_with_the_voice_and_the_noise_that_fits(self):
        self._make_mel_frames([1, 2, 3], is_last_piece=False)
        not_last_call = self.s3token2mel.forward.call_args
        self._make_mel_frames([1, 2, 3], is_last_piece=True)
        last_call = self.s3token2mel.forward.call_args

        for call in (not_last_call, last_call):
            self.assertIs(call.args[0], self.model.s3gen)
            self.assertIs(call.kwargs["ref_dict"], self.model.conds.gen)
            self.assertEqual(call.kwargs["n_cfm_timesteps"], 2)
            self.assertIs(call.kwargs["finalize"], True)
        # Two mel frames for every sound token, the last piece has 3 more tokens
        self.assertTrue(
            torch.equal(not_last_call.kwargs["noised_mels"], self.noise[:, :, :6])
        )
        self.assertTrue(
            torch.equal(last_call.kwargs["noised_mels"], self.noise[:, :, :12])
        )


class ChatterboxTTSProviderMakeAudioPiecesTest(unittest.TestCase):
    SAMPLES_PER_FRAME = 480

    def setUp(self):
        self.provider = ChatterboxTTSProvider()
        self.audio_values = itertools.repeat(1.0)

        self.model = Mock()
        self.model.device = "cpu"
        self.model.sr = 24000
        self.model.s3gen.dtype = torch.float32
        self.model.s3gen.trim_fade = torch.ones(10)
        self.model.s3gen.hift_inference.side_effect = self._make_audio
        self.watermark = self.model.watermarker.apply_watermark
        self.watermark.side_effect = lambda audio, sample_rate: audio

    def _make_audio(self, mel_frames, cache):
        """The vocoder: 480 samples for every mel frame, all of one value, so a
        test can follow every sample."""
        value = next(self.audio_values)
        samples = mel_frames.shape[2] * self.SAMPLES_PER_FRAME
        return torch.full((1, samples), value), None

    def _speak(self, frames_of_each_piece: list[int]) -> list[np.ndarray]:
        """Runs the real __make_audio_pieces. Only the steps before it are faked:
        piece number n has frames_of_each_piece[n] mel frames, and the last of
        them is the last piece."""
        last_index = len(frames_of_each_piece) - 1
        token_groups = [
            ([1, 2, 3], index == last_index) for index in range(last_index + 1)
        ]
        mel_frames = [torch.zeros(1, 80, frames) for frames in frames_of_each_piece]
        with (
            patch.object(
                self.provider,
                _mangled("give_tokens_so_far_for_each_piece"),
                return_value=iter(token_groups),
            ),
            patch.object(
                self.provider, _mangled("make_mel_frames"), side_effect=mel_frames
            ),
        ):
            make_audio_pieces = getattr(self.provider, _mangled("make_audio_pieces"))
            return list(make_audio_pieces(self.model, "Hello"))

    def test_pieces_together_hold_every_frame_exactly_once(self):
        pieces = self._speak([20, 40])

        # The first piece keeps its last frame back for the crossfade (19 frames),
        # the second starts 4 frames early for the vocoder and throws them away
        self.assertEqual(
            [len(piece) for piece in pieces],
            [19 * self.SAMPLES_PER_FRAME, 21 * self.SAMPLES_PER_FRAME],
        )

    def test_the_vocoder_starts_four_frames_early_to_be_warm(self):
        self._speak([20, 40])

        frames_given_to_the_vocoder = [
            call.args[0].shape[2]
            for call in self.model.s3gen.hift_inference.call_args_list
        ]
        # The first piece has nothing before it. The second one starts 4 frames
        # before the 19 frames that were played, so 40 - 15 frames
        self.assertEqual(frames_given_to_the_vocoder, [20, 25])

    def test_the_first_piece_fades_in_with_the_trim_fade(self):
        self.model.s3gen.trim_fade = torch.zeros(10)

        pieces = self._speak([20, 40])

        np.testing.assert_array_equal(pieces[0][:10], np.zeros(10))
        self.assertEqual(pieces[0][10], 1.0)

    def test_the_start_of_the_next_piece_is_crossfaded_with_the_held_back_frame(
        self,
    ):
        self.audio_values = iter([1.0, 0.0])  # first piece loud, second silent

        pieces = self._speak([20, 40])

        crossfade = pieces[1][: self.SAMPLES_PER_FRAME]
        self.assertEqual(crossfade[0], 1.0)  # still the end of the first piece
        self.assertAlmostEqual(float(crossfade[-1]), 0.0, places=5)
        self.assertTrue(np.all(np.diff(crossfade) < 0))
        np.testing.assert_array_equal(
            pieces[1][self.SAMPLES_PER_FRAME :],
            np.zeros(len(pieces[1]) - self.SAMPLES_PER_FRAME),
        )

    def test_every_piece_goes_through_the_watermarker(self):
        self.watermark.side_effect = lambda audio, sample_rate: audio * 0.5

        pieces = self._speak([20, 40])

        self.assertEqual(self.watermark.call_count, 2)
        for call in self.watermark.call_args_list:
            self.assertEqual(call.kwargs["sample_rate"], 24000)
        self.assertEqual(
            [len(call.args[0]) for call in self.watermark.call_args_list],
            [19 * self.SAMPLES_PER_FRAME, 21 * self.SAMPLES_PER_FRAME],
        )
        self.assertEqual(pieces[0][50], 0.5)

    def test_pieces_are_float32_numpy_arrays(self):
        self.watermark.side_effect = lambda audio, sample_rate: audio.astype(np.float64)

        pieces = self._speak([20, 40])

        for piece in pieces:
            self.assertIsInstance(piece, np.ndarray)
            self.assertEqual(piece.dtype, np.float32)


class _FakeTransformerOutput:
    """What the transformer of T3 gives: the hidden states at index 0 and the
    cache of keys and values."""

    def __init__(self, hidden_states, past_key_values):
        self.hidden_states = hidden_states
        self.past_key_values = past_key_values

    def __getitem__(self, index):
        return (self.hidden_states,)[index]


class ChatterboxTTSProviderSpeechTokensTest(unittest.TestCase):
    VOCABULARY_SIZE = 200
    STOP_TOKEN = 101

    def setUp(self):
        modules_patcher = patch.dict(
            sys.modules,
            {
                "chatterbox": Mock(),
                "chatterbox.tts_turbo": SimpleNamespace(punc_norm=lambda text: text),
            },
        )
        modules_patcher.start()
        self.addCleanup(modules_patcher.stop)

        self.provider = ChatterboxTTSProvider()
        self.script = iter([])  # the token T3 wants to say next, one for every call
        self.tokens_given_back = []
        self.pasts_given_back = []
        self.transformer_runs = 0

        self.model = Mock()
        self.model.device = "cpu"
        self.model.tokenizer.side_effect = lambda text, return_tensors: SimpleNamespace(
            input_ids=torch.tensor([[11, 12, 13]])
        )
        t3 = self.model.t3
        t3.hp.start_speech_token = 100
        t3.hp.stop_speech_token = self.STOP_TOKEN
        t3.prepare_input_embeds.return_value = (torch.zeros(1, 4, 8), None)
        t3.tfmr.side_effect = self._run_transformer
        t3.speech_head.side_effect = self._choose_next_token
        t3.speech_emb.side_effect = self._embed_token

    def _run_transformer(self, inputs_embeds, use_cache=True, past_key_values=None):
        if past_key_values is not None:
            self.pasts_given_back.append(past_key_values)
        past = f"past-{self.transformer_runs}"
        self.transformer_runs += 1
        return _FakeTransformerOutput(torch.zeros(1, inputs_embeds.shape[1], 8), past)

    def _choose_next_token(self, hidden_states):
        """Logits that make the sampling pick the next token of the script, always."""
        logits = torch.zeros(1, hidden_states.shape[1], self.VOCABULARY_SIZE)
        logits[0, :, next(self.script)] = 10000.0
        return logits

    def _embed_token(self, token):
        self.tokens_given_back.append(int(token.item()))
        return torch.zeros(1, 1, 8)

    def _make_speech_tokens(self, script, at_most: int = 50) -> list[int]:
        self.script = iter(script)
        make_speech_tokens = getattr(self.provider, _mangled("make_speech_tokens"))
        return list(itertools.islice(make_speech_tokens(self.model, "Hello"), at_most))

    def test_speech_tokens_end_when_t3_says_stop_and_the_stop_is_not_given(self):
        with patch("torch.multinomial", wraps=torch.multinomial) as sampling:
            tokens = self._make_speech_tokens([5, 5, 5, self.STOP_TOKEN])

        self.assertEqual(tokens, [5, 5, 5])
        # Three tokens and the stop: T3 is not asked for anything after the stop
        self.assertEqual(sampling.call_count, 4)

    def test_speech_tokens_end_after_the_maximum_without_a_stop(self):
        with patch.object(chatterbox_tts_provider, "MAX_SPEECH_TOKENS", 4):
            tokens = self._make_speech_tokens(itertools.repeat(5))

        self.assertEqual(tokens, [5, 5, 5, 5])

    def test_every_token_is_fed_back_into_t3_with_the_cache_of_the_step_before(self):
        self._make_speech_tokens([5, 6, 7, self.STOP_TOKEN])

        self.assertEqual(self.tokens_given_back, [5, 6, 7])
        self.assertEqual(self.pasts_given_back, ["past-0", "past-1", "past-2"])
