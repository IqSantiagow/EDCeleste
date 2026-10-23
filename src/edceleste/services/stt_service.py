from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncGenerator

import numpy as np
import whisper

from edceleste.protocols.hotkey_protocol import HotkeyProtocol
from edceleste.protocols.speaker_protocol import SpeakerProtocol
from edceleste.services.exceptions.stt_exception import SttException
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.hotkey_model import Hotkey
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.settings_service import SettingsService

import logging

if TYPE_CHECKING:
    import sounddevice as sd

logger = logging.getLogger(__name__)

_WHISPER_SAMPLE_RATE = 16_000

GAME_VOCABULARY_PROMPT = (
    "Celeste, is this system safe? What is in my hold? Do I have enough fuel for the "
    "next jump? Deploy hardpoints. Landing gear, cargo scoop, jettison cargo. Frame "
    "shift drive, FSD, supercruise. Flight assist off, boost. Four pips to systems, "
    "engines, weapons. Heat sink, chaff launcher, shield cell bank. Night vision, "
    "galaxy map, FSS."
)


class SttService:
    enabled: bool = True
    model: str | None = None
    input_device: int | None = None
    whisper_model: whisper.Whisper | None = None
    _recording_stream: sd.InputStream | None = None
    _recorded_frames: list[np.ndarray]

    def __init__(
        self,
        settings_service: SettingsService,
        hotkey_protocol: HotkeyProtocol,
        speaker_protocol: SpeakerProtocol,
    ) -> None:
        """Only stores the dependencies. The settings are applied in
        reload_service() and Whisper is loaded in cold_start() or on the first
        transcription. hotkey_protocol is where the push-to-talk key is
        registered. speaker_protocol is asked to go silent when a recording
        starts."""
        self.__settings_service = settings_service
        self.__hotkey_protocol = hotkey_protocol
        self.__speaker_protocol = speaker_protocol
        self._hotkey_key_name: str | None = None
        self._stt_queue: asyncio.Queue[str] = asyncio.Queue()
        self._app_loop: asyncio.AbstractEventLoop | None = None
        self._recorded_frames = []

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Only checks that a Whisper model name is set, even when STT is
        disabled. Does not check that the name exists, that the input device
        works or the hotkey. Returns None when the name is set, otherwise a
        SettingsIssueModel for the model field. Changes nothing."""
        if not new_settings.stt.model:
            return SettingsIssueModel(
                section="stt",
                field="model",
                message="Model is not set.",
            )
        return None

    def start_recording(self) -> None:
        """Opens the microphone and returns at once. sounddevice records in
        its own thread and hands every chunk to _audio_recording_callback().
        Mono, 16 kHz, the format Whisper wants.

        Raises SttException when STT is disabled or a recording already runs.
        Otherwise Celeste goes silent first (SpeakerProtocol.stop_speaking), so the
        pilot is not talking over her and the microphone does not record her
        voice. The press of the mic button and of the hotkey both end up here.
        Frames left from an earlier recording are dropped.
        """
        import sounddevice as sd

        if not self.enabled:
            logger.info("STT is disabled. Cannot start recording.")
            raise SttException("STT is disabled. Cannot start recording.")
        if self._recording_stream is not None:
            logger.warning("Recording is already in progress.")
            raise SttException("Recording is already in progress.")
        self.__speaker_protocol.stop_speaking()
        self._recorded_frames = []
        self._recording_stream = sd.InputStream(
            samplerate=_WHISPER_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=self.input_device,
            callback=self._audio_recording_callback,
        )
        self._recording_stream.start()
        logger.info("Audio recording started.")

    def _audio_recording_callback(
        self, indata: np.ndarray, frames: int, time, status
    ) -> None:
        """Called by sounddevice from its audio thread for every chunk. Keeps a
        copy of the first channel, because sounddevice reuses the buffer.
        Problems such as lost input are only logged, recording goes on."""
        if status:
            logger.warning("Audio recording status: %s", status)
        self._recorded_frames.append(indata[:, 0].copy())

    def stop_recording_and_transcribe(self) -> None:
        """Stops the microphone AND turns the recording into text. Blocking
        and slow: it may load Whisper first and then transcribes on this
        thread. Returns nothing, the text comes out of consume_stt_queue().

        1. Raises SttException when no recording runs.
        2. Stops and closes the microphone stream.
        3. No audio captured -> Whisper is not called, nothing is queued.
        4. Loads Whisper if needed (raises SttException when no model is set).
        5. Transcribes with GAME_VOCABULARY_PROMPT, so Whisper spells game
           words like "FSD" and "hardpoints" right.
        6. Puts the text in the STT queue. Nothing is queued when Whisper heard
           no words, or when nobody consumes the queue yet (logged).
        """
        if self._recording_stream is None:
            logger.warning(
                "stop_recording_and_transcribe called but no recording is in progress."
            )
            raise SttException("No recording is in progress.")
        self._recording_stream.stop()
        self._recording_stream.close()
        self._recording_stream = None
        logger.info("Audio recording stopped.")

        if not self._recorded_frames:
            logger.warning("No audio data was captured during the recording.")
            return

        whisper_model = self.load_stt_model()

        audio = np.concatenate(self._recorded_frames)
        self._recorded_frames = []
        result = whisper_model.transcribe(
            audio, fp16=False, initial_prompt=GAME_VOCABULARY_PROMPT
        )
        text: str = result.get("text", "").strip()
        if not text:
            return
        if self._app_loop is None:
            logger.warning("Nobody consumes the STT queue, dropped: %r", text)
            return
        # This runs on a worker or pynput thread, an asyncio queue is not
        # thread safe, so the put is handed to the event loop
        self._app_loop.call_soon_threadsafe(self._stt_queue.put_nowait, text)

    def transcribe_in_background(self) -> None:
        """Called on the pynput thread when the hotkey goes up. Stops the
        recording and transcribes it on a worker thread of the app event loop,
        so the pynput thread comes back at once and the other hotkeys keep
        working. The text comes out of consume_stt_queue(), like for the mic
        button.

        Before the app loop is known (nobody consumes the STT queue yet) it
        does the same on this thread, so the microphone is closed anyway and
        the text is dropped and logged. An error of the transcription is
        logged when the worker thread ends, it is not raised here.
        """
        if self._app_loop is None:
            self.stop_recording_and_transcribe()
            return
        transcription = asyncio.run_coroutine_threadsafe(
            asyncio.to_thread(self.stop_recording_and_transcribe), self._app_loop
        )
        transcription.add_done_callback(self._log_error_of_transcription)

    def _log_error_of_transcription(self, transcription) -> None:
        """Called when the background transcription ends. Logs its error, an
        error of a worker thread would otherwise be lost. A cancelled or
        successful transcription logs nothing."""
        if not transcription.cancelled() and transcription.exception() is not None:
            logger.error(
                "The transcription from the hotkey failed.",
                exc_info=transcription.exception(),
            )

    async def consume_stt_queue(self) -> AsyncGenerator[str, None]:
        """Never ends. Yields every text that stop_recording_and_transcribe()
        puts in the queue, one by one, in the order they were spoken. The
        first call remembers the running event loop, the texts are queued on
        it.

        Exactly one consumer, a queue does not copy items."""
        self._app_loop = asyncio.get_running_loop()
        while True:
            yield await self._stt_queue.get()

    def reload_service(self) -> None:
        """Applies the saved STT settings. Called by cold_start() and after
        the settings change. A new model name or a changed enabled flag drops
        the loaded Whisper model, it is loaded again on the next use. A new
        input device is used from the next recording on. Does not load
        anything itself.

        The push-to-talk key is moved too: the key of the last reload is
        unregistered, then stt.hotkey is registered (None means no hotkey).
        The press of that key calls start_recording() on the pynput thread,
        its release calls transcribe_in_background(). The key is registered
        also when STT is disabled, a press then only logs the error of
        start_recording().
        """
        new_settings = self.__settings_service.get_settings()
        new_model = new_settings.stt.model
        new_enabled = new_settings.stt.enabled
        new_input_device = new_settings.stt.input_device
        if new_model != self.model or new_enabled != self.enabled:
            self.whisper_model = None
        self.enabled = new_enabled
        self.model = new_model
        self.input_device = new_input_device

        if self._hotkey_key_name is not None:
            self.__hotkey_protocol.unregister_hotkey(self._hotkey_key_name)
        self._hotkey_key_name = new_settings.stt.hotkey
        if self._hotkey_key_name is not None:
            self.__hotkey_protocol.register_hotkey(
                Hotkey(
                    key_name=self._hotkey_key_name,
                    on_press=self.start_recording,
                    on_release=self.transcribe_in_background,
                )
            )

    def is_stt_enabled(self) -> bool:
        """Reads the value applied by the last reload_service(), not the
        settings file. True before the first reload."""
        return self.enabled

    def get_stt_models(self) -> list[str]:
        """Every model name Whisper knows, downloaded or not. No network."""
        return whisper.available_models()

    def get_stt_input_devices(self) -> list[tuple[str, int]]:
        """Microphones as (name, sounddevice index), for the settings
        dropdown. Output only devices are left out. The same microphone can
        show up many times (once per Windows audio API), only the first index
        of each name is kept. An empty list means no microphone. An error of
        the sound system (PortAudio) is not caught."""
        import sounddevice as sd

        all_devices = sd.query_devices()
        seen: dict[str, int] = {}
        for index, device in enumerate(all_devices):
            if device["max_input_channels"] > 0 and device["name"] not in seen:
                seen[device["name"]] = index
        return list(seen.items())

    def load_stt_model(self) -> whisper.Whisper:
        """Loads Whisper on the first call and keeps it, later calls return
        the same one. The first load is slow and blocking, and whisper
        downloads the model files from the internet when they are not cached
        yet. Raises SttException when no model name is set."""
        if not self.model:
            logger.warning("STT model is not set. Cannot load model.")
            raise SttException("STT model is not set. Cannot load model.")

        if self.whisper_model is None:
            logger.info("Loading Whisper model '%s' (lazy)...", self.model)
            self.whisper_model = whisper.load_model(self.model)

        return self.whisper_model

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Applies the settings and, when STT is enabled, loads Whisper now,
           so the first push to talk is fast. The load blocks the event loop.
        3. Yields completed. Never raises, an error ends up in the status
           message.
        """
        status = ColdStartStatus(
            service="stt",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status
        try:
            self.reload_service()
            if self.enabled:
                self.load_stt_model()
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
