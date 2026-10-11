import asyncio

from edceleste.protocols.instinct_protocol import InstinctProtocol
from edceleste.protocols.llm_protocol import LLMProtocol


class SendPilotMessageUseCase:
    def __init__(
        self, instinct_protocol: InstinctProtocol, llm_protocol: LLMProtocol
    ) -> None:
        """Only stores the dependencies and an empty set that keeps the running
        tasks alive (the event loop holds only a weak reference to a task)."""
        self.instinct_protocol = instinct_protocol
        self.llm_protocol = llm_protocol
        self.running_tasks: set[asyncio.Task] = set()

    def __call__(self, message: str) -> None:
        """Returns at once, the message is handled in a background task (send).
        Needs a running event loop, without one create_task raises RuntimeError.
        The reply comes later from StreamLLMResponsesUseCase, whoever handled
        the message. Nobody receives an error of the task, asyncio only logs
        it. Every message gets its own task, so when one message waits for
        Instinct, the order of two quickly sent messages is not guaranteed."""
        task = asyncio.create_task(self.send(message))
        # The loop keeps only a weak reference to a task, so we keep it alive
        self.running_tasks.add(task)
        task.add_done_callback(self.running_tasks.discard)

    async def send(self, message: str) -> None:
        """Instinct goes first. When it returns a reply (a key was pressed, or
        the game window was not found), the reply goes to COMMS and the history,
        and the LLM is not called. Otherwise (it returned None, it never raises)
        the message goes to the LLM queue as before."""
        reply = await self.instinct_protocol.try_fast_command(message)
        if reply is None:
            self.llm_protocol.add_llm_request_to_queue(message)
        else:
            self.llm_protocol.add_reply_without_llm_to_queue(message, reply)
