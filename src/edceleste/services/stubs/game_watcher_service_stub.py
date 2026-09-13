import asyncio
from datetime import datetime
from typing import override

from edceleste.services.event_bus import EventBus
from edceleste.services.game_watcher_service import GameWatcherService
from edceleste.services.models.game_events import LoadedGameEvent

from edceleste.services.settings_service import SettingsService


class GameWatcherServiceStub(GameWatcherService):
    def __init__(self, event_bus: EventBus, settings_handler: SettingsService):
        super().__init__(
            journal_path="", event_bus=event_bus, settings_handler=settings_handler
        )

    @override
    def start_watcher_service(self):
        self._game_watcher_tasks.append(
            asyncio.create_task(self.__generate_journal_events())
        )

    async def __generate_journal_events(self) -> None:
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
            await self.event_bus.publish(event)
