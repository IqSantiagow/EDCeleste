from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.services.models.settings_model import LLMProviderModel


class FindLlmConnectionErrorUseCase:
    def __init__(self, llm_protocol: LLMProtocol):
        self.llm_protocol = llm_protocol

    async def __call__(self, provider_settings: LLMProviderModel) -> str | None:
        """Goes to the network and sends one real request to the provider
        (costs a few tokens), using the values still being edited, so they
        can be checked before saving. Returns None when the provider answers,
        otherwise a short error text for the screen. Never raises."""
        return await self.llm_protocol.find_connection_error(provider_settings)
