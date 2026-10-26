import asyncio
import ctypes
import itertools
import logging
import queue
import sys
import threading
import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine

import numpy as np

from edceleste.services.models.service_status import ServiceState, ServiceStatus
from edceleste.services.service_status_stream import ServiceStatusStream

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import sounddevice as sd

# The speaker gets audio in slices of this length, so a stop is heard at once
SPEAKER_WRITE_SECONDS = 0.05


@dataclass(order=True)
class QueuedSpeech:
    """One thing Celeste is going to say, waiting in the speech queue. The queue
    sorts by priority and then by order_number (the order of arrival), the other
    fields are not compared."""

    priority: int
    order_number: int
    speak: Callable[[], Coroutine[Any, Any, None]] = field(compare=False)
    # Done when the speech has been played, dropped or has failed
    finished: asyncio.Future = field(compare=False)
    enqueued_at: float = field(compare=False, default_factory=time.monotonic)
    max_wait_seconds: float | None = field(compare=False, default=None)

    def has_waited_too_long(self) -> bool:
        """True when max_wait_seconds is set and the speech has been in the queue
        for longer. Always False for a speech with no limit."""
        if self.max_wait_seconds is None:
            return False
        return time.monotonic() - self.enqueued_at > self.max_wait_seconds

    def finish(self, error: BaseException | None = None) -> None:
        """Marks the speech as done: with the error when there is one, otherwise
        with the result None. Does nothing when the future is already done, which
        happens when whoever waits for it was cancelled (cancelling a waiter
        cancels the future). Setting a done future would raise and kill the
        worker of the speech queue."""
        if self.finished.done():
            return
        if error is None:
            self.finished.set_result(None)
        else:
            self.finished.set_exception(error)


class SpeakerService:
    def __init__(self) -> None:
        """Only makes the empty speech queue and the stop flag. The worker that
        plays the queue starts on the first queue_speech(). Knows no settings
        and no voice: it plays the audio it is given. The status of TTS for the
        app header starts as OK "Nothing played yet", because the speaker has
        nothing to check before the first speech."""
        self.__speech_queue: asyncio.PriorityQueue[QueuedSpeech] = (
            asyncio.PriorityQueue()
        )
        self.__status_stream = ServiceStatusStream(
            ServiceStatus(ServiceState.OK, "Nothing played yet")
        )
        self.__speech_order_numbers = itertools.count()
        self.__speech_worker: asyncio.Task | None = None
        self.__speech_loop: asyncio.AbstractEventLoop | None = None
        # Set by stop_speaking() (from any thread), cleared before every speech
        # starts. The playing thread and the loop that feeds it look at it.
        self.__stop_playing = threading.Event()

    def stream_status(self) -> AsyncGenerator[ServiceStatus, None]:
        """The status of TTS for the app header (ServiceStatusProtocol). Starts
        as OK "Nothing played yet". After every speech that was played to the
        end it is OK, after a speech that raised an error it is ERROR with the
        error. A speech that was dropped (waited too long, or stop_speaking())
        changes nothing."""
        return self.__status_stream.stream_latest_status_then_every_new_one()

    def queue_speech(
        self,
        speak: Callable[[], Coroutine[Any, Any, None]],
        priority: int,
        max_wait_seconds: float | None = None,
    ) -> asyncio.Future:
        """Puts speak in the speech queue and returns a future that is done when
        the speech has been played, dropped (waited longer than max_wait_seconds,
        or stop_speaking() was called) or has failed. A dropped speech ends its
        future with the result None, never with an exception, so whoever waits
        for it just continues. An error of speak ends up in the future and in
        the log, once.

        The first call starts the worker (__run_speech_queue_worker) on the running
        event loop, so it needs one (RuntimeError otherwise)."""
        if self.__speech_worker is None:
            self.__speech_loop = asyncio.get_running_loop()
            self.__speech_worker = asyncio.create_task(self.__run_speech_queue_worker())

        finished = asyncio.get_running_loop().create_future()
        finished.add_done_callback(self.__log_error_of_speech)
        self.__speech_queue.put_nowait(
            QueuedSpeech(
                priority=priority,
                order_number=next(self.__speech_order_numbers),
                speak=speak,
                finished=finished,
                max_wait_seconds=max_wait_seconds,
            )
        )
        return finished

    async def play_clip(self, samples: np.ndarray, sample_rate: int) -> None:
        """Plays the whole audio on the speaker and returns when it has played,
        or when stop_speaking() cut it. Only for code run by queue_speech().
        samples are mono or stereo floats between -1 and 1.

        1. Puts the whole audio as one piece, and then None (the end), in a
           queue for the player.
        2. Runs __write_pieces_to_speaker() in a worker thread, the same way as
           for a streamed voice, and waits for it.
        Raises sounddevice.PortAudioError when no speaker can be opened."""
        pieces_for_player: queue.Queue[np.ndarray | None] = queue.Queue()
        pieces_for_player.put(samples)
        pieces_for_player.put(None)
        await asyncio.to_thread(
            self.__write_pieces_to_speaker, pieces_for_player, sample_rate
        )

    async def play_pieces_from(
        self, pieces: AsyncIterator[np.ndarray], sample_rate: int
    ) -> None:
        """Starts a player thread (__write_pieces_to_speaker) and feeds it with
        every piece that comes out of the iterator, as it comes, so the voice is
        made while the first part of it is already playing. Puts None after the
        last piece and waits for the player.

        When stop_speaking() was called, the loop stops asking the iterator for
        more pieces. Also when the iterator fails: the player is told that
        nothing more comes, that error is raised and an error of the player is
        dropped. An error of the player (sounddevice.PortAudioError, e.g. no
        speaker can be opened) is raised only at the end, after the whole voice
        was made, because the player is awaited last."""
        pieces_for_player: queue.Queue[np.ndarray | None] = queue.Queue()
        player = asyncio.create_task(
            asyncio.to_thread(
                self.__write_pieces_to_speaker, pieces_for_player, sample_rate
            )
        )
        # When the iterator fails first, its error is raised and the player is
        # never awaited. Reading the exception of the player here keeps asyncio
        # from warning that it was never retrieved.
        player.add_done_callback(lambda task: task.cancelled() or task.exception())

        try:
            async for piece in pieces:
                if self.__stop_playing.is_set():
                    break
                pieces_for_player.put(piece)
        finally:
            pieces_for_player.put(None)
        await player

    def stop_speaking(self) -> None:
        """Sets the stop flag at once, the player thread cuts the sound within
        one slice (SPEAKER_WRITE_SECONDS) and the loop that feeds it stops. Then
        drops everything waiting in the queue (every dropped speech counts as
        done). Does not touch the queue before the first queue_speech().

        Safe from any thread (the push-to-talk hotkey calls it from the keyboard
        thread). An asyncio queue belongs to its loop, so from another thread
        the dropping is handed to the loop and happens a moment later. On the
        loop itself it happens at once, so a speech queued right after this call
        is not dropped."""
        self.__stop_playing.set()
        if self.__speech_loop is None:
            return
        try:
            is_on_speech_loop = asyncio.get_running_loop() is self.__speech_loop
        except RuntimeError:
            is_on_speech_loop = False
        if is_on_speech_loop:
            self.__drop_waiting_speech()
        else:
            self.__speech_loop.call_soon_threadsafe(self.__drop_waiting_speech)

    def __drop_waiting_speech(self) -> None:
        """Empties the speech queue, every dropped speech counts as done. Must
        run on the event loop of the queue. The speech that is playing is not
        touched here, it ends by itself when it sees the stop flag."""
        while not self.__speech_queue.empty():
            self.__speech_queue.get_nowait().finish()

    def __log_error_of_speech(self, finished: asyncio.Future) -> None:
        """Called when the future of a queued speech is done. Logs the error of
        the speech with its traceback at ERROR level, because most callers do
        not wait for the future and the error would be lost. Logs nothing for a
        speech that went well, and nothing for a cancelled future (a waiter that
        was cancelled cancels it)."""
        if not finished.cancelled() and finished.exception() is not None:
            logger.error("Celeste could not speak.", exc_info=finished.exception())

    async def __run_speech_queue_worker(self) -> None:
        """Never ends, one task for the whole app. Takes the speech with the
        smallest priority number from the queue (the oldest first), clears the
        stop flag, says it until the end and takes the next one. A speech is
        never played over another one and never cut by a more important one.

        A speech that waited longer than its max_wait_seconds is dropped
        (logged), it is not played. The error of a speech goes to its future
        and the loop goes on. A speech cut by stop_speaking() just ends sooner
        and counts as done."""
        while True:
            speech = await self.__speech_queue.get()
            if speech.has_waited_too_long():
                logger.info("Celeste dropped a speech that waited too long.")
                speech.finish()
                continue

            self.__stop_playing.clear()
            try:
                await speech.speak()
            except Exception as error:
                self.__status_stream.set_status(
                    ServiceState.ERROR, f"Celeste could not speak: {error}"
                )
                speech.finish(error)
            else:
                self.__status_stream.set_status(
                    ServiceState.OK, "The last speech was played"
                )
                speech.finish()

    def __write_pieces_to_speaker(
        self, pieces: "queue.Queue[np.ndarray | None]", sample_rate: int
    ) -> None:
        """Plays the audio that arrives in the queue, as it arrives, and returns
        after the last piece was played, when None arrives. Blocking: runs in a
        worker thread. The one place where any voice meets the hardware.

        Every piece is mono (samples) or stereo (samples x 2) float32. A mono
        piece is played from both speakers. An empty piece (a provider may make
        one) is skipped, because a write of zero samples to a speaker is not
        worth the risk of an error of the driver. When the next piece is late,
        the speaker plays silence. The speaker is closed when the function ends,
        also after an error. The queue has no size limit, and without the None
        at the end the function waits for it for ever.

        A piece is written to the speaker in slices of SPEAKER_WRITE_SECONDS,
        and the stop flag is checked before every slice. When it is set, the
        speaker is aborted (what it still holds is thrown away), the rest of the
        audio is dropped and the function returns.

        Raises sounddevice.PortAudioError when no speaker can be opened."""
        slice_length = int(sample_rate * SPEAKER_WRITE_SECONDS)
        with self.__open_speaker(sample_rate) as speaker:
            while (piece := pieces.get()) is not None:
                if len(piece) == 0:
                    continue
                if piece.ndim == 1:
                    piece = np.stack([piece, piece], axis=1)
                piece = np.ascontiguousarray(piece, dtype=np.float32)
                for start in range(0, len(piece), slice_length):
                    if self.__stop_playing.is_set():
                        speaker.abort()
                        return
                    speaker.write(piece[start : start + slice_length])

    def __open_speaker(self, sample_rate: int) -> "sd.OutputStream":
        """Opens a stereo float32 speaker with low latency, not started yet. The
        caller uses it as a context manager, which starts it and closes it. On
        Windows it is WASAPI, with about 40 ms of delay, where the default way
        (MME) has about 200 ms. WASAPI needs COM started in the thread that
        opens it, and a worker thread has none, so COM is started here (and
        stays started for the life of the thread). When WASAPI cannot be opened,
        or is not on the list, the default speaker is used, and a failed WASAPI
        is logged as a warning. On other systems it is always the default
        speaker. Raises sounddevice.PortAudioError when the default speaker
        cannot be opened either."""
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
