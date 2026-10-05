from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.services.models.settings_model import LLMProviderModel


class TestLlmConnectionUseCase:
    # Not a test, the name only starts with "Test" - tells pytest to skip it
    __test__ = False

    def __init__(self, llm_protocol: LLMProtocol):
        self.llm_protocol = llm_protocol

    async def __call__(self, provider: LLMProviderModel) -> str | None:
        return await self.llm_protocol.test_connection(provider)
