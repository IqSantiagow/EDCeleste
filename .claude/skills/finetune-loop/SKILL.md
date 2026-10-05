---
name: finetune-loop
description: >-
  Iterative loop for fine-tuning a small local model on a user's own task and proving it against a reference:
  frame the decision interface, build synthetic data from the app's real code, collect real examples from the user
  (e.g. voice through the app's speech-to-text), train in stages on the local GPU, score every model on the same
  held-out test, publish an HTML progress dashboard as an artifact, and plan the next iteration. Bundles a generic
  trainer for Jev-style decision models (decider), an evaluator for any /v1/systemone endpoint, a recorder, a data
  review page, a dashboard builder and a private Hugging Face dataset publisher. Use it whenever the user wants to
  fine-tune, retrain, "dotrenować", or compare a local model (decider, Laya, Gemma, Whisper, any small model) for
  their app, build or extend training data, record examples, check whether a new training round is better, update
  the training dashboard, or continue an earlier training session, even if they only say "zróbmy kolejną iterację"
  or "sprawdź, czy model jest lepszy".
---

# Fine-tune loop

Make a small local model good at one narrow job of the user's app, one measured iteration at a time.
Every iteration ends with numbers on the same test split, a dashboard the user can open, and a short
plan for the next round. `examples/edceleste/` shows a project-side data generator and project metrics for a
decision model in an Elite Dangerous copilot.

Keep the history of a project's iterations (scores, run names, dashboard URL) in the project's
`iterations.json` and in your project memory, not in this skill: the skill stays generic and may be public.

## Ground rules

These come from mistakes that cost real time. Read them before touching data.

- **One workspace folder holds everything**: venv, model weights, caches, binaries, data, runs, results.
  Add it to `.git/info/exclude` (local, not `.gitignore`) and point every cache inside it, so the user can
  delete the whole experiment with one command. The env vars that matter are in `references/workspace.md`.
  After every session check for strays outside it (`~/.triton`, `~/.ollaya`, `~/.cache/...`) and remove
  only the ones you created.
- **Never invent the app's policy.** If what the model should do is the user's choice (which key to press
  on an event, when Celeste should speak), the data must teach the model to *follow an instruction* given
  in the question, with varied instructions on the same state. Labels you can be sure of come from facts
  the model can read in its input, never from a tactic you made up.
- **Training and inference must see byte-identical prompts.** Build training rows with the same functions
  the runtime uses to render state and questions (for decider: `render_state`, `render_question`, one
  question per row). A format mismatch silently wastes the whole run.
- **Review before training.** The user reads the data review page and answers the open decisions before
  the first training of a data version. Labels encode their product decisions, not yours.
- **The honest test is real user data the model and you never used to build anything.** Synthetic test
  splits come from the same generator as training and flatter every model. Once you have looked at test
  errors to design new data, that test is spent: plan a fresh collection for the next measurement and
  say so in the report.
- **Always score a reference.** A hosted model (e.g. Jev) and the untrained base on the same split. A
  number without a baseline is not a result.
- **Ask before outward actions.** Uploading data, using API keys, spending money, publishing anything
  public. Private by default; the user's voice recordings never go public.

## The loop

### 1. Frame the job and the interface

Write down, with the user: what the model decides, what input it gets at runtime (the exact state text
the app builds), what questions it is asked and in which wire format, and what an error costs (a false
"yes" that presses a key in combat is worse than a missed one). For Jev-style models the format is
`POST /v1/systemone {model, state, questions}` with `noul` (yes/no), `choice` and `score` questions; see
`references/decision-models.md`. Look for gaps in what the app puts into the state; a condition the
state never mentions cannot be learned or tested, so report it as a finding instead.

### 2. Baseline and candidates

Score the reference and the candidate base models on a first small benchmark before building big data.
`scripts/eval_split.py ask` talks to any `/v1/systemone` endpoint (hosted Jev, Ollaya, llama-server with
decision models, decider.serve) or runs decider in-process. Measure under real conditions too: if the
app runs next to a game, measure with the game running (VRAM left, latency, p95).

### 3. Synthetic data from the app's own code

Write a project generator (template: `examples/edceleste/build_training_data.py`). It should:
- build states with the app's real code path (e.g. publish events into the real state service), varying
  names, numbers and sentence order so the model cannot memorize them;
- emit one JSON line per example: `{id, kind, split, state, questions, gold}`, questions exactly as the
  app will send them;
- hold out whole templates (phrasings, prompts) for the test split, not just random rows, so the test
  measures generalization;
- keep every "yes" share reasonable (10–90%) per question; a constant answer teaches a constant;
- include hard negatives on purpose: sentences that mention an action without asking for it (negations,
  why/how questions, past tense, reminders). They are the first thing a model gets wrong.

Then `scripts/build_review_page.py --intro intro.html` and publish the page as an artifact. Put the open
decisions at the top of the intro, each with the current default, so the user can answer "D1: x".

### 4. Real examples from the user

Real input beats any amount of synthetic text. For voice, export a prompt list (what to say + a style
hint, never the exact words) and have the user run `scripts/record_examples.py` in their own terminal;
it uses the same STT model as the app, saves raw transcripts plus `.wav`, and resumes where it stopped.
Split by session: what you inspected goes to training, a later session stays the clean test. Keep the
audio (private): it can later fine-tune the STT model itself, which needs a corrected `reference_text`.

### 5. Train in stages

1. Smoke test: `--max_steps 5` to see peak memory, seconds per step and that backward works on this OS.
2. Full run with the settings of the previous iteration, so the data change is the only change.
3. Change one training knob at a time, and only when the data stops paying.
`scripts/train_decider.py` handles decider models; resource limits (`--gpu_memory_share`,
`--gpu_busy_share`, `--adam_8bit`, `--freeze_embeddings`) let it share the GPU with a game. For other model
families see `references/other-models.md`.

### 6. Evaluate and analyse

`eval_split.py ask` for every model on the same test split, then `eval_split.py report --extra
<project metrics>`. Project metrics are the ones the app cares about (e.g. "key pressed while the pilot
was only talking"), written as a small `extra_metrics(rows)` function. Read the errors, group them
(speech-to-text confusions, negations, ambiguous labels) and check whether a simple app-side rule (e.g.
"no key when the model says the LLM is needed") fixes a class of them before adding data.

### 7. Publish and plan

- Add the run to `iterations.json` (entries + one history line: change, result) and rebuild the
  dashboard with `scripts/build_dashboard.py`; republish to the same artifact URL (store it in
  `iterations.json` as `dashboard_url`).
- Publish the data version with `scripts/publish_dataset.py` (or the `hf` CLI: `hf repos create ... --private`,
  `hf upload`) to a private Hugging Face dataset. Use the user's `hf auth login` or a token file inside the
  workspace; a token is never pasted in chat. Confirm the repo reports `private: True` before uploading audio.
- End with: what got better, what got worse, the one biggest error class, and the next data change.

## Bundled scripts

| Script | Job |
|---|---|
| `scripts/eval_split.py` | `ask`: score a model on the test split (systemone HTTP or decider in-process); `report`: per-kind accuracy, false/missed yes at 0.5/0.7/0.9, `--extra` project metrics |
| `scripts/train_decider.py` | fine-tune a decider model on `split == "train"` rows; smoke test and GPU-sharing flags |
| `scripts/record_examples.py` | the user's recorder: prompt → speak → STT → confirm; CSV + WAV, resumable |
| `scripts/build_review_page.py` | data review page: counts, yes-share per question, every example with filters |
| `scripts/build_dashboard.py` | progress dashboard from `iterations.json`: history, per-kind bars, project metrics, loss curves, table |
| `scripts/publish_dataset.py` | upload a data version (and recordings) to a private HF dataset; refuses a public repo |

## Reference files

- `references/workspace.md` — folder layout, cache env vars, Windows GPU notes, cleanup checklist. Read at the start of a session.
- `references/data-design.md` — how to design labels, splits and negatives; the mistakes behind the ground rules.
- `references/decision-models.md` — System One format, decider internals that matter, measured speed/VRAM, which local decision models were tried.
- `references/other-models.md` — adapting the loop to a generative LLM (LoRA SFT) or to Whisper STT.

## Example files

`examples/edceleste/`: `build_training_data.py` (states built through the app's real state service, reaction
prompts, facts, utterances with speech-to-text noise, held-out templates), `build_scenarios.py` and `bench.py`
(its helpers), `extra_metrics.py` (key-press metrics for `--extra`), `recording_prompts.json` (240 recorder prompts).
They import the app's own code, so they are templates to copy and adapt, not tools to run elsewhere.
