from dataclasses import dataclass

from services.models.llm_response import LLMResponse


@dataclass
class CommsMessageViewModel:
    content: str
    is_user_message: bool
    is_action: bool

    @classmethod
    def from_protocol_message(cls, message: LLMResponse) -> "CommsMessageViewModel":
        return cls(
            content=message.message.message, is_user_message=False, is_action=False
        )  # hardcoded for now

    @classmethod
    def from_user_message(cls, message: str) -> "CommsMessageViewModel":
        return cls(content=message, is_user_message=True, is_action=False)
