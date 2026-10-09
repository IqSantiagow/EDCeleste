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
    """Decimal units for the UI: "1.6 GB" from 1 GB up (one decimal), whole
    "MB" below that, so a small size can show as "0 MB"."""
    if byte_count >= 1_000_000_000:
        return f"{byte_count / 1_000_000_000:.1f} GB"
    return f"{byte_count / 1_000_000:.0f} MB"


def describe_download_progress(progress: DownloadProgress) -> str:
    """Text like "42% · 680 MB of 1.6 GB". The percent is rounded down, and a
    total of 0 does not divide by zero, it just shows 0%."""
    percent = progress.bytes_done * 100 // max(progress.bytes_total, 1)
    done = describe_size(progress.bytes_done)
    total = describe_size(progress.bytes_total)
    return f"{percent}% · {done} of {total}"
