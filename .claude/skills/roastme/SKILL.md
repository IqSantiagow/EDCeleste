---
name: roastme
description: >-
  A code roast with a teaching mission. Scans the EDCeleste repository (src/edceleste by default,
  or a given path) and points out code that can be simplified or modernized with idiomatic
  Python 3.12: list/dict/set comprehensions, any/all, match/case, walrus, dict.get, defaultdict,
  Counter, enumerate, zip(strict=True), StrEnum, PEP 604/695 and similar. Every finding shows
  "now" and "could be", names the construct and explains how it works, so the user learns to
  write code differently than out of habit. Use on /roastme, "roast my code", "what can I
  simplify", "make this more pythonic", "modern Python in my code", or Polish requests such as
  "zroastuj mój kod", "co mogę uprościć". Report only — no code edits unless the user asks.
---

# Roastme — a code roast that teaches

## What it is for

The user writes code the way they have it drilled into their head: a `for` loop, `append`,
`if/elif/else`, a hand-rolled counter. This skill has two goals, equally important:

1. **The project** — find places that can be written shorter, clearer or more modern.
2. **Learning** — show a construct the user does not use yet, and explain it well enough that
   next time they reach for it on their own.

Roast means: with humor and a jab, but **friendly**. Mock the code, never the person.
One short roast sentence per finding is enough; the rest is substance.

## The most important rule: "ape style" wins

`CLAUDE.md` says code must be simple enough for an ape to understand. A modern construct is not
a goal in itself. Suggest a change **only when the result is at least as readable** as the
original. Do not suggest:

- a comprehension with two `for` clauses plus a condition, or longer than one line (~90 chars),
- a walrus squeezed into the middle of a complex expression,
- `functools.reduce`, nested lambdas, clever one-liners,
- a change that only moves the complexity somewhere else.

If something **looks** like a candidate but the loop is better there (side effects, `await`
inside, doing several things at once), you may show it as a "defended snippet" — that teaches too.

## Arguments

- no argument → scan `src/edceleste`
- a file or directory path → scan only that
- `diff` → only files changed against `main` (`git diff --name-only main...HEAD` plus
  uncommitted changes from `git status`)
- `quiz` (combinable with the above, e.g. `quiz src/edceleste/ui`) → exercise mode, see below

## Steps

### Step 1 — Quick pass with the linter

Activate the virtualenv (`.venv`) and run ruff with the modernization rules. No `--fix`, change
nothing:

```bash
ruff check <path> --preview --no-fix --exit-zero --output-format concise \
  --select UP,SIM,C4,PERF,FURB,RET,PIE,RUF --ignore RUF100,RUF012
```

- `RUF100` (unused `noqa`) and `RUF012` (mutable class attribute, e.g. `BINDINGS` in Textual)
  are noise, not lessons — that is why they are ignored.
- Ruff results are **hints where to look**, not ready findings. Verify each one in the code.
- Group mass hits (e.g. 50× `Optional[X]` → `X | None`) into **one** finding with a list of
  locations. That is one lesson, not fifty.

### Step 2 — Read the code and look for what the linter cannot see

Ruff catches mechanical things. The best lessons are in places that need understanding the code.
Read the files in scope and look for the patterns in
[references/catalog.md](references/catalog.md). Read the catalog before searching.
The most common hits:

- a loop building a list/dict/set via `append` / `d[k] = v` / `add`,
- a loop looking for the first matching element or checking "is any of them",
- a long `if/elif` comparing one value against many constants (→ a dict or `match`),
- a manual index counter, manual grouping, manual counting of occurrences,
- `if key in d: x = d[key] else: x = default`,
- `try/except: pass`, nested `if` instead of a guard clause,
- old-style types (`Optional`, `Union`, `List`, `Generic[T]`, `str, Enum`).

The catalog is not a closed list. If you see another idiom that fits the rules, use it.

### Step 3 — Check that "could be" does exactly the same thing

Before showing a suggestion, make sure the behavior does not change. Typical traps:

- `d.get(k)` does not raise `KeyError` — if the original relied on the exception, it is not the same,
- `x or default` treats `0`, `""`, `[]` as missing; `x if x is not None else default` does not,
- a comprehension replacing a loop with side effects (logging, `await`, mutation) changes meaning,
- `any()`/`all()` stop at the first hit — same as `break`, but check for a loop `else`,
- element order (`set` does not keep it); `zip` without `strict` truncates the longer list.

When in doubt, write a small script in the scratchpad directory and compare the outputs of the
old and new version. If the behavior differs but the change still makes sense, say so explicitly
in the finding.

### Step 4 — Pick the best findings

- **At most 10 findings.** Better 6 good ones than 15 mediocre ones.
- Highest learning value first (a new construct), then the biggest gain for the project.
- **Variety**: one construct = one finding. Further places with the same pattern go under
  "Same in: ..." with links.
- Skip generated code and pure data (e.g. long lists of Pydantic models without logic).

### Step 5 — Report

Write the report in the language the user is talking in. Identifiers and code stay as they are.
Link files as markdown with line numbers, paths relative to the repo root.

Start with one sentence summing up the roast (e.g. "Found 7 places where your code writes an
essay instead of a sentence."). Then each finding in this format:

````markdown
### 🔥 1. <Short title> — `<construct name>`

> <one roast sentence>

[file.py:42-48](src/edceleste/.../file.py#L42-L48) · level: basics | intermediate | advanced

**Now:**
```python
<original snippet, relevant lines only>
```

**Could be:**
```python
<suggestion>
```

**How it works:** <2–4 sentences: what the construct does, how to read it out loud, why it fits here.>

**When NOT to use it:** <1 sentence: the line past which this construct hurts.>

📚 <link to the Python docs>

Same in: <links, if any>
````

At the end:

1. **Cheat sheet** — a table: construct | in one sentence | when to reach for it. Only the
   constructs from this roast.
2. **Defended snippets** (optional, max 2) — places that looked like candidates but the original
   is better, with one sentence why.
3. A question: does the user want to rewrite some place themselves (then you review their
   version), or would they rather you apply selected changes.

### `quiz` mode

Instead of "Could be", show only "Now", the construct name and a one-sentence hint.
The user writes their version in the reply. You review it: does it behave the same, is it
readable, what to improve. Show the full suggestion only after their attempt or when they ask
("show the answer", "I give up", "pokaż odpowiedź", "poddaję się").

## What not to do

- **Do not edit code** until the user explicitly asks you to apply changes. This is a report.
- Do not report logic bugs as the main content — that is what `code-review` is for. If you
  notice an obvious bug along the way, mention it in one sentence at the end.
- Do not invent findings. If the code is already idiomatic, say so and give fewer findings.
  A short roast of clean code is fine too.
- Do not suggest dependencies outside the standard library and the ones the project already has.
