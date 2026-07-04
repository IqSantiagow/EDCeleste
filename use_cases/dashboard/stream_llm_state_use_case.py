from collections.abc import AsyncGenerator

from protocols.llm_protocol import LLMProtocol
from services.models.llm_response import LLMStatus


class StreamLLMStateUseCase:
    def __init__(self, llm_protocol: LLMProtocol) -> None:
        self.llm_protocol = llm_protocol

    async def __call__(self) -> AsyncGenerator[LLMStatus, None]:
        async for status in self.llm_protocol.stream_llm_status():
            yield status
