from collections.abc import AsyncGenerator

from protocols.llm_protocol import LLMProtocol
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class StreamLLMResponsesUseCase:
    def __init__(self, llm_protocol: LLMProtocol) -> None:
        self.llm_protocol = llm_protocol

    async def __call__(self) -> AsyncGenerator[CommsMessageViewModel, None]:
        async for response in self.llm_protocol.stream_responses():
            yield CommsMessageViewModel.from_protocol_message(response)
