import enum
from dataclasses import dataclass
from typing import Literal


@dataclass
class DownloadProgress:
    bytes_done: int
    bytes_total: int


class InstinctModelState(enum.StrEnum):
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass
class InstinctFailure:
    step: Literal["download", "load"]
    reason: str


@dataclass
class InstinctStatus:
    state: InstinctModelState
    download_progress: DownloadProgress | None
    running_device: str | None
    failure: InstinctFailure | None


def describe_size(byte_count: int) -> str:
    if byte_count >= 1_000_000_000:
        return f"{byte_count / 1_000_000_000:.1f} GB"
    return f"{byte_count / 1_000_000:.0f} MB"


def describe_download_progress(progress: DownloadProgress) -> str:
    percent = progress.bytes_done * 100 // max(progress.bytes_total, 1)
    done = describe_size(progress.bytes_done)
    total = describe_size(progress.bytes_total)
    return f"{percent}% · {done} of {total}"
