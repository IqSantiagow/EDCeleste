from pydantic import BaseModel, ConfigDict


class IgnoreExtraFieldsModel(BaseModel):
    model_config = ConfigDict(extra='allow')
