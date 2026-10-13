import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import torch

from edceleste.services.models.settings_model import (
    ChatterboxParamsModel,
    SettingsIssueModel,
    TtsProviderParams,
)
from edceleste.services.tts_providers.tts_provider_protocol import (
    CloningTTSProviderProtocol,
    StreamingTTSProviderProtocol,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from chatterbox.tts_turbo import ChatterboxTurboTTS

# Speaking in pieces (issue #179). The first piece is small to start fast, the
# next ones are about one second of speech each.
FIRST_PIECE_TOKENS = 12
NEXT_PIECE_TOKENS = 25
# The same limit as the model has in generate()
MAX_SPEECH_TOKENS = 1000
# Speech tokens from this number up are not sounds (stop, start, ...)
FIRST_NOT_A_SOUND_TOKEN = 6561
# S3Gen turns every speech token into 2 mel frames, and every frame into 480
# samples (24 kHz, 50 frames per second)
FRAMES_PER_TOKEN = 2
SAMPLES_PER_FRAME = 480
# S3Gen is unsure about the last 3 tokens until the text is finished
UNSURE_FRAMES = 6
# Frames before the new ones that the vocoder looks at to start warm
CONTEXT_FRAMES = 4


class ChatterboxTTSProvider(CloningTTSProviderProtocol, StreamingTTSProviderProtocol):
    # Chatterbox learns a voice from the first 10 seconds of a clip
    reference_seconds = 10.0
    profile_file_extension = ".pt"
    # S3Gen, the part that makes the audio, always speaks at 24 kHz (model.sr)
    stream_sample_rate = 24000

    def __init__(self) -> None:
        """Only sets the state of the loaded model. The model is loaded on the
        first use, not here, because loading takes seconds and a lot of memory.
        The settings are not stored, they come with every call."""
        self.model: "ChatterboxTurboTTS | None" = None
        self.loaded_device: str | None = None
        self.loaded_nano: bool | None = None
        self.loaded_profile_path: Path | None = None

    async def synthesize(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> tuple[np.ndarray, int]:
        """Speaks the text with the voice profile in profile_path.

        1. Loads the model if needed, or again when device or nano differ from
           the loaded model. This may download it from the Hugging Face Hub the
           first time.
        2. Loads the voice profile into the model when it is not the loaded one.
        3. Generates the speech in a worker thread with the exaggeration and
           cfg_weight from params.
        Returns the samples and the sample rate, plays nothing. Raises
        TypeError for params of another provider, ValueError when
        profile_path is None and FileNotFoundError for a missing profile file.
        """
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )
        if profile_path is None:
            raise ValueError("Chatterbox needs a voice profile.")

        model = await asyncio.to_thread(self.__get_or_load_model, params)
        await asyncio.to_thread(self.__load_voice_profile_into_model, profile_path)

        output = await asyncio.to_thread(
            model.generate,
            text=text,
            norm_loudness=False,
            exaggeration=params.exaggeration,
            cfg_weight=params.cfg_weight,
        )
        return output.squeeze(0).cpu().numpy(), model.sr

    async def synthesize_stream(
        self,
        text: str,
        params: TtsProviderParams,
        profile_path: Path | None = None,
    ) -> AsyncIterator[np.ndarray]:
        """Speaks the text with the voice profile in profile_path, in pieces of
        about one second. The first piece comes after about 200 ms on a GPU, the
        rest is made while the pilot already hears it.

        1. Loads the model and the voice profile exactly as synthesize() does.
        2. Asks __make_audio_pieces for the next piece in a worker thread, so the
           event loop stays free while the GPU works.
        3. Gives each piece as it comes: mono float32 at stream_sample_rate.
        Plays nothing and adds no effects. exaggeration and cfg_weight are not
        passed to the model (synthesize() passes them to generate(), and Turbo
        and Nano ignore them there, the library only logs a warning). Read the
        pieces with `async for`, without `await`. Check can_stream() first, on a
        CPU the pieces come too late.

        Raises TypeError for params of another provider, ValueError when
        profile_path is None and FileNotFoundError for a missing profile file,
        all before the first piece. An error of the model while the speech is
        made comes out of the `async for` as it is, the pieces already given
        stay given. A caller that stops reading leaves at most the piece in
        progress to finish in its worker thread. A text with no sound gives no
        pieces.
        """
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )
        if profile_path is None:
            raise ValueError("Chatterbox needs a voice profile.")

        model = await asyncio.to_thread(self.__get_or_load_model, params)
        await asyncio.to_thread(self.__load_voice_profile_into_model, profile_path)

        pieces = self.__make_audio_pieces(model, text)
        while (piece := await asyncio.to_thread(next, pieces, None)) is not None:
            yield piece

    def can_stream(self, params: TtsProviderParams) -> bool:
        """True when the device in params is a GPU. On a CPU the model makes
        audio slower than it is played, so a piece would come late and the
        voice would stutter, and speaking the whole text at once is better.
        "auto" is turned into the device it would pick. Cheap: loads no model
        and does not look at the model that is loaded now. TTSService asks it
        before every sentence. Raises TypeError for params of another
        provider."""
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )
        return self.__pick_device(params) == "cuda"

    async def create_voice_profile(
        self,
        reference_audio_path: str,
        profile_path: Path,
        params: TtsProviderParams,
    ) -> None:
        """Lets the model learn the voice from the clip in reference_audio_path
        and saves it to the file profile_path (a .pt file, its folder must
        exist). A file already there is replaced, the caller checks the name
        first.
        1. Loads the model in a worker thread if needed (slow, may download
           it from the Hugging Face Hub the first time).
        2. Clears loaded_profile_path, because learning replaces the voice in
           the model, also when it fails or is cancelled half way. The next
           synthesize() then loads its profile from the file again.
        3. Learns the voice in a worker thread, then saves the file.

        Raises TypeError for params of another provider, before anything is
        loaded. Errors of the model (e.g. a clip it cannot read) come out as
        they are and nothing is saved. A cancel during learning also saves
        nothing, the thread only finishes the learning in the background.
        """
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )

        model = await asyncio.to_thread(self.__get_or_load_model, params)
        self.loaded_profile_path = None
        await asyncio.to_thread(
            model.prepare_conditionals,
            wav_fpath=reference_audio_path,
            norm_loudness=False,
        )
        model.conds.save(profile_path)

    def validate_params(self, params: TtsProviderParams) -> SettingsIssueModel | None:
        """Only checks that a profile name is set. Does not check that the
        profile file exists, a missing file shows up on the first sentence.
        Raises TypeError for params of another provider."""
        if not isinstance(params, ChatterboxParamsModel):
            raise TypeError(
                f"Chatterbox needs ChatterboxParamsModel, got {type(params)}"
            )

        if not params.profile:
            return SettingsIssueModel(
                section="tts",
                field="profile",
                message="Profile is not set.",
            )
        return None

    def get_available_device(self) -> Literal["cuda", "cpu"]:
        """What the "auto" device setting turns into: "cuda" when torch sees a
        GPU, otherwise "cpu"."""
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    # Without inference_mode autograd keeps every step: 14 GB on a long text
    @torch.inference_mode()
    def __make_audio_pieces(
        self, model: "ChatterboxTurboTTS", text: str
    ) -> Iterator[np.ndarray]:
        """Gives the speech of the text piece by piece, mono float32 at 24 kHz.
        Blocking: every next() runs the model until the next piece is ready.
        The voice (model.conds) must be loaded.

        generate() makes all speech tokens and only then the audio. Here the
        audio is made after every group of tokens (from
        __give_tokens_so_far_for_each_piece). S3Gen turns ALL tokens so far
        into mel frames (it needs to see the whole sequence), and the vocoder
        makes audio only from the frames that are new. So each frame is voiced
        once, and the pilot hears the start of the text while the end is still
        being made.

        The vocoder starts a few frames early, to be warm, and that audio is
        thrown away. The last frame of a piece is kept back and mixed into the
        start of the next piece (20 ms crossfade), so there is no click; the
        last piece is given whole, nothing is kept back after it. The first
        piece fades in as the audio of generate() does, and every piece gets
        the Perth watermark, as generate() puts on its audio.

        One random noise is made for the whole text and used by every piece, so
        a frame does not change from piece to piece. A text with no speech
        tokens gives no pieces. Errors of the model come out of next() as they
        are.
        """
        s3gen = model.s3gen
        # One noise for the whole text, so a frame does not change from piece to piece
        noise = torch.randn(
            1,
            80,
            FRAMES_PER_TOKEN * (MAX_SPEECH_TOKENS + 10),
            device=model.device,
            dtype=s3gen.dtype,
        )
        fade_in = torch.linspace(0, 1, SAMPLES_PER_FRAME, device=model.device)
        frames_played = 0
        held_back_frame: torch.Tensor | None = None

        for speech_tokens, is_last_piece in self.__give_tokens_so_far_for_each_piece(
            model, text
        ):
            mel_frames = self.__make_mel_frames(
                model, speech_tokens, is_last_piece, noise
            )
            first_frame_for_vocoder = max(0, frames_played - CONTEXT_FRAMES)
            audio, _ = s3gen.hift_inference(
                mel_frames[:, :, first_frame_for_vocoder:].to(s3gen.dtype), None
            )
            context_samples = (
                frames_played - first_frame_for_vocoder
            ) * SAMPLES_PER_FRAME
            audio = audio[0, context_samples:].clone()

            if frames_played == 0:
                audio[: len(s3gen.trim_fade)] *= s3gen.trim_fade
            if held_back_frame is not None:
                audio[:SAMPLES_PER_FRAME] = (
                    held_back_frame * (1 - fade_in)
                    + audio[:SAMPLES_PER_FRAME] * fade_in
                )

            if is_last_piece:
                piece = audio
                held_back_frame = None
                frames_played = mel_frames.shape[2]
            else:
                piece = audio[:-SAMPLES_PER_FRAME]
                held_back_frame = audio[-SAMPLES_PER_FRAME:]
                frames_played = mel_frames.shape[2] - 1

            watermarked_piece = model.watermarker.apply_watermark(
                piece.float().cpu().numpy(), sample_rate=model.sr
            )
            yield np.asarray(watermarked_piece, dtype=np.float32)

    def __give_tokens_so_far_for_each_piece(
        self, model: "ChatterboxTurboTTS", text: str
    ) -> Iterator[tuple[list[int], bool]]:
        """Starts T3 (through __make_speech_tokens) and, for every piece of
        audio, gives ALL speech tokens made so far and whether T3 has finished:
        after the first FIRST_PIECE_TOKENS tokens, then after every
        NEXT_PIECE_TOKENS more, and at the end. So the lists grow, they are not
        separate parts. The end comes also when the last tokens fall exactly on
        the border of a piece: the same tokens are given once more, with True.
        A text with no tokens gives nothing. It is always the same list object,
        grown: use it before asking for the next piece, copy it to keep it.
        Blocking, the work is done by T3 on the GPU."""
        speech_tokens: list[int] = []
        next_piece_at = FIRST_PIECE_TOKENS
        for speech_token in self.__make_speech_tokens(model, text):
            speech_tokens.append(speech_token)
            if len(speech_tokens) == next_piece_at:
                yield speech_tokens, False
                next_piece_at += NEXT_PIECE_TOKENS
        if speech_tokens:
            yield speech_tokens, True

    @torch.inference_mode()
    def __make_speech_tokens(
        self, model: "ChatterboxTurboTTS", text: str
    ) -> Iterator[int]:
        """Gives the speech tokens of the text one by one, as T3 makes them
        (T3 is the part of Chatterbox that turns text into speech tokens). The
        text is turned into tokens here and the voice in model.conds is used,
        so the voice must be loaded. Ends when T3 says stop (that token is not
        given) or after MAX_SPEECH_TOKENS tokens, about 40 seconds of speech: a
        longer text is cut there, with no error and no log, as in generate().
        Blocking: every next() runs the model for one token.

        The same work as T3.inference_turbo() inside generate(), the same
        sampling, only that the caller gets a token as soon as it exists."""
        from chatterbox.tts_turbo import punc_norm
        from transformers.generation.logits_process import (
            LogitsProcessorList,
            RepetitionPenaltyLogitsProcessor,
            TemperatureLogitsWarper,
            TopKLogitsWarper,
            TopPLogitsWarper,
        )

        t3 = model.t3
        # The defaults of generate(): temperature, top k, top p, repetition penalty
        sampling = LogitsProcessorList(
            [
                TemperatureLogitsWarper(0.8),
                TopKLogitsWarper(1000),
                TopPLogitsWarper(0.95),
                RepetitionPenaltyLogitsProcessor(1.2),
            ]
        )

        text_tokens = model.tokenizer(punc_norm(text), return_tensors="pt").input_ids
        text_tokens = text_tokens.to(model.device)
        start_token = t3.hp.start_speech_token * torch.ones_like(text_tokens[:, :1])
        embeds, _ = t3.prepare_input_embeds(
            t3_cond=model.conds.t3,
            text_tokens=text_tokens,
            speech_tokens=start_token,
            cfg_weight=0.0,
        )
        output = t3.tfmr(inputs_embeds=embeds, use_cache=True)
        past_key_values = output.past_key_values
        logits = t3.speech_head(output[0][:, -1:])[:, -1, :]

        tokens_so_far = start_token
        for _ in range(MAX_SPEECH_TOKENS):
            probabilities = torch.softmax(sampling(tokens_so_far, logits), dim=-1)
            token = torch.multinomial(probabilities, num_samples=1)
            speech_token = int(token.item())
            if speech_token == t3.hp.stop_speech_token:
                return
            tokens_so_far = torch.cat([tokens_so_far, token], dim=1)
            yield speech_token

            output = t3.tfmr(
                inputs_embeds=t3.speech_emb(token),
                past_key_values=past_key_values,
                use_cache=True,
            )
            past_key_values = output.past_key_values
            logits = t3.speech_head(output[0])[:, -1, :]

    @torch.inference_mode()
    def __make_mel_frames(
        self,
        model: "ChatterboxTurboTTS",
        speech_tokens: list[int],
        is_last_piece: bool,
        noise: torch.Tensor,
    ) -> torch.Tensor:
        """Turns ALL speech tokens made so far into mel frames, shape
        (1, 80, frames). Tokens that are not sounds are left out. After the
        last piece the 3 silence tokens are added, as generate() does. All
        frames come for the last piece, for the others without the last
        UNSURE_FRAMES, which the next piece makes again.

        Only the token-to-mel half of S3Gen is run (S3Token2Mel.forward called
        on the S3Gen object, its own forward would also run the vocoder).
        finalize=True, because finalize=False is broken in chatterbox 0.1.7: it
        cuts the frames and not the mask.

        noise is the random noise of the whole text, shape (1, 80, frames), the
        same one for every piece, so a frame does not change from piece to
        piece. FRAMES_PER_TOKEN columns of it are used for every sound token.
        Errors of S3Gen come out as they are.
        """
        from chatterbox.models.s3gen.const import S3GEN_SIL
        from chatterbox.models.s3gen.s3gen import S3Token2Mel

        sound_tokens = [t for t in speech_tokens if t < FIRST_NOT_A_SOUND_TOKEN]
        if is_last_piece:
            sound_tokens += [S3GEN_SIL] * 3

        mel_frames = S3Token2Mel.forward(
            model.s3gen,
            torch.tensor(sound_tokens, device=model.device),
            None,
            None,
            ref_dict=model.conds.gen,
            n_cfm_timesteps=2,
            finalize=True,
            noised_mels=noise[:, :, : FRAMES_PER_TOKEN * len(sound_tokens)],
        )
        if is_last_piece:
            return mel_frames
        return mel_frames[:, :, :-UNSURE_FRAMES]

    def __pick_device(self, params: ChatterboxParamsModel) -> str:
        """The device the model runs on: "cpu" or "cuda" as set in params, and
        for "auto" whatever get_available_device() says."""
        if params.device in ["cpu", "cuda"]:
            return params.device
        return self.get_available_device()

    def __load_model(self, params: ChatterboxParamsModel) -> None:
        """Loads Chatterbox Turbo on the device from params ("auto" -> see
        get_available_device) and with the nano flag. Slow and blocking. The
        first time, from_pretrained downloads the model from the Hugging Face
        Hub. The new model has no voice profile, so loaded_profile_path is
        cleared."""
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        logger.info("Preparing Chatterbox TTS model...")

        device = self.__pick_device(params)

        self.model = ChatterboxTurboTTS.from_pretrained(device=device, nano=params.nano)
        self.loaded_device = params.device
        self.loaded_nano = params.nano
        self.loaded_profile_path = None

    def __get_or_load_model(
        self, params: ChatterboxParamsModel
    ) -> "ChatterboxTurboTTS":
        """Loads the model on the first call (slow, blocking) and again when
        device or nano in params differ from the loaded model. Otherwise returns
        the loaded one. Raises RuntimeError when loading left no model."""
        is_other_model_wanted = (
            self.loaded_device != params.device or self.loaded_nano != params.nano
        )
        if self.model is None or is_other_model_wanted:
            self.__load_model(params)

        if self.model is None:
            raise RuntimeError("Chatterbox TTS model could not be prepared.")

        return self.model

    def __load_voice_profile_into_model(self, profile_path: Path) -> None:
        """Makes the model speak with the profile: reads the .pt file into
        model.conds. Does nothing when this profile is already loaded. Blocking.
        Raises FileNotFoundError when the profile file does not exist."""
        from chatterbox.tts_turbo import Conditionals

        if self.model is None:
            raise RuntimeError(
                "Chatterbox TTS model is not loaded. "
                "You tried to load a voice profile without a model."
            )
        if self.loaded_profile_path == profile_path:
            return

        if not profile_path.exists():
            raise FileNotFoundError(f"Voice profile not found: {profile_path}")

        self.model.conds = Conditionals.load(profile_path, self.model.device)
        self.loaded_profile_path = profile_path
