import asyncio
from datetime import datetime
from typing import AsyncGenerator, override

from services.event_bus import EventBus
from services.journal_watcher_service import JournalWatcherService
from services.models.game_events import (
    DockedEvent,
    DockingGrantedEvent,
    FSDJumpEvent,
    FuelScoopEvent,
    GameEvent,
    LoadedGameEvent,
    LocationEvent,
    StartJumpEvent,
    UndockedEvent,
)
from services.models.game_models import (
    BaseFactionModel,
    FactionModel,
    StationEconomyModel,
)
from services.settings_service import SettingsService


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
            ),
            StartJumpEvent(
                event="StartJump",
                timestamp=datetime(2024, 1, 1, 12, 1, 0),
                JumpType="Hyperspace",
                Taxi=False,
                StarSystem="Sol",
                SystemAddress=1,
                StarClass="G",
            ),
            FSDJumpEvent(
                event="FSDJump",
                timestamp=datetime(2024, 1, 1, 12, 2, 0),
                StarSystem="Alpha Centauri",
                SystemAddress=2,
                StarPos=[0.0, 0.0, 0.0],
                SystemAllegiance="Independent",
                SystemEconomy_Localised="Industrial",
                SystemSecondEconomy_Localised="Refinery",
                SystemGovernment_Localised="Democracy",
                SystemSecurity_Localised="High",
                Population=1000,
                JumpDist=4.2,
                FuelUsed=0.5,
                FuelLevel=0.5,
                Factions=[
                    FactionModel(
                        Name="Test Faction",
                        Government="Democracy",
                        Influence=0.5,
                        Allegiance="Independent",
                        MyReputation=10.0,
                    )
                ],
                SystemFaction=BaseFactionModel(Name="Test Faction"),
            ),
            DockedEvent(
                event="Docked",
                timestamp=datetime(2024, 1, 1, 12, 3, 0),
                StarSystem="Alpha Centauri",
                StationName="Hutton Orbital",
                StationType="Coriolis Starport",
                SystemAddress=2,
                MarketID=12345,
                StationFaction=BaseFactionModel(Name="Test Faction"),
                StationGovernment_Localised="Democracy",
                StationAllegiance="Independent",
                StationServices=["dock", "market"],
                StationEconomy_Localised="Industrial",
                StationEconomies=[
                    StationEconomyModel(Name_Localised="Industrial", Proportion=1.0)
                ],
                DistFromStarLS=12.3,
            ),
            UndockedEvent(
                event="Undocked",
                timestamp=datetime(2024, 1, 1, 12, 4, 0),
                StationName="Hutton Orbital",
            ),
            FuelScoopEvent(
                event="FuelScoop",
                timestamp=datetime(2024, 1, 1, 12, 5, 0),
                Scooped=1.5,
                Total=2.0,
            ),
            DockingGrantedEvent(
                event="DockingGranted",
                timestamp=datetime(2024, 1, 1, 12, 6, 0),
                StationName="Hutton Orbital",
                StationType="Coriolis Starport",
                MarketID=12345,
                LandingPad=42,
            ),
            LocationEvent(
                event="Location",
                timestamp=datetime(2024, 1, 1, 12, 7, 0),
                StarSystem="Sol",
                SystemAddress=1,
                StarPos=[0.0, 0.0, 0.0],
                DistFromStarLS=0.0,
                Docked=True,
                StationName="Galileo",
                StationType="Coriolis Starport",
                MarketID=67890,
                StationFaction=BaseFactionModel(Name="Test Faction"),
                StationGovernment_Localised="Democracy",
                StationAllegiance="Federation",
                StationEconomy_Localised="High Tech",
                StationEconomies=[
                    StationEconomyModel(Name_Localised="High Tech", Proportion=1.0)
                ],
                SystemAllegiance="Federation",
                SystemEconomy_Localised="High Tech",
                SystemSecondEconomy_Localised="Industrial",
                SystemGovernment_Localised="Democracy",
                SystemSecurity_Localised="High",
                Population=10000000000,
                Body="Earth",
                BodyID=1,
                BodyType="Planet",
                ControllingPower="None",
                Powers=[],
                PowerplayState=None,
                Factions=[],
                SystemFaction=BaseFactionModel(Name="Federation"),
            ),
        ]

        for event in list_of_events:
            await asyncio.sleep(0.1)  # Simulate a delay between events
            yield event
