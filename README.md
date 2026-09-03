# EDCeleste

LLM-powered terminal-like copilot for Elite Dangerous with a voice interface.

Celeste is an AI companion that reacts to in-game events in real time and acts like a human co-pilot. She reads the game's journal, keeps a live picture of your ship and location, listens and talks back, and can press keybinds on your behalf.

> **Status:** Active development — real-time journal parsing, game-state projections, a Textual dashboard, an LLM co-pilot chat, STT/TTS voice, and in-game action tooling are all working. EDMC / Galnet / E:D API lookups are still planned.

## Features

**Working today:**

- **Real-time journal ingestion** — `JournalWatcherService` finds the latest `Journal*.log`, tails it, and parses each line into typed Pydantic models published on an in-process event bus.
- **Typed event parsing** — a discriminated union covers game load, travel and location (`FSDJump`, `StartJump`, `Location`, `SupercruiseEntry/Exit`, `ApproachBody`, `LeaveBody`, `ApproachSettlement`), docking (`Docked`, `Undocked`, `DockingGranted`), fuel (`FuelScoop`, `RefuelAll`, `ReservoirReplenished`), and commander progression (`Commander`, `Rank`, `Promotion`, `Reputation`, `Died`, `Resurrect`). Unrecognised events fall back to `UnknownCheckedEvent` instead of crashing.
- **Game-state projections** — dedicated projections track the player (name, credits, ship, combat/trade/exploration ranks, faction reputation, alive/rebuy state), location (current system, docked station, supercruise, nearby body/settlement, active FSD jump), and fuel level/capacity. `GameStateService` aggregates them into a text snapshot that grounds the LLM.
- **LLM co-pilot (Celeste)** — `LLMService` talks to the LLM through a provider-agnostic `LLMSdkProtocol` adapter (`ClaudeAgentSDK` by default, or a chat-completions-compatible endpoint), with running conversation history and the current game state injected into each prompt. Responses and thinking/idle status are streamed to the UI.
- **STT voice input** — `SttService` runs a local Whisper model to transcribe speech, with live recording, input device selection, and an enable/disable toggle.
- **TTS voice output** — `TTSService` speaks Celeste's replies through a pluggable provider layer: `EdgeTTSProvider` (cloud) or `ChatterboxTTSProvider` (local voice cloning from a reference profile), with volume and voice/profile selection.
- **In-game action tooling** — the LLM can press keybinds through the `PerformGameAction` tool (`ToolProtocol`), which resolves bindings via `KeybindService`.
- **Event reactions** — `EventReactionsService` triggers an automatic LLM response for configurable journal events (e.g. `LoadGame`), driven by per-event toggles in `config.yaml`.
- **Persistent settings** — `SettingsService` loads and live-edits `config.yaml` (paths, LLM provider, TTS, STT, event reactions) through the UI, backed by `use_cases/settings/`.
- **Textual TUI dashboard** — an amber-themed grid with:
  - a header showing live **SYS / SHIP / FUEL** stats plus **LLM / JRNL** health indicators (`OK` / `FAIL`),
  - a **COMMS** chat panel where you type commands and watch Celeste's streamed replies,
  - a **SHIP LOG** panel that streams journal events as they arrive.
- **Health checks** — the journal watcher and the LLM endpoint are polled and surfaced live in the header.

> The dashboard can run against live journal files (`JournalWatcherService`) or a bundled sample event stream (`JournalWatcherServiceStub`, used by default during UI development).

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
pip install .
```

## Configuration

Copy and edit the env file (process bootstrap — logging only):

```bash
cp .env-example .env
```

- `LOGGING__LEVEL` — `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL`

Copy and edit the app settings file (journal/keybinds paths, LLM, speech, and event reactions):

```bash
cp config-example.yaml config.yaml
```

- `paths.journal_path` — your Elite Dangerous journal directory (typically `C:\Users\<you>\Saved Games\Frontier Developments\Elite Dangerous`).
- `paths.keybindings_path` — the folder containing your `.binds` keybindings file(s).
- `llm.provider` — LLM backend configuration. The default is:

  ```yaml
  provider:
    type: claude_agent_sdk
    model: claude-haiku-4-5-20251001
  ```

  To use a compatible chat-completions endpoint instead, configure `type: chat_completions` together with `model`, `base_url`, and `bearer_token`.
- `llm.system_prompt` — instructions given to Celeste. `llm.user_prompt` is a saved prompt reserved for future use and is not sent by the current LLM service.
- `tts.provider` — text-to-speech provider. `type: edge` uses Microsoft Edge's cloud voices (`voice`); `type: chatterbox` clones a local voice `profile` (with `exaggeration`, `cfg_weight`, `device`, `nano`). `tts.volume` must be between `0.0` and `1.0`.
- `stt.enabled` / `stt.model` / `stt.input_device` — speech-to-text toggle, Whisper model, and optional audio input-device index. Omit `input_device` or set it to `null` to use the system default device.
- `event_reaction.reactions` — map of journal event names to booleans. Set an event to `true` when Celeste should react to it automatically; set it to `false` to suppress the automatic reaction. Keep the event list from `config-example.yaml`; unknown names are ignored and missing supported events default to `false`.

The Claude Agent SDK uses its own Anthropic authentication setup. When using `chat_completions`, put the endpoint token in `llm.provider.bearer_token`.

## Usage

Install the package into your virtualenv, then launch it with the console command:

```bash
pip install -e .
edceleste
```

`python -m edceleste` works too and does exactly the same thing.

## Development

```bash
# Lint
ruff check
ruff format --diff        # check only; drop --diff to auto-fix

# Tests with coverage
coverage run -m pytest
coverage report -m

# Run a single test file
python -m pytest tests/services/journal/test_journal_watcher.py
```

## Debugging

Run the console in a separate terminal to see logs and events:

```bash
textual console -x EVENT --port 5000
```

Run the app in dev mode so it connects to that console:

```bash
textual run --dev --port 5000 src/edceleste/__main__.py
```

## Architecture

```
ED journal files → JournalWatcherService → EventBus → Projections → GameStateService
                                                            ↓                ↓
                                                EventReactionsService   UIApp (Textual TUI) ← EdDashboardRepository ← use_cases
                                                            ↓                ↓
                                            STTService → LLMService (adapters/: LLMSdkProtocol, ToolProtocol → PerformGameAction → KeybindService)
                                                            ↓
                                            TTSService (services/tts_providers/: edge / chatterbox)
```

- `services/` — core services: event bus, journal watcher, game state, LLM, TTS, STT, event reactions, keybinds, settings.
- `services/tts_providers/` — pluggable `TtsProviderProtocol` implementations (`EdgeTTSProvider`, `ChatterboxTTSProvider`).
- `adapters/` — external SDK implementations (`ClaudeAgentSDK`, an `LLMSdkProtocol` adapter) and tools (`PerformGameAction`, a `ToolProtocol` implementation the LLM can call).
- `projection/` — per-concern projections (player, location, fuel) that build the LLM's game-state snapshot.
- `use_cases/` — thin callables bridging the game/LLM state to UI view models; `use_cases/settings/` holds the settings-editing use cases (get/update settings, list voices/devices, clone a voice, load keybinds).
- `containers/` — a single `dependency-injector` container wiring everything together.
- `ui/` — the Textual TUI (dashboard widgets, screens, themes, CSS).
- `config/` — pydantic-settings config loading (logging).
- `services/settings_service.py` — `SettingsService`, loading/persisting `config.yaml` (journal/keybinds paths, LLM provider, TTS provider/volume, STT settings, event reactions).

## Project Structure

```
EDCeleste/
├── pyproject.toml         # Packaging metadata, `edceleste` console script
├── config-example.yaml    # Template for config.yaml (source of truth for settings fields)
├── src/
│   └── edceleste/
│       ├── __main__.py    # Entry point (main())
│       ├── adapters/      # LLM SDK adapters (ClaudeAgentSDK) and tools (PerformGameAction)
│       │   └── tools/         # ToolProtocol implementations callable by the LLM
│       ├── config/        # Config loading (pydantic-settings + .env), tracing
│       ├── containers/    # dependency-injector wiring
│       ├── projection/    # Event projections (fuel, location, player)
│       ├── protocols/     # Structural protocols (game state, journal, LLM SDK, tool, TTS/STT, voice cloning, settings, keybinds, event reactions, device detection)
│       ├── services/      # Core services (journal watcher, event bus, LLM, game state, TTS, STT, event reactions, keybinds, settings)
│       │   ├── event_bus.py   # Pub/sub event bus
│       │   ├── exceptions/    # Service-specific exceptions (STT, voice cloning)
│       │   ├── models/        # Pydantic models for journal events and settings
│       │   ├── stubs/         # Sample event stream for UI development
│       │   └── tts_providers/ # Pluggable TTS providers (EdgeTTSProvider, ChatterboxTTSProvider)
│       ├── use_cases/     # UI-facing use cases (streaming stats, events, LLM)
│       │   └── settings/      # Settings use cases (get/update settings, list voices/devices, clone voice, load keybinds)
│       └── ui/            # Textual TUI (widgets, screens, themes, css.tcss)
└── tests/                 # Tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
