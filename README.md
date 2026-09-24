# EDCeleste

LLM-powered terminal-like copilot for Elite Dangerous with a voice interface.

Celeste is an AI companion that reacts to in-game events in real time and acts like a human co-pilot. She reads the game's journal, keeps a live picture of your ship and location, listens and talks back, and can press keybinds on your behalf.

> **Status:** Active development — real-time journal parsing, game-state projections, a Textual dashboard with a settings screen, an LLM co-pilot chat, STT/TTS voice, and in-game action tooling are all working. EDMC / Galnet / E:D API lookups are still planned.

## Features

**Working today:**

- **Real-time game file watching** — `GameWatcherService` tails the latest `Journal*.log` and also watches the `Status.json` and `Market.json` side files. Every line is parsed into a typed Pydantic model and published on an in-process event bus.
- **Typed event parsing** — a discriminated union covers game load and ship loadout (`LoadGame`, `Loadout`), travel and location (`FSDTarget`, `StartJump`, `FSDJump`, `Location`, `SupercruiseEntry/Exit`, `SupercruiseDestinationDrop`, `ApproachBody`, `LeaveBody`, `ApproachSettlement`), docking (`Docked`, `Undocked`, `DockingGranted`), fuel (`FuelScoop`, `RefuelAll`, `ReservoirReplenished`) and commander progression (`Commander`, `Rank`, `Promotion`, `Reputation`, `Died`, `Resurrect`). Unrecognised events fall back to `UnknownCheckedEvent` instead of crashing.
- **Game-state projections** — player, location, fuel, ship, loadout and market projections each keep one slice of the game state. `GameStateService` runs them all, streams stats to the dashboard and publishes a text snapshot that grounds the LLM.
- **LLM co-pilot (Celeste)** — `LLMService` runs a [`pydantic-ai`](https://ai.pydantic.dev) `Agent`. The provider is built from config alone, so every provider `pydantic-ai` supports works (OpenRouter by default). The current game state and conversation history go with every prompt; replies, thinking, tool calls and tool results are streamed to the UI. Voice rules (short spoken sentences, no markdown) are always put in front of your system prompt.
- **STT voice input** — `SttService` runs a local Whisper model to transcribe speech, with input device selection and an enable/disable toggle.
- **TTS voice output** — `TTSService` speaks Celeste's replies through a pluggable provider: `EdgeTTSProvider` (Microsoft Edge cloud voices) or `ChatterboxTTSProvider` (local voice cloning from a reference profile). Voice profiles can be recorded, cloned, previewed, renamed and removed from the settings screen.
- **In-game action tooling** — the LLM can press keybinds through the `PerformGameAction` tool, which resolves bindings from your `.binds` file via `KeybindService`. Off by default (`game_actions.enabled`).
- **Event reactions** — `EventReactionsService` triggers an automatic LLM reply for the journal events you switch on in `config.yaml` (by default only `LoadGame`).
- **Textual TUI** — an amber-themed app with three screens:
  - **PREFLIGHT** — on start every service runs its cold start (settings, game watcher, keybinds, LLM, TTS, STT, event reactions) with a progress bar. A critical failure stops the app, a non-critical one is shown and skipped.
  - **Dashboard** — a header with commander, ship, credits and clock; **NAVIGATION**, **FLIGHT & DRIVE** and **SHIP** stat panels; a **COMMS** chat panel where you type or speak to Celeste; and a tabbed **SHIP LOG** (live journal feed and the station market card; the other tabs are placeholders for now).
  - **Settings** — edit keybinds, paths, event reactions, LLM, TTS, STT and game actions. Every section is validated by its service before it is saved to `config.yaml`.

**Planned:** EDMC / Galnet / E:D API lookups.

![alt text](image.png)

## Setup

**Requirements:** Python 3.12+, Elite Dangerous (PC)

```bash
git clone https://github.com/IqSantiagow/EDCeleste
cd EDCeleste
python -m venv .venv
.venv/Scripts/activate     # Windows
source .venv/bin/activate  # Linux/macOS
pip install -e .
```

## Configuration

There are two config files. Both are gitignored.

### `.env` — process bootstrap (logging only)

```bash
cp .env-example .env
```

- `LOGGING__LEVEL` — `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL` (required)

### `config.yaml` — app settings

```bash
cp config-example.yaml config.yaml
```

If you skip this step, the first start copies `config-example.yaml` to `config.yaml` for you and exits with a message asking you to edit it and restart. The file is read from the current working directory, so start the app from the repo root.

Most of these values can also be changed later in the app's settings screen (`Ctrl+R`).

- `paths.journal_path` — your Elite Dangerous journal directory (typically `C:\Users\<you>\Saved Games\Frontier Developments\Elite Dangerous`). `Status.json` and `Market.json` are read from the same folder.
- `paths.keybindings_path` — the folder containing your `.binds` keybindings file(s) (typically `C:\Users\<you>\AppData\Local\Frontier Developments\Elite Dangerous\Options\Bindings`).
- `llm.provider` — the LLM backend. The default is:

  ```yaml
  provider:
    type: "openrouter"
    model: "anthropic/claude-haiku-4.5"
    api_key: ""
    base_url: ""
  ```

  - `type` — any provider name from `SUPPORTED_LLM_PROVIDER_TYPES` in `services/models/settings_model.py` (for example `openrouter`, `anthropic`, `openai`, `google`, `ollama`, `vllm`, `azure`, `groq`, `mistral`). A few of them (`bedrock`, `cohere`, `groq`, `mistral`, `voyageai`, `xai`) need an extra package installed; the settings check tells you which one.
  - `model` — the model name exactly as the provider names it.
  - `api_key` — the provider's API key.
  - `base_url` — leave empty for the provider's default endpoint. Needed for providers without a public endpoint, like a local `ollama` or `vllm` server.
- `llm.system_prompt` — instructions given to Celeste. `llm.user_prompt` is saved but not sent by the LLM service yet.
- `tts.provider` — text-to-speech provider:
  - `type: edge` with `voice` (for example `en-GB-SoniaNeural`),
  - `type: chatterbox` with `profile` (a voice profile from the voices directory — `%LOCALAPPDATA%\EDCeleste\voices` on Windows), `exaggeration` (`0.0`–`2.0`), `cfg_weight` (`0.0`–`1.0`), `device` (`auto` | `cuda` | `cpu`) and `nano` (faster model that ignores `exaggeration` and `cfg_weight`).
- `tts.volume` — between `0.0` and `1.0`.
- `stt.enabled` / `stt.model` / `stt.input_device` — speech-to-text toggle, Whisper model (for example `tiny.en`) and an optional audio input device index. Omit `input_device` or set it to `null` to use the system default device.
- `event_reactions.reactions` — journal event name → boolean. `true` makes Celeste react to that event automatically. Unknown names are ignored and missing events default to `false`.
- `game_actions.enabled` — safety toggle. When `false` (the default) the LLM cannot press keybinds through the `PerformGameAction` tool.

## Usage

Launch the app with the console command (from the repo root, with the virtualenv active):

```bash
edceleste
```

`python -m edceleste` works too and does exactly the same thing.

| Key      | Where     | Action                               |
|----------|-----------|--------------------------------------|
| `Ctrl+R` | Dashboard | Open settings                        |
| `Ctrl+E` | Dashboard | Toggle the ship log to full width    |
| `Ctrl+S` | Settings  | Validate and save settings           |
| `Esc`    | Settings  | Back to the dashboard                |
| `Ctrl+C` | Anywhere  | Quit                                 |

## Development

Install the dev and test extras (ruff, mypy, textual-dev, coverage):

```bash
pip install -e ".[dev,test]"
```

```bash
# Lint
ruff check
ruff format --diff        # check only; drop --diff to auto-fix

# Tests with coverage
coverage run -m unittest discover
coverage report -m

# Run a single test file
python -m unittest tests.services.journal.test_journal_watcher
```

## Debugging

Run the Textual console in a separate terminal to see logs and events:

```bash
textual console -x EVENT --port 7342
```

Run the app in dev mode so it connects to that console:

```bash
textual run --dev --port 7342 -c edceleste
```

## Architecture

```
ED journal + Status.json + Market.json
            ↓
   GameWatcherService → EventBus → GameStateService (projections) → dashboard stats / SHIP LOG
                           │              ↓
                           │       GameStateChangedEvent (text snapshot)
                           ↓              ↓
               EventReactionsService → LLMService (pydantic-ai Agent) ← COMMS input / SttService
                                          │    └─ tools: PerformGameAction → KeybindService
                                          ↓
                                      TTSService (edge / chatterbox)
```

All source lives under `src/edceleste/`; the paths below are relative to that package.

- `services/` — core services: event bus, game watcher, game state, LLM, TTS, STT, event reactions, keybinds, settings. Each one implements `cold_start()` (used by the PREFLIGHT screen), `validate_settings()` and `reload_service()`.
- `services/models/` — Pydantic models for journal and side-file events (`game_events.py`, `journal_event.py`), settings (`settings_model.py`) and the stats sent to the UI.
- `services/tts_providers/` — `EdgeTTSProvider` and `ChatterboxTTSProvider`.
- `services/stubs/` — `GameWatcherServiceStub`, a sample event stream for UI development without the game.
- `projection/` — one `Projection` per concern (player, location, fuel, ship, loadout, market). Each turns events into state and a text snippet for the LLM.
- `adapters/tools/` — tools the LLM can call. A tool is a plain object implementing `ToolProtocol`; `pydantic-ai` derives its arguments from the `execute` signature and its description from the docstring.
- `protocols/` — structural protocols the UI and use cases depend on instead of concrete services.
- `use_cases/` — thin callables between services and the UI, grouped by screen (`app/`, `dashboard/`, `settings/`, `system_check/`).
- `containers/main_container.py` — a single `dependency-injector` container wiring everything together.
- `ui/` — the Textual app. Each screen lives in `ui/screens/<screen>/` with its own `widgets/`, `view_models/` and repository; shared widgets are in `ui/widgets/`, styles in `ui/css.tcss`.
- `config/` — pydantic-settings loading of `.env` (logging).

**Adding a new game event:**

1. Add a Pydantic model in `services/models/game_events.py`.
2. Register it in `JournalEventType` and the `JournalEvent` union in `services/models/journal_event.py`.
3. Handle it in the relevant projection.

## Project Structure

```
EDCeleste/
├── pyproject.toml         # Packaging metadata, `edceleste` console script
├── .env-example           # Template for .env (logging level)
├── config-example.yaml    # Template for config.yaml (app settings)
├── src/
│   └── edceleste/
│       ├── __main__.py    # Entry point (main())
│       ├── adapters/
│       │   └── tools/         # Tools the LLM can call (PerformGameAction)
│       ├── config/        # .env loading (pydantic-settings)
│       ├── containers/    # dependency-injector wiring
│       ├── projection/    # Game-state projections (player, location, fuel, ship, loadout, market)
│       ├── protocols/     # Structural protocols (game state, LLM, tool, TTS/STT, voice cloning, settings, keybinds, ...)
│       ├── services/      # Core services
│       │   ├── exceptions/    # Service-specific exceptions (STT, voice cloning)
│       │   ├── models/        # Pydantic models for events, settings and stats
│       │   ├── stubs/         # Sample event stream for UI development
│       │   └── tts_providers/ # Edge and Chatterbox TTS providers
│       ├── use_cases/     # UI-facing use cases
│       │   ├── app/           # Header stats
│       │   ├── dashboard/     # Stats, journal, LLM and STT streams
│       │   ├── settings/      # Settings, voices, devices, models, keybinds
│       │   └── system_check/  # PREFLIGHT cold start
│       └── ui/            # Textual TUI
│           ├── screens/       # app (header), dashboard, settings, system_check
│           ├── themes/        # Amber theme
│           ├── widgets/       # Shared widgets
│           └── css.tcss       # All styles
└── tests/                 # Tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
