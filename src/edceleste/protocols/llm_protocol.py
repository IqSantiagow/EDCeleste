from collections.abc import AsyncGenerator

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.llm_stream_item import LLMStreamItem
from edceleste.services.models.settings_model import (
    LLMProviderModel,
    SettingsIssueModel,
    SettingsModel,
)


class LLMProtocol(BaseServiceProtocol):
    def add_llm_request_to_queue(self, message: str) -> None: ...

    def consume_llm_queue(self) -> AsyncGenerator[LLMStreamItem, None]:
        """The stream has exactly one consumer - a queue does not duplicate items."""
        ...

    async def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...

    async def get_models(
        self, provider: LLMProviderModel | None = None
    ) -> list[str]: ...
