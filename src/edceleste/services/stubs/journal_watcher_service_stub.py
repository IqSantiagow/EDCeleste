import asyncio
from datetime import datetime
from typing import AsyncGenerator, override

from edceleste.services.event_bus import EventBus
from edceleste.services.journal_watcher_service import JournalWatcherService
from edceleste.services.models.game_events import (
    GameEvent,
    LoadedGameEvent,
)

from edceleste.services.settings_service import SettingsService


class JournalWatcherServiceStub(JournalWatcherService):
    def __init__(self, event_bus: EventBus, settings_handler: SettingsService):
        super().__init__(
            journal_path="", event_bus=event_bus, settings_handler=settings_handler
        )

    @override
    def start_watcher_service(self):
        async def watch_journal_task():
            async for event in self.__generate_journal_events():
                await self.event_bus.publish(event)

        self._journal_watcher_task = asyncio.create_task(watch_journal_task())

    async def __generate_journal_events(self) -> AsyncGenerator[GameEvent, None]:
        list_of_events = [
            LoadedGameEvent(
                event="LoadGame",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                Commander="TestCommander",
                FID="F123456",
                Horizons=True,
                Odyssey=False,
                Ship="Sidewinder",
                ShipID=1,
                StartLanded=False,
                StartDead=False,
                GameMode="Solo",
                Group="",
                Credits=1000000,
                Loan=0,
                ShipName="Test Ship",
                ShipIdent="TS-001",
                FuelLevel=1.0,
                FuelCapacity=4.0,
            )
        ]

        for event in list_of_events:
            yield event
