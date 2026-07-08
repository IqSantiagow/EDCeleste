import asyncio
from collections.abc import AsyncGenerator

from protocols.journal_watcher_protocol import JournalWatcherProtocol

POLL_INTERVAL_SECONDS = 5.0


class JournalGetHealthCheckUseCase:
    def __init__(self, journal_watcher_reader: JournalWatcherProtocol):
        self.journal_watcher_reader = journal_watcher_reader

    async def __call__(self) -> AsyncGenerator[bool, None]:
        while True:
            yield self.journal_watcher_reader.get_journal_healthcheck()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
