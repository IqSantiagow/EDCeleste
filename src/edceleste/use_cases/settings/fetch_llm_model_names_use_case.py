from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.services.models.settings_model import LLMProviderModel


class FetchLlmModelNamesUseCase:
    def __init__(self, llm_protocol: LLMProtocol):
        self.llm_protocol = llm_protocol

    async def __call__(
        self, provider_settings: LLMProviderModel | None = None
    ) -> list[str]:
        """Goes to the network and asks the provider for its model list.
        provider_settings may be the values still being edited on the
        settings screen. Without them the saved provider is used. An empty
        list means "we do not know", not "no models"."""
        return await self.llm_protocol.fetch_available_model_names(provider_settings)
