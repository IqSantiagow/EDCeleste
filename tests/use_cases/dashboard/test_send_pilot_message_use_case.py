import asyncio
import unittest

from edceleste.services.models.fast_command_reply import FastCommandReply
from edceleste.use_cases.dashboard.send_pilot_message_use_case import (
    SendPilotMessageUseCase,
)


class FakeInstinct:
    def __init__(self, reply: FastCommandReply | None, order: list[str] | None = None):
        self.reply = reply
        self.asked: list[str] = []
        self.order = order if order is not None else []

    async def try_fast_command(self, pilot_message: str) -> FastCommandReply | None:
        self.order.append("instinct")
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


class FakeTTS:
    def __init__(self):
        self.queued: list[str] = []

    def queue_reply_to_pilot(self, text: str) -> None:
        self.queued.append(text)


class FakeSpeaker:
    def __init__(self, order: list[str] | None = None):
        self.stop_count = 0
        self.order = order if order is not None else []

    def stop_speaking(self) -> None:
        self.order.append("stop")
        self.stop_count += 1


def _make_use_case(
    instinct: FakeInstinct,
    llm: FakeLLM | None = None,
    tts: FakeTTS | None = None,
    speaker: FakeSpeaker | None = None,
) -> SendPilotMessageUseCase:
    return SendPilotMessageUseCase(
        instinct,  # type: ignore
        llm or FakeLLM(),  # type: ignore
        tts or FakeTTS(),  # type: ignore
        speaker or FakeSpeaker(),  # type: ignore
    )


class TestSendPilotMessageUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_send_the_message_to_the_llm_when_instinct_skips_it(
        self,
    ):
        instinct = FakeInstinct(reply=None)
        llm = FakeLLM()
        tts = FakeTTS()
        use_case = _make_use_case(instinct, llm, tts)

        await use_case.send("Where am I?")

        self.assertEqual(instinct.asked, ["Where am I?"])
        self.assertEqual(llm.requests, ["Where am I?"])
        self.assertEqual(llm.replies_without_llm, [])
        self.assertEqual(tts.queued, [])

    async def test_should_queue_the_reply_without_llm_when_instinct_handles_it(
        self,
    ):
        instinct = FakeInstinct(reply=FastCommandReply("Throttle zero"))
        llm = FakeLLM()
        use_case = _make_use_case(instinct, llm)

        await use_case.send("stop the ship")

        self.assertEqual(llm.requests, [])
        self.assertEqual(
            llm.replies_without_llm,
            [("stop the ship", "Throttle zero")],
        )

    async def test_should_queue_the_same_text_that_goes_to_comms(self):
        llm = FakeLLM()
        tts = FakeTTS()
        use_case = _make_use_case(
            FakeInstinct(FastCommandReply("Throttle zero")), llm, tts
        )

        await use_case.send("stop the ship")

        self.assertEqual(tts.queued, ["Throttle zero"])
        self.assertEqual(llm.replies_without_llm[0][1], tts.queued[0])

    async def test_should_write_but_not_queue_a_reply_the_game_state_says(self):
        llm = FakeLLM()
        tts = FakeTTS()
        use_case = _make_use_case(
            FakeInstinct(FastCommandReply("Landing gear deployed", is_spoken=False)),
            llm,
            tts,
        )

        await use_case.send("deploy landing gear")

        self.assertEqual(
            llm.replies_without_llm,
            [("deploy landing gear", "Landing gear deployed")],
        )
        self.assertEqual(tts.queued, [])

    async def test_should_put_the_reply_in_comms_before_it_is_queued_for_speech(self):
        llm = FakeLLM()

        class TTSThatChecksComms(FakeTTS):
            def queue_reply_to_pilot(self, text: str) -> None:
                self.comms_had_the_reply = bool(llm.replies_without_llm)

        tts = TTSThatChecksComms()
        use_case = _make_use_case(FakeInstinct(FastCommandReply("Boosting")), llm, tts)

        await use_case.send("boost")

        self.assertTrue(tts.comms_had_the_reply)

    async def test_should_make_celeste_go_silent_before_asking_instinct(self):
        order: list[str] = []
        use_case = _make_use_case(
            FakeInstinct(FastCommandReply("Boosting"), order),
            speaker=FakeSpeaker(order),
        )

        await use_case.send("boost")

        self.assertEqual(order, ["stop", "instinct"])

    async def test_should_make_celeste_go_silent_when_the_message_goes_to_the_llm(
        self,
    ):
        speaker = FakeSpeaker()
        use_case = _make_use_case(FakeInstinct(reply=None), speaker=speaker)

        await use_case.send("Where am I?")

        self.assertEqual(speaker.stop_count, 1)

    async def test_should_make_celeste_go_silent_once_for_every_message(self):
        speaker = FakeSpeaker()
        use_case = _make_use_case(FakeInstinct(reply=None), speaker=speaker)

        await use_case.send("first")
        await use_case.send("second")

        self.assertEqual(speaker.stop_count, 2)

    async def test_call_returns_at_once_and_sends_the_message_in_a_task(self):
        instinct = FakeInstinct(reply=None)
        llm = FakeLLM()
        use_case = _make_use_case(instinct, llm)

        result = use_case("Where am I?")

        # Nothing ran yet: the task is only scheduled
        self.assertIsNone(result)
        self.assertEqual(llm.requests, [])
        self.assertEqual(len(use_case.running_tasks), 1)
        await asyncio.gather(*use_case.running_tasks)
        self.assertEqual(llm.requests, ["Where am I?"])

    async def test_finished_task_is_forgotten(self):
        use_case = _make_use_case(FakeInstinct(reply=None))

        use_case("Where am I?")
        await asyncio.gather(*use_case.running_tasks)
        await asyncio.sleep(0)  # the done callback runs on the next loop turn

        self.assertEqual(use_case.running_tasks, set())


if __name__ == "__main__":
    unittest.main()
