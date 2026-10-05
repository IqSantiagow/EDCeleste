# Jev-style decision models

## The wire format (TypeSafe System One)

`POST /v1/systemone` with `{"model": "...", "state": <string|object|array>, "questions": {id: question}}` →
`{"model", "answers": {id: answer}, "usage"}`. Question types:
- `noul`: yes/no. `{"type": "noul", "instructions": "...", "criteria": {"true": "...", "false": "..."}}` → `{"noul": p_yes}`
- `choice`: `{"type": "choice", "instructions": "...", "criteria": {"option": "description" | null, ...}}` → `{"choice", "confidence", "probabilities"}`
- `score`: ordered levels → `{"score", "probabilities", ...}`

Endpoints that speak it: OpenRouter `https://openrouter.ai/api/v1/systemone` (Jev, `typesafe/jev-1.13`;
the separate `/api/alpha/decisions` "Decisions API" is a different surface), `decider.serve`, Ollaya
(`/v1/systemone`, `/v1/decisions` alias; no chat endpoint), llama-server ≥ b11361 with decision GGUFs,
jev-style serve. pydantic-ai does not fit: it speaks chat completions; use a small httpx client.

## decider (Mapika/decider, Apache 2.0, pip `decider-ai`)

- Qwen3.5 fine-tunes: 0.8b, 2b, 4b (+ larger). Reads answer slots, never generates text.
- `Decider(path).system_one(state, questions)` scores every question in its own row with a shared state
  prefix. Rendering: `Context:\n<render_state(state)>\n\nQuestion: <text>\nOptions:\n(A) no: <false>\n(B) yes: <true>\nAnswer: (`.
- `decider_config.json` holds the temperature; copy it next to a fine-tuned model (train_decider.py does).
- Engine compiles with `torch.compile` by default (needs Triton); see workspace.md for Windows.
- `decider/train.py` has `make_items`, `batches_by_tokens`, `loss_fn` (cross-entropy over option letters);
  train_decider.py reuses them so training matches the official recipe.

## Speed and memory, measured on one RTX 3080 Ti (12 GB) in October 2026

Hardware numbers only; how well each model does depends on the task, so measure that on your own test split.

| Model | 1 / 12 questions | VRAM | Note |
|---|---|---|---|
| Jev 1.13 hosted | ~230 / ~250 ms | — | network; 12 questions cost the same as 1 |
| decider-0.8b, no FLA | 36 / 118 ms idle; 52 / 187 ms next to a game | ~2 GB | |
| decider-0.8b + triton-windows | 35 / 124 ms next to a game | ~2.1 GB | first call compiles ~30 s |
| decider-2b | 73 / 235 ms next to a game | ~4.1 GB | |
| Winnow-E4B (Ollaya) | 20 ms per question, linear | ~6 GB | too big next to a game using ~6 GB |
| Kev-4B, lev (llama-server, Q4) | ~125 ms / 540–770 ms | ~3 GB | questions run one after another |
| Laya (ModernBERT) | 15–34 / 36–76 ms | 2–3 GB | 512/1 024-token window |
| TinyDecide (10M, numpy on CPU) | 180 / 810 ms | CPU | 127-token window |

Training decider-0.8b, full AdamW bf16, 6–7M tokens: ~10 s/step, 16–18 min per epoch, 8.2 GB peak. With
`--adam_8bit --freeze_embeddings --max_tokens 2048 --accum 16`: 4.1 GB peak.

## Where to look for new candidates

Ollaya results (ollaya.dev/results, yes/no column is closest to noul), the Decision Index space
(multimodalart/jev-decision-index), JevBench, ggml-org GGUF conversions. Check license (several are
non-commercial), context window, Windows/CUDA path and whether all questions share one pass.
