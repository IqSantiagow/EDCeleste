from enum import Enum, auto


class SaveState(Enum):
    SAVED = auto()
    SAVING = auto()
    MODIFIED = auto()
    FAILED = auto()
    IDLE = auto()
