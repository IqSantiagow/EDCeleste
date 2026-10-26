import asyncio
import gc
import sys
import threading
import time
import unittest
from unittest.mock import Mock, call, patch

import numpy as np

from edceleste.protocols.speaker_protocol import PRIORITY_ANSWER, PRIORITY_REACTION
from edceleste.services import speaker_service
from edceleste.services.models.service_status import ServiceState, ServiceStatus
from edceleste.services.speaker_service import SpeakerService

SAMPLE_RATE = 1000  # one slice of the speaker (50 ms) is 50 samples


class FakePortAudioError(Exception):
    """Stands for sounddevice.PortAudioError, the error of a speaker that cannot be
    opened."""


class FakeDevice:
    """A speaker that remembers what it was given. It writes to the shared log of
    the test, so the order of speaker and speech events can be checked."""

    def __init__(self, log: list[str], seconds_per_write: float = 0.0):
        self.log = log
        self.seconds_per_write = seconds_per_write
        self.writes: list[np.ndarray] = []
        self.is_closed = threading.Event()
        self.was_aborted = False
        self.after_each_write = None

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        self.log.append("device closed")
        self.is_closed.set()

    def write(self, piece):
        self.writes.append(piece)
        time.sleep(self.seconds_per_write)
        if self.after_each_write is not None:
            self.after_each_write()

    def abort(self):
        self.was_aborted = True
        self.log.append("device aborted")


class SpeakerServiceTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = SpeakerService()
        self.log: list[str] = []
        self.device = FakeDevice(self.log)
        self.opened_sample_rates: list[int] = []

        def open_fake_device(sample_rate):
            self.opened_sample_rates.append(sample_rate)
            return self.device

        # The real speaker needs a sound card, name mangling because the method is
        # private
        self.service._SpeakerService__open_speaker = open_fake_device

    def _speech(self, name: str, gate: asyncio.Event | None = None, error=None):
        """A speech that writes "start <name>" and "end <name>" to the log. With a
        gate it waits for it in between, with an error it raises it instead of
        ending."""

        async def speak():
            self.log.append(f"start {name}")
            if gate is not None:
                await gate.wait()
            if error is not None:
                raise error
            self.log.append(f"end {name}")

        return speak

    async def _let_the_worker_run(self):
        for _ in range(5):
            await asyncio.sleep(0)

    async def _wait_until(self, condition, timeout: float = 2.0):
        started_at = time.monotonic()
        while not condition():
            if time.monotonic() - started_at > timeout:
                self.fail("The condition did not come true in time.")
            await asyncio.sleep(0.005)

    def _play_clip_speech(self, name: str, sample_count: int):
        async def speak():
            self.log.append(f"start {name}")
            await self.service.play_clip(
                np.full(sample_count, 0.1, dtype=np.float32), SAMPLE_RATE
            )
            self.log.append(f"end {name}")

        return speak


class SpeechQueueTest(SpeakerServiceTestCase):
    async def test_speeches_play_one_after_another_in_the_order_they_came(self):
        self.service.queue_speech(self._speech("a"), PRIORITY_ANSWER)
        self.service.queue_speech(self._speech("b"), PRIORITY_ANSWER)
        last = self.service.queue_speech(self._speech("c"), PRIORITY_ANSWER)

        await last

        self.assertEqual(
            self.log,
            ["start a", "end a", "start b", "end b", "start c", "end c"],
        )

    async def test_an_answer_goes_before_a_waiting_reaction(self):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("first", gate), PRIORITY_ANSWER)
        reaction = self.service.queue_speech(
            self._speech("reaction"), PRIORITY_REACTION
        )
        answer = self.service.queue_speech(self._speech("answer"), PRIORITY_ANSWER)
        await self._let_the_worker_run()

        gate.set()
        await asyncio.gather(reaction, answer)

        self.assertEqual(
            [line for line in self.log if line.startswith("start")],
            ["start first", "start answer", "start reaction"],
        )

    async def test_a_speech_that_is_playing_is_not_cut_by_an_answer(self):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("reaction", gate), PRIORITY_REACTION)
        await self._let_the_worker_run()

        answer = self.service.queue_speech(self._speech("answer"), PRIORITY_ANSWER)
        await self._let_the_worker_run()
        self.assertEqual(self.log, ["start reaction"])

        gate.set()
        await answer

        self.assertEqual(
            self.log, ["start reaction", "end reaction", "start answer", "end answer"]
        )

    async def test_a_reaction_that_waited_too_long_is_dropped_and_not_played(self):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("answer", gate), PRIORITY_ANSWER)
        stale = self.service.queue_speech(
            self._speech("reaction"), PRIORITY_REACTION, max_wait_seconds=0.05
        )
        await asyncio.sleep(0.15)

        gate.set()
        await stale

        self.assertNotIn("start reaction", self.log)
        self.assertTrue(stale.done())

    async def test_a_reaction_that_waited_less_than_its_limit_is_played(self):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("answer", gate), PRIORITY_ANSWER)
        reaction = self.service.queue_speech(
            self._speech("reaction"), PRIORITY_REACTION, max_wait_seconds=5.0
        )
        await self._let_the_worker_run()

        gate.set()
        await reaction

        self.assertIn("end reaction", self.log)

    async def test_a_speech_without_a_limit_never_expires(self):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("answer", gate), PRIORITY_ANSWER)
        waiting = self.service.queue_speech(
            self._speech("waiting"), PRIORITY_REACTION, max_wait_seconds=None
        )
        await asyncio.sleep(0.1)

        gate.set()
        await waiting

        self.assertIn("end waiting", self.log)

    async def test_the_future_is_done_with_none_after_the_speech_is_played(self):
        finished = self.service.queue_speech(self._speech("a"), PRIORITY_ANSWER)

        result = await finished

        self.assertIsNone(result)
        self.assertEqual(self.log, ["start a", "end a"])

    async def test_an_error_of_a_speech_goes_to_its_future_and_the_next_one_plays(
        self,
    ):
        broken = self.service.queue_speech(
            self._speech("broken", error=RuntimeError("no speaker")), PRIORITY_ANSWER
        )
        next_speech = self.service.queue_speech(self._speech("next"), PRIORITY_ANSWER)

        with self.assertLogs("edceleste.services.speaker_service", "ERROR"):
            with self.assertRaisesRegex(RuntimeError, "no speaker"):
                await broken
        await next_speech

        self.assertIn("end next", self.log)

    async def test_an_error_of_a_speech_nobody_waits_for_is_logged_once(self):
        broken = self.service.queue_speech(
            self._speech("broken", error=RuntimeError("no speaker")), PRIORITY_ANSWER
        )

        with self.assertLogs("edceleste.services.speaker_service", "ERROR") as logs:
            await asyncio.wait([broken])
            await asyncio.sleep(0)  # the done callback runs on the next loop turn

        self.assertEqual(len(logs.records), 1)
        self.assertIsNotNone(logs.records[0].exc_info)

    async def test_a_cancelled_waiter_does_not_kill_the_speech_queue(self):
        gate = asyncio.Event()
        finished = self.service.queue_speech(
            self._speech("first", gate), PRIORITY_ANSWER
        )

        async def wait_for_the_speech():
            await finished

        waiter = asyncio.create_task(wait_for_the_speech())
        await self._let_the_worker_run()
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        self.assertTrue(finished.cancelled())

        gate.set()
        after = self.service.queue_speech(self._speech("after"), PRIORITY_ANSWER)
        await asyncio.wait_for(after, timeout=2)

        self.assertIn("end after", self.log)

    async def test_stop_speaking_with_a_cancelled_waiter_in_the_queue_does_not_fail(
        self,
    ):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("first", gate), PRIORITY_ANSWER)
        waiting = self.service.queue_speech(self._speech("waiting"), PRIORITY_ANSWER)
        await self._let_the_worker_run()
        waiting.cancel()

        self.service.stop_speaking()

        self.assertTrue(waiting.cancelled())
        gate.set()


class SpeakerStatusTest(SpeakerServiceTestCase):
    async def _latest_status(self) -> ServiceStatus:
        """The status a new listener of stream_status() gets at once."""
        stream = self.service.stream_status()
        try:
            return await asyncio.wait_for(stream.__anext__(), timeout=1)
        finally:
            await stream.aclose()

    async def test_status_is_ok_before_anything_was_played(self):
        status = await self._latest_status()

        self.assertEqual(status, ServiceStatus(ServiceState.OK, "Nothing played yet"))

    async def test_status_is_ok_after_a_speech_was_played(self):
        await self.service.queue_speech(self._speech("a"), PRIORITY_ANSWER)

        status = await self._latest_status()

        self.assertEqual(
            status, ServiceStatus(ServiceState.OK, "The last speech was played")
        )

    async def test_status_is_error_with_the_error_after_a_speech_failed(self):
        broken = self.service.queue_speech(
            self._speech("broken", error=RuntimeError("no speaker")), PRIORITY_ANSWER
        )

        with self.assertLogs("edceleste.services.speaker_service", "ERROR"):
            with self.assertRaises(RuntimeError):
                await broken
        status = await self._latest_status()

        self.assertEqual(
            status,
            ServiceStatus(ServiceState.ERROR, "Celeste could not speak: no speaker"),
        )

    async def test_a_dropped_speech_does_not_change_the_status(self):
        gate = asyncio.Event()
        broken = self.service.queue_speech(
            self._speech("broken", gate, error=RuntimeError("no speaker")),
            PRIORITY_ANSWER,
        )
        stale = self.service.queue_speech(
            self._speech("reaction"), PRIORITY_REACTION, max_wait_seconds=0.05
        )
        await asyncio.sleep(0.15)

        gate.set()
        with self.assertLogs("edceleste.services.speaker_service", "ERROR"):
            with self.assertRaises(RuntimeError):
                await broken
        await stale
        status = await self._latest_status()

        self.assertNotIn("start reaction", self.log)
        self.assertEqual(
            status,
            ServiceStatus(ServiceState.ERROR, "Celeste could not speak: no speaker"),
        )


class StopSpeakingTest(SpeakerServiceTestCase):
    async def test_stop_speaking_drops_every_waiting_speech_and_finishes_its_future(
        self,
    ):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("first", gate), PRIORITY_ANSWER)
        second = self.service.queue_speech(self._speech("second"), PRIORITY_ANSWER)
        third = self.service.queue_speech(self._speech("third"), PRIORITY_REACTION)
        await self._let_the_worker_run()

        self.service.stop_speaking()

        self.assertTrue(second.done())
        self.assertTrue(third.done())
        gate.set()
        await self._let_the_worker_run()
        self.assertEqual(self.log, ["start first", "end first"])

    async def test_a_speech_queued_after_stop_speaking_is_played(self):
        self.service.stop_speaking()
        finished = self.service.queue_speech(
            self._play_clip_speech("clip", 100), PRIORITY_ANSWER
        )

        await finished

        self.assertEqual(sum(len(piece) for piece in self.device.writes), 100)
        self.assertFalse(self.device.was_aborted)

    async def test_a_speech_queued_right_after_stop_speaking_on_the_loop_is_not_dropped(
        self,
    ):
        first = self.service.queue_speech(self._speech("first"), PRIORITY_ANSWER)
        await first

        self.service.stop_speaking()
        after = self.service.queue_speech(self._speech("after"), PRIORITY_ANSWER)
        await asyncio.wait_for(after, timeout=2)

        self.assertIn("end after", self.log)

    async def test_stop_speaking_from_another_thread_drops_the_waiting_speeches(self):
        gate = asyncio.Event()
        self.service.queue_speech(self._speech("first", gate), PRIORITY_ANSWER)
        waiting = self.service.queue_speech(self._speech("waiting"), PRIORITY_ANSWER)
        await self._let_the_worker_run()

        await asyncio.to_thread(self.service.stop_speaking)
        await asyncio.wait_for(waiting, timeout=2)

        gate.set()
        await self._let_the_worker_run()
        self.assertNotIn("start waiting", self.log)

    def test_stop_speaking_before_any_speech_does_nothing(self):
        SpeakerService().stop_speaking()

    async def test_the_cut_speech_stops_the_speaker_and_the_next_one_waits_for_it(
        self,
    ):
        self.device.seconds_per_write = 0.02
        cut = self.service.queue_speech(
            self._play_clip_speech("long", 1000), PRIORITY_ANSWER
        )
        await self._wait_until(lambda: len(self.device.writes) >= 2)

        self.service.stop_speaking()
        after = self.service.queue_speech(self._speech("after"), PRIORITY_ANSWER)
        await asyncio.wait_for(asyncio.gather(cut, after), timeout=2)

        self.assertTrue(self.device.was_aborted)
        self.assertLess(len(self.device.writes), 20)
        self.assertLess(self.log.index("device closed"), self.log.index("start after"))


class PlayClipTest(SpeakerServiceTestCase):
    async def test_play_clip_writes_the_audio_in_slices_and_closes_the_speaker(self):
        await self.service.play_clip(np.full(120, 0.1, dtype=np.float32), SAMPLE_RATE)

        self.assertEqual([len(piece) for piece in self.device.writes], [50, 50, 20])
        self.assertEqual(self.opened_sample_rates, [SAMPLE_RATE])
        self.assertTrue(self.device.is_closed.is_set())

    async def test_a_mono_clip_is_played_from_both_speakers(self):
        await self.service.play_clip(
            np.array([0.1, 0.2, 0.3], dtype=np.float32), SAMPLE_RATE
        )

        np.testing.assert_allclose(
            self.device.writes[0],
            np.array([[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]], dtype=np.float32),
        )

    async def test_a_stereo_float64_clip_is_written_as_contiguous_float32(self):
        stereo_float64_not_contiguous = np.asfortranarray(
            np.array([[0.1, 0.4], [0.2, 0.5]], dtype=np.float64)
        )

        await self.service.play_clip(stereo_float64_not_contiguous, SAMPLE_RATE)

        written = self.device.writes[0]
        self.assertEqual(written.dtype, np.float32)
        self.assertTrue(written.flags["C_CONTIGUOUS"])
        np.testing.assert_allclose(written, [[0.1, 0.4], [0.2, 0.5]])

    async def test_the_stop_flag_aborts_the_speaker_and_drops_the_rest_of_the_clip(
        self,
    ):
        self.device.after_each_write = self.service.stop_speaking

        await self.service.play_clip(np.full(500, 0.1, dtype=np.float32), SAMPLE_RATE)

        self.assertEqual(len(self.device.writes), 1)
        self.assertTrue(self.device.was_aborted)
        self.assertTrue(self.device.is_closed.is_set())


class PlayPiecesFromTest(SpeakerServiceTestCase):
    async def test_every_piece_is_played_in_the_order_it_came(self):
        async def pieces():
            for value in (0.1, 0.2, 0.3):
                yield np.full(50, value, dtype=np.float32)

        await self.service.play_pieces_from(pieces(), SAMPLE_RATE)

        self.assertEqual(
            [float(piece[0, 0]) for piece in self.device.writes],
            [np.float32(0.1), np.float32(0.2), np.float32(0.3)],
        )
        self.assertTrue(self.device.is_closed.is_set())

    async def test_an_empty_piece_is_skipped(self):
        async def pieces():
            yield np.array([0.1, 0.2], dtype=np.float32)
            yield np.zeros(0, dtype=np.float32)
            yield np.array([0.3], dtype=np.float32)

        await self.service.play_pieces_from(pieces(), SAMPLE_RATE)

        self.assertEqual([len(piece) for piece in self.device.writes], [2, 1])

    async def test_the_voice_is_not_asked_for_more_after_stop_speaking(self):
        asked_for: list[int] = []

        async def pieces():
            for number in range(1, 6):
                if number == 2:
                    self.service.stop_speaking()
                asked_for.append(number)
                yield np.full(10, 0.1, dtype=np.float32)

        await self.service.play_pieces_from(pieces(), SAMPLE_RATE)

        self.assertEqual(asked_for, [1, 2])

    async def test_an_error_of_the_voice_is_raised_and_the_speaker_gets_the_end(self):
        async def pieces():
            yield np.full(10, 0.1, dtype=np.float32)
            raise RuntimeError("GPU out of memory")

        with self.assertRaisesRegex(RuntimeError, "GPU out of memory"):
            await self.service.play_pieces_from(pieces(), SAMPLE_RATE)

        closed = await asyncio.to_thread(self.device.is_closed.wait, 2)
        self.assertTrue(closed)

    async def test_an_error_of_the_speaker_is_raised_at_the_end(self):
        def cannot_open_speaker(sample_rate):
            raise FakePortAudioError("no speaker")

        self.service._SpeakerService__open_speaker = cannot_open_speaker

        async def pieces():
            yield np.full(10, 0.1, dtype=np.float32)

        with self.assertRaisesRegex(FakePortAudioError, "no speaker"):
            await self.service.play_pieces_from(pieces(), SAMPLE_RATE)

    async def test_an_unread_error_of_the_speaker_does_not_upset_asyncio(
        self,
    ):
        def cannot_open_speaker(sample_rate):
            raise FakePortAudioError("no speaker")

        self.service._SpeakerService__open_speaker = cannot_open_speaker
        loop_complaints = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: loop_complaints.append(context["message"])
        )

        async def pieces():
            yield np.full(10, 0.1, dtype=np.float32)
            raise RuntimeError("GPU out of memory")

        with self.assertRaisesRegex(RuntimeError, "GPU out of memory"):
            await self.service.play_pieces_from(pieces(), SAMPLE_RATE)
        await asyncio.sleep(0.2)  # the player thread fails and its task ends
        gc.collect()  # asyncio complains when a failed task is collected unread

        self.assertEqual(loop_complaints, [])


class OpenSpeakerTest(unittest.TestCase):
    def setUp(self):
        self.service = SpeakerService()
        self.sounddevice = Mock()
        self.sounddevice.PortAudioError = FakePortAudioError
        sounddevice_patch = patch.dict(sys.modules, {"sounddevice": self.sounddevice})
        sounddevice_patch.start()
        self.addCleanup(sounddevice_patch.stop)

    def _set_up_windows_with_wasapi(self, wasapi_listed=True):
        host_apis = [{"name": "MME", "default_output_device": 1}]
        if wasapi_listed:
            host_apis.append({"name": "Windows WASAPI", "default_output_device": 7})
        self.sounddevice.query_hostapis.return_value = host_apis

    def _open_speaker(self, sample_rate: int):
        return self.service._SpeakerService__open_speaker(sample_rate)

    def test_uses_wasapi_with_low_latency_on_windows(self):
        self._set_up_windows_with_wasapi()

        with (
            patch.object(speaker_service.sys, "platform", "win32"),
            patch.object(speaker_service, "ctypes") as ctypes,
        ):
            speaker = self._open_speaker(24000)

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

    def test_falls_back_to_the_default_speaker_when_wasapi_fails(self):
        self._set_up_windows_with_wasapi()
        self.sounddevice.OutputStream.side_effect = [
            FakePortAudioError("device busy"),
            "the default speaker",
        ]

        with (
            patch.object(speaker_service.sys, "platform", "win32"),
            patch.object(speaker_service, "ctypes"),
            self.assertLogs(speaker_service.logger, level="WARNING"),
        ):
            speaker = self._open_speaker(24000)

        self.assertEqual(speaker, "the default speaker")
        self.assertEqual(
            self.sounddevice.OutputStream.call_args_list[1],
            call(samplerate=24000, channels=2, dtype="float32", latency="low"),
        )

    def test_uses_the_default_speaker_when_windows_has_no_wasapi(self):
        self._set_up_windows_with_wasapi(wasapi_listed=False)

        with (
            patch.object(speaker_service.sys, "platform", "win32"),
            patch.object(speaker_service, "ctypes") as ctypes,
        ):
            self._open_speaker(24000)

        self.sounddevice.OutputStream.assert_called_once_with(
            samplerate=24000, channels=2, dtype="float32", latency="low"
        )
        ctypes.windll.ole32.CoInitializeEx.assert_not_called()

    def test_uses_the_default_speaker_on_other_systems(self):
        # WASAPI is on the list, so only the system tells the code not to use it
        self._set_up_windows_with_wasapi()

        with patch.object(speaker_service.sys, "platform", "linux"):
            self._open_speaker(24000)

        self.sounddevice.OutputStream.assert_called_once_with(
            samplerate=24000, channels=2, dtype="float32", latency="low"
        )
        self.sounddevice.WasapiSettings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
