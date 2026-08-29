from collections.abc import AsyncGenerator
from typing import Protocol

from edceleste.services.models.llm_stream_item import LLMStreamItem
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel


class LLMProtocol(Protocol):
    def add_llm_request_to_queue(self, message: str) -> None: ...

    def consume_llm_queue(self) -> AsyncGenerator[LLMStreamItem, None]:
        """The stream has exactly one consumer - a queue does not duplicate items."""
        ...

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None: ...

    def reload_service(self) -> None: ...
