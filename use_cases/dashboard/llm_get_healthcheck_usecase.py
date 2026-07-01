import asyncio
from collections.abc import AsyncGenerator

from protocols.llm_protocol import LLMProtocol

POLL_INTERVAL_SECONDS = 5.0


class LlmGetHealthCheckUseCase:
    def __init__(self, llm_protocol: LLMProtocol):
        self.llm_protocol = llm_protocol

    async def __call__(self) -> AsyncGenerator[bool, None]:
        while True:
            yield await asyncio.to_thread(self.llm_protocol.get_llm_healthcheck)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
