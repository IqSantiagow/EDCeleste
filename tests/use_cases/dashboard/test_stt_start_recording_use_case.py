import unittest

from use_cases.dashboard.stt_start_recording_use_case import SttStartRecordingUseCase


class FakeSttProtocol:
    def __init__(self) -> None:
        self.start_recording_calls: int = 0

    def start_recording(self) -> None:
        self.start_recording_calls += 1


class TestSttStartRecordingUseCase(unittest.TestCase):
    def test_should_delegate_to_stt_protocol(self):
        stt = FakeSttProtocol()
        use_case = SttStartRecordingUseCase(stt)  # type: ignore

        use_case()

        self.assertEqual(stt.start_recording_calls, 1)

    def test_should_delegate_each_call_separately(self):
        stt = FakeSttProtocol()
        use_case = SttStartRecordingUseCase(stt)  # type: ignore

        use_case()
        use_case()

        self.assertEqual(stt.start_recording_calls, 2)


if __name__ == "__main__":
    unittest.main()
