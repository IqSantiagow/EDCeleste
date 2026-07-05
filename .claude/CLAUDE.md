# CLAUDE.md

## Commands

```bash
# Run the app
python app.py

# Lint
ruff check
ruff format --diff   # check only; drop --diff to auto-fix

# Tests with coverage
coverage run -m unittest discover
coverage report -m

# Run a single test file
python -m pytest tests/services/journal/test_journal_watcher.py
```

## Disclaimer - always activate venv, there is nothing installed globally

## Configuration

Copy `.env-example` to `.env`. Required variables (double-underscore = nested):

- `ED__MAIN_PATH` — path to `Saved Games\Frontier Developments\Elite Dangerous`
- `LLM__ANTHROPIC_API_KEY` — Anthropic API key
- `ED__LOGGING__LEVEL` — `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL`

Config is loaded via Pydantic-settings (`AppConfig` in `config/config.py`).

## Architecture

**Data flow:**
```
ED journal files → JournalWatcherService → EventBus → Projections → GameStateService
                                                                          ↓
                                        UIApp (Textual TUI) ← EdDashboard ← EdDashboardPresenter
                                                                          ↓
                                                                     LLMService
```

**Key layers:**

- `services/event_bus.py` — simple pub/sub by event type; subscribers registered via `subscribe(EventType, callback)`
- `services/journal_watcher_service.py` — polls latest `Journal*.log` from the ED directory, parses lines with Pydantic, publishes to `EventBus`
- `services/models/journal_event.py` — Pydantic discriminated union (`_JournalEvent`) that maps raw JSON `event` field to typed models; unknown events become `UnknownCheckedEvent`
- `projection/` — each `Projection` (protocol in `projection/event_projections/projection.py`) processes events and returns a text snippet for the LLM; `GameStateService` orchestrates all projections
- `ui/protocols/game_state_reader.py` — `GameStateReader` is a structural Protocol that `GameStateService` implements; the UI depends only on this protocol, not the concrete class
- `use_cases/` — thin callable classes that bridge `GameStateReader` → `DashboardViewModel`
- `containers/main_container.py` — single `dependency-injector` `DeclarativeContainer`; wires everything together; UI widgets are injected via `@inject` + `Provide[Container.*]`
- `ui/` — Textual TUI app; `UIApp` starts `JournalWatcherService` in a daemon thread on mount

**Adding a new game event:**
1. Add a Pydantic model in `services/models/game_events.py`
2. Register it in `KNOWN_EVENTS` and `_JournalEvent` union in `services/models/journal_event.py`
3. Handle it in the relevant `Projection`

## Constraints

- No `tkinter` — forbidden by ruff config
- No direct `rich` imports — use Textual and CSS (`ui/css.tcss`) instead
- LLM model: `claude-haiku-4-5-20251001` via LangChain Anthropic; configured in `services/llm_service.py`