import asyncio
import ctypes
import logging
import os
import queue
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator, Literal

import edge_tts
import numpy as np
import soundfile as sf

from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.settings_model import (
    SettingsIssueModel,
    SettingsModel,
    TTSModel,
    TtsProviderParams,
)
from edceleste.services.models.voice_cloning_models import (
    VoiceAnalysisResult,
    VoiceCloningState,
)
from edceleste.services.exceptions.voice_cloning_exception import (
    VoiceCloningException,
)
from edceleste.services.settings_service import SettingsService
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_providers.tts_provider_protocol import (
    CloningTTSProviderProtocol,
    StreamingTTSProviderProtocol,
    TTSProviderProtocol,
)
from edceleste.services.voice_lab_service import VoiceLabService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import sounddevice as sd

TTS_PROVIDER_CLASSES = {
    "edge": EdgeTTSProvider,
    "chatterbox": ChatterboxTTSProvider,
}

DEFAULT_VOICE_SAMPLE_TEXT = "Hello Commander. How can I assist you today?"
# Spoken without sound at startup, so the voice model is loaded and its first
# run is behind it before the first reply
WARM_UP_TEXT = "Ready, Commander."
# Long enough to hear the reverb ring out, with a few "s" sounds for the clarity
VOICE_LAB_TEST_TEXT = (
    "Commander, all systems are online. "
    "Shields are up, and the ship is ready when you are."
)
RECOMMENDED_REFERENCE_AUDIO_SECONDS_RANGE = (10.0, 30.0)

# How much audio goes into one waveform bar. Small enough to look smooth,
# big enough that a 30s file does not send thousands of numbers to the UI.
WAVEFORM_ENVELOPE_WINDOW_SECONDS = 0.1

# Below this amplitude, audio is treated as silence for dBFS math (avoids
# log10(0) blowing up on fully silent clips).
SILENCE_FLOOR_DBFS = -120.0


def calculate_peak_dbfs(audio_samples: np.ndarray) -> float:
    """Loudest single sample in the clip, in dBFS (0 dBFS = full scale).
    A fully silent clip gives SILENCE_FLOOR_DBFS."""
    peak_amplitude = float(np.max(np.abs(audio_samples)))
    if peak_amplitude == 0:
        return SILENCE_FLOOR_DBFS
    return 20 * np.log10(peak_amplitude)


def calculate_noise_floor_dbfs(audio_samples: np.ndarray, sample_rate: int) -> float:
    """Background noise level: RMS loudness of the quietest 100ms window.
    Stereo is mixed to mono first. A fully silent window gives
    SILENCE_FLOOR_DBFS."""
    mono_samples = (
        audio_samples if audio_samples.ndim == 1 else audio_samples.mean(axis=1)
    )
    window_size = max(1, int(sample_rate * 0.1))
    window_count = max(1, len(mono_samples) // window_size)

    quietest_window_rms = min(
        float(
            np.sqrt(
                np.mean(
                    mono_samples[i * window_size : (i + 1) * window_size].astype(
                        np.float64
                    )
                    ** 2
                )
            )
        )
        for i in range(window_count)
    )

    if quietest_window_rms == 0:
        return SILENCE_FLOOR_DBFS
    return 20 * np.log10(quietest_window_rms)


def calculate_waveform_envelope(
    audio_samples: np.ndarray,
    sample_rate: int,
    window_seconds: float = WAVEFORM_ENVELOPE_WINDOW_SECONDS,
) -> list[float]:
    """Peak amplitude per short window, for drawing a waveform sparkline.
    Stereo is mixed to mono first. A last window shorter than the others is
    left out."""
    mono_samples = (
        audio_samples if audio_samples.ndim == 1 else audio_samples.mean(axis=1)
    )
    window_size = max(1, int(sample_rate * window_seconds))
    window_count = max(1, len(mono_samples) // window_size)

    return [
        float(np.max(np.abs(mono_samples[i * window_size : (i + 1) * window_size])))
        for i in range(window_count)
    ]


def find_voices_directory(operating_system_name: str = os.name) -> Path:
    """Voice profiles are stored in the per-user application data directory:
    %LOCALAPPDATA%\\EDCeleste\\voices on Windows ("nt"), otherwise
    ~/.local/share/EDCeleste/voices. Only builds the path, the folder is
    created later by clone_voice()."""
    if operating_system_name == "nt":
        application_data_directory = Path(os.environ["LOCALAPPDATA"])
    else:
        application_data_directory = Path.home() / ".local" / "share"

    return application_data_directory / "EDCeleste" / "voices"


VOICES_DIR = find_voices_directory()

NO_VOICE_PROFILES_MESSAGE = (
    "The active TTS provider does not support voice profiles. "
    "Switch the TTS provider to 'chatterbox' and try again."
)


class TTSEvent:
    def __init__(self, text: str):
        """Published on the event bus by LLMService for every finished text
        block of a reply. TTSService says the text out loud."""
        self.text = text


class TTSService:
    provider_type: str | None = None
    provider: TTSProviderProtocol | None = None

    def __init__(
        self,
        event_bus: EventBus,
        settings_service: SettingsService,
        voice_lab_service: VoiceLabService,
    ) -> None:
        """Only stores the dependencies and subscribes to the event bus. The
        provider stays None until reload_service() builds it.

        Subscriptions:
        - TTSEvent -> speak_text_from_tts_event
        """
        self.__event_bus = event_bus
        self.__settings_service = settings_service
        self.__voice_lab_service = voice_lab_service
        self.__event_bus.subscribe(TTSEvent, self.speak_text_from_tts_event)

    def build_provider(self, provider_type: str) -> TTSProviderProtocol:
        """Creates a new provider object for settings.tts.provider. Cheap, no
        model is loaded here, Chatterbox loads it on the first use. Raises
        KeyError for a provider type not in TTS_PROVIDER_CLASSES."""
        return TTS_PROVIDER_CLASSES[provider_type]()

    async def synthesize_and_play(self, text: str) -> None:
        """Turns the text into speech AND plays it on the speakers, with the
        Voice Lab effects (when they are switched on in the saved settings)
        and the saved volume. Waits until the audio has finished, so the next
        text is not spoken over this one.

        A provider that can speak in pieces for the saved params (Chatterbox on
        a GPU) speaks through speak_while_synthesizing(), so the first sound
        comes long before the text is done. Every other provider makes the
        whole audio first and plays it then.
        Raises RuntimeError when reload_service() has not built the provider
        yet. Provider errors are raised."""
        logger.info("Synthesizing TTS for text: %s", text)
        if self.provider is None:
            raise RuntimeError("The TTS provider is not built yet.")

        tts_settings = self.__settings_service.get_settings().tts
        profile_path = self.find_profile_path(self.provider, tts_settings.params)

        if isinstance(
            self.provider, StreamingTTSProviderProtocol
        ) and self.provider.can_stream(tts_settings.params):
            await self.speak_while_synthesizing(
                self.provider,
                text,
                tts_settings.params,
                tts_settings.volume,
                profile_path,
            )
            return

        apply_voice_lab_effects = tts_settings.voice_lab.enabled

        samples, sample_rate = await self.provider.synthesize(
            text, tts_settings.params, profile_path
        )
        await self.play_samples(
            samples,
            sample_rate,
            tts_settings.volume,
            apply_voice_lab_effects=apply_voice_lab_effects,
        )

    async def speak_while_synthesizing(
        self,
        provider: StreamingTTSProviderProtocol,
        text: str,
        params: TtsProviderParams,
        volume: float,
        profile_path: Path | None,
    ) -> None:
        """Speaks the text while the provider is still making it. Returns when
        the voice has been played to the end.

        A worker thread (play_pieces) plays what is put in a queue. Here every
        piece the provider makes is added to the audio so far, and the Voice
        Lab effects are run on ALL of it, not on the piece alone, so a filter or
        the reverb does not start again at every piece. The effects only look
        back in time, so the part that was already queued comes out the same,
        and only the new samples are put in the queue, at the volume. After the
        last piece the rest of the output (the reverb ringing out) is queued.
        Running the effects again over the audio so far costs 40 ms for 10
        seconds of speech.

        The effects are always asked for: VoiceLabService.apply_effects gives
        the audio back untouched when Voice Lab is switched off in the saved
        settings. volume is the saved volume, a factor from 0 to 1.

        The player is stopped also when the provider fails, and that error is
        raised. An error of the player (sounddevice.PortAudioError, e.g. no
        speaker can be opened) is raised only at the end, after the whole voice
        was made, because the player is awaited last.
        """
        pieces_to_play: queue.Queue[np.ndarray | None] = queue.Queue()
        player = asyncio.create_task(
            asyncio.to_thread(
                self.play_pieces, pieces_to_play, provider.stream_sample_rate
            )
        )
        audio_so_far = np.zeros(0, dtype=np.float32)
        audio_with_effects = audio_so_far
        samples_queued = 0

        try:
            async for piece in provider.synthesize_stream(text, params, profile_path):
                audio_so_far = np.concatenate([audio_so_far, piece])
                audio_with_effects = await asyncio.to_thread(
                    self.__voice_lab_service.apply_effects,
                    audio_so_far,
                    provider.stream_sample_rate,
                )
                new_samples = audio_with_effects[samples_queued : len(audio_so_far)]
                pieces_to_play.put(new_samples * volume)
                samples_queued = len(audio_so_far)

            pieces_to_play.put(audio_with_effects[samples_queued:] * volume)
        finally:
            pieces_to_play.put(None)
        await player

    def play_pieces(
        self, pieces: "queue.Queue[np.ndarray | None]", sample_rate: int
    ) -> None:
        """Plays the audio that arrives in the queue, as it arrives, and returns
        after the last piece was played, when None arrives. Blocking: runs in a
        worker thread. The one place where a streamed voice meets the
        hardware, the same as play_samples() is for a whole voice.

        Every piece is mono (samples) or stereo (samples x 2) float32. A mono
        piece is played from both speakers. An empty piece (what is left after
        the last piece when the effects add no tail) is skipped, because a write
        of zero samples to a speaker is not worth the risk of an error of the
        driver. When the next piece is late, the speaker plays silence. The
        speaker is closed when the function ends, also after an error. The
        queue has no size limit, and without the None at the end the function
        waits for it for ever.

        Raises sounddevice.PortAudioError when no speaker can be opened. The
        error stays in the worker thread and reaches speak_while_synthesizing()
        only at its end, so the voice is made to the end for nothing."""
        with self.open_speaker(sample_rate) as speaker:
            while (piece := pieces.get()) is not None:
                if len(piece) == 0:
                    continue
                if piece.ndim == 1:
                    piece = np.stack([piece, piece], axis=1)
                speaker.write(np.ascontiguousarray(piece, dtype=np.float32))

    def open_speaker(self, sample_rate: int) -> "sd.OutputStream":
        """Opens a stereo float32 speaker with low latency, not started yet. The
        caller uses it as a context manager, which starts it and closes it. On
        Windows it is WASAPI, with about 40 ms of delay, where the default way
        (MME, what sd.play uses) has about 200 ms. WASAPI needs COM started in
        the thread that opens it, and a worker thread has none, so COM is
        started here (and stays started for the life of the thread). When
        WASAPI cannot be opened, or is not on the list, the default speaker is
        used, and a failed WASAPI is logged as a warning. On other systems it
        is always the default speaker. Raises sounddevice.PortAudioError when
        the default speaker cannot be opened either."""
        import sounddevice as sd

        settings = {
            "samplerate": sample_rate,
            "channels": 2,
            "dtype": "float32",
            "latency": "low",
        }
        if sys.platform == "win32":
            wasapi = next(
                (api for api in sd.query_hostapis() if api["name"] == "Windows WASAPI"),
                None,
            )
            if wasapi is not None:
                try:
                    ctypes.windll.ole32.CoInitializeEx(None, 0)
                    return sd.OutputStream(
                        **settings,
                        device=wasapi["default_output_device"],
                        extra_settings=sd.WasapiSettings(auto_convert=True),
                    )
                except sd.PortAudioError:
                    logger.warning(
                        "WASAPI speaker could not be opened, using the default one.",
                        exc_info=True,
                    )
        return sd.OutputStream(**settings)

    async def warm_up_voice(self, provider: StreamingTTSProviderProtocol) -> None:
        """Loads the model and the voice profile of the saved settings and runs
        the model once on WARM_UP_TEXT, without playing anything: it reads
        provider.synthesize_stream() to the end and throws the pieces away.
        Slow, several seconds. Provider errors are raised (a missing voice
        profile too). Only a streaming provider is asked, because only for it
        cold_start() warms up."""
        tts_settings = self.__settings_service.get_settings().tts
        profile_path = self.find_profile_path(provider, tts_settings.params)
        async for _ in provider.synthesize_stream(
            WARM_UP_TEXT, tts_settings.params, profile_path
        ):
            pass

    async def speak_text_from_tts_event(self, event: TTSEvent) -> None:
        """Runs when a TTSEvent is published on the event bus. Says the text
        out loud and returns when the audio has finished."""
        logger.info("Received TTS request: %s", event.text)
        await self.synthesize_and_play(event.text)

    async def play_samples(
        self,
        samples: np.ndarray,
        sample_rate: int,
        volume: float,
        apply_voice_lab_effects: bool,
    ) -> None:
        """Plays the samples at the volume and waits until they have played.
        With apply_voice_lab_effects the Voice Lab effects are added first, and
        that makes the audio longer (the reverb rings out)."""
        import sounddevice as sd

        if apply_voice_lab_effects:
            samples = self.__voice_lab_service.apply_effects(samples, sample_rate)

        sd.play(samples * volume, sample_rate)  # type: ignore
        await asyncio.sleep(len(samples) / sample_rate)

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the TTS part of settings that are not saved yet. Returns the
        first problem found, or None when everything is fine. The active
        provider is not touched.

        1. Builds a throwaway provider of the new type (KeyError for a type
           that is not in TTS_PROVIDER_CLASSES) and lets it check its own
           params (Edge: voice is set, Chatterbox: profile is set).
        2. For a provider that clones voices, the profile file must also exist
           in the voices folder, e.g. not deleted a moment ago. Reads the disk.
        """
        tts_settings = new_settings.tts
        provider = self.build_provider(tts_settings.provider)

        issue = provider.validate_params(tts_settings.params)
        if issue is not None:
            return issue

        profile_path = self.find_profile_path(provider, tts_settings.params)
        if profile_path is not None and not profile_path.exists():
            return SettingsIssueModel(
                section="tts",
                field="profile",
                message=f"Profile '{profile_path.stem}' does not exist.",
            )
        return None

    def reload_service(self) -> None:
        """Applies the saved TTS settings. Called by cold_start() and after
        the settings change.
        A different provider type -> builds a new provider, the old one and
        its loaded model are dropped. Raises KeyError for a provider type that
        is not in TTS_PROVIDER_CLASSES.
        The same type -> nothing, the provider gets the saved params with every
        sentence and reloads its model itself when e.g. the device changed.
        """
        new_provider_type = self.__settings_service.get_settings().tts.provider

        if new_provider_type != self.provider_type:
            self.provider_type = new_provider_type
            self.provider = self.build_provider(new_provider_type)

    async def fetch_edge_tts_voice_names(self) -> list[str]:
        """Asks the Microsoft Edge voice service over the network for every
        voice name, e.g. "en-GB-SoniaNeural". Works whichever provider is
        active. Network errors are raised."""
        return [voice["ShortName"] for voice in await edge_tts.list_voices()]

    def build_profile_path(self, profile_name: str, file_extension: str) -> Path:
        """Puts "<profile_name><file_extension>", e.g. "celeste.pt" or
        "celeste_sample.wav", in the voices folder. Any folder part of the name
        is dropped, so a name like "../x" cannot reach outside the voices
        folder. Does not check that the file exists."""
        return VOICES_DIR / (Path(profile_name).name + file_extension)

    def find_profile_path(
        self, provider: TTSProviderProtocol, params: TtsProviderParams
    ) -> Path | None:
        """The voice profile file named in params, for a provider that clones
        voices. None for the other providers (Edge has no profiles)."""
        if not isinstance(provider, CloningTTSProviderProtocol):
            return None

        profile_name = getattr(params, "profile")
        return self.build_profile_path(profile_name, provider.profile_file_extension)

    def get_active_or_new_provider_for(
        self, params: TtsProviderParams
    ) -> TTSProviderProtocol:
        """Picks the provider for the engine in params, the settings as they are
        on the screen now. Nothing is stored and the active provider is never
        replaced here.
        - Same type as the active provider -> the active one (self.provider),
          which keeps its loaded model.
        - Another type, because the pilot picked an engine that is not saved
          yet -> a new throwaway provider, built on every call. It has no model
          yet, so a throwaway Chatterbox loads its own model on first use and
          drops it together with the provider, which is slow every time.
        - No active provider built yet (reload_service() has not run) -> a new
          one as well, also not stored.
        Raises KeyError for a type that is not in TTS_PROVIDER_CLASSES."""
        if params.type == self.provider_type and self.provider is not None:
            return self.provider
        return self.build_provider(params.type)

    def get_cloning_provider_for(
        self, params: TtsProviderParams
    ) -> CloningTTSProviderProtocol:
        """Picks the provider for params like get_active_or_new_provider_for(),
        but only one that can clone voices. Returns it, never None. Raises
        VoiceCloningException (with NO_VOICE_PROFILES_MESSAGE) when that
        provider cannot clone voices (Edge), and KeyError for an unknown
        type."""
        provider = self.get_active_or_new_provider_for(params)

        if not isinstance(provider, CloningTTSProviderProtocol):
            raise VoiceCloningException(NO_VOICE_PROFILES_MESSAGE)

        return provider

    async def clone_voice(
        self, path_to_audio_file: str, profile_name: str, params: TtsProviderParams
    ) -> AsyncGenerator[VoiceCloningState, None]:
        """Makes a new voice profile from an audio file and yields after every
        step, so the UI can show progress. params are the settings as they are
        on the screen now, not the saved ones. Nothing runs before the first
        state is asked for, so every error comes out while iterating.

        1. Raises VoiceCloningException when the provider of params cannot
           clone. Creates the voices folder. Raises FileNotFoundError when the
           audio file does not exist and FileExistsError when a profile with
           this name exists already (an existing voice is never replaced).
           Folder parts of profile_name are dropped ("../x" -> "x"). Yields
           DIRECTORY_CREATED.
        2. Raises ValueError when the clip is shorter than the provider needs.
           Reads only that many seconds of it. Yields AUDIO_PROCESSED.
        3. Writes those seconds into a new temporary folder, outside the voices
           folder, and lets the provider learn the voice from them and save
           the profile file in the voices folder. Yields COMPLETED.
        4. Generates <name>_sample.wav with DEFAULT_VOICE_SAMPLE_TEXT. Yields
           SAMPLE_CREATED and ends.

        Any error in steps 3 and 4 is raised again as RuntimeError, with the
        original error as its cause. A cancel is not wrapped. A cancel during
        step 3 leaves no profile file. An error or a cancel after COMPLETED
        leaves the profile file on disk, the caller deletes it. The temporary
        folder is always deleted. When that fails (on Windows a file still
        open in the model thread), the folder is left in the system temp
        folder and no error is raised.
        """
        provider = self.get_cloning_provider_for(params)
        profile_path = self.build_profile_path(
            profile_name, provider.profile_file_extension
        )

        VOICES_DIR.mkdir(parents=True, exist_ok=True)

        if not os.path.isfile(path_to_audio_file):
            raise FileNotFoundError(f"Audio file '{path_to_audio_file}' not found.")

        if profile_path.exists():
            raise FileExistsError(f"Voice profile '{profile_name}' already exists.")

        yield VoiceCloningState.DIRECTORY_CREATED

        audio_info = sf.info(path_to_audio_file)
        audio_duration = audio_info.frames / audio_info.samplerate

        if audio_duration < provider.reference_seconds:
            raise ValueError(
                f"Audio file '{path_to_audio_file}' is too short. "
                f"It must be at least {provider.reference_seconds} seconds long."
            )

        audio_file_name = os.path.basename(path_to_audio_file)
        frames_to_read = int(provider.reference_seconds * audio_info.samplerate)
        audio_data, sample_rate = sf.read(path_to_audio_file, frames=frames_to_read)

        yield VoiceCloningState.AUDIO_PROCESSED

        # A new empty folder, so the trimmed clip can never replace a file of
        # the pilot, whatever its name is
        clip_folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        trimmed_clip_path = Path(clip_folder.name) / audio_file_name
        try:
            sf.write(
                trimmed_clip_path, audio_data, sample_rate, subtype=audio_info.subtype
            )

            await provider.create_voice_profile(
                str(trimmed_clip_path), profile_path, params
            )

            yield VoiceCloningState.COMPLETED

            samples, sample_rate = await provider.synthesize(
                DEFAULT_VOICE_SAMPLE_TEXT,
                params.model_copy(update={"profile": profile_name}),
                profile_path,
            )
            sample_path = self.build_profile_path(f"{profile_name}_sample", ".wav")
            sf.write(sample_path, samples, sample_rate)

            yield VoiceCloningState.SAMPLE_CREATED

        except Exception as e:
            raise RuntimeError(
                f"Failed to prepare voice profile '{profile_name}' "
                f"from audio file '{audio_file_name}'."
            ) from e

        finally:
            clip_folder.cleanup()

    def get_available_profiles(self, params: TtsProviderParams) -> list[str]:
        """Voice profile names from the voices folder, without the file
        extension of the provider of params (the settings as they are on the
        screen, saved or not). Empty when that provider cannot clone voices, or
        the folder does not exist yet, even if profiles exist on disk."""
        try:
            provider = self.get_cloning_provider_for(params)
        except VoiceCloningException:
            return []

        if not VOICES_DIR.exists():
            return []

        file_extension = provider.profile_file_extension
        return [
            profile_file.name.removesuffix(file_extension)
            for profile_file in VOICES_DIR.iterdir()
            if profile_file.is_file() and profile_file.name.endswith(file_extension)
        ]

    def remove_profile(self, profile_name: str, params: TtsProviderParams) -> None:
        """Deletes the profile file and its <name>_sample.wav from the voices
        folder. A file that is not there is skipped. The settings are not
        changed, they may still point at it. params are the settings as they
        are on the screen now. Raises VoiceCloningException when their provider
        cannot clone voices."""
        provider = self.get_cloning_provider_for(params)

        profile_path = self.build_profile_path(
            profile_name, provider.profile_file_extension
        )
        sample_path = self.build_profile_path(f"{profile_name}_sample", ".wav")

        profile_path.unlink(missing_ok=True)
        sample_path.unlink(missing_ok=True)

    def rename_profile(
        self, old_profile_name: str, new_profile_name: str, params: TtsProviderParams
    ) -> None:
        """Renames the profile file and its sample on disk, nothing is cloned
        again. params are the settings as they are on the screen now. Raises
        VoiceCloningException when their provider cannot clone voices,
        FileExistsError when the new name is taken and FileNotFoundError when
        the old profile does not exist. A missing sample is skipped. The
        settings are not changed."""
        provider = self.get_cloning_provider_for(params)

        old_profile_path = self.build_profile_path(
            old_profile_name, provider.profile_file_extension
        )
        new_profile_path = self.build_profile_path(
            new_profile_name, provider.profile_file_extension
        )

        if new_profile_path.exists():
            raise FileExistsError(f"Voice profile '{new_profile_name}' already exists.")

        old_profile_path.rename(new_profile_path)

        old_sample_path = self.build_profile_path(f"{old_profile_name}_sample", ".wav")
        new_sample_path = self.build_profile_path(f"{new_profile_name}_sample", ".wav")
        if old_sample_path.exists():
            old_sample_path.rename(new_sample_path)

    async def preview_voice_sample(
        self, profile_name: str, text: str, params: TtsProviderParams
    ) -> None:
        """Speaks the text with the profile's voice at the saved volume, without
        Voice Lab effects, and waits until it has played. Nothing is written to
        disk, so the saved sample stays as it is. params are the settings as
        they are on the screen now. Raises VoiceCloningException when their
        provider cannot clone voices, FileNotFoundError for a missing profile."""
        provider = self.get_cloning_provider_for(params)
        profile_path = self.build_profile_path(
            profile_name, provider.profile_file_extension
        )

        samples, sample_rate = await provider.synthesize(
            text, params.model_copy(update={"profile": profile_name}), profile_path
        )
        volume = self.__settings_service.get_settings().tts.volume
        await self.play_samples(
            samples, sample_rate, volume, apply_voice_lab_effects=False
        )

    async def play_voice_lab_test_sentence(self, tts_settings: TTSModel) -> None:
        """Lets the pilot hear the Voice Lab: speaks VOICE_LAB_TEST_TEXT and
        waits until it has played. tts_settings are the settings as they are on
        the screen now, saved or not: the engine, the volume and the Voice Lab
        switch and sliders all come from them, so a change is heard before it is
        saved. Nothing is saved or written to disk.

        1. Takes the provider of the engine on the screen
           (get_active_or_new_provider_for) and lets it check its params. A
           problem, e.g. no voice or no profile picked, is raised as ValueError
           with its message.
        2. Speaks the sentence. Edge goes to the network. Chatterbox loads its
           model on first use, and again on every call when the engine on the
           screen is not the saved one (a throwaway provider).
        3. Adds the Voice Lab effects from tts_settings. Switched off -> the
           plain voice, as Celeste would sound.
        4. Plays the result at the volume of tts_settings.
        Provider errors are raised, e.g. no network or a profile file that is
        gone (FileNotFoundError).
        """
        provider = self.get_active_or_new_provider_for(tts_settings.params)

        issue = provider.validate_params(tts_settings.params)
        if issue is not None:
            raise ValueError(issue.message)

        profile_path = self.find_profile_path(provider, tts_settings.params)
        samples, sample_rate = await provider.synthesize(
            VOICE_LAB_TEST_TEXT, tts_settings.params, profile_path
        )
        samples = self.__voice_lab_service.apply_effects(
            samples, sample_rate, tts_settings.voice_lab
        )
        await self.play_samples(
            samples,
            sample_rate,
            tts_settings.volume,
            apply_voice_lab_effects=False,
        )

    async def play_sample_voice(self, profile_name: str) -> None:
        """Plays the sample saved when the profile was cloned and waits until
        it has played. No speech is generated and no model is loaded. Raises
        FileNotFoundError when the sample file is missing."""
        sample_path = self.build_profile_path(f"{profile_name}_sample", ".wav")

        if not sample_path.exists():
            raise FileNotFoundError(
                f"Profile '{profile_name}' not found at '{sample_path}'."
            )

        await self.play_audio_file(str(sample_path))

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        """Plays any audio file at the saved TTS volume, without voice effects,
        and waits until it has played. Used to listen to a clip before cloning.
        Raises when the file cannot be read."""
        samples, sample_rate = await asyncio.to_thread(sf.read, path_to_audio_file)
        volume = self.__settings_service.get_settings().tts.volume

        await self.play_samples(
            samples, sample_rate, volume, apply_voice_lab_effects=False
        )

    def perform_sample_voice_analysis_and_validate(
        self, path_to_audio_file: str, params: TtsProviderParams
    ) -> VoiceAnalysisResult:
        """Reads the whole file and measures it for the clone screen: length,
        sample rate, channels, peak and noise floor in dBFS, clipping (peak at
        0 dBFS or more) and a waveform for the sparkline. Loads no model.

        Only the length decides is_valid: shorter than the provider of params
        needs -> is_valid False with a message. Clipping, stereo or noise never
        make it invalid, the UI only shows them as hints. A missing or broken
        file raises. Raises VoiceCloningException when the provider of params
        cannot clone voices.
        """
        minimum_seconds = self.get_cloning_provider_for(params).reference_seconds

        audio_info = sf.info(path_to_audio_file)
        audio_duration_seconds = audio_info.frames / audio_info.samplerate
        audio_samples, _ = sf.read(path_to_audio_file, always_2d=False)

        validation_error_message = None
        if audio_duration_seconds < minimum_seconds:
            recommended_min, recommended_max = RECOMMENDED_REFERENCE_AUDIO_SECONDS_RANGE
            validation_error_message = (
                f"Too short - minimum {minimum_seconds:.0f}s, "
                f"recommended {recommended_min:.0f}-{recommended_max:.0f}s"
            )

        peak_dbfs = calculate_peak_dbfs(audio_samples)

        return VoiceAnalysisResult(
            file_name=os.path.basename(path_to_audio_file),
            duration_seconds=audio_duration_seconds,
            sample_rate=audio_info.samplerate,
            channels=audio_info.channels,
            is_mono=audio_info.channels == 1,
            peak_dbfs=peak_dbfs,
            has_clipping=peak_dbfs >= 0.0,
            noise_floor_dbfs=calculate_noise_floor_dbfs(
                audio_samples, audio_info.samplerate
            ),
            waveform_envelope=calculate_waveform_envelope(
                audio_samples, audio_info.samplerate
            ),
            is_valid=validation_error_message is None,
            validation_error_message=validation_error_message,
        )

    def get_available_device(self, params: TtsProviderParams) -> Literal["cuda", "cpu"]:
        """Device "auto" would pick for the provider of params (the settings as
        they are on the screen now). Always "cpu" when that provider cannot
        clone voices, even on a machine with a GPU."""
        try:
            provider = self.get_cloning_provider_for(params)
        except VoiceCloningException:
            return "cpu"

        return provider.get_available_device()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Builds the provider (reload_service).
        3. A provider that speaks in pieces for the saved params (Chatterbox on
           a GPU) loads its model and voice now and speaks WARM_UP_TEXT with no
           sound, which takes several seconds. Otherwise the pilot would wait
           for that on the first reply. Other providers load nothing, a broken
           voice shows up on the first reply.
        4. Yields completed. Never raises, an error (also a voice profile that
           is missing) ends up in the status message. The check is not
           critical: with an error the app still starts, and the problem shows
           on the first reply.
        """
        status = ColdStartStatus(
            service="tts",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status
        try:
            self.reload_service()
            if isinstance(
                self.provider, StreamingTTSProviderProtocol
            ) and self.provider.can_stream(
                self.__settings_service.get_settings().tts.params
            ):
                status.progress_text = "Loading the voice"
                yield status
                await self.warm_up_voice(self.provider)
                status.progress_text = None
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
