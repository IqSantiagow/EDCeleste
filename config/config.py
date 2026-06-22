from typing import Literal

import yaml
from pydantic import BaseModel


class Logging(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class EDConfig(BaseModel):
    main_path: str
    logging: Logging


class LLMConfig(BaseModel):
    anthropic_api_key: str


class AppConfig(BaseModel):
    ed: EDConfig
    llm: LLMConfig


def load_config(path="config.yaml") -> AppConfig:
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    return AppConfig(**config)
