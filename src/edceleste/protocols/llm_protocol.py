from typing import Protocol

from collections.abc import AsyncGenerator

from edceleste.protocols.base_service_protocol import BaseServiceProtocol
from edceleste.services.models.llm_stream_item import LLMStreamItem
from edceleste.services.models.settings_model import (
    LLMProviderModel,
    SettingsIssueModel,
    SettingsModel,
)


class LLMProtocol(BaseServiceProtocol, Protocol):
    def add_llm_request_to_queue(self, message: str) -> None:
        """Only puts the message in the queue and returns at once. The reply
        comes later out of consume_llm_queue()."""
        ...

    def consume_llm_queue(self) -> AsyncGenerator[LLMStreamItem, None]:
        """Never ends. For every queued message it yields LLMStatus.THINKING,
        the reply blocks and LLMStatus.IDLE. A failed turn comes as a
        SystemMessage, the stream goes on.

        The stream has exactly one consumer - a queue does not duplicate items.
        """
        ...

    async def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Checks the provider type and model of settings that are not saved
        yet. Goes to the network for the model list. Changes nothing in the
        service. None means fine."""
        ...

    def reload_service(self) -> None:
        """Builds a new agent from the saved settings. Keeps the conversation
        history and the queue. Does not go to the network, so a wrong API key
        shows up only on the first request."""
        ...

    async def fetch_available_model_names(
        self, provider_settings: LLMProviderModel | None = None
    ) -> list[str]:
        """Asks the provider for its models over the network. Without
        provider_settings the saved provider is used. An empty list means "we
        do not know", not "no models"."""
        ...

    async def find_connection_error(
        self, provider_settings: LLMProviderModel
    ) -> str | None:
        """Sends one real test request to the provider (costs a few tokens).
        Uses provider_settings, not the saved settings, so values can be tested
        before saving. Returns None when the provider answers, otherwise a
        short error text for the screen, with the API key hidden. Never
        raises."""
        ...
