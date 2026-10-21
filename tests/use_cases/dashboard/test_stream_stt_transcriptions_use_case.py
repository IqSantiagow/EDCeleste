import unittest

from edceleste.use_cases.dashboard.stream_stt_transcriptions_use_case import (
    StreamSttTranscriptionsUseCase,
)


class FakeSttProtocol:
    def __init__(self, stream) -> None:
        self._stream = stream

    def consume_stt_queue(self):
        return self._stream


class TestStreamSttTranscriptionsUseCase(unittest.IsolatedAsyncioTestCase):
    def test_should_return_the_stream_of_the_stt_protocol(self):
        stream = object()
        use_case = StreamSttTranscriptionsUseCase(FakeSttProtocol(stream))  # type: ignore

        self.assertIs(use_case(), stream)

    async def test_should_give_texts_from_the_queue_one_by_one(self):
        async def spoken_texts():
            yield "deploy landing gear"
            yield "open the cargo scoop"

        use_case = StreamSttTranscriptionsUseCase(
            FakeSttProtocol(spoken_texts())  # type: ignore
        )

        texts = [text async for text in use_case()]

        self.assertEqual(texts, ["deploy landing gear", "open the cargo scoop"])


if __name__ == "__main__":
    unittest.main()
