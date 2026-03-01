from typing import Optional

from pydantic import BaseModel


class ActiveFactionStateModel(BaseModel):
    State: str


class BaseFactionModel(BaseModel):
    Name: str
    FactionState: Optional[str] = None


class FactionModel(BaseFactionModel):
    Government: str
    Influence: float
    Allegiance: str
    Happiness_Localised: Optional[str] = None
    MyReputation: float
    ActiveStates: Optional[list[ActiveFactionStateModel]] = None


class StationEconomyModel(BaseModel):
    Name_Localised: str
    Proportion: float
