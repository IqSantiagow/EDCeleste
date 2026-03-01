from datetime import datetime
from typing import Literal, Optional

from services.models.pydantic_base_models import IgnoreExtraFieldsModel


class LoadedGameEvent(IgnoreExtraFieldsModel):
    event: Literal["LoadGame"]
    timestamp: datetime
    Commander: str
    FID: int
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


class UnknownCheckedEvent(IgnoreExtraFieldsModel):
    event: str
    timestamp: datetime
