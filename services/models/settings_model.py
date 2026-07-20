from pydantic import BaseModel, Field


class PathModel(BaseModel):
    journal_path: str = Field(
        description="The path to the journal file",
    )
    keybindings_path: str = Field(
        description="The path to the keybindings file",
    )


class TTSModel(BaseModel):
    voice: str = Field(
        description="The voice to use for text-to-speech",
    )
    volume: float = Field(
        ge=0.0,
        le=1.0,
        description="The volume of speech for text-to-speech",
    )


class LLMModel(BaseModel):
    api_key: str = Field(
        description="The Anthropic API key for the LLM",
    )

    system_prompt: str = Field(
        description="The system prompt for the LLM",
    )
    user_prompt: str = Field(
        description="The user prompt for the LLM",
    )


class SettingsModel(BaseModel):
    paths: PathModel = Field(
        description="The paths to the journal and keybindings files",
    )
    tts: TTSModel = Field(
        description="The text-to-speech settings for the LLM",
    )
    llm: LLMModel = Field(
        description="The LLM connection settings",
    )


class SettingsIssueModel(BaseModel):
    section: str = Field(
        description="The section of the settings that has an issue",
    )

    field: str = Field(
        description="The field of the settings that has an issue",
    )

    message: str = Field(
        description="The message describing the issue with the settings",
    )
