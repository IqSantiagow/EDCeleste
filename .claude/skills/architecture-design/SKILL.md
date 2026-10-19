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
- `services/game_watcher_service.py` — `GameWatcherService` starts one `asyncio` task that first loads, then follows: it reads the latest `Journal*.log` from its first line, then `Status.json` and `Market.json` once (parses with Pydantic, publishes to `EventBus`), then publishes `StartupLoadingFinishedEvent`, and from then on tails the journal (from where the loading stopped) and watches `Status.json` and `Market.json`, publishing `StatusEvent` and `MarketEvent`. It is started by `cold_start()` / `reload_service()` and stopped by `DashboardScreen.on_unmount()`; it implements `protocols/game_watcher_protocol.py`
- Startup loading — whatever the game had already written when the app starts is **loading**, whatever it writes later is **live**. Every loading event carries `GameEvent.is_startup_loading = True` (set only by the watcher, never read from a file, never in a JSON dump). A loading event builds state only: the projections consume it, but `EventReactionsService` skips it (no reaction, no LLM request) and `GameStateService.process_event` stops after the projections (no UI stream, no state text rebuild, no `GameStateChangedEvent`). When `StartupLoadingFinishedEvent` arrives, `GameStateService.publish_game_state_after_startup_loading` wakes the stats and market streams once and publishes the state for the LLM. Anything new that reacts to `GameEvent` (a service that talks to the LLM, a sound, a key press) must check `is_startup_loading` and ignore loading events. Projections must overwrite rather than accumulate, so loading the same files twice gives the same state
- `services/models/journal_event.py` — `JournalEventType` enum plus the Pydantic discriminated union `JournalEvent` (tagged by `event_discriminator`) that maps the raw JSON `event` field to typed models; unknown events become `UnknownCheckedEvent`
- `projection/` — each `Projection` (protocol in `projection/event_projections/projection.py`) processes events and returns its sentences for the LLM, joined with one space; `GameStateService` orchestrates all projections: it keeps them in a list in a fixed order (commander → location → ship → fuel → hull → market) and puts each non-empty text on its own line. A new projection goes into that list where it belongs. The "Current game state is:" heading is added only by `LLMService` when it builds the prompt
- `protocols/game_state_protocol.py` — `GameStateProtocol` is a structural Protocol that `GameStateService` implements; the UI depends only on this protocol, not the concrete class
- `use_cases/` — thin callable classes that depend on service protocols from `protocols/` (e.g. `GameStateProtocol`, `LLMProtocol`) and turn their data into UI view models (`use_cases/dashboard/stream_*_use_case.py`); settings and system-check use cases live in their own subfolders
- Fast commands — every pilot message goes to `use_cases/dashboard/send_pilot_message_use_case.py` first. It asks `InstinctService.try_fast_command()`: the local decision model gets one `choice` question over the actions that have a key (`services/models/instinct_actions.py`, the texts the model was trained on) and `none`. There is no threshold, the model's choice decides. It decides only on the GPU, within 1 s, and only when game actions are on. The chosen action goes to the `PerformGameAction` tool (`adapters/tools/perform_game_action.py`), the same one the LLM calls and the only place that presses a key. It holds the table of what the ship cannot do (`get_unavailable_reason`: landing gear, cargo scoop and hardpoints are refused when docked, landed, in supercruise or in a hyperspace jump) and decides from `GameStateProtocol.get_game_stats()`, the state the projections already built from Status.json, not from a second read of the file. A refused action presses nothing and the tool answers with `unavailable=True` and the reason ("Landing gear unavailable: the ship is in supercruise."); the LLM tells the pilot in its own words, Instinct uses that text as its reply. The reply is one text of `REPLY_TEXTS` (`services/models/reply_texts.py`): `pick_reply_text_for_pressed_action` names a pressed key, a toggle after the direction it went (read from `GameStateProtocol.get_game_stats().ship` BEFORE the press), a refusal gives the tool text up to the colon ("Landing gear unavailable"). The reply goes through `LLMProtocol.add_reply_without_llm_to_queue` (no LLM call, written to the conversation history) and then `SendPilotMessageUseCase` says it with `TTSProtocol.speak_reply`: the clip prepared for the active voice (`voices/<provider>/<profile>/replies/<text>.wav`, no model runs, ship effect and volume added on play), or the text spoken live when the clip is missing. Not done yet: "already deployed" replies (the model picks a toggle, not a direction). `None` sends the message to `add_llm_request_to_queue` as before
- `use_cases/system_check/system_check_use_case.py` — runs `cold_start()` of every service (including `GameWatcherService`) behind the `SystemCheckScreen` before the dashboard opens
- `containers/main_container.py` — single `dependency-injector` `DeclarativeContainer`; wires everything together; every module using `@inject` + `Provide[Container.*]` must be listed in `MODULES_USING_PROVIDE` (same file) — `tests/containers/test_wired_modules.py` fails otherwise
- `ui/` — Textual TUI app (see the `ui-conventions` skill)
- `__main__.py` — `main()`, exposed as the `edceleste` console script in `pyproject.toml`

## Adding a new game event

1. Add a Pydantic model in `services/models/game_events.py`
2. In `services/models/journal_event.py` add it to `JournalEventType` and to the `JournalEvent` union (`Annotated[<Model>, Tag(JournalEventType.<Name>)]`). `KNOWN_EVENTS` is built from `JournalEventType`, so it needs no edit
3. Handle it in the relevant `Projection` — `tests/projection/test_recognized_events_feed_game_state.py` fails when a recognized event is handled by no projection (it looks for `isinstance(event, <Model>)` in `projection/event_projections/`)

## LLM (pydantic-ai)

- The LLM runs through `pydantic-ai`. `LLMService` builds an `Agent` in `reload_service()` and streams it with `run_stream_events`.
- Providers are not hand wired: `build_provider` calls `infer_provider_class(type)(api_key=...)` and `build_model` calls `infer_model("<type>:<model>")` with that provider, so every provider `pydantic_ai` supports works from config alone. Default: `openrouter` with `anthropic/claude-haiku-4.5`.
- Tools are plain objects implementing `ToolProtocol` and are wrapped with `pydantic_ai.Tool` in `LLMService.build_tools()`. `pydantic_ai` derives the arguments from the `execute` signature and the description from its docstring, so a tool never hand writes a JSON schema.
