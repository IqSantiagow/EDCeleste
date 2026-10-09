---
name: blind-check
description: Two-stage blind check of the source files a change touched. Stage 1 gives the blind-signature-reader agent only the method names and types and fixes the names it gets wrong. Stage 2 gives it names plus docstrings, asks what each method returns, raises and changes, and makes the docstrings more descriptive where it guesses wrong. Use after a feature, a fix or a refactor, before the PR, or when the user says "blind check", "ślepy test", "sprawdź nazwy" or "sprawdź docstringi".
---

Checks that someone who never saw the code understands it from the names and the
docstrings alone. The reader is the `blind-signature-reader` agent: it sees only stripped
copies of the files, and a hook blocks every other read, so it cannot peek at the code.

You are the one who knows the code. The agent guesses, you compare its guesses with the
real code and fix the names and the docstrings. Never fix behaviour here: if you find a
bug, write it down for the report.

Execute the steps in order.

## Step 1 — Pick the files

- If the user named files, use them.
- Otherwise the script finds them itself: Python files under `src/edceleste` changed
  against `main`, uncommitted or new. Tests are never checked.
- Files without any function (plain models, constants) are skipped by the script.

## Step 2 — Stage 1: names only

1. Run `python signature_check/strip_method_bodies.py --without-docstrings [files]`.
   It writes the copies to `signature_check/stripped/` and prints their paths.
2. Start the `blind-signature-reader` agent. The prompt is only `Stage 1` and the
   printed paths. Never describe the project or the code: the test is blind, every hint
   spoils it.
3. Compare every guess with the real code. A method needs work when:
   - the guess is wrong, or misses a side effect that matters (network, event bus, files,
     audio, stored state, tokens), or
   - the confidence is not high.
4. Rename those methods. Pick a name that says what the method really does, e.g.
   `process_game_state_change` that only stores → `remember_latest_game_state`,
   `get_models` that goes to the network → `fetch_available_model_names`.
   - Grep `src/`, `tests/` and `.claude/` for the old name as a word and inside longer
     names (`test_get_models_...`, `mock_get_models`), and rename all of them.
   - Never rename dunder methods, Textual hooks (`compose`, `on_*`, `watch_*`,
     `action_*`), pydantic fields, or methods every service shares (`cold_start`,
     `reload_service`, `validate_settings`).
   - A name that is only weak, not wrong, can stay. Then stage 2 must cover it in
     the docstring.
5. Run `ruff check`, `ruff format` and the tests of the touched files.

## Step 3 — Stage 2: names and docstrings

1. Run `python signature_check/strip_method_bodies.py [files]` again, now with
   docstrings, after the renames.
2. Start the `blind-signature-reader` agent with only `Stage 2` and the printed paths.
   It answers per method: what it does, returns, raises and changes.
3. Compare each answer with the real code. Read the body, and one level of the
   methods it calls, to know which exceptions really come out. A docstring needs work
   when the agent:
   - got the return wrong, or did not know what `None` or an empty result means,
   - listed exceptions that do not come out, missed ones that do, or wrote "unknown",
   - missed a side effect, or
   - had confidence below high.
4. Rewrite those docstrings: numbered steps for a flow, what comes back in every case,
   what is raised and when, and the side effects. Simple English, short sentences.
   Never repeat the name or the signature. `__init__` that only stores its dependencies
   needs no docstring.
5. If you changed more than a few docstrings, run stage 2 once more on those files only.
   Stop after that second round even if a few answers are still medium.

## Step 4 — Check and report

1. Run `ruff check`, `ruff format --diff`, `mypy` and the whole test suite.
2. Report to the user in Polish:
   - per stage: how many methods were guessed with high, medium and low confidence,
   - the renames (old → new),
   - the docstrings you rewrote and what was missing in them,
   - anything that looked like a bug, with file and line, not fixed.
