import unittest

from use_cases.dashboard.llm_send_message_use_case import LLMSendMessageUseCase


class FakeGameStateReader:
    def __init__(self, projection: str = ""):
        self._projection = projection

    def get_game_state_projection(self) -> str:
        return self._projection


class FakeLLMProtocol:
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.calls: list[tuple[str, str]] = []

    async def send_message(self, message: str, game_state: str) -> None:
        self.calls.append((message, game_state))
        if self._error is not None:
            raise self._error


class TestLLMSendMessageUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_read_game_state_and_forward_message_with_state(self):
        reader = FakeGameStateReader(projection="Current game state is: docked")
        llm = FakeLLMProtocol()
        use_case = LLMSendMessageUseCase(llm, reader)  # type: ignore

        await use_case("Where am I?")

        self.assertEqual(llm.calls, [("Where am I?", "Current game state is: docked")])

    async def test_should_forward_empty_game_state(self):
        reader = FakeGameStateReader(projection="")
        llm = FakeLLMProtocol()
        use_case = LLMSendMessageUseCase(llm, reader)  # type: ignore

        await use_case("Hello")

        self.assertEqual(llm.calls, [("Hello", "")])

    async def test_should_propagate_exception_from_llm_protocol(self):
        reader = FakeGameStateReader()
        llm = FakeLLMProtocol(error=RuntimeError("boom"))
        use_case = LLMSendMessageUseCase(llm, reader)  # type: ignore

        with self.assertRaises(RuntimeError):
            await use_case("Hello")


if __name__ == "__main__":
    unittest.main()
