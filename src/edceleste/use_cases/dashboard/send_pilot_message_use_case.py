import asyncio
import logging

from edceleste.protocols.instinct_protocol import InstinctProtocol
from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.protocols.tts_protocol import TTSProtocol

logger = logging.getLogger(__name__)


class SendPilotMessageUseCase:
    def __init__(
        self,
        instinct_protocol: InstinctProtocol,
        llm_protocol: LLMProtocol,
        tts_protocol: TTSProtocol,
    ) -> None:
        """Only stores the dependencies and an empty set that keeps the running
        tasks alive (the event loop holds only a weak reference to a task)."""
        self.instinct_protocol = instinct_protocol
        self.llm_protocol = llm_protocol
        self.tts_protocol = tts_protocol
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
        """Instinct goes first (try_fast_command, it never raises).

        1. Instinct returned None: the message goes to the LLM queue
           (add_llm_request_to_queue) as before, nothing is spoken here. An
           error of that queue is not handled here.
        2. Instinct returned a reply. It can be "a key was pressed", but also a
           refusal ("Landing gear unavailable"), "Game actions disabled" or "Game
           window not found, nothing was pressed.". The LLM is not called. The
           text goes to COMMS and the conversation history with
           add_reply_without_llm_to_queue, before any speech, so it is on the
           screen before it is said.
        3. A reply with is_spoken False (the game state says the same by itself
           a moment later, when Status.json shows the change, e.g. "Landing gear
           deployed") stops here, or the pilot would hear it twice.
        4. Otherwise TTSProtocol.speak_reply says the text (the prepared clip
           when there is one, otherwise live) and send returns when the speech
           is over. It says nothing when the switch tts.play_ship_replies is
           off. An error of the speech (the voice model failed, no speaker) is
           logged and not raised, the same as the speech of an LLM reply: the
           reply stays in COMMS and the key was already pressed."""
        reply = await self.instinct_protocol.try_fast_command(message)
        if reply is None:
            self.llm_protocol.add_llm_request_to_queue(message)
            return

        self.llm_protocol.add_reply_without_llm_to_queue(message, reply.text)
        if not reply.is_spoken:
            return
        try:
            await self.tts_protocol.speak_reply(reply.text)
        except Exception:
            logger.exception("Celeste could not say the reply %r", reply.text)
