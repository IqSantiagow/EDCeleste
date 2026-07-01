from typing import Protocol


class JournalWatcherReader(Protocol):
    def get_journal_healthcheck(self) -> bool: ...
