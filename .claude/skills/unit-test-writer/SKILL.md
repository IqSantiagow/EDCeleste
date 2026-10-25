---
name: unit-test-writer
description: Writes unit tests for code that was just added or changed. Runs the existing suite first, drafts a test plan with method names for approval, then implements the approved tests. Use when the user asks to add, update, or backfill unit tests for recent changes.
---

Write unit tests for this codebase. All test code you produce — file names, test method names, docstrings, comments — must be in English, regardless of the language used in the conversation.

Execute the steps in order. Do not skip ahead or merge steps.

## Step 1 — Baseline: do the existing tests pass?

```bash
coverage run -m pytest
coverage report -m
```

The pipeline and the CI run pytest, so run pytest here, not `unittest discover`: a test can pass under one and fail under the other. In a worktree set `PYTHONPATH=src` for every run (the shared virtualenv imports `edceleste` from the main checkout), and print `edceleste.__file__` once to see which copy the tests load.

- If everything passes: continue to Step 2.
- If anything fails: stop. Report the failing tests to the user and ask whether you should fix them before continuing, or proceed anyway despite the pre-existing failures. Wait for a response before continuing.

## Step 2 — Inspect what changed

```bash
git status
git diff HEAD
```

Identify the added/modified production files relevant to testing (ignore unrelated churn such as formatting-only diffs). For each, note the new or changed functions, methods, classes, and branches (new conditionals, error paths, edge cases) that need coverage.

## Step 3 — Draft the test plan

For each unit identified in Step 2, write a plan entry with:

- Target: file, class, function/method under test
- Test file: where it belongs, mirroring the source path (e.g. `services/foo/bar.py` → `tests/services/foo/test_bar.py`), matching the existing layout under `tests/`
- Test method names: `test_<behavior>` style (e.g. `test_returns_none_when_queue_is_empty`), one per case — happy path, edge cases, and error/exception paths
- One line per method: what it verifies and why it matters
- One line per method: the change to the production code that turns the test red (for example "delete the line that resets the field", "swap `>=` for `>`"). If you cannot name one, the test checks nothing, so rework it.

A test that asserts an absence (`None`, "file does not exist", "was not called") proves nothing until its setup rules out every other way to reach that state:
- Put in place what a precondition step would reset or create on its own (a model the code would load, a file it would write), so the code under test is the only thing that can produce the state.
- Capture the real path or value the code used (a `side_effect` that records it) and assert on the captured value, never on a hard-coded name that a rename can make stale.

Do not write any test code in this step.

## Step 4 — Present the plan for approval

Present the full plan to the user and ask explicitly whether to proceed with implementation. Wait for a response before continuing.

## Step 5 — Branch on the user's decision

- **Approved:** implement exactly the planned test methods, following existing conventions under `tests/` (unittest-style, matching naming and fixture patterns already used in neighboring test files). Then re-run:
  ```bash
  coverage run -m pytest
  coverage report -m
  ```
  Confirm the new tests pass and nothing else regressed. Report the result and the updated coverage.
- **Changes requested / not approved:** revise the plan per the feedback and go back to Step 4. Stay in this planning/refinement loop — do not write any test implementation code until the user approves a plan.

## Scope

- You write tests only. If Steps 2–3 surface an apparent bug in production code, flag it in the plan for the user instead of fixing it yourself.
- Never weaken or delete an existing test just to make the suite pass.
