from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import threading
import time
from dataclasses import replace
from typing import TYPE_CHECKING, AsyncGenerator, Literal

import httpx

from edceleste.protocols.game_state_protocol import GameStateProtocol
from edceleste.protocols.keybinds_protocol import KeybindsProtocol
from edceleste.protocols.tool_protocol import ToolProtocol
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
    DownloadCancelled,
)
from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.services.models.instinct_actions import (
    COMMAND_QUESTION_NAME,
    NO_ACTION,
    build_which_action_questions,
)
from edceleste.services.models.instinct_status import (
    DownloadProgress,
    InstinctFailure,
    InstinctModelState,
    InstinctStatus,
    describe_download_progress,
)
from edceleste.services.models.keybinds_model import EdAction
from edceleste.services.models.reply_texts import (
    GAME_ACTIONS_DISABLED_TEXT,
    pick_reply_text_for_pressed_action,
)
from edceleste.services.models.settings_model import SettingsIssueModel, SettingsModel
from edceleste.services.settings_service import SettingsService

if TYPE_CHECKING:
    from decider.infer import Decider

logger = logging.getLogger(__name__)

SECONDS_BETWEEN_PROGRESS_UPDATES = 0.2

# A slower model call is not waited for, the message goes to the LLM instead
FAST_COMMAND_TIMEOUT_SECONDS = 1.0
SCORES_IN_LOG = 3

DeviceChoice = Literal["auto", "cuda", "cpu"]

WARM_UP_QUESTIONS = {
    "warm_up": {
        "type": "noul",
        "instructions": "Did the pilot ask for a ship action?",
        "criteria": {"true": "yes", "false": "no"},
    }
}


class ModelNotDownloaded(Exception):
    pass


# transformers swaps these for flash-linear-attention kernels, which run only on the GPU
GPU_ONLY_KERNELS = ["torch_chunk_gated_delta_rule", "torch_recurrent_gated_delta_rule"]
gpu_kernels: dict = {}


def switch_qwen_kernels_to_device(device: str) -> None:
    """Changes global state: swaps functions inside the transformers qwen3_5
    module, so it affects every Qwen model in the process. Called right
    before the model is loaded.

    The first call saves the original GPU kernels in gpu_kernels. "cuda" puts
    the GPU kernels back, any other device puts in the plain torch version
    hidden under the GPU wrapper, which also runs on the CPU.
    """
    from transformers.models.qwen3_5 import modeling_qwen3_5

    for kernel_name in GPU_ONLY_KERNELS:
        gpu_kernel = gpu_kernels.setdefault(
            kernel_name, getattr(modeling_qwen3_5, kernel_name)
        )
        kernel = gpu_kernel if device == "cuda" else inspect.unwrap(gpu_kernel)
        setattr(modeling_qwen3_5, kernel_name, kernel)


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
    enabled: bool = False
    background_task: asyncio.Task | None = None
    download_progress: DownloadProgress | None = None
    failure: InstinctFailure | None = None
    download_size: int | None = None
    decider: Decider | None = None
    device_choice: DeviceChoice = "auto"
    # The size of the input of the last decision, as the model reported it. 0
    # when there was none yet or the model did not report it.
    last_input_tokens: int = 0

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

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Always None. enabled and device are already limited by the
        settings model, so Instinct never blocks saving the settings."""
        return None

    def reload_service(self) -> None:
        """Applies the saved Instinct settings. Called by cold_start() and
        after the settings change.

        1. Stores enabled and the device. A new device unloads the model.
        2. Enabled -> starts the download and load in a background task and
           returns at once, it does not wait for the task.
           Disabled -> unloads the model and frees the GPU memory. A download
           that is already running is not cancelled, it finishes, but the
           model is not loaded after it.
        """
        instinct_settings = self.settings_service.get_settings().llm.instinct
        self.enabled = instinct_settings.enabled
        self.change_device(instinct_settings.device)
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
           worker thread (warm_up(): a small question and, when there is a game
           state and keys, a real command question and the compile of the
           sizes next to it), so the first real command is fast.

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

    def change_device(self, device_choice: DeviceChoice) -> None:
        """A different device unloads the model, the same device keeps it. The
        model is not loaded again here, only by the next load_model() call."""
        if device_choice != self.device_choice:
            self.unload_model()  # loaded again on the new device by the next call
        self.device_choice = device_choice

    def unload_model(self) -> None:
        """Forgets the loaded model and empties the CUDA cache. Does nothing
        when no model is loaded. The files on disk stay."""
        if self.decider is None:
            return
        self.decider = None
        import torch

        torch.cuda.empty_cache()  # give the GPU memory back to the game

    def running_device(self) -> str | None:
        """Device the loaded model really runs on, e.g. "cuda" or "cpu", so
        the settings row can show where "auto" ended up. None when no model is
        loaded."""
        return str(self.decider.dev) if self.decider is not None else None

    def load_model(self) -> Decider:
        """Loads the model on the first call, later calls return the same one.
        Slow and blocking, so callers run it in a worker thread.

        1. Raises ModelNotDownloaded when the files are not on disk. It never
           downloads anything.
        2. "auto" becomes "cuda" when torch sees a GPU, otherwise "cpu".
        3. Switches the Qwen kernels to that device.
        4. Loads the model. Without Triton, torch.compile cannot run, so the
           slower eager forward is used.
        """
        if self.decider is not None:
            return self.decider
        if not self.download_service.is_model_downloaded():
            raise ModelNotDownloaded("The Instinct model is not downloaded yet.")
        import torch
        from decider.infer import Decider

        device = self.device_choice
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        switch_qwen_kernels_to_device(device)
        start = time.perf_counter()
        self.decider = Decider(str(self.download_service.model_folder), device=device)
        if self.decider.eng is not None and importlib.util.find_spec("triton") is None:
            # torch.compile needs Triton; without it run the slower eager forward
            logger.warning(
                "Triton is missing, the decision model runs without compile."
            )
            self.decider.eng._fwd_impl = self.decider.eng._fwd_eager
        logger.info(
            "Decision model loaded on %s in %.1f s",
            self.decider.dev,
            time.perf_counter() - start,
        )
        return self.decider

    def ask_decision_model(self, state: dict, questions: dict) -> dict:
        """Runs the local model once. Blocking, and slow when the model is not
        loaded yet, because it loads it first (errors like ModelNotDownloaded
        are raised). Logs what the pilot said or which event came, the answers
        and how long it took. Remembers the size of the model's input in
        last_input_tokens.

        Only one thread uses the model at a time, a second caller waits for the
        first, without a time limit (a call that ran out of time in
        try_fast_command() is still running in its thread, and holds the model
        until it ends).

        state holds e.g. "game_state" and "pilot_said". questions maps a
        question name to its type, instructions and criteria, see
        WARM_UP_QUESTIONS. The answers are keyed by the same question names.
        A "choice" answer holds "choice" (the chosen option) and
        "probabilities" (a score for every option, together about 1), plus
        fields we do not use. A "noul" (yes or no) answer holds "noul", the
        probability of yes.

        Raises ModelNotDownloaded when the model files are not on disk, and
        whatever the model itself raises.
        """
        with self.model_lock:
            decider = self.load_model()
            start = time.perf_counter()
            result = decider.system_one(state, questions)
            answers = result["answers"]
            self.last_input_tokens = result.get("usage", {}).get("input_tokens", 0)
            logger.info(
                "Decision model: %s -> %s in %.0f ms",
                state.get("pilot_said") or state.get("event"),
                answers,
                (time.perf_counter() - start) * 1000,
            )
            return answers

    def warm_up(self) -> None:
        """Loads the model and makes it ready for the real commands, so the slow
        part happens at startup and not on the pilot's first command. The
        answers are thrown away. Blocking.

        The model is compiled again for every size of its input, and a
        compile takes seconds, so one tiny question is not enough.
        1. Asks one made up question, which loads the model.
        2. Asks the real command question about the real game state and the
           offered actions, which compiles the size of a real command.
        3. Compiles the sizes next to it (compile_engine_for_input_sizes_near).
        Steps 2 and 3 are left out when there is no game state yet or no action
        has a key, because then commands are not decided either. The pilot
        message of step 2 is a made up one, "deploy hardpoints". Called by
        download_and_load_model() right after loading, in a worker thread.
        Errors (ModelNotDownloaded, errors of the model) are raised.
        """
        state = {"game_state": "", "pilot_said": "deploy hardpoints"}
        self.ask_decision_model(state, WARM_UP_QUESTIONS)

        game_state = self.game_state_protocol.get_game_state_projection()
        offered_actions = self.find_actions_with_a_key()
        if not game_state or not offered_actions:
            return
        self.ask_which_action(game_state, "deploy hardpoints", offered_actions)
        self.compile_engine_for_input_sizes_near(self.last_input_tokens)

    def compile_engine_for_input_sizes_near(self, input_tokens: int) -> None:
        """Compiles the input size of a command (the smallest size the model
        has that holds input_tokens) and the size below and above it. A game
        state that grows or shrinks a little moves the prompt to the next size,
        and the first decision at a size that was never compiled takes seconds.
        Then Instinct runs over its time limit and the message goes to the LLM,
        and the compile, which runs in Python, slows the rest of the app
        meanwhile. Blocking, holds the model lock.

        Does nothing without the engine of the model (on a CPU), when
        input_tokens is 0 (the model did not tell its input size), or when
        input_tokens is bigger than the biggest size the engine has."""
        engine = getattr(self.decider, "eng", None)
        if engine is None or input_tokens <= 0:
            return
        from decider.engine import T_BUCKETS

        command_size = next((size for size in T_BUCKETS if size >= input_tokens), None)
        if command_size is None:
            return
        position = T_BUCKETS.index(command_size)
        nearby_sizes = T_BUCKETS[max(0, position - 1) : position + 2]
        with self.model_lock:
            engine.warmup([(1, size) for size in nearby_sizes])

    # ----- Fast commands -----

    async def try_fast_command(self, pilot_message: str) -> str | None:
        """Does the action the pilot asked for, without the LLM. Returns the
        short reply, the one COMMS shows and Celeste says. When a key was
        pressed it is the text of REPLY_TEXTS for what the key did, e.g.
        "Landing gear deployed" (a toggle is named after the direction it
        went, read from the ship before the press). When the ship cannot do
        the action now, nothing is pressed and the reply is the text of the
        tool up to the colon, e.g. "Landing gear unavailable". When the model took
        the message for a command but game actions are switched off, nothing is
        pressed and the reply is "Game actions disabled". Any other failure of
        the tool (the game window was not found) gives the text of the tool as
        it is, which has no prepared clip. None means "not handled", and then
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
                    self.ask_which_action, game_state, pilot_message, offered_actions
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
                return GAME_ACTIONS_DISABLED_TEXT
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
            return reply

        if tool_metadata.get("is_error"):
            reply = str(tool_result.return_value)
            logger.info(
                "Fast command %r: %s was not done (%s)",
                pilot_message,
                action.value,
                reply,
            )
            return reply

        logger.info(
            "Fast command %r: Instinct pressed %s in %.0f ms (%s)",
            pilot_message,
            action.value,
            (time.perf_counter() - start) * 1000,
            scores,
        )
        return pick_reply_text_for_pressed_action(action, ship_before_press)

    def is_module_enabled(self) -> bool:
        """True when Instinct may take a pilot message from the LLM: Instinct
        is on, the model is loaded and runs on the GPU ("cuda"). On the CPU one
        call takes about 2 s, so the LLM is faster there and Instinct stays out
        of it. A model that is still loading or failed to load has no device,
        so it gives False too. The first check of try_fast_command(). Only
        reads memory."""
        return self.enabled and self.running_device() == "cuda"

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

    def ask_which_action(
        self, game_state: str, pilot_message: str, offered_actions: list[EdAction]
    ) -> dict:
        """Blocking, so try_fast_command() runs it in a worker thread. Asks the
        model the one "action" question about offered_actions (see
        build_which_action_questions) and returns its answer: "choice" (an
        EdAction value or "none") and "probabilities" with a score for every
        option, together about 1. Raises what ask_decision_model raises
        (ModelNotDownloaded, errors of the model), try_fast_command catches
        them. May load the model first when it is not loaded."""
        state = {"game_state": game_state, "pilot_said": pilot_message}
        answers = self.ask_decision_model(
            state, build_which_action_questions(offered_actions)
        )
        return answers[COMMAND_QUESTION_NAME]

    # ----- Status for the UI and the cold start -----

    def get_status(self) -> InstinctStatus:
        """Snapshot for the Instinct row in settings. Checks the disk to see
        if the model is downloaded."""
        return InstinctStatus(
            state=self.get_model_state(),
            download_progress=self.download_progress,
            running_device=self.running_device(),
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
           still goes through Celeste. A model that runs on the CPU is a
           warning too: it is too slow, so the commands go through Celeste.
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
            device = self.running_device()
            if device is not None and device != "cuda":
                yield replace(
                    status,
                    completed=True,
                    is_warning=True,
                    message=f"model runs on the {device.upper()}, too slow for "
                    "commands. Commands go through Celeste.",
                )
                return
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
