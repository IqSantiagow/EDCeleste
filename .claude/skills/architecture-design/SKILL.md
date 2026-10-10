---
name: architecture-design
description: EDCeleste architecture — data flow from journal files to the LLM, what each layer under src/edceleste/ does, how to add a new game event, how the pydantic-ai LLMService and its tools work. Use when adding or changing services, projections, events, use cases, the DI container, LLM providers or tools, or when you need to know which layer a piece of code belongs in.
---

All source lives under `src/edceleste/`; paths below are relative to that package root.

## Data flow

```
ED journal, Status.json, Market.json → GameWatcherService → EventBus → Projections → GameStateService
                                                                          ↓
                                        UIApp (Textual TUI) ← DashboardScreen ← EdDashboardRepository
                                                                          ↓
                                                                     LLMService
```

## Layers

- `services/event_bus.py` — simple pub/sub by event type; subscribers registered via `subscribe(EventType, callback)`
- `services/game_watcher_service.py` — `GameWatcherService` runs three `asyncio` tasks: it tails the latest `Journal*.log` (parses lines with Pydantic, publishes to `EventBus`) and watches `Status.json` and `Market.json`, publishing `StatusEvent` and `MarketEvent`. It is started by `cold_start()` / `reload_service()` and stopped by `DashboardScreen.on_unmount()`; it implements `protocols/game_watcher_protocol.py`
- `services/models/journal_event.py` — `JournalEventType` enum plus the Pydantic discriminated union `JournalEvent` (tagged by `event_discriminator`) that maps the raw JSON `event` field to typed models; unknown events become `UnknownCheckedEvent`
- `projection/` — each `Projection` (protocol in `projection/event_projections/projection.py`) processes events and returns a text snippet for the LLM; `GameStateService` orchestrates all projections
- `protocols/game_state_protocol.py` — `GameStateProtocol` is a structural Protocol that `GameStateService` implements; the UI depends only on this protocol, not the concrete class
- `use_cases/` — thin callable classes that depend on service protocols from `protocols/` (e.g. `GameStateProtocol`, `LLMProtocol`) and turn their data into UI view models (`use_cases/dashboard/stream_*_use_case.py`); settings and system-check use cases live in their own subfolders
- `use_cases/system_check/system_check_use_case.py` — runs `cold_start()` of every service (including `GameWatcherService`) behind the `SystemCheckScreen` before the dashboard opens
- `containers/main_container.py` — single `dependency-injector` `DeclarativeContainer`; wires everything together; every module using `@inject` + `Provide[Container.*]` must be listed in `MODULES_USING_PROVIDE` (same file) — `tests/containers/test_wired_modules.py` fails otherwise
- `ui/` — Textual TUI app (see the `ui-conventions` skill)
- `__main__.py` — `main()`, exposed as the `edceleste` console script in `pyproject.toml`

## Adding a new game event

1. Add a Pydantic model in `services/models/game_events.py`
2. In `services/models/journal_event.py` add it to `JournalEventType`, to `KNOWN_EVENTS` and to the `JournalEvent` union (`Annotated[<Model>, Tag(JournalEventType.<Name>)]`)
3. Handle it in the relevant `Projection` — `tests/projection/test_recognized_events_feed_game_state.py` fails when a recognized event is handled by no projection (it looks for `isinstance(event, <Model>)` in `projection/event_projections/`)

## LLM (pydantic-ai)

- The LLM runs through `pydantic-ai`. `LLMService` builds an `Agent` in `reload_service()` and streams it with `run_stream_events`.
- Providers are not hand wired: `build_provider` calls `infer_provider_class(type)(api_key=...)` and `build_model` calls `infer_model("<type>:<model>")` with that provider, so every provider `pydantic_ai` supports works from config alone. Default: `openrouter` with `anthropic/claude-haiku-4.5`.
- Tools are plain objects implementing `ToolProtocol` and are wrapped with `pydantic_ai.Tool` in `LLMService.build_tools()`. `pydantic_ai` derives the arguments from the `execute` signature and the description from its docstring, so a tool never hand writes a JSON schema.
