from datetime import datetime
from typing import Literal, Optional

from services.models.game_models import (
    FactionModel,
    BaseFactionModel,
    StationEconomyModel,
)
from services.models.pydantic_base_models import IgnoreExtraFieldsModel


class LoadedGameEvent(IgnoreExtraFieldsModel):
    event: Literal["LoadGame"]
    timestamp: datetime
    Commander: str
    FID: str
    Horizons: bool
    Odyssey: bool
    Ship: str
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


class FSDJumpEvent(IgnoreExtraFieldsModel):
    event: Literal["FSDJump"]
    timestamp: datetime
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


class DockedEvent(IgnoreExtraFieldsModel):
    event: Literal["Docked"]
    timestamp: datetime
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


class UndockedEvent(IgnoreExtraFieldsModel):
    event: Literal["Undocked"]
    timestamp: datetime
    StationName: str


class FuelScoopEvent(IgnoreExtraFieldsModel):
    event: Literal["FuelScoop"]
    timestamp: datetime
    Scooped: float
    Total: float


class DockingGrantedEvent(IgnoreExtraFieldsModel):
    event: Literal["DockingGranted"]
    timestamp: datetime
    StationName: str
    StationType: str
    MarketID: int
    LandingPad: int


class StartJumpEvent(IgnoreExtraFieldsModel):
    event: Literal["StartJump"]
    timestamp: datetime
    JumpType: str
    Taxi: bool
    StarSystem: str
    SystemAddress: int
    StarClass: Optional[str] = None


class UnknownCheckedEvent(IgnoreExtraFieldsModel):
    event: str
    timestamp: datetime
