from typing import Union

import yaml
from pydantic import BaseModel


class EDConfig(BaseModel):
    main_path: str
    logging: Logging


# TODO: Add strict validation for loglevel types
class Logging(BaseModel):
    level: str


class AppConfig(BaseModel):
    ed: EDConfig


def load_config(path='config.yaml') -> AppConfig:
    with open(path, 'r') as f:
        config = yaml.safe_load(f)
    return AppConfig(**config)
