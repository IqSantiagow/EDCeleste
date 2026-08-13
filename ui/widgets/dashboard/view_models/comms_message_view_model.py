from dataclasses import dataclass

from services.models.llm_response import LLMResponse, LLMResponseSource


@dataclass
class CommsMessageViewModel:
    content: str
    is_user_message: bool
    is_action: bool
    is_system_message: bool = False

    @classmethod
    def from_protocol_message(cls, message: LLMResponse) -> "CommsMessageViewModel":

        return cls(
            content=message.message,
            is_user_message=False,
            is_action=False,
            is_system_message=message.source == LLMResponseSource.SYSTEM,
        )  # hardcoded for now

    @classmethod
    def from_user_message(cls, message: str) -> "CommsMessageViewModel":
        return cls(content=message, is_user_message=True, is_action=False)
