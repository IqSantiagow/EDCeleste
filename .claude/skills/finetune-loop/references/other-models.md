# Running the loop with other model families

The loop (frame → data → real examples → staged training → same-split evaluation → dashboard) does not
change. Two pieces are model-specific: the trainer and the "asker" that eval_split.py uses. Nothing below
has been run yet; treat it as the starting plan and, once something works, move it into this file.

## A generative LLM (e.g. Gemma, Qwen) as a classifier or decider

- Keep the data format. Render each question into a chat prompt and teach a fixed short answer
  ("yes"/"no", or the option name). Read P(yes) from the answer token's logprob at inference.
- Train with LoRA (peft) so a 2–4B model fits in 12 GB: base weights in bf16, adapters only; or QLoRA
  (4-bit base, bitsandbytes) for larger. Use the model's own chat template for training and inference.
- Add an asker to eval_split.py: llama-server or transformers, one request per question or one prompt with
  numbered answers under a grammar (see the Qwen3.5-2B experiment: plain prompting without fine-tuning
  showed strong position bias and was slower than decider).
- Merge the adapter for serving, or serve base + adapter.

## Whisper (speech-to-text) on the user's phrases

- Data: the recordings `.wav` + `reference_text` (what was really said; fill it in a review pass, the
  recorder leaves it empty) — the raw transcription is the model's current mistake, not the target.
- Metric: word error rate on a held-out session, plus the downstream metric (does the decision model act
  right on the new transcripts?). Re-run eval_split on transcripts from the new STT.
- Small models (tiny.en, base.en) fine-tune on a consumer GPU with Hugging Face `WhisperForConditionalGeneration`
  + `Seq2SeqTrainer`; a few hundred utterances adapt vocabulary (ship names, "Celeste", "hardpoints")
  but can overfit: keep a general English check set.
- A cheaper first step: Whisper's `initial_prompt` with the game vocabulary, measured on the same session.

## Training somewhere else

Kaggle (free P100 / 2×T4, ~30 GPU h/week; TPU v5e-8 ~20 h/week) works through the API: dataset create,
`kernels push` with `enable_gpu`/`machine_shape`, `kernels output`. T4/P100 have no bf16, and decider's
code is CUDA-specific (TPU would need a torch_xla port; the Qwen3.5 fast kernels are Triton-only). For
0.8B it is slower than a local RTX 30xx; consider it only to free the local GPU or for models that do not fit.
