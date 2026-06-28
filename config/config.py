from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Logging(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]


class EDConfig(BaseModel):
    main_path: str
    logging: Logging


class LLMConfig(BaseModel):
    anthropic_api_key: str


class AppConfig(BaseSettings):
    ed: EDConfig
    llm: LLMConfig

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )


def load_config() -> AppConfig:
    return AppConfig()  # type: ignore[call-arg]
