import yaml
from pydantic import BaseModel


# TODO: Add strict validation for loglevel types
class Logging(BaseModel):
    level: str


class EDConfig(BaseModel):
    main_path: str
    logging: Logging


class AppConfig(BaseModel):
    ed: EDConfig


def load_config(path="config.yaml") -> AppConfig:
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return AppConfig(**config)
