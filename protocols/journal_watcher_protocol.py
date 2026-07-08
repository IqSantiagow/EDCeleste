from typing import Protocol


class JournalWatcherProtocol(Protocol):
    def get_journal_healthcheck(self) -> bool: ...
