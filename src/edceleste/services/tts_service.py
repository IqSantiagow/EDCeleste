import asyncio
import logging
import os
import shutil
import tempfile
from functools import partial
from pathlib import Path
from typing import AsyncGenerator, Callable, Literal

import edge_tts
import numpy as np
import soundfile as sf

from edceleste.protocols.speaker_protocol import (
    PRIORITY_ANSWER,
    PRIORITY_REACTION,
    SpeakerProtocol,
)
from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.game_events import GameEvent, StatusEvent
from edceleste.services.models.reply_texts import (
    JOURNAL_EVENT_REPLY_TEXTS,
    REPLY_TEXTS,
    build_reply_wav_file_name,
    pick_reply_texts_for_changed_flags,
)
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
from edceleste.services.ship_voice_effect import ShipVoiceEffect
from edceleste.services.tts_providers.chatterbox_tts_provider import (
    ChatterboxTTSProvider,
)
from edceleste.services.tts_providers.edge_tts_provider import EdgeTTSProvider
from edceleste.services.tts_providers.pocket_tts_provider import PocketTTSProvider
from edceleste.services.tts_providers.tts_provider_protocol import (
    CloningTTSProviderProtocol,
    StreamingTTSProviderProtocol,
    TTSProviderProtocol,
)

logger = logging.getLogger(__name__)

TTS_PROVIDER_CLASSES: dict[str, Callable[[], TTSProviderProtocol]] = {
    "edge": EdgeTTSProvider,
    "chatterbox": ChatterboxTTSProvider,
    "pocket": PocketTTSProvider,
}

DEFAULT_VOICE_SAMPLE_TEXT = "Hello Commander. How can I assist you today?"
# Spoken without sound at startup, so the voice model is loaded and its first
# run is behind it before the first reply
WARM_UP_TEXT = "Ready, Commander."
# Long enough to hear the ship effect ring out
VOICE_TEST_TEXT = (
    "Commander, all systems are online. "
    "Shields are up, and the ship is ready when you are."
)
RECOMMENDED_REFERENCE_AUDIO_SECONDS_RANGE = (10.0, 30.0)

# A reaction that waited in the queue longer than this is not said any more, it
# would describe something that happened a long time ago. It is never written
# to COMMS (only the answers to the pilot are), so it is simply not heard.
REACTION_MAX_WAIT_SECONDS = 5.0

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

# What lies in the folder of a profile, voices/<provider>/<profile name>/
PROFILE_FILE_STEM = "profile"  # plus the extension of the provider, profile.npy
SAMPLE_FILE_NAME = "sample.wav"
REPLIES_FOLDER_NAME = "replies"  # holds one <reply>.wav for every reply text

NO_VOICE_PROFILES_MESSAGE = (
    "The active TTS provider does not support voice profiles. "
    "Switch the TTS provider to 'chatterbox' or 'pocket' and try again."
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
        speaker_protocol: SpeakerProtocol,
    ) -> None:
        """Only stores the dependencies and subscribes to the event bus. The
        provider stays None until reload_service() builds it. Everything
        Celeste says goes through speaker_protocol, which plays it one speech
        at a time.

        Subscriptions:
        - TTSEvent -> __queue_answer_from_tts_event
        - StatusEvent -> __queue_reactions_for_changed_ship_switches
        - GameEvent -> __queue_reaction_for_journal_event
        """
        self.__event_bus = event_bus
        self.__settings_service = settings_service
        self.__speaker_protocol = speaker_protocol
        # Flags of the last Status.json, None until the first one comes
        self.__last_status_flags: int | None = None
        self.__event_bus.subscribe(TTSEvent, self.__queue_answer_from_tts_event)
        self.__event_bus.subscribe(
            StatusEvent, self.__queue_reactions_for_changed_ship_switches
        )
        self.__event_bus.subscribe(GameEvent, self.__queue_reaction_for_journal_event)

    async def __queue_reactions_for_changed_ship_switches(
        self, event: StatusEvent
    ) -> None:
        """Runs for every Status.json event. Compares its Flags with the Flags of
        the previous one and says the prepared reply of every switch of
        SHIP_FLAG_REPLY_TEXTS (models/reply_texts.py) that changed (landing
        gear, cargo scoop, flight assist, shields, fuel and so on), whoever
        flipped it: the pilot by hand, a fast command or the LLM. Returns at
        once: the replies only go to the speech queue (__queue_reaction_replies),
        so the event bus is not held up while the voice plays.

        Always remembers the new Flags, also from an event of the startup
        loading. Says nothing for such an event (event.is_startup_loading, set by
        the game watcher for what the game wrote before the app started, old
        state) and for the first Status.json (nothing to compare with). When
        several switches changed, their replies are said in the order of
        SHIP_FLAG_REPLY_TEXTS. This method does not read the settings:
        __play_reply() says nothing when the switch settings.tts.play_ship_replies
        is off."""
        old_flags = self.__last_status_flags
        self.__last_status_flags = event.Flags
        if old_flags is None or event.is_startup_loading:
            return
        texts = pick_reply_texts_for_changed_flags(old_flags, event.Flags)
        if texts:
            self.__queue_reaction_replies(texts)

    async def __queue_reaction_for_journal_event(self, event: GameEvent) -> None:
        """Runs for every game event, also the unknown journal lines (they come as
        UnknownCheckedEvent, the name is in event.event). When the name is in
        JOURNAL_EVENT_REPLY_TEXTS, e.g. "DockingGranted", puts its reply in the
        speech queue and returns at once. Says nothing for any other event and
        for an event of the startup loading (old state). Whether Celeste really
        speaks is decided by __play_reply()."""
        text = JOURNAL_EVENT_REPLY_TEXTS.get(event.event)
        if text is None or event.is_startup_loading:
            return
        self.__queue_reaction_replies([text])

    def __queue_reaction_replies(self, texts: list[str]) -> None:
        """Puts every text in the speech queue as a reaction: it waits for the
        answers to the pilot, and it is dropped without a word when it waited
        longer than REACTION_MAX_WAIT_SECONDS. Returns at once. Needs a running
        event loop."""
        for text in texts:
            self.__speaker_protocol.queue_speech(
                partial(self.__play_reply, text),
                PRIORITY_REACTION,
                REACTION_MAX_WAIT_SECONDS,
            )

    def queue_reply_to_pilot(self, text: str) -> None:
        """Puts a short answer to the pilot (a fast command reply) in the speech
        queue and returns at once. It goes before every waiting reaction and
        never expires. An error of the speech is logged by the queue. Needs a
        running event loop."""
        self.__speaker_protocol.queue_speech(
            partial(self.__play_reply, text), PRIORITY_ANSWER
        )

    def build_provider(self, provider_type: str) -> TTSProviderProtocol:
        """Creates a new provider object for settings.tts.provider. Cheap, no
        model is loaded here, Chatterbox and Pocket TTS load theirs on the
        first use. Raises
        KeyError for a provider type not in TTS_PROVIDER_CLASSES."""
        return TTS_PROVIDER_CLASSES[provider_type]()

    async def __play_reply(self, text: str) -> None:
        """Says a short reply (a fast command, or a change of the game state) out
        loud and waits until it has played, with the saved volume and the ship
        effect (when it is on). Called only by the speech queue, whoever wants
        a reply said uses queue_reply_to_pilot() or __queue_reaction_replies().

        0. The switch settings.tts.play_ship_replies is off -> nothing is said
           and nothing is read or played.
        1. The voice of the saved settings has a prepared clip of this text
           (__find_prepared_reply_clip) -> the clip is read from disk and played.
           No model runs, so it starts at once.
        2. Otherwise (the profile was cloned before this text was added, the
           replies were never made, or the file is gone) -> the text is spoken
           live by __synthesize_and_play(), which is slower but still comes.
        Raises RuntimeError when reload_service() has not built the provider
        yet and the clip is missing. A clip that cannot be read raises the error
        of soundfile, and the reply is not spoken then. Raises ValueError for a
        profile name that is empty or ".." (__find_prepared_reply_clip). Provider
        and speaker errors are raised."""
        tts_settings = self.__settings_service.get_settings().tts
        if not tts_settings.play_ship_replies:
            return

        clip_path = self.__find_prepared_reply_clip(text)
        if clip_path is None:
            await self.__synthesize_and_play(text)
            return

        samples, sample_rate = await asyncio.to_thread(sf.read, str(clip_path))
        await self.__play_samples(
            samples,
            sample_rate,
            tts_settings.volume,
            with_ship_effect=tts_settings.ship_effect,
        )

    def __find_prepared_reply_clip(self, text: str) -> Path | None:
        """The wav file made by __prepare_replies() for this text in the replies
        folder of the voice in the saved settings, e.g.
        voices/pocket/celeste/replies/landing_gear_deployed.wav. The voice is
        the profile of a cloning provider, or the voice name of Edge. None when
        the file is not there (a text that is not in REPLY_TEXTS, or replies
        that were never made). Only checks the disk. Raises ValueError for a
        profile name that is empty or ".." (see __build_profile_folder)."""
        params = self.__settings_service.get_settings().tts.params
        profile_name = params.voice if params.type == "edge" else params.profile
        clip_path = self.__build_replies_folder(params.type, profile_name) / (
            build_reply_wav_file_name(text)
        )
        return clip_path if clip_path.is_file() else None

    async def __synthesize_and_play(self, text: str) -> None:
        """Turns the text into speech AND plays it on the speakers, with the
        ship effect (when it is switched on in the saved settings) and the saved
        volume. Waits until the audio has finished, so the next text is not
        spoken over this one.

        A provider that can speak in pieces for the saved params (Chatterbox on
        a GPU, Pocket TTS) speaks through __stream_voice_to_speaker(), so the
        first sound
        comes long before the text is done. Every other provider makes the
        whole audio first and plays it then.
        Raises RuntimeError when reload_service() has not built the provider
        yet. Provider errors are raised."""
        logger.info("Synthesizing TTS for text: %s", text)
        if self.provider is None:
            raise RuntimeError("The TTS provider is not built yet.")

        tts_settings = self.__settings_service.get_settings().tts
        profile_path = self.__build_profile_path_named_in_params(
            self.provider, tts_settings.params
        )

        if isinstance(
            self.provider, StreamingTTSProviderProtocol
        ) and self.provider.can_stream(tts_settings.params):
            await self.__stream_voice_to_speaker(
                self.provider,
                text,
                tts_settings.params,
                tts_settings.volume,
                profile_path,
                tts_settings.ship_effect,
            )
            return

        samples, sample_rate = await self.provider.synthesize(
            text, tts_settings.params, profile_path
        )
        await self.__play_samples(
            samples,
            sample_rate,
            tts_settings.volume,
            with_ship_effect=tts_settings.ship_effect,
        )

    async def __stream_voice_to_speaker(
        self,
        provider: StreamingTTSProviderProtocol,
        text: str,
        params: TtsProviderParams,
        volume: float,
        profile_path: Path | None,
        with_ship_effect: bool,
    ) -> None:
        """Speaks the text while the provider is still making it. Returns when
        the voice has been played to the end, or when stop_speaking() cut it.
        The speaker plays the pieces that __make_voice_pieces() makes, as they
        come (SpeakerProtocol.play_pieces_from).

        With with_ship_effect one ShipVoiceEffect is made for this reply (it
        keeps its state from piece to piece, so the pieces together sound like
        the whole reply). params and profile_path are given to
        provider.synthesize_stream() as they are. volume is the saved volume, a
        factor from 0 to 1.

        If the ShipVoiceEffect cannot be made, its error is raised at once,
        before the speaker or the provider is started. Provider errors and
        speaker errors are raised by play_pieces_from()."""
        # Made before the speaker starts: when making it fails, nothing is
        # running yet that would wait for a piece forever.
        ship_effect = (
            ShipVoiceEffect(provider.stream_sample_rate) if with_ship_effect else None
        )
        await self.__speaker_protocol.play_pieces_from(
            self.__make_voice_pieces(
                provider, text, params, volume, profile_path, ship_effect
            ),
            provider.stream_sample_rate,
        )

    async def __make_voice_pieces(
        self,
        provider: StreamingTTSProviderProtocol,
        text: str,
        params: TtsProviderParams,
        volume: float,
        profile_path: Path | None,
        ship_effect: ShipVoiceEffect | None,
    ) -> AsyncGenerator[np.ndarray, None]:
        """Yields the voice piece by piece, as the provider makes it. Every
        piece goes through ship_effect (in a worker thread) when there is one,
        then it is multiplied by volume. After the last piece the rest of the
        effect (the echo and the rooms ringing out) is yielded as one more
        piece. Nobody asks for more once the speaker has been stopped."""
        async for piece in provider.synthesize_stream(text, params, profile_path):
            if ship_effect is not None:
                piece = await asyncio.to_thread(ship_effect.process, piece)
            yield piece * volume

        if ship_effect is not None:
            yield ship_effect.finish() * volume

    async def __warm_up_voice(self, provider: StreamingTTSProviderProtocol) -> None:
        """Loads the model and the voice profile of the saved settings and runs
        the model once on WARM_UP_TEXT, without playing anything: it reads
        provider.synthesize_stream() to the end and throws the pieces away.
        Slow, several seconds. Provider errors are raised (a missing voice
        profile too). Only a streaming provider is asked, because only for it
        cold_start() warms up."""
        tts_settings = self.__settings_service.get_settings().tts
        profile_path = self.__build_profile_path_named_in_params(
            provider, tts_settings.params
        )
        async for _ in provider.synthesize_stream(
            WARM_UP_TEXT, tts_settings.params, profile_path
        ):
            pass

    async def __queue_answer_from_tts_event(self, event: TTSEvent) -> None:
        """Runs when a TTSEvent is published on the event bus (LLMService
        publishes one for every finished text block of its reply). Puts the text
        in the speech queue as an answer to the pilot and returns at once, so the
        LLM does not wait for the voice. The text is spoken live with
        __synthesize_and_play(), never from a prepared clip. The switch
        settings.tts.play_ship_replies does not apply: it silences only the
        short prepared replies of __play_reply(), not the answers of the LLM. A
        blank text (empty, only spaces or newlines) is not queued, because a
        real voice may fail on it and turn the TTS dot red for nothing. An error
        of the voice is logged by the speech queue."""
        if not event.text.strip():
            logger.info("Blank TTS request, nothing to say")
            return

        logger.info("Received TTS request: %s", event.text)
        self.__speaker_protocol.queue_speech(
            partial(self.__synthesize_and_play, event.text), PRIORITY_ANSWER
        )

    async def __wait_for_turn_then_play_samples(
        self,
        samples: np.ndarray,
        sample_rate: int,
        volume: float,
        with_ship_effect: bool = False,
    ) -> None:
        """Plays the samples with __play_samples(), but only when it is their turn
        in the speech queue (as an answer to the pilot), so they never play over
        Celeste. They wait as an answer to the pilot (PRIORITY_ANSWER, no time
        limit). Returns when they have played, or when the pilot made Celeste go
        silent (they are dropped then, nothing is played and nothing is raised).
        Errors of __play_samples() are raised. For the settings screen (voice
        test, sample, preview), which waits for the sound."""
        await self.__speaker_protocol.queue_speech(
            partial(
                self.__play_samples,
                samples,
                sample_rate,
                volume,
                with_ship_effect=with_ship_effect,
            ),
            PRIORITY_ANSWER,
        )

    async def __play_samples(
        self,
        samples: np.ndarray,
        sample_rate: int,
        volume: float,
        with_ship_effect: bool = False,
    ) -> None:
        """Plays the samples at the volume and waits until they have played, or
        until stop_speaking() cut them. samples are mono or stereo floats between
        -1 and 1, volume is a factor from 0 to 1 that is applied after the
        effect. The samples passed in are not changed. With with_ship_effect the
        whole audio goes through a new ShipVoiceEffect first (in a worker
        thread), and that makes it stereo and longer (the echo and the rooms
        ring out). Only for code run by the speech queue
        (SpeakerProtocol.play_clip). Errors of the sound system are raised."""
        if with_ship_effect:
            samples = await asyncio.to_thread(
                self.__add_ship_effect_to_whole_audio, samples, sample_rate
            )

        await self.__speaker_protocol.play_clip(samples * volume, sample_rate)

    def __add_ship_effect_to_whole_audio(
        self, samples: np.ndarray, sample_rate: int
    ) -> np.ndarray:
        """The whole audio through a new ShipVoiceEffect, followed by the tail
        that rings out after it. In: mono or stereo samples. Out: stereo
        float32 samples, longer than the input by the tail. The samples passed
        in are not changed. Blocking, so callers run it in a worker thread."""
        ship_effect = ShipVoiceEffect(sample_rate)
        return np.concatenate([ship_effect.process(samples), ship_effect.finish()])

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the TTS part of settings that are not saved yet. Returns the
        first problem found, or None when everything is fine. The active
        provider is not touched.

        1. Builds a throwaway provider of the new type (KeyError for a type
           that is not in TTS_PROVIDER_CLASSES) and lets it check its own
           params (Edge: voice is set, Chatterbox and Pocket TTS: profile is
           set).
        2. For a provider that clones voices, the profile file must also exist
           in the voices folder, e.g. not deleted a moment ago. Reads the disk.
        """
        tts_settings = new_settings.tts
        provider = self.build_provider(tts_settings.provider)

        issue = provider.validate_params(tts_settings.params)
        if issue is not None:
            return issue

        profile_path = self.__build_profile_path_named_in_params(
            provider, tts_settings.params
        )
        if profile_path is not None and not profile_path.exists():
            return SettingsIssueModel(
                section="tts",
                field="profile",
                message=f"Profile '{profile_path.parent.name}' does not exist.",
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

    def __build_profile_folder(self, provider_type: str, profile_name: str) -> Path:
        """The folder of one profile: "<voices>/<provider_type>/<profile_name>".
        Everything of the profile lies in it: the profile file, the sample and
        the folder of replies. The same for every provider. A profile is a
        cloned voice (voices/pocket/celeste) or a voice picked from the list of
        a remote provider (voices/edge/en-US-AriaNeural). provider_type is the
        name of the provider in TTS_PROVIDER_CLASSES (params.type). Any folder
        part of the name is dropped, so a name like "../x" cannot reach outside
        the folder of the provider. Does not check that the folder exists.
        Raises ValueError for a name that is empty or ".." after that, because
        its folder would be the folder of the provider or the voices folder,
        and a profile that is removed deletes its folder."""
        folder_name = Path(profile_name).name
        if folder_name in ("", ".."):
            raise ValueError(f"'{profile_name}' cannot name a folder of a profile.")

        return VOICES_DIR / provider_type / folder_name

    def __build_profile_path(
        self, provider_type: str, profile_name: str, file_extension: str
    ) -> Path:
        """The voice profile file of a cloned profile: "profile" plus the
        extension of the provider, in the folder of the profile, e.g.
        voices/pocket/celeste/profile.npy. Does not check that the file exists.
        Raises ValueError for a name without a folder (see
        __build_profile_folder)."""
        return self.__build_profile_folder(provider_type, profile_name) / (
            PROFILE_FILE_STEM + file_extension
        )

    def __build_sample_path(self, provider_type: str, profile_name: str) -> Path:
        """The demo sample of a cloned profile in the folder of the profile,
        e.g. voices/pocket/celeste/sample.wav. Does not check that the file
        exists. Raises ValueError for a name without a folder (see
        __build_profile_folder)."""
        return (
            self.__build_profile_folder(provider_type, profile_name) / SAMPLE_FILE_NAME
        )

    def __build_replies_folder(self, provider_type: str, profile_name: str) -> Path:
        """The folder with the prepared replies of one profile, inside the folder
        of the profile, e.g. voices/pocket/celeste/replies or
        voices/edge/en-US-AriaNeural/replies. Does not check that the folder
        exists. Raises ValueError for a name without a folder (see
        __build_profile_folder)."""
        return (
            self.__build_profile_folder(provider_type, profile_name)
            / REPLIES_FOLDER_NAME
        )

    async def __prepare_replies(
        self,
        provider: TTSProviderProtocol,
        params: TtsProviderParams,
        profile_path: Path | None,
        replies_folder: Path,
    ) -> None:
        """Speaks every text of REPLY_TEXTS with the provider and saves each one
        as a wav file in replies_folder, named by build_reply_wav_file_name(text).

        Works with any provider, a local one (Chatterbox, Pocket TTS) or a
        remote one (Edge, goes to the network for every text), because it only
        asks provider.synthesize(). params and profile_path are given to the
        provider as they are (profile_path is None for Edge).

        Creates replies_folder when it is not there. A file that exists is
        replaced. The ship effect and the volume are not added, they are
        added when a reply is played. Slow: one synthesis per text. A provider
        error is raised at once, the files made until then stay on disk."""
        replies_folder.mkdir(parents=True, exist_ok=True)

        for reply_text in REPLY_TEXTS:
            samples, sample_rate = await provider.synthesize(
                reply_text, params, profile_path
            )
            sf.write(
                replies_folder / build_reply_wav_file_name(reply_text),
                samples,
                sample_rate,
            )

    def __build_profile_path_named_in_params(
        self, provider: TTSProviderProtocol, params: TtsProviderParams
    ) -> Path | None:
        """The voice profile file named in params, for a provider that clones
        voices, e.g. voices/pocket/celeste/profile.npy. None for the other
        providers (Edge has no profile file). Does not check that the file
        exists. Raises ValueError for a profile name that is empty or ".."
        (see __build_profile_folder)."""
        if not isinstance(provider, CloningTTSProviderProtocol):
            return None

        profile_name = getattr(params, "profile")
        return self.__build_profile_path(
            params.type, profile_name, provider.profile_file_extension
        )

    def __get_active_or_new_provider_for(
        self, params: TtsProviderParams
    ) -> TTSProviderProtocol:
        """Picks the provider for the engine in params, the settings as they are
        on the screen now. Nothing is stored and the active provider is never
        replaced here.
        - Same type as the active provider -> the active one (self.provider),
          which keeps its loaded model.
        - Another type, because the pilot picked an engine that is not saved
          yet -> a new throwaway provider, built on every call. It has no model
          yet, so a throwaway Chatterbox or Pocket TTS loads its own model on
          first use and drops it together with the provider, which is slow
          every time.
        - No active provider built yet (reload_service() has not run) -> a new
          one as well, also not stored.
        Raises KeyError for a type that is not in TTS_PROVIDER_CLASSES."""
        if params.type == self.provider_type and self.provider is not None:
            return self.provider
        return self.build_provider(params.type)

    def __get_cloning_provider_for(
        self, params: TtsProviderParams
    ) -> CloningTTSProviderProtocol:
        """Picks the provider for params like __get_active_or_new_provider_for(),
        but only one that can clone voices. Returns it, never None. Raises
        VoiceCloningException (with NO_VOICE_PROFILES_MESSAGE) when that
        provider cannot clone voices (Edge), and KeyError for an unknown
        type."""
        provider = self.__get_active_or_new_provider_for(params)

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
           clone. Creates the folder of the profile, voices/<provider>/<name>
           (and the folders above it). Raises FileNotFoundError when the
           audio file does not exist and FileExistsError when the profile file
           of this name exists already (an existing voice is never replaced; a
           folder of that name without a profile file, left by a clone that did
           not get that far, is used again). The folder is made before these
           two checks, so a missing audio file leaves an empty folder of the
           profile behind.
           Folder parts of profile_name are dropped ("../x" -> "x"). Raises
           ValueError for a name that is empty or ".." after that (see
           __build_profile_folder), before anything is created. Yields
           DIRECTORY_CREATED.
        2. Raises ValueError when the clip is shorter than the provider needs.
           Reads only that many seconds of it. Yields AUDIO_PROCESSED.
        3. Writes those seconds into a new temporary folder, outside the voices
           folder, and lets the provider learn the voice from them and save
           the profile file in the folder of the profile. Yields COMPLETED.
        4. Generates sample.wav in the folder of the profile with
           DEFAULT_VOICE_SAMPLE_TEXT. Yields SAMPLE_CREATED.
        5. Prepares the replies of the new voice (__prepare_replies) in the
           replies folder of the profile. Slow, one synthesis per text of
           REPLY_TEXTS. Yields REPLIES_CREATED and ends.

        Any error in steps 3 to 5 is raised again as RuntimeError, with the
        original error as its cause. A cancel is not wrapped. A cancel during
        step 3 leaves no profile file. An error or a cancel at any step leaves
        the folder of the profile on disk (empty before COMPLETED, after it
        with the profile file, the sample and the replies made so far), and
        the caller deletes it with remove_profile(), which deletes the whole
        folder of the profile. The temporary folder is always deleted.
        When that fails (on Windows a file still open in the model thread), the
        folder is left in the system temp folder and no error is raised.
        """
        provider = self.__get_cloning_provider_for(params)
        profile_path = self.__build_profile_path(
            params.type, profile_name, provider.profile_file_extension
        )

        profile_path.parent.mkdir(parents=True, exist_ok=True)

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

            new_profile_params = params.model_copy(update={"profile": profile_name})
            samples, sample_rate = await provider.synthesize(
                DEFAULT_VOICE_SAMPLE_TEXT, new_profile_params, profile_path
            )
            sample_path = self.__build_sample_path(params.type, profile_name)
            sf.write(sample_path, samples, sample_rate)

            yield VoiceCloningState.SAMPLE_CREATED

            await self.__prepare_replies(
                provider,
                new_profile_params,
                profile_path,
                self.__build_replies_folder(params.type, profile_name),
            )

            yield VoiceCloningState.REPLIES_CREATED

        except Exception as e:
            raise RuntimeError(
                f"Failed to prepare voice profile '{profile_name}' "
                f"from audio file '{audio_file_name}'."
            ) from e

        finally:
            clip_folder.cleanup()

    def get_available_profiles(self, params: TtsProviderParams) -> list[str]:
        """Voice profile names of the provider of params (the settings as they
        are on the screen, saved or not): the names of the folders in
        voices/<provider> that hold a profile file. A folder without one (a
        clone that did not get that far) and a file lying in the folder of the
        provider (a profile of the old layout) are not listed. Empty when that
        provider cannot clone voices, or its folder does not exist yet. The
        profiles of another provider are not listed. The order is the one of
        the disk."""
        try:
            provider = self.__get_cloning_provider_for(params)
        except VoiceCloningException:
            return []

        provider_folder = VOICES_DIR / params.type
        if not provider_folder.exists():
            return []

        return [
            profile_folder.name
            for profile_folder in provider_folder.iterdir()
            if self.__build_profile_path(
                params.type, profile_folder.name, provider.profile_file_extension
            ).is_file()
        ]

    def remove_profile(self, profile_name: str, params: TtsProviderParams) -> None:
        """Deletes the whole folder of the profile, with the profile file, the
        sample and the replies in it. A folder that is not there is skipped. The
        settings are not changed, they may still point at it. params are the
        settings as they are on the screen now. Raises VoiceCloningException
        when their provider cannot clone voices and ValueError for a name that
        is empty or ".." (see __build_profile_folder), before anything is
        deleted. A file that cannot be deleted (on Windows a file in use) raises
        OSError, and what was already deleted stays deleted."""
        self.__get_cloning_provider_for(params)
        profile_folder = self.__build_profile_folder(params.type, profile_name)

        try:
            shutil.rmtree(profile_folder)
        except FileNotFoundError:
            pass  # Nothing to delete

    def rename_profile(
        self, old_profile_name: str, new_profile_name: str, params: TtsProviderParams
    ) -> None:
        """Renames the folder of the profile, so the profile file, the sample and
        the replies in it move together, nothing is cloned or spoken again.
        params are the settings as they are on the screen now. Raises
        VoiceCloningException when their provider cannot clone voices,
        FileExistsError when the new name is taken (the same old and new name
        counts as taken) and FileNotFoundError when the old profile does not
        exist. A folder already lying under the new name without a profile file
        belongs to no profile (a clone that did not get that far), so it is
        deleted first. Raises ValueError for a name that is empty or ".." (see
        __build_profile_folder), before anything is renamed. The settings are not
        changed."""
        provider = self.__get_cloning_provider_for(params)

        old_profile_folder = self.__build_profile_folder(params.type, old_profile_name)
        new_profile_folder = self.__build_profile_folder(params.type, new_profile_name)
        new_profile_path = self.__build_profile_path(
            params.type, new_profile_name, provider.profile_file_extension
        )

        if new_profile_path.exists():
            raise FileExistsError(f"Voice profile '{new_profile_name}' already exists.")

        shutil.rmtree(new_profile_folder, ignore_errors=True)
        old_profile_folder.rename(new_profile_folder)

    async def preview_voice_sample(
        self, profile_name: str, text: str, params: TtsProviderParams
    ) -> None:
        """Speaks the text with the profile's voice at the saved volume, without
        the ship effect, and waits until it has played. The sound waits for its
        turn in the speech queue (__wait_for_turn_then_play_samples) and is
        dropped when the pilot makes Celeste go silent. Nothing is written to
        disk, so the saved sample stays as it is. params are the settings as
        they are on the screen now. Raises VoiceCloningException when their
        provider cannot clone voices, FileNotFoundError for a missing profile."""
        provider = self.__get_cloning_provider_for(params)
        profile_path = self.__build_profile_path(
            params.type, profile_name, provider.profile_file_extension
        )

        samples, sample_rate = await provider.synthesize(
            text, params.model_copy(update={"profile": profile_name}), profile_path
        )
        volume = self.__settings_service.get_settings().tts.volume
        await self.__wait_for_turn_then_play_samples(samples, sample_rate, volume)

    async def play_voice_test_sentence(self, tts_settings: TTSModel) -> None:
        """Lets the pilot hear the voice: speaks VOICE_TEST_TEXT and waits until
        it has played. tts_settings are the settings as they are on the screen
        now, saved or not: the engine, the volume and the ship effect switch all
        come from them, so a change is heard before it is saved. Nothing is
        saved or written to disk.

        1. Takes the provider of the engine on the screen
           (__get_active_or_new_provider_for) and lets it check its params. A
           problem, e.g. no voice or no profile picked, is raised as ValueError
           with its message.
        2. Speaks the whole sentence first. Edge goes to the network. Chatterbox
           and Pocket TTS load their model on first use, and again on every call
           when the engine on the screen is not the saved one (a throwaway
           provider).
        3. Plays the result at the volume of tts_settings, through the ship
           effect when tts_settings.ship_effect is on, as Celeste would sound.
           The sound waits for its turn in the speech queue
           (__wait_for_turn_then_play_samples), and is dropped when the pilot
           makes Celeste go silent.
        Provider errors are raised, e.g. no network or a profile file that is
        gone (FileNotFoundError).
        """
        provider = self.__get_active_or_new_provider_for(tts_settings.params)

        issue = provider.validate_params(tts_settings.params)
        if issue is not None:
            raise ValueError(issue.message)

        profile_path = self.__build_profile_path_named_in_params(
            provider, tts_settings.params
        )
        samples, sample_rate = await provider.synthesize(
            VOICE_TEST_TEXT, tts_settings.params, profile_path
        )
        await self.__wait_for_turn_then_play_samples(
            samples,
            sample_rate,
            tts_settings.volume,
            with_ship_effect=tts_settings.ship_effect,
        )

    async def play_sample_voice(
        self, profile_name: str, params: TtsProviderParams
    ) -> None:
        """Plays the sample saved when the profile was cloned, from the folder
        of the profile of the provider of params (the settings as they are on
        the screen now), and waits until it has played. No speech is generated
        and no model is loaded. Raises VoiceCloningException when that provider
        cannot clone voices and FileNotFoundError when the sample file is
        missing."""
        self.__get_cloning_provider_for(params)
        sample_path = self.__build_sample_path(params.type, profile_name)

        if not sample_path.exists():
            raise FileNotFoundError(
                f"Profile '{profile_name}' not found at '{sample_path}'."
            )

        await self.play_audio_file(str(sample_path))

    async def play_audio_file(self, path_to_audio_file: str) -> None:
        """Plays any audio file at the saved TTS volume, without the ship effect,
        and waits until it has played. Used to listen to a clip before cloning.

        The file is read first, then the sound waits for its turn in the speech
        queue (__wait_for_turn_then_play_samples), so it never plays over
        Celeste. Returns without a sound when the pilot made Celeste go silent
        in between. Raises the error of soundfile (soundfile.LibsndfileError, a
        RuntimeError) when the file is missing or cannot be read."""
        samples, sample_rate = await asyncio.to_thread(sf.read, path_to_audio_file)
        volume = self.__settings_service.get_settings().tts.volume

        await self.__wait_for_turn_then_play_samples(samples, sample_rate, volume)

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
        minimum_seconds = self.__get_cloning_provider_for(params).reference_seconds

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
            provider = self.__get_cloning_provider_for(params)
        except VoiceCloningException:
            return "cpu"

        return provider.get_available_device()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Builds the provider (reload_service).
        3. A provider that speaks in pieces for the saved params (Chatterbox on
           a GPU, Pocket TTS) loads its model and voice now and speaks
           WARM_UP_TEXT with no sound, which takes several seconds (and the
           first time Pocket TTS downloads its model). Otherwise the pilot
           would wait for that on the first reply. Other providers load
           nothing, a broken voice shows up on the first reply.
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
                await self.__warm_up_voice(self.provider)
                status.progress_text = None
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
