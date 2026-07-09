from enum import Enum

from pydantic import Field, BaseModel


class LLMMessage(BaseModel):
    """Represents a message from the LLM"""

    message: str = Field(description="The message content from the LLM")


class LLMAction(BaseModel):
    """Represents an action from the LLM"""

    # TODO: Implement action types and their parameters
    action: str


class LLMResponse(BaseModel):
    """Represents a response from the LLM"""

    message: LLMMessage


class LLMStatus(Enum):
    THINKING = "thinking"
    IDLE = "idle"
