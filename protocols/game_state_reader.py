from typing import AsyncGenerator, Protocol


class GameStateReader(Protocol):
    def get_dashboard_stats(self) -> dict: ...

    def stream_dashboard_stats(self) -> AsyncGenerator[dict[str, str], None]: ...
