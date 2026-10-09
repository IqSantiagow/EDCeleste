import logging
import os
import shutil
from dataclasses import replace
from pathlib import Path
from typing import AsyncGenerator

import httpx

from edceleste.services.models.instinct_status import DownloadProgress

logger = logging.getLogger(__name__)

MODEL_REPO = "IqSantiagow/edceleste-decider-0.8b"
MODEL_VERSION = "v5"

# Written after the last file, so a half-downloaded model never counts as downloaded
DOWNLOAD_COMPLETE_FILE = "download_complete"
CHUNK_BYTES = 1024 * 1024


class DownloadCancelled(Exception):
    pass


def find_models_directory(operating_system_name: str = os.name) -> Path:
    """%LOCALAPPDATA%\\EDCeleste\\models on Windows, ~/.local/share/EDCeleste/models
    everywhere else. Only builds the path, the folder is not created here."""
    if operating_system_name == "nt":
        application_data_directory = Path(os.environ["LOCALAPPDATA"])
    else:
        application_data_directory = Path.home() / ".local" / "share"
    return application_data_directory / "EDCeleste" / "models"


def fetch_file_sizes_by_name_from_hub() -> dict[str, int]:
    """Asks the Hugging Face Hub over the network for every file of
    MODEL_REPO at MODEL_VERSION, without a token. A file without a known size
    counts as 0 bytes. Network errors are not caught, they go to the caller."""
    from huggingface_hub import HfApi

    model_info = HfApi(token=False).model_info(
        MODEL_REPO, revision=MODEL_VERSION, files_metadata=True
    )
    return {file.rfilename: file.size or 0 for file in model_info.siblings or []}


def build_file_url_on_hub(file_name: str) -> str:
    """Only builds the download URL of one file at MODEL_VERSION, no network."""
    from huggingface_hub import hf_hub_url

    return hf_hub_url(MODEL_REPO, file_name, revision=MODEL_VERSION)


class DecisionModelDownloadService:
    def __init__(self, models_directory: Path | None = None) -> None:
        """Without models_directory the per-user folder from
        find_models_directory() is used. Every model version gets its own
        folder inside it. Nothing is created or downloaded here."""
        models_directory = models_directory or find_models_directory()
        self.model_folder = models_directory / f"edceleste-decider-0.8b-{MODEL_VERSION}"
        self.cancel_requested = False

    def is_model_downloaded(self) -> bool:
        """Looks only for the DOWNLOAD_COMPLETE_FILE marker on disk, the model
        files themselves are not checked. No marker means a missing or
        half-downloaded model."""
        return (self.model_folder / DOWNLOAD_COMPLETE_FILE).exists()

    def fetch_download_size(self) -> int:
        """Total bytes of all model files. Goes to the network every call, the
        result is not cached here. Network errors go to the caller."""
        return sum(fetch_file_sizes_by_name_from_hub().values())

    def cancel_download(self) -> None:
        """Only sets a flag. The running download_model() stops at its next
        chunk with DownloadCancelled and deletes the model folder."""
        self.cancel_requested = True

    async def download_model(self) -> AsyncGenerator[DownloadProgress, None]:
        """Downloads every model file into model_folder and yields the progress
        after every chunk. Goes to the network.

        1. Clears an old cancel request and asks the Hub for the file list.
        2. Downloads the files one by one.
        3. Writes DOWNLOAD_COMPLETE_FILE last, so only a full download counts.
        4. Yields a final progress with bytes_done == bytes_total.
        On any error, a cancel, or when the caller stops iterating, the whole
        model folder is deleted, so the next try starts over, and the error is
        raised again.
        """
        self.cancel_requested = False
        file_sizes_by_name = fetch_file_sizes_by_name_from_hub()
        progress = DownloadProgress(
            bytes_done=0, bytes_total=sum(file_sizes_by_name.values())
        )
        self.model_folder.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Downloading %s %s (%d bytes) to %s",
            MODEL_REPO,
            MODEL_VERSION,
            progress.bytes_total,
            self.model_folder,
        )

        bytes_in_finished_files = 0
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                for file_name, file_size in file_sizes_by_name.items():
                    async for file_bytes_done in self.download_file(client, file_name):
                        yield replace(
                            progress,
                            bytes_done=bytes_in_finished_files + file_bytes_done,
                        )
                    bytes_in_finished_files += file_size
        except BaseException:
            # cancelled or broken: drop what came so far, the next try starts over
            shutil.rmtree(self.model_folder, ignore_errors=True)
            raise

        (self.model_folder / DOWNLOAD_COMPLETE_FILE).write_text(MODEL_VERSION)
        logger.info("Model download complete.")
        yield replace(progress, bytes_done=progress.bytes_total)

    async def download_file(
        self, client: httpx.AsyncClient, file_name: str
    ) -> AsyncGenerator[int, None]:
        """Streams one file from the Hub to model_folder in CHUNK_BYTES pieces
        and yields the bytes of this file written so far after every chunk.
        Raises DownloadCancelled when cancel_download() was called, and
        httpx.HTTPStatusError when the Hub answers with an error code."""
        bytes_done = 0
        async with client.stream("GET", build_file_url_on_hub(file_name)) as response:
            response.raise_for_status()
            with (self.model_folder / file_name).open("wb") as output:
                async for chunk in response.aiter_bytes(CHUNK_BYTES):
                    if self.cancel_requested:
                        raise DownloadCancelled("The model download was cancelled.")
                    output.write(chunk)
                    bytes_done += len(chunk)
                    yield bytes_done
