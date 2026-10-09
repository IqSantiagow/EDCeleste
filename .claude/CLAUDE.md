# CLAUDE.md

## Commands

```bash
# Run the app (after `pip install -e .`)
edceleste

# Lint
ruff check
ruff format --diff   # check only; drop --diff to auto-fix

# Type check (settings in pyproject.toml)
mypy

# Tests with coverage
coverage run -m pytest
coverage report -m

# Run a single test file
python -m pytest tests/services/journal/test_journal_watcher.py

# Mutation tests (mutmut needs Linux; on Windows this runs in Docker, report in mutation_testing/report/)
bash mutation_testing/run_in_docker.sh src/edceleste/services/event_bus.py   # given files
bash mutation_testing/run_in_docker.sh                                       # whole project, ~30 min
```

After implementing a feature or a bug fix and once the tests pass, ask the `mutation-tester`
subagent (`.claude/agents/mutation-tester.md`) to check the changed files, then add the tests
for the gaps it reports. The `mutation` job in `.github/workflows/pr-pipeline.yml` runs the same
check on the source files a PR changes and fails below `MIN_MUTATION_SCORE` (75%).

Every function and method has a docstring that describes its logic: the steps, side effects
(event bus, network, files, stored state, UI messages, audio, tokens), error handling and what
`None` or an empty result means. Never a docstring that only repeats the name. An `__init__`
that only stores its dependencies needs none, `__call__` of a use case carries the description.
A name that lies or is vague gets renamed first (`process_game_state_change` that only stores →
`remember_latest_game_state`). Before a PR, run the `blind-check` skill
(`.claude/skills/blind-check/SKILL.md`): the `blind-signature-reader` subagent first guesses the
changed methods from names alone (wrong guesses → rename), then from names plus docstrings what
they return, raise and change (wrong guesses → better docstrings). It sees only stripped copies
made by `signature_check/strip_method_bodies.py`, a hook blocks every other read.

Every push to `main` runs `lint` and `test` again, and the `report` job of the same workflow turns
the pytest results into an Allure 3 report (`allurerc.json`) and publishes it to the `gh-pages`
branch, with the last 50 runs in `history.jsonl`: https://iqsantiagow.github.io/EDCeleste/.
Pull requests publish nothing.

End-to-end tests (`tests/e2e/`) read like scenarios in that report: every test has an
`@allure.title` in plain words, every file an `allure.feature`, and the body is split into
`with allure.step("Given / When / Then ...")` blocks. Use `with`, not the `@allure.step`
decorator, which does not wait for an `async def`. Unit tests need no steps.
Before `allure generate`, the `report` job runs `tests/allure_report/hide_empty_fixtures.py`,
which drops every fixture without steps that did not fail (`tmp_path`, `monkeypatch`, pytest's
cleanup lambdas), so "Set up" and "Tear down" show only the steps of the `edceleste` fixture.

> **Note:** Always activate the virtualenv before running any of these commands — nothing is installed globally.

## Configuration

Two independent, both-gitignored config sources:

- **`.env`** (copy from `.env-example`) — process bootstrap, loaded via Pydantic-settings (`AppConfig` in `config/config.py`). Only `logging`:
  - `LOGGING__LEVEL` — `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL` (required)

- **`config.yaml`** (copy from `config-example.yaml`) — user/runtime settings, loaded via `services/settings_service.py` (`SettingsService`) into `SettingsModel` (`services/models/settings_model.py`):
  - `paths.journal_path` / `paths.keybindings_path`
  - `llm.provider` — `type` (any provider name in `SUPPORTED_LLM_PROVIDER_TYPES`,
    `services/models/settings_model.py`), `model`, `api_key` and an optional
    `base_url` for providers without a public endpoint (ollama, vllm, azure).
  - `llm.system_prompt` — used to build the LLM agent
  - `llm.instinct` — `enabled` and `device` (`auto` | `cuda` | `cpu`) of Instinct, the local
    fast-command model. `InstinctService` downloads it on first use to
    `%LOCALAPPDATA%\EDCeleste\models` and loads it; its repo and revision are fixed in
    `decision_model_download_service.py`.
  - `llm.user_prompt` (reserved, not wired into `LLMService` yet)
  - `tts.provider` — `edge` (`voice`) or `chatterbox` (`profile`, `exaggeration`,
    `cfg_weight`, `device`, `nano`); `tts.volume` is `0.0`–`1.0`
  - `tts.voice_lab` — voice effects for either engine (`VoiceLabService` in `services/voice_lab_service.py`, applied
    right before `sd.play`): `enabled`, `clarity`, `reverb`, `stereo_width`, each `0.0`–`1.0`,
    `0.5` = fitted to Celeste's voice clip
  - `stt.enabled` / `stt.model` / `stt.input_device`
  - `event_reactions.reactions` — per-journal-event booleans for automatic replies
  - `game_actions.enabled` — safety toggle for the `PerformGameAction` tool (default `false`)

  `SettingsService.load_settings()` runs eagerly the first time the DI container resolves it (`containers/main_container.py`), before any service needing a bootstrap value is built. If `config.yaml` is missing, it's auto-created from `config-example.yaml` and startup fails with `FileNotFoundError` asking you to edit it and restart. Both paths are constructor arguments of `SettingsService` (`config_path`, `example_config_path`) — tests always pass a temp folder, never the real `config.yaml`.

## Architecture

**Data flow:**
```
ED journal files → GameWatcherService → EventBus → Projections → GameStateService
                                                                       ↓
                         UIApp (Textual TUI) ← DashboardScreen ← EdDashboardRepository
                                                                       ↓
                                                                  LLMService
```

**Key layers:**

All source lives under `src/edceleste/`; the paths below are relative to that package root.

- `services/event_bus.py` — simple pub/sub by event type; subscribers registered via `subscribe(EventType, callback)`
- `services/game_watcher_service.py` — `GameWatcherService` follows the newest `Journal*.log` (plus `Status.json` and `Market.json`) in the ED directory, parses lines with Pydantic, publishes to `EventBus`
- `services/models/journal_event.py` — Pydantic discriminated union (`JournalEvent`) that maps raw JSON `event` field to typed models; unknown events become `UnknownCheckedEvent`
- `projection/` — each `Projection` (protocol in `projection/event_projections/projection.py`) processes events and returns a text snippet for the LLM; `GameStateService` orchestrates all projections
- `protocols/game_state_protocol.py` — `GameStateProtocol` is a structural Protocol that `GameStateService` implements; the UI depends only on this protocol, not the concrete class
- `use_cases/` — thin callable classes that depend on service protocols from `protocols/` (e.g. `GameStateProtocol`, `LLMProtocol`) and turn their data into UI view models (e.g. `ShipStatsViewModel`)
- `containers/main_container.py` — single `dependency-injector` `DeclarativeContainer`; wires everything together; UI widgets are injected via `@inject` + `Provide[Container.*]`; every module that does this must be listed in `MODULES_USING_PROVIDE` (same file) — `tests/containers/test_wired_modules.py` fails otherwise
- `ui/` — Textual TUI app; `UIApp` pushes `SystemCheckScreen` on mount, which runs every service's `cold_start()`; `GameWatcherService.cold_start()` starts its own `asyncio` watcher tasks, and `DashboardScreen.on_unmount()` stops them
- `__main__.py` — `main()`, exposed as the `edceleste` console script in `pyproject.toml`

**Adding a new game event:**
1. Add a Pydantic model in `services/models/game_events.py`
2. Register it in `KNOWN_EVENTS` and `_JournalEvent` union in `services/models/journal_event.py`
3. Handle it in the relevant `Projection` — `tests/projection/test_recognized_events_feed_game_state.py` fails when a recognized event is handled by no projection (it looks for `isinstance(event, <Model>)` in `projection/event_projections/`)

## Constraints

- No `tkinter` — forbidden by ruff config
- No direct `rich` imports — use Textual and CSS (`ui/css.tcss`) instead
- The LLM runs through `pydantic-ai`. `LLMService` builds an `Agent` in `reload_service()` and streams it with `run_stream_events`. Providers are not hand wired: `build_provider` calls `infer_provider_class(type)(api_key=...)` and `build_model` calls `infer_model("<type>:<model>")` with that provider, so every provider `pydantic_ai` supports works from config alone. Default: `openrouter` with `anthropic/claude-haiku-4.5`. Tools are plain objects implementing `ToolProtocol` and are wrapped with `pydantic_ai.Tool` in `LLMService.build_tools()` — `pydantic_ai` derives the arguments from the `execute` signature and the description from its docstring, so a tool never hand writes a JSON schema

## UI rules
- Widgets used only within specific widgets should be kept in one file. F.e `WidgetCommsInput` is only used within the dashboard screen, so it stays in `ui/screens/dashboard/widgets/comms/widget_comms_input.py`.
- Follow the following structure when creating new things in the UI: 
  - `ui/screens/<screen_name>/widgets/` — widgets specific to a screen
  - `ui/screens/<screen_name>/view_models/` — view models specific to a screen
  - `ui/screens/<screen_name>/services/` — services specific to a screen
  - `ui/screens/<screen_name>/repositories/` — repositories specific to a screen

## Ape style code
- Write a code so understandable that even an ape can understand it. Use simple names and exhausting function and variable names

<reasoning_example>
> User ordered to add a new feature to the LLMService that allows it to register tools dynamically. 
Hmm... Lets write this in that way
 ```python                                                                                                                                                                                                                                                                                                                                 
import importlib
import pkgutil
from typing import Callable

_TOOL_REGISTRY: dict[str, Callable] = {}

def register(name: str | None = None):
    def decorator(fn: Callable) -> Callable:
        _TOOL_REGISTRY[name or fn.__name__] = fn
        return fn
    return decorator

def load_all_tools(package: str) -> None:
    pkg = importlib.import_module(package)
    for _, mod_name, _ in pkgutil.walk_packages(pkg.__path__, prefix=f"{package}."):
        importlib.import_module(mod_name)

def get_tool(name: str) -> Callable:
    if name not in _TOOL_REGISTRY:
        raise KeyError(f"Tool '{name}' not registered")
    return _TOOL_REGISTRY[name]
 ```    

 > But wait, i am an superior AI and i can understand that, but ape wont. I need more concise and simple code without clutter.
```python
def register_tool(name: str, func: Callable) -> None:
    self.tools = [PerformGameAction()]
    self.__agent.register_tools(self.tools)

def get_tool(name: str) -> Callable:
    return self.tools[name]
```

> Now its simple, maybe its not too much but ape can understand it. Good ape.


## Code review
Look for overengineering, overcomplication, and unnecessary abstractions. Keep it simple and direct. Avoid unnecessary classes or methods that don't add value. Use clear and descriptive names for functions and variables.

Ape style coding is there? Good. Good Ape.