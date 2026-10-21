import unittest

from edceleste.use_cases.dashboard.stt_stop_recording_use_case import (
    SttStopRecordingUseCase,
)


class FakeSttProtocol:
    def __init__(self) -> None:
        self.stop_recording_and_transcribe_calls: int = 0

    def stop_recording_and_transcribe(self) -> None:
        self.stop_recording_and_transcribe_calls += 1


class TestSttStopRecordingUseCase(unittest.TestCase):
    def test_should_stop_recording_through_stt_protocol_and_return_nothing(self):
        stt = FakeSttProtocol()
        use_case = SttStopRecordingUseCase(stt)  # type: ignore

        result = use_case()

        self.assertIsNone(result)
        self.assertEqual(stt.stop_recording_and_transcribe_calls, 1)


if __name__ == "__main__":
    unittest.main()
