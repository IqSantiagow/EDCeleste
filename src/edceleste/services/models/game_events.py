from datetime import datetime
from enum import IntFlag
from typing import Literal, Optional

from edceleste.services.models.game_models import (
    FactionModel,
    BaseFactionModel,
    StationEconomyModel,
)
from edceleste.services.models.pydantic_base_models import IgnoreExtraFieldsModel


class GameEvent(IgnoreExtraFieldsModel):
    timestamp: datetime


class LoadedGameEvent(GameEvent):
    event: Literal["LoadGame"]
    Commander: str
    FID: str
    Horizons: bool
    Odyssey: bool
    Ship: str
    Ship_Localised: Optional[str] = None
    ShipID: int
    StartLanded: Optional[bool] = None
    StartDead: Optional[bool] = None
    GameMode: str
    Group: Optional[str] = None
    Credits: int
    Loan: int
    ShipName: str
    ShipIdent: str
    FuelLevel: float
    FuelCapacity: float


class LoadoutFuelCapacityModel(IgnoreExtraFieldsModel):
    Main: float
    Reserve: float


class LoadoutModuleModel(IgnoreExtraFieldsModel):
    Slot: str
    Item: str
    On: bool
    Priority: int
    Health: float = 1.0


class LoadoutEvent(GameEvent):
    event: Literal["Loadout"]
    Ship: str
    ShipID: int
    ShipName: str
    ShipIdent: str
    HullValue: int = 0
    ModulesValue: int = 0
    HullHealth: float = 1.0
    UnladenMass: float
    CargoCapacity: int
    MaxJumpRange: float
    FuelCapacity: LoadoutFuelCapacityModel
    Rebuy: int
    Modules: list[LoadoutModuleModel] = []


class FSDJumpEvent(GameEvent):
    event: Literal["FSDJump"]
    StarSystem: str
    SystemAddress: int
    StarPos: list[float]
    SystemAllegiance: str
    SystemEconomy_Localised: str
    SystemSecondEconomy_Localised: str
    SystemGovernment_Localised: str
    SystemSecurity_Localised: str
    Population: int
    JumpDist: float
    FuelUsed: float
    FuelLevel: float
    Factions: list[FactionModel] = []
    SystemFaction: Optional[BaseFactionModel] = None


class DockedEvent(GameEvent):
    event: Literal["Docked"]
    StarSystem: str
    StationName: str
    StationType: str
    SystemAddress: int
    MarketID: int
    StationFaction: BaseFactionModel
    StationGovernment_Localised: str
    StationAllegiance: Optional[str] = None
    StationServices: list[str]
    StationEconomy_Localised: str
    StationEconomies: list[StationEconomyModel]
    DistFromStarLS: float


class UndockedEvent(GameEvent):
    event: Literal["Undocked"]
    StationName: str


class FuelScoopEvent(GameEvent):
    event: Literal["FuelScoop"]
    Scooped: float
    Total: float


class DockingGrantedEvent(GameEvent):
    event: Literal["DockingGranted"]
    StationName: str
    StationType: str
    MarketID: int
    LandingPad: int


class StartJumpEvent(GameEvent):
    event: Literal["StartJump"]
    JumpType: str
    Taxi: bool
    # StarSystem/SystemAddress are only present for the "Hyperspace" variant;
    # the "Supercruise" variant omits them, so both must be optional.
    StarSystem: Optional[str] = None
    SystemAddress: Optional[int] = None
    StarClass: Optional[str] = None


class FSDTargetEvent(GameEvent):
    event: Literal["FSDTarget"]
    Name: str
    SystemAddress: int
    StarClass: str
    RemainingJumpsInRoute: int


class LocationEvent(GameEvent):
    event: Literal["Location"]
    StarSystem: str
    SystemAddress: int
    StarPos: list[float]
    DistFromStarLS: float
    Docked: bool
    StationName: Optional[str] = None
    StationType: Optional[str] = None
    MarketID: Optional[int] = None
    StationFaction: Optional[BaseFactionModel] = None
    StationGovernment_Localised: Optional[str] = None
    StationAllegiance: Optional[str] = None
    StationEconomy_Localised: Optional[str] = None
    StationEconomies: list[StationEconomyModel] = []
    SystemAllegiance: Optional[str] = None
    SystemEconomy_Localised: Optional[str] = None
    SystemSecondEconomy_Localised: Optional[str] = None
    SystemGovernment_Localised: Optional[str] = None
    SystemSecurity_Localised: Optional[str] = None
    Population: Optional[int] = None
    Body: Optional[str] = None
    BodyID: Optional[int] = None
    BodyType: Optional[str] = None
    ControllingPower: Optional[str] = None
    Powers: list[str] = []
    PowerplayState: Optional[str] = None
    Factions: list[FactionModel] = []
    SystemFaction: Optional[BaseFactionModel] = None


class SupercruiseEntryEvent(GameEvent):
    event: Literal["SupercruiseEntry"]
    StarSystem: str
    SystemAddress: int


class SupercruiseExitEvent(GameEvent):
    event: Literal["SupercruiseExit"]
    StarSystem: str
    SystemAddress: int
    Body: str
    BodyID: int
    BodyType: str


class SupercruiseDestinationDropEvent(GameEvent):
    event: Literal["SupercruiseDestinationDrop"]
    Type: str
    Type_Localised: Optional[str] = None
    Threat: int
    MarketID: Optional[int] = None


class ApproachBodyEvent(GameEvent):
    event: Literal["ApproachBody"]
    StarSystem: str
    SystemAddress: int
    Body: str
    BodyID: int


class LeaveBodyEvent(GameEvent):
    event: Literal["LeaveBody"]
    StarSystem: str
    SystemAddress: int
    Body: str
    BodyID: int


class ApproachSettlementEvent(GameEvent):
    event: Literal["ApproachSettlement"]
    Name: str
    SystemAddress: int
    BodyID: Optional[int] = None
    BodyName: Optional[str] = None
    Latitude: Optional[float] = None
    Longitude: Optional[float] = None


class ReservoirReplenishedEvent(GameEvent):
    event: Literal["ReservoirReplenished"]
    FuelMain: float
    FuelReservoir: float


class RefuelAllEvent(GameEvent):
    event: Literal["RefuelAll"]
    Cost: int
    Amount: float


class CommanderEvent(GameEvent):
    event: Literal["Commander"]
    FID: str
    Name: str


class RankEvent(GameEvent):
    event: Literal["Rank"]
    Combat: int = 0
    Trade: int = 0
    Explore: int = 0
    Soldier: int = 0
    Exobiologist: int = 0
    Empire: int = 0
    Federation: int = 0
    CQC: int = 0


class PromotionEvent(GameEvent):
    event: Literal["Promotion"]
    # A Promotion event carries only the rank(s) that changed, so every
    # field is optional.
    Combat: Optional[int] = None
    Trade: Optional[int] = None
    Explore: Optional[int] = None
    Soldier: Optional[int] = None
    Exobiologist: Optional[int] = None
    Empire: Optional[int] = None
    Federation: Optional[int] = None
    CQC: Optional[int] = None


class ReputationEvent(GameEvent):
    event: Literal["Reputation"]
    Empire: float = 0.0
    Federation: float = 0.0
    Independent: float = 0.0
    Alliance: float = 0.0


class DiedEvent(GameEvent):
    event: Literal["Died"]
    KillerName: Optional[str] = None
    KillerShip: Optional[str] = None
    KillerRank: Optional[str] = None


class ResurrectEvent(GameEvent):
    event: Literal["Resurrect"]
    Option: str
    Cost: int
    Bankrupt: bool


class StatusFlags(IntFlag):
    Docked = 1
    Landed = 2
    LandingGearDown = 4
    ShieldsUp = 8
    Supercruise = 16
    FlightAssistOff = 32
    HardpointsDeployed = 64
    InWing = 128
    LightsOn = 256
    CargoScoopDeployed = 512
    SilentRunning = 1024
    ScoopingFuel = 2048
    SrvHandbrake = 4096
    SrvUsingTurret = 8192
    SrvTurretRetracted = 16384
    SrvDriveAssist = 32768
    FsdMassLocked = 65536
    FsdCharging = 131072
    FsdCooldown = 262144
    LowFuel = 524288
    Overheating = 1048576
    HasLatLong = 2097152
    IsInDanger = 4194304
    BeingInterdicted = 8388608
    InMainShip = 16777216
    InFighter = 33554432
    InSRV = 67108864
    HudInAnalysisMode = 134217728
    NightVision = 268435456
    AltitudeFromAverageRadius = 536870912
    FsdJump = 1073741824
    SrvHighBeam = 2147483648


class StatusFlags2(IntFlag):
    OnFoot = 1
    InTaxi = 2
    InMulticrew = 4
    OnFootInStation = 8
    OnFootOnPlanet = 16
    AimDownSight = 32
    LowOxygen = 64
    LowHealth = 128
    Cold = 256
    Hot = 512
    VeryCold = 1024
    VeryHot = 2048
    GlideMode = 4096
    OnFootInHangar = 8192
    OnFootSocialSpace = 16384
    OnFootExterior = 32768
    BreathableAtmosphere = 65536
    TelepresenceMulticrew = 131072
    PhysicalMulticrew = 262144
    FsdHyperdriveCharging = 524288
    SupercruiseOverdriveActive = 1048576
    SupercruiseAssistActive = 2097152


class NonJournalFileEvent:
    """Marker for events that never came from the journal log file (e.g.
    Status.json is polled separately, not read from a Journal*.log line).
    GameStateService checks for this marker to keep such events out of the
    live journal event stream shown on the frontend."""


class StatusFuelModel(IgnoreExtraFieldsModel):
    FuelMain: float
    FuelReservoir: float


class StatusEvent(GameEvent, NonJournalFileEvent):
    event: Literal["Status"]
    Flags: int = 0
    Flags2: int = 0
    Pips: list[int] = []
    Cargo: Optional[float] = None
    LegalState: Optional[str] = None
    Fuel: Optional[StatusFuelModel] = None


class UnknownCheckedEvent(GameEvent):
    event: str
