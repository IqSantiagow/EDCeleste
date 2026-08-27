import unittest

from use_cases.dashboard.llm_send_message_use_case import LLMSendMessageUseCase


class FakeLLMProtocol:
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.calls: list[str] = []

    def add_llm_request_to_queue(self, message: str) -> None:
        self.calls.append(message)
        if self._error is not None:
            raise self._error


class TestLLMSendMessageUseCase(unittest.TestCase):
    def test_should_forward_message_to_llm_protocol(self):
        llm = FakeLLMProtocol()
        use_case = LLMSendMessageUseCase(llm)  # type: ignore

        use_case("Where am I?")

        self.assertEqual(llm.calls, ["Where am I?"])

    def test_should_propagate_exception_from_llm_protocol(self):
        llm = FakeLLMProtocol(error=RuntimeError("boom"))
        use_case = LLMSendMessageUseCase(llm)  # type: ignore

        with self.assertRaises(RuntimeError):
            use_case("Hello")


if __name__ == "__main__":
    unittest.main()
