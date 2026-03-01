from typing import Optional

from services.models.pydantic_base_models import IgnoreExtraFieldsModel


class ActiveFactionStateModel(IgnoreExtraFieldsModel):
    State: str


class BaseFactionModel(IgnoreExtraFieldsModel):
    Name: str
    FactionState: Optional[str] = "None"


class FactionModel(BaseFactionModel):
    Government: str
    Influence: float
    Allegiance: str
    Happiness_Localised: Optional[str] = None
    MyReputation: float
    ActiveStates: Optional[list[ActiveFactionStateModel]] = None


class StationEconomyModel(IgnoreExtraFieldsModel):
    Name_Localised: str
    Proportion: float
