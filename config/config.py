from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Logging(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"]


class EDConfig(BaseModel):
    main_path: str
    keybinds_path: str
    logging: Logging


class LLMConfig(BaseModel):
    anthropic_api_key: str


class LangSmithConfig(BaseModel):
    tracing: bool = False
    api_key: str = ""
    project: str = "EDCeleste"
    endpoint: str = "https://api.smith.langchain.com"


class TTSConfig(BaseModel):
    voice: str = "en-GB-SoniaNeural"


class AppConfig(BaseSettings):
    ed: EDConfig
    llm: LLMConfig
    langsmith: LangSmithConfig = LangSmithConfig()
    tts: TTSConfig = TTSConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )


def load_config() -> AppConfig:
    return AppConfig()  # type: ignore[call-arg]
