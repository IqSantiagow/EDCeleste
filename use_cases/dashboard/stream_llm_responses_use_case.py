from collections.abc import AsyncGenerator

from protocols.llm_protocol import LLMProtocol
from services.models.llm_status import LLMStatus
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)

CommsStreamItem = CommsMessageViewModel | LLMStatus


class StreamLLMResponsesUseCase:
    def __init__(self, llm_protocol: LLMProtocol) -> None:
        self.llm_protocol = llm_protocol

    async def __call__(self) -> AsyncGenerator[CommsStreamItem, None]:
        async for item in self.llm_protocol.consume_llm_queue():
            if isinstance(item, LLMStatus):
                yield item
                continue

            comms_message = CommsMessageViewModel.from_message_block(item)

            if comms_message is not None:
                yield comms_message
