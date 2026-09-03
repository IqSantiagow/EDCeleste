from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Logging(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]


class AppConfig(BaseSettings):
    logging: Logging

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )
