import unittest

from use_cases.dashboard.stt_transcribe_audio_use_case import SttTranscribeAudioUseCase


class FakeSttProtocol:
    def __init__(self, transcription: str | None):
        self._transcription = transcription
        self.calls: list[str] = []

    def handle_stt_request(self, audio_path: str) -> str | None:
        self.calls.append(audio_path)
        return self._transcription

    def validate_settings(self, new_settings):
        raise NotImplementedError

    def reload_service(self) -> None:
        raise NotImplementedError


class TestSttTranscribeAudioUseCase(unittest.TestCase):
    def test_should_forward_audio_path_to_stt_protocol_and_return_transcribed_text(
        self,
    ):
        stt = FakeSttProtocol(transcription="Turn on the engines")
        use_case = SttTranscribeAudioUseCase(stt)  # type: ignore

        result = use_case("turn_on_the_engines_sample.mp3")

        self.assertEqual(result, "Turn on the engines")
        self.assertEqual(stt.calls, ["turn_on_the_engines_sample.mp3"])

    def test_should_return_none_when_stt_protocol_returns_none(self):
        stt = FakeSttProtocol(transcription=None)
        use_case = SttTranscribeAudioUseCase(stt)  # type: ignore

        result = use_case("silent.mp3")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
