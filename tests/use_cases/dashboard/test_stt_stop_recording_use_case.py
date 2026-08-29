import unittest

from edceleste.use_cases.dashboard.stt_stop_recording_use_case import (
    SttStopRecordingUseCase,
)


class FakeSttProtocol:
    def __init__(self, transcription: str | None) -> None:
        self._transcription = transcription
        self.stop_recording_calls: int = 0

    def stop_recording(self) -> str | None:
        self.stop_recording_calls += 1
        return self._transcription


class TestSttStopRecordingUseCase(unittest.TestCase):
    def test_should_return_transcription_from_stt_protocol(self):
        stt = FakeSttProtocol(transcription="Turn on the engines")
        use_case = SttStopRecordingUseCase(stt)  # type: ignore

        result = use_case()

        self.assertEqual(result, "Turn on the engines")
        self.assertEqual(stt.stop_recording_calls, 1)

    def test_should_return_none_when_stt_protocol_returns_none(self):
        stt = FakeSttProtocol(transcription=None)
        use_case = SttStopRecordingUseCase(stt)  # type: ignore

        result = use_case()

        self.assertIsNone(result)
        self.assertEqual(stt.stop_recording_calls, 1)


if __name__ == "__main__":
    unittest.main()
