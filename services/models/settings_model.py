from pydantic import BaseModel, Field


class PathModel(BaseModel):
    journal_path: str = Field(
        description="The path to the journal file",
    )
    keybindings_path: str = Field(
        description="The path to the keybindings file",
    )


class PromptModel(BaseModel):
    system_prompt: str = Field(
        description="The system prompt for the LLM",
    )
    user_prompt: str = Field(
        description="The user prompt for the LLM",
    )


class TTSModel(BaseModel):
    voice: str = Field(
        description="The voice to use for text-to-speech",
    )
    volume: float = Field(
        description="The volume of speech for text-to-speech",
    )


class SettingsModel(BaseModel):
    paths: PathModel = Field(
        description="The paths to the journal and keybindings files",
    )
    prompts: PromptModel = Field(
        description="The system and user prompts for the LLM",
    )
    tts: TTSModel = Field(
        description="The text-to-speech settings for the LLM",
    )


class SettingsChangedEvent:
    def __init__(self, settings: SettingsModel):
        self.settings = settings


class NewServiceEvent: ...
