# CLAUDE.md

Only the critical rules live here. Details are in skills, loaded on demand:

- `architecture-design` — data flow, layers, adding a game event, LLM / pydantic-ai tools
- `ui-conventions` — Textual TUI structure, widget placement, DI in the UI
- `configuration-reference` — `.env` and `config.yaml` keys, how settings load

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

> **Note:** Always activate the virtualenv before running any of these commands — nothing is installed globally.

The CI pipelines have a built-in Allure report of the test results, published from `main` to
https://iqsantiagow.github.io/EDCeleste/. The e2e conventions that feed it live in the `e2e-test-writer` agent.

The mutation tests and the e2e tests of the pipeline run on a remote runner (a VPS) when the
`edceleste-runner` MCP connector is connected, otherwise on this machine. The two subagents pick
by themselves. They send the working copy with `bash mutation_testing/send_code.sh`, which needs
`RUNNER_URL` (with the port, e.g. `http://100.x.y.z:8765`) and `RUNNER_TOKEN` in the environment.

## Pipeline of a feature or a bug fix

Go through the steps in order. Do not call the work done before step 6 is done.

1. **Implement** the feature or the fix.
2. **Unit tests** — write them with the `unit-test-writer` skill, until `python -m pytest` is green.
3. **End-to-end tests** — ask the `e2e-test-writer` subagent (`.claude/agents/e2e-test-writer.md`):
   1. It scans the changes and returns proposed scenarios. Review them and approve (or trim) them.
   2. After approval it writes the tests, runs them and reports passed and failed.
   3. A failed e2e test means the app breaks a business requirement. Fix the **app**, never the
      test, then run the e2e tests again until all are green. Change a test only when the
      scenario itself was wrong, and say so.
4. **Blind check** — before the PR run the `blind-check` skill (`.claude/skills/blind-check/SKILL.md`).
   The `blind-signature-reader` subagent guesses the changed methods from names alone (wrong
   guesses → rename), then from names plus docstrings (wrong guesses → better docstrings). Only
   backend logic is checked, everything under `src/edceleste/ui/` is skipped. It sees
   only stripped copies made by `signature_check/strip_method_bodies.py`; a hook blocks every other read.
   Iterate until all changes are correctly guessed and the blind check passes.

## Constraints

- No `tkinter` — forbidden by ruff config
- No direct `rich` imports — use Textual and CSS (`ui/css.tcss`) instead
- Tests never touch the real `config.yaml` — `SettingsService` always gets a temp folder
- Every module using `@inject` + `Provide[Container.*]` must be listed in `MODULES_USING_PROVIDE` in `containers/main_container.py`

- Every function and method has a docstring that describes its logic: the steps, side effects
  (event bus, network, files, stored state, UI messages, audio, tokens), error handling and what
  `None` or an empty result means. Never a docstring that only repeats the name. An `__init__`
  that only stores its dependencies needs none, `__call__` of a use case carries the description.
  A name that lies or is vague gets renamed first (`process_game_state_change` that only stores →
  `remember_latest_game_state`)
- Exception: a Textual method (`compose`, `on_mount`, `on_*`, `watch_*`, `action_*` and the like) gets
  no docstring. The library defines what it does, so a docstring would only retell the Textual docs.

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

This repository has already clean architecture and its only because it was designed by human. Do not re-invent a wheel, and keep it simple.
No one cares about super advanced programming techniques and hundreds of edge cases when user has multiple different network cards and two keyboards which he click simultaneously. NO ONE CARES. Do absolutely minimal work to keep it working and not crash to desktop in a basic use case. Keep it as simple as possible. if user want to break the app, then they will sooner or later, its not your or my business.


If you find a potential bug in your simple solution which will occur with rare or unusual setups, never try to cover that. No one cares, test agents will find that and create an issue, maybe someday someone will fix it. as soon as it works, no one cares.


## Code review
Look for overengineering, overcomplication, and unnecessary abstractions. Keep it simple and direct. Avoid unnecessary classes or methods that don't add value. Use clear and descriptive names for functions and variables.

Ape style coding is there? Good. Good Ape.
