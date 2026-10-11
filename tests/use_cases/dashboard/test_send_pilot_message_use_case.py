import asyncio
import unittest

from edceleste.use_cases.dashboard.send_pilot_message_use_case import (
    SendPilotMessageUseCase,
)


class FakeInstinct:
    def __init__(self, reply: str | None):
        self.reply = reply
        self.asked: list[str] = []

    async def try_fast_command(self, pilot_message: str) -> str | None:
        self.asked.append(pilot_message)
        return self.reply


class FakeLLM:
    def __init__(self):
        self.requests: list[str] = []
        self.replies_without_llm: list[tuple[str, str]] = []

    def add_llm_request_to_queue(self, message: str) -> None:
        self.requests.append(message)

    def add_reply_without_llm_to_queue(self, pilot_message: str, reply: str) -> None:
        self.replies_without_llm.append((pilot_message, reply))


class TestSendPilotMessageUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_send_the_message_to_the_llm_when_instinct_skips_it(
        self,
    ):
        instinct = FakeInstinct(reply=None)
        llm = FakeLLM()
        use_case = SendPilotMessageUseCase(instinct, llm)  # type: ignore

        await use_case.send("Where am I?")

        self.assertEqual(instinct.asked, ["Where am I?"])
        self.assertEqual(llm.requests, ["Where am I?"])
        self.assertEqual(llm.replies_without_llm, [])

    async def test_should_queue_the_reply_without_llm_when_instinct_handles_it(
        self,
    ):
        instinct = FakeInstinct(reply="Done: Landing gear toggle")
        llm = FakeLLM()
        use_case = SendPilotMessageUseCase(instinct, llm)  # type: ignore

        await use_case.send("deploy landing gear")

        self.assertEqual(llm.requests, [])
        self.assertEqual(
            llm.replies_without_llm,
            [("deploy landing gear", "Done: Landing gear toggle")],
        )

    async def test_call_returns_at_once_and_sends_the_message_in_a_task(self):
        instinct = FakeInstinct(reply=None)
        llm = FakeLLM()
        use_case = SendPilotMessageUseCase(instinct, llm)  # type: ignore

        result = use_case("Where am I?")

        # Nothing ran yet: the task is only scheduled
        self.assertIsNone(result)
        self.assertEqual(llm.requests, [])
        self.assertEqual(len(use_case.running_tasks), 1)
        await asyncio.gather(*use_case.running_tasks)
        self.assertEqual(llm.requests, ["Where am I?"])

    async def test_finished_task_is_forgotten(self):
        use_case = SendPilotMessageUseCase(FakeInstinct(reply=None), FakeLLM())  # type: ignore

        use_case("Where am I?")
        await asyncio.gather(*use_case.running_tasks)
        await asyncio.sleep(0)  # the done callback runs on the next loop turn

        self.assertEqual(use_case.running_tasks, set())


if __name__ == "__main__":
    unittest.main()
