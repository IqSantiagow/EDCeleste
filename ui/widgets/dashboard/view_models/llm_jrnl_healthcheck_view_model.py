from dataclasses import dataclass


@dataclass(slots=True)
class LlmJrnlHealthCheckViewModel:
    llm_healthcheck: bool
    journal_healthcheck: bool

    @classmethod
    def empty(cls) -> "LlmJrnlHealthCheckViewModel":
        return cls(llm_healthcheck=False, journal_healthcheck=False)
