---
name: agent-swarm
description: Bug hunt with a swarm. The agent starts one tester subagent per area of EDCeleste (boot, ship log, comms and LLM, voice out, voice in, Instinct and game actions, event reactions, settings, header). Every subagent attacks its area with throw-away e2e tests that run the real app and tries to break it. The agent then re-runs every red test alone, sorts real bugs from bad tests and flaky runs, and reports the bugs. Use when the user says "agent swarm", "rój agentów", "szukaj bugów", "przetestuj całą aplikację", "znajdź potencjalne bugi" or wants the whole app, or a few areas, checked for bugs without a feature behind it. Not for proving a single change, that is the e2e-test-writer agent.
---

A swarm does not prove that a change works, it looks for what is broken. You are the
orchestrator: you cut the app into areas, send one tester per area in parallel, and judge
what they bring back. A tester is a subagent that writes e2e tests as a hostile Commander.
A red test is only a lead until you have checked it.

Write the report to the user in Polish. Everything else (tests, prompts) in English.

The swarm never touches `src/`, never fixes a bug and never uploads an issue on its own.
It finds, checks and reports.

## Step 1 — Pick the areas

- User named areas or files: use only the areas that cover them.
- User said nothing: all areas below. If the user gave a feature or a diff to look at,
  use only the areas it touches.

| Area | Where the code lives (`src/edceleste/`) | Existing e2e (`tests/e2e/`) |
|---|---|---|
| `boot` | `ui/screens/system_check`, `use_cases/system_check`, `services/decision_model_download_service.py` | `test_boot`, `test_startup_loading` |
| `ship-log` | `services/game_watcher_service.py`, `services/game_state_service.py`, `projection`, `ui/screens/dashboard` | `test_journal_to_ship_log`, `test_journal_to_dashboard_stats`, `test_ship_log_expand` |
| `comms-llm` | `services/llm_service.py`, `ui/screens/dashboard/widgets/comms` | `test_comms`, `test_conversation_memory`, `test_game_state_prompt`, `test_ship_replies*` |
| `voice-out` | `services/tts_service.py`, `services/tts_providers`, `services/speaker_service.py`, `services/ship_voice_effect.py` | `test_speech`, `test_voice_*`, `test_streaming_voice`, `test_pocket_tts`, `test_ship_effect`, `test_tts_settings` |
| `voice-in` | `services/stt_service.py`, `services/hotkey_service.py`, bind hotkey dialog | `test_push_to_talk_hotkey`, `test_bind_hotkey_dialog` |
| `actions` | `services/instinct_service.py`, `services/keybinds_service.py`, `services/game_window.py` | `test_instinct_*`, `test_game_action_availability`, `test_keybindings_problems` |
| `reactions` | `services/event_reactions_service.py`, `services/event_bus.py` | `test_event_reactions` |
| `settings` | `services/settings_service.py`, `ui/screens/settings`, `use_cases/settings` | `test_settings`, `test_settings_llm`, `test_tts_settings` |
| `header` | `ui/screens/app`, `services/service_status_stream.py` | `test_service_status_dots` |

The table is a starting point. If the code has moved, the tester looks for the new place
itself. Nine testers at once is the top: do not split an area into more.

## Step 2 — Prepare the ground

1. Activate the virtualenv (nothing is installed globally). In a worktree use `PYTHONPATH=src`.
2. Make `tests/e2e/swarm/` empty with an `__init__.py`. It is git-ignored scratch, a folder from
   an earlier swarm is deleted first. Check that `/tests/e2e/swarm` is in `.gitignore`, add it if not.
3. Run `python -m pytest tests/e2e` once. If it is red, stop and tell the user: a swarm on
   a red base only finds noise. Do not go on without their answer.
4. Check for the remote runner: are the `mcp__edceleste-runner__*` tools connected? The testers
   follow the section "Run them" of `.claude/agents/e2e-test-writer.md` (runner when connected,
   local otherwise). The runner runs one job at a time, so with it the swarm is slower but
   does not load this machine.

## Step 3 — Release the swarm

Start all testers in **one message**, one `Agent` call each, `subagent_type: general-purpose`,
`model: sonnet`, so they run side by side. Use the prompt below, filled in for the area.
Do not add hints about bugs you suspect: a tester that gets your hypothesis returns it confirmed.

```
You are a tester in a bug-hunting swarm for EDCeleste, an Elite Dangerous AI copilot with a
Textual TUI. Your area: <AREA>. Its code lives in: <PATHS>. Existing e2e tests of it: <TESTS>.
Other testers work on other areas at the same time, in the same working copy.

Goal: find places where the app does not meet what the Commander (the user) expects, with
ordinary use and ordinary trouble. Not to prove that it works.

1. Learn the area. Read `tests/e2e/conftest.py` (the `edceleste` fixture and its fakes), the
   existing e2e tests of your area, then the code of your area, to see what the Commander can
   do and what can go wrong. Read the sections "Conventions for e2e tests" and "Run them" of
   `.claude/agents/e2e-test-writer.md` and follow them.
2. Write 5 to 8 attacking scenarios. Think like someone who wants to break it, in a normal setup:
   - the same action twice, fast, or in a different order than the happy path
   - empty, very long, Polish-diacritics and emoji text; a journal line that is broken or unknown
   - a missing, empty or half-written file (journal, Status.json, config, keybindings)
   - a service that fails (the LLM raises, the TTS raises, the microphone cannot be opened)
     and whether the app stays alive and tells the Commander
   - a setting changed while the app is running: does it take effect, is it saved
   - what the Commander sees after an error: is the screen, the log and the status dot telling
     the truth, is the next action still possible
   Do NOT test exotic setups (many network cards, two keyboards at once, a broken OS). The
   scenario must be something a real Commander does in one evening.
   Skip a scenario that an existing test already covers.
3. Write them as e2e tests in `tests/e2e/swarm/test_swarm_<area>.py` only. Never edit `src/`,
   `conftest.py`, other tests or other testers' files. If you need a new fake, define it in
   your own file; if the boundary cannot be faked, write it down as "e2e cannot reach".
   A scenario test asserts what the Commander sees or what leaves the computer, and the
   expectation must be a fair business requirement, not what the code happens to do.
4. Run the file, fix the failures that are your own mistakes (selector, missing wait, typo),
   then run it 3 times. Parallel load makes timeouts, so a failure that appears in one run
   only is flaky: report it as flaky, do not hide it.
5. A red test that is left after that is a suspected bug. Do not change the test to make
   it green and do not fix the app.

Finish within about 40 tool calls. Your final message is ONLY this, nothing before or after:

AREA: <area>
Scenarios written: N   Green: N   Suspected bugs: N   Flaky: N   Not reachable by e2e: N
BUGS
1. <title, one sentence>
   Commander does: <steps>
   Expected: <what a fair requirement says>
   Actual: <what happened, 1 or 2 lines of the failure>
   Test: tests/e2e/swarm/test_swarm_<area>.py::<test name>
   Where in code (if you know): <file:line>
FLAKY
- <test name>: <how it fails>
NOT REACHABLE
- <thing and why>
```

## Step 4 — Judge the findings

The testers are fast and wrong sometimes. For every suspected bug, in this order:

1. Run its test **alone**, 3 times, on a quiet machine (the swarm is finished). Red in 0 or 1
   of 3 runs → flaky, drop it from the bugs. Red in 3 of 3 → go on.
2. Read the test and the failure. Ask: is the expectation a fair business requirement, and
   does the app really break it? Sort it:
   - **BUG** — the app breaks a fair requirement,
   - **TEST WRONG** — wrong selector, missing wait, a fake that behaves unlike the real thing,
   - **EXPECTED** — the app does it on purpose (check the docs, the issue text, the code comments),
   - **UNSURE** — a design question only the owner can answer.
3. For a BUG, read the code the tester pointed at and name the likely cause in one sentence.
   Do not fix it.
4. Merge duplicates: two testers hitting the same cause is one bug.
5. Give a severity: **high** (crash, lost data, a wrong action sent to the game, the app
   hangs), **medium** (a feature does not work or lies to the Commander), **low** (cosmetic,
   a missing message).

## Step 5 — Report and clean up

1. Write `swarm-report.md` to the scratchpad directory of the session (the Claude app can open
   it), and put the same content in the answer, in Polish:
   - the table of areas: scenarios, green, bugs, flaky, not reachable,
   - the confirmed bugs, highest severity first, each with: title, steps of the Commander,
     expected, actual, the likely cause with `file:line`, the test,
   - UNSURE items as questions for the owner,
   - what e2e could not reach,
   - what was dropped (flaky, test wrong, expected) in one line each, so the user can disagree.
2. Copy the test files of the confirmed bugs to a `swarm-tests/` folder next to the report, then
   delete `tests/e2e/swarm/`. A red test left there would break every later `pytest` run.
3. Do not commit anything. The only change in the repo can be the `.gitignore` line.
4. Ask the user what next. Offer: write the confirmed bugs as GitHub issues (then use the
   `anthropic-skills:edceleste-issues` skill, the upload only after the user says yes), or fix
   one now through the pipeline in `CLAUDE.md`, where the saved test is the starting reproduction.
