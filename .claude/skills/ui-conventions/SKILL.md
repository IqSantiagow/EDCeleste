---
name: ui-conventions
description: Rules for the EDCeleste Textual TUI — where screens, widgets, view models, services and repositories live under ui/screens/<screen_name>/, and when a widget gets its own file. Use whenever adding, moving or changing anything in src/edceleste/ui/, including new widgets, screens, view models and CSS.
---

Rules for everything under `src/edceleste/ui/`.

## Where things go

- Widgets used only within specific widgets stay in one file. For example `WidgetCommsInput` is only used within the dashboard screen, so it stays in `ui/screens/dashboard/widgets/comms/widget_comms_input.py`.
- Follow this structure when creating new things in the UI:
  - `ui/screens/<screen_name>/widgets/` — widgets specific to a screen
  - `ui/screens/<screen_name>/view_models/` — view models specific to a screen
  - `ui/screens/<screen_name>/services/` — services specific to a screen
  - `ui/screens/<screen_name>/repositories/` — repositories specific to a screen

## Dependency injection in the UI

- UI widgets are injected via `@inject` + `Provide[Container.*]` (`containers/main_container.py`).
- Every module that does this must be listed in `MODULES_USING_PROVIDE` in the same file. `tests/containers/test_wired_modules.py` fails otherwise.
- The UI depends on `GameStateProtocol` (`protocols/game_state_protocol.py`), never on the concrete `GameStateService`.

## Styling

- Styling goes through Textual CSS in `ui/css.tcss`. No direct `rich` imports.
- Use Textual built-in widgets (`ProgressBar`, `WidgetSpinner`, ...). Never hand-draw bars or spinner frames in a `Label`.

## App lifecycle

- `UIApp` (`ui/ui_app.py`) pushes `SystemCheckScreen` on mount; its `cold_start()` run starts `GameWatcherService`. When the check passes, `UIApp` pushes `DashboardScreen`, whose `on_unmount()` stops the watcher; when it fails, the app exits.
