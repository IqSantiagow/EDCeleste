from collections.abc import AsyncGenerator

from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.services.models.llm_status import LLMStatus
from edceleste.ui.screens.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)

CommsStreamItem = CommsMessageViewModel | LLMStatus


class StreamLLMResponsesUseCase:
    def __init__(self, llm_protocol: LLMProtocol) -> None:
        self.llm_protocol = llm_protocol

    async def __call__(self) -> AsyncGenerator[CommsStreamItem, None]:
        """Never ends. Takes the LLM reply stream and turns it into COMMS rows.
        LLMStatus (thinking / idle) goes through as it is. Blocks COMMS does
        not show are dropped, e.g. thinking and tool results without an
        error.

        Only one caller may run it, the LLM queue does not copy items for a
        second listener.
        """
        async for item in self.llm_protocol.consume_llm_queue():
            if isinstance(item, LLMStatus):
                yield item
                continue

            comms_message = CommsMessageViewModel.from_message_block(item)

            if comms_message is not None:
                yield comms_message
