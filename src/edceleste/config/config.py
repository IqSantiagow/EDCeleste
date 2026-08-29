from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Logging(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]


class LangSmithConfig(BaseModel):
    tracing: bool = False
    api_key: str = ""
    project: str = "EDCeleste"
    endpoint: str = "https://api.smith.langchain.com"


class AppConfig(BaseSettings):
    logging: Logging
    langsmith: LangSmithConfig = LangSmithConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )
