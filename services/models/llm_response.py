from enum import Enum

from pydantic import BaseModel, Field, PrivateAttr


class LLMResponseSource(Enum):
    """Represents the source of the LLM response"""

    SYSTEM = "system"
    LLM = "llm"


class LLMResponse(BaseModel):
    """Represents a response from the LLM"""

    message: str = Field(description="The message content from the LLM")
    _source: LLMResponseSource = PrivateAttr(default=LLMResponseSource.LLM)

    @property
    def source(self) -> LLMResponseSource:
        return self._source

    @source.setter
    def source(self, value: LLMResponseSource) -> None:
        self._source = value


class LLMStatus(Enum):
    THINKING = "thinking"
    IDLE = "idle"
