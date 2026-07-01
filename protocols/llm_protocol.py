from typing import Protocol


class LLMProtocol(Protocol):
    def get_llm_healthcheck(self) -> bool: ...
