from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import replace
from typing import AsyncGenerator, Literal

import httpx
import numpy as np
import onnxruntime
from tokenizers import Tokenizer

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.protocols.keybinds_protocol import KeybindsProtocol
from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.fast_command_reply import FastCommandReply
from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
    InstinctStatus,
    describe_download_progress,
)
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.reply_texts import (
    ACTIONS_SAID_BY_GAME_STATE,
    pick_reply_text_for_pressed_action,
)
from edceleste.services.models.reply_text import ReplyTexts
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

SECONDS_BETWEEN_PROGRESS_UPDATES = 0.2

# A slower model call is not waited for, the message goes to the LLM instead
FAST_COMMAND_TIMEOUT_SECONDS = 1.0
SCORES_IN_LOG = 3

MODEL_FILE = "command_classifier_int8.onnx"
TOKENIZER_FILE = "tokenizer.json"
CLASSES_FILE = "classes.json"
MAX_TOKENS = 32
WARM_UP_MESSAGE = "deploy hardpoints"

# The model's 42nd class, next to the 41 EdAction values: the pilot talks, asks
# or refuses instead of asking for a ship action
NO_ACTION = "none"

# A best score below this is "none", so the message goes to the LLM. Without it
# the model presses a key for talk about a ship part it does not understand.
CONFIDENCE_THRESHOLD = 0.5


class ModelNotDownloaded(Exception):
    pass


def describe_failure_reason(error: Exception) -> str:
    """Short reason shown in the settings row and the cold start warning.
    No connection or a timeout -> "no connection to huggingface.co".
    Anything else -> the first line of the error text cut to 120 characters,
    or the exception class name when the text is empty."""
    if isinstance(error, (httpx.ConnectError, httpx.TimeoutException)):
        return "no connection to huggingface.co"
    first_line = str(error).splitlines()[0] if str(error) else type(error).__name__
    return first_line[:120]


def describe_top_scores(probabilities: dict[str, float]) -> str:
    """The best SCORES_IN_LOG options of a model answer for the log, best first,
    e.g. "LandingGearToggle 0.97, none 0.02, SetSpeedZero 0.00". Scores have two
    decimals. Options with the same score keep the order of the answer. An empty
    answer gives an empty string. Only builds the text."""
    best_options = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    return ", ".join(
        f"{name} {score:.2f}" for name, score in best_options[:SCORES_IN_LOG]
    )


class InstinctService:
    """Instinct: all-MiniLM-L6-v2 with a 42-class head (int8 ONNX, on the CPU,
    about 1 ms per message) from IqSantiagow/edceleste-command-classifier. It
    knows only the actions it was trained on, which are the EdAction values."""

    enabled: bool = False
    background_task: asyncio.Task | None = None
    download_progress: DownloadProgress | None = None
    failure: InstinctFailure | None = None
    download_size: int | None = None
    session: onnxruntime.InferenceSession | None = None
    tokenizer: Tokenizer | None = None

    def __init__(
        self,
        settings_service: SettingsService,
        download_service: DecisionModelDownloadService,
        keybinds_protocol: KeybindsProtocol,
        game_state_protocol: GameStateProtocol,
        perform_game_action: ToolProtocol,
    ) -> None:
        """Only stores the dependencies and creates the lock that lets one
        thread at a time use the model. Nothing is downloaded or loaded here,
        that starts in reload_service(). perform_game_action is a PerformGameAction,
        the class of the tool the LLM calls (the container makes a separate
        object for each), so a key is pressed (or refused) by one set of
        rules."""
        self.settings_service = settings_service
        self.download_service = download_service
        self.keybinds_protocol = keybinds_protocol
        self.game_state_protocol = game_state_protocol
        self.perform_game_action = perform_game_action
        self.model_lock = threading.Lock()
        self.class_names: list[str] = []

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Always None. enabled is already limited by the settings model, so
        Instinct never blocks saving the settings."""
        return None

    def reload_service(self) -> None:
        """Applies the saved Instinct settings. Called by cold_start() and
        after the settings change.

        1. Stores enabled.
        2. Enabled -> starts the download and load in a background task and
           returns at once, it does not wait for the task.
           Disabled -> unloads the model. A download that is already running
           is not cancelled, it finishes, but the model is not loaded after it.
        """
        self.enabled = self.settings_service.get_settings().llm.instinct.enabled
        if self.enabled:
            self.download_and_load_model_in_background()
        else:
            self.unload_model()

    def download_and_load_model_in_background(self) -> None:
        """Starts download_and_load_model() as an asyncio task and returns at
        once. Needs a running event loop.
        Does nothing while the previous task still runs. Clears the last
        failure, so the UI stops showing it."""
        if self.is_busy():
            return
        self.failure = None
        self.background_task = asyncio.create_task(self.download_and_load_model())

    def cancel_download(self) -> None:
        """Only raises the cancel flag in the download service. The download
        stops at its next chunk, deletes the half downloaded files, and
        download_and_load_model() ends without a failure."""
        self.download_service.cancel_download()

    def is_busy(self) -> bool:
        """True while the background download and load task runs. A finished,
        failed or cancelled task is not busy."""
        return self.background_task is not None and not self.background_task.done()

    async def download_and_load_model(self) -> None:
        """Body of the background task. Goes to the network.

        1. When the model is not on disk yet, downloads it from the Hugging
           Face Hub and keeps the newest progress in download_progress, so the
           UI and cold_start() can show it.
        2. When Instinct is still enabled, loads the model and warms it up in a
           worker thread (warm_up()), so the first real command is fast.

        Errors are not raised. A cancelled download is only logged. Any other
        error is logged and saved in failure, together with the step that failed
        ("download" or "load"). download_progress is always cleared at the end.
        """
        step: Literal["download", "load"] = "download"
        try:
            if not self.download_service.is_model_downloaded():
                async for progress in self.download_service.download_model():
                    self.download_progress = progress
            step = "load"
            if self.enabled:
                await asyncio.to_thread(self.warm_up)
        except DownloadCancelled:
            logger.info("Instinct model download cancelled.")
        except Exception as error:
            logger.exception("Instinct model %s failed", step)
            self.failure = InstinctFailure(step, describe_failure_reason(error))
        finally:
            self.download_progress = None

    def fetch_download_size(self) -> int | None:
        """Model size in bytes, for the "Not downloaded" row in settings.

        The first call asks the Hugging Face Hub over the network and blocks,
        later calls return the saved answer. Returns None when the Hub cannot
        be reached. That error is logged, not raised, and the next call asks
        the Hub again."""
        if self.download_size is None:
            try:
                self.download_size = self.download_service.fetch_download_size()
            except Exception:
                # without the Hub the row says just "Not downloaded"
                logger.warning("Cannot ask the Hub for the model size", exc_info=True)
        return self.download_size

    # ----- The model itself -----

    def unload_model(self) -> None:
        """Forgets the loaded model, so is_module_enabled() is False until
        load_model_once() runs again. Does nothing when no model is loaded. The
        files on disk stay. It does not take model_lock, so it does not wait for
        a message that is being scored."""
        self.session = None

    def load_model_once(self) -> None:
        """Reads the model, the tokenizer and the class names from the model
        folder on the first call, later calls do nothing. Blocking, so callers
        run it in a worker thread.

        Raises ModelNotDownloaded when the files are not on disk. It never
        downloads anything. A missing or broken file raises the error of the
        library that reads it (FileNotFoundError, json.JSONDecodeError or an
        onnxruntime error) and the model stays unloaded.
        """
        if self.session is not None:
            return
        if not self.download_service.is_model_downloaded():
            raise ModelNotDownloaded("The Instinct model is not downloaded yet.")
        start = time.perf_counter()
        model_folder = self.download_service.model_folder
        self.tokenizer = Tokenizer.from_file(str(model_folder / TOKENIZER_FILE))
        self.tokenizer.enable_truncation(MAX_TOKENS)
        self.class_names = json.loads(
            (model_folder / CLASSES_FILE).read_text(encoding="utf-8")
        )
        # One thread is enough for a message of a few words, and the game keeps
        # the other cores
        session_options = onnxruntime.SessionOptions()
        session_options.intra_op_num_threads = 1
        self.session = onnxruntime.InferenceSession(
            str(model_folder / MODEL_FILE),
            session_options,
            providers=["CPUExecutionProvider"],
        )
        logger.info(
            "Instinct model loaded in %.0f ms", (time.perf_counter() - start) * 1000
        )

    def warm_up(self) -> None:
        """Loads the model and runs one made up message through it, so the
        first real command does not pay for the start of the model. The answer
        is thrown away. Blocking. Errors (ModelNotDownloaded, a broken model
        file) are raised. Called by download_and_load_model() right after the
        download, in a worker thread."""
        with self.model_lock:
            self.load_model_once()
            self.score_every_class(WARM_UP_MESSAGE)

    def score_every_class(self, pilot_message: str) -> dict[str, float]:
        """Runs the loaded model once and returns the softmax score of every
        class by class name, in the order of classes.json (the 41 EdAction
        values and "none"). The scores add up to 1. A message longer than
        MAX_TOKENS is cut. The caller holds model_lock and has called
        load_model_once(): with no model loaded this raises AssertionError. Has
        no other effect."""
        assert self.session is not None and self.tokenizer is not None
        encoded = self.tokenizer.encode(pilot_message)
        logits = self.session.run(
            None,
            {
                "input_ids": np.array([encoded.ids], dtype=np.int64),
                "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
            },
        )[0][0]
        exponents = np.exp(logits - logits.max())
        scores = exponents / exponents.sum()
        return dict(zip(self.class_names, scores.tolist()))

    # ----- Fast commands -----

    async def try_fast_command(self, pilot_message: str) -> FastCommandReply | None:
        """Does the action the pilot asked for, without the LLM. Returns the
        short reply, the one COMMS shows and Celeste says (is_spoken is False
        for a pressed action of ACTIONS_SAID_BY_GAME_STATE: the game state says
        it by itself, so the reply is only written). When a key was
        pressed it is the text of REPLY_TEXTS for what the key did, e.g.
        "Landing gear deployed" (a toggle is named after the direction it
        went, read from the ship before the press). When the ship cannot do
        the action now, nothing is pressed and the reply is the text of the
        tool up to the colon, e.g. "Landing gear unavailable". When the model took
        the message for a command but game actions are switched off, nothing is
        pressed and the reply is "Game actions disabled". Any other failure of
        the tool (the game window was not found) gives the text of the tool as
        it is, which has no prepared clip. These refusals and failures are always
        spoken (is_spoken True), only a key that was pressed for an action of
        ACTIONS_SAID_BY_GAME_STATE is not. None means "not handled", and then
        the caller sends the message to the LLM as before.

        1. Nothing is asked when is_module_enabled() is False, when no action
           has a keyboard key or when there is no game state yet. The message
           may be a question, which only the LLM can answer, so it goes there.
        2. Asks the model in a worker thread. It gets FAST_COMMAND_TIMEOUT_SECONDS,
           the model is never waited for longer.
        3. The model picks one option. "none" means the pilot is talking or
           asking, so nothing is done. For an action, can_decide_commands() is
           asked now: when game actions are off, the tool is not called and the
           reply is "Game actions disabled". Otherwise the action goes to the
           PerformGameAction tool, which has all the rules (see
           get_unavailable_reason there) and presses the key. The tool answers
           with a ToolReturn: "is_error" or "unavailable" in its metadata means
           the key was not pressed and its text is the reply, anything else
           means the key was pressed.
        4. Logs one line: the message, the best scores, the chosen action and
           the time from the message to the end of the tool.

        Never raises. A timeout, a model error, a wrong answer or a tool that
        raises are logged and give None (a call that ran out of time keeps
        running in its thread and holds the model, so the next command may wait
        for it). A tool that answers "unavailable" or with an error (e.g. no
        game window) is a normal case, not a failure: we already know the
        message is a command, so the LLM would only say the same after seconds,
        and the reply comes at once.
        """
        start = time.perf_counter()
        try:
            if not self.is_module_enabled():
                return None
            offered_actions = self.find_actions_with_a_key()
            game_state = self.game_state_protocol.get_game_state_projection()
            if not offered_actions or not game_state:
                # The model is not asked, so we do not know if this is a command
                # or a question. Only the LLM can tell the pilot what is missing.
                return None

            answer = await asyncio.wait_for(
                asyncio.to_thread(
                    self.pick_offered_action, pilot_message, offered_actions
                ),
                timeout=FAST_COMMAND_TIMEOUT_SECONDS,
            )
            scores = describe_top_scores(answer["probabilities"])
            if answer["choice"] == NO_ACTION:
                logger.info(
                    "Fast command %r: no ship action (%s), the message goes to the LLM",
                    pilot_message,
                    scores,
                )
                return None
            action = EdAction(answer["choice"])
            if not self.can_decide_commands():
                logger.info(
                    "Fast command %r: %s was not done, game actions are off",
                    pilot_message,
                    action.value,
                )
                return FastCommandReply(ReplyTexts.GAME_ACTIONS_DISABLED)
            # Read before the press: the key changes the ship, and a toggle is
            # named after what it did, not after what the ship is now
            ship_before_press = self.game_state_protocol.get_game_stats().ship
            tool_result = await self.perform_game_action.execute(action)
        except TimeoutError:
            logger.warning(
                "Fast command %r: the model needed more than %.1f s, the message "
                "goes to the LLM",
                pilot_message,
                FAST_COMMAND_TIMEOUT_SECONDS,
            )
            return None
        except Exception:
            logger.exception(
                "Fast command %r failed, the message goes to the LLM", pilot_message
            )
            return None

        tool_metadata = tool_result.metadata or {}
        if tool_metadata.get("unavailable"):
            # "Landing gear unavailable: the ship is in supercruise." -> the
            # part before the colon is the text of the prepared reply
            reply = str(tool_result.return_value).split(":")[0]
            logger.info(
                "Fast command %r: %s was not done (%s)",
                pilot_message,
                action.value,
                tool_result.return_value,
            )
            return FastCommandReply(reply)

        if tool_metadata.get("is_error"):
            reply = str(tool_result.return_value)
            logger.info(
                "Fast command %r: %s was not done (%s)",
                pilot_message,
                action.value,
                reply,
            )
            return FastCommandReply(reply)

        logger.info(
            "Fast command %r: Instinct pressed %s in %.0f ms (%s)",
            pilot_message,
            action.value,
            (time.perf_counter() - start) * 1000,
            scores,
        )
        return FastCommandReply(
            text=pick_reply_text_for_pressed_action(action, ship_before_press),
            is_spoken=action not in ACTIONS_SAID_BY_GAME_STATE,
        )

    def is_module_enabled(self) -> bool:
        """True when Instinct may take a pilot message from the LLM: Instinct
        is on and the model is loaded. A model that is still loading or failed
        to load gives False. The first check of try_fast_command(). Only reads
        memory."""
        return self.enabled and self.session is not None

    def can_decide_commands(self) -> bool:
        """True when game actions (game_actions.enabled) are switched on in the
        saved settings, so a command the model picked may be done. Asked only
        after the model picked an action, never before. Only reads the saved
        settings."""
        return self.settings_service.get_settings().game_actions.enabled

    def find_actions_with_a_key(self) -> list[EdAction]:
        """The actions that have a keyboard key, in the order of EdAction. The
        model is asked only about these. Empty when the keybinds are not
        loaded yet, and also when no action has a keyboard key (then the
        caller cannot tell the two apart). Only reads memory."""
        try:
            return [
                action for action in EdAction if self.keybinds_protocol.is_bound(action)
            ]
        except KeyError:
            return []

    def pick_offered_action(
        self, pilot_message: str, offered_actions: list[EdAction]
    ) -> dict:
        """Blocking, so try_fast_command() runs it in a worker thread. Which of
        offered_actions the pilot asked for, or none.

        Scores all classes in one model run, then lets only the offered
        actions and "none" compete, so an action without a key is never chosen.
        An offered action that is not a class of the model (added after the
        model was trained) is left out: the model cannot know it, so its
        commands go to the LLM.

        Returns {"choice": ..., "probabilities": ...}:
        - "probabilities" holds the score of every offered action that is a
          class of the model, in the offered order, and "none" last. The
          scores come from the softmax over all classes, so they do not add up
          to 1 when some classes are not offered.
        - "choice" is the option with the best score (an EdAction value or
          "none"), but "none" when that score is below CONFIDENCE_THRESHOLD.
          "none" is also the answer for an empty offer, and when "none" itself
          has the best score (the pilot is talking or asking).

        Logs the message, the best scores and how long it took. Only one thread
        uses the model at a time, a second caller waits for the first, without
        a time limit. May load the model first when it is not loaded. Raises
        ModelNotDownloaded when the model files are not on disk, and whatever
        the model itself raises, try_fast_command catches them.
        """
        with self.model_lock:
            self.load_model_once()
            start = time.perf_counter()
            scores_by_class = self.score_every_class(pilot_message)
            offered_names = [
                action.value
                for action in offered_actions
                if action.value in scores_by_class
            ]
            probabilities = {
                name: scores_by_class[name] for name in [*offered_names, NO_ACTION]
            }
            best_name = max(probabilities, key=lambda name: probabilities[name])
            is_sure = probabilities[best_name] >= CONFIDENCE_THRESHOLD
            logger.info(
                "Instinct: %r -> %s in %.1f ms",
                pilot_message,
                describe_top_scores(probabilities),
                (time.perf_counter() - start) * 1000,
            )
            return {
                "choice": best_name if is_sure else NO_ACTION,
                "probabilities": probabilities,
            }

    # ----- Status for the UI and the cold start -----

    def get_status(self) -> InstinctStatus:
        """Snapshot for the Instinct row in settings. Checks the disk to see
        if the model is downloaded."""
        return InstinctStatus(
            state=self.get_model_state(),
            download_progress=self.download_progress,
            failure=self.failure,
        )

    def get_model_state(self) -> InstinctModelState:
        """Picks the one state the UI shows, first match wins:
        1. background task runs -> LOADING when the files are on disk,
           otherwise DOWNLOADING,
        2. the last task failed -> FAILED,
        3. files are on disk -> READY, even when the model is not in memory,
        4. otherwise NOT_DOWNLOADED.
        """
        is_downloaded = self.download_service.is_model_downloaded()
        if self.is_busy():
            if is_downloaded:
                return InstinctModelState.LOADING
            return InstinctModelState.DOWNLOADING
        if self.failure:
            return InstinctModelState.FAILED
        if is_downloaded:
            return InstinctModelState.READY
        return InstinctModelState.NOT_DOWNLOADED

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen. May download the
        model, which can take minutes.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Applies the settings (reload_service). Disabled -> yields completed
           with is_disabled and stops.
        3. Enabled -> waits for the background download and load, and yields
           the download progress every 0.2 s.
        4. Yields completed. A failed download or load is only a warning with
           the reason, never critical, because without Instinct every command
           still goes through Celeste.
        """
        status = ColdStartStatus(
            service="instinct",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status

        self.reload_service()
        if not self.enabled:
            yield replace(status, completed=True, is_disabled=True)
            return

        while self.is_busy():
            if self.download_progress:
                progress_text = describe_download_progress(self.download_progress)
                yield replace(
                    status, progress_text=f"Downloading model {progress_text}"
                )
            await asyncio.sleep(SECONDS_BETWEEN_PROGRESS_UPDATES)

        if self.failure is None:
            yield replace(status, completed=True)
            return
        # Not critical: without Instinct every command goes through Celeste
        failed_step = (
            "model download failed"
            if self.failure.step == "download"
            else "model failed to load"
        )
        yield replace(
            status,
            completed=True,
            is_warning=True,
            message=f"{failed_step} ({self.failure.reason}). "
            "Commands go through Celeste.",
        )
