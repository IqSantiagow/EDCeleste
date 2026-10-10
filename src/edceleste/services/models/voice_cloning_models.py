from enum import Enum, auto
from typing import TypedDict


class VoiceCloningState(Enum):
    DIRECTORY_CREATED = auto()
    AUDIO_PROCESSED = auto()
    COMPLETED = auto()
    SAMPLE_CREATED = auto()


class VoiceAnalysisResult(TypedDict):
    file_name: str
    duration_seconds: float
    sample_rate: int
    channels: int
    is_mono: bool
    peak_dbfs: float
    has_clipping: bool
    noise_floor_dbfs: float
    waveform_envelope: list[float]
    is_valid: bool
    validation_error_message: str | None
