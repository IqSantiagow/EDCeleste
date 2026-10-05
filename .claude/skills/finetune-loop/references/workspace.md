# Workspace, caches and the GPU

## Layout

```
<project>/<workspace>/          e.g. EDCeleste/model_bench, listed in .git/info/exclude
  .venv/                        separate venv (uv), never the app's venv
  hf_cache/  uv_cache/  cache/  every cache (HF_HOME, UV_CACHE_DIR, TRITON_CACHE_DIR, TORCHINDUCTOR_CACHE_DIR)
  bin/                          prebuilt binaries (llama.cpp, Ollaya portable)
  models/                       single GGUF/model files downloaded on purpose
  training_data/  training_data_v2/ ...   one folder per data version, *.jsonl + review.html
  recordings/                   recordings.csv + *.wav from record_examples.py
  runs/<name>/                  train.log, train_config.json, model/
  results/                      eval_<name>.json, eval_summary.json, dashboard.html
  scripts/                      project generator, extra_metrics.py, glue
  secrets/                      API tokens in files (hf_token, openrouter_key); excluded with the rest
  iterations.json               the registry the dashboard is built from
```

Delete everything: `Remove-Item <workspace> -Recurse -Force`, then drop the line from `.git/info/exclude`.

## Environment for every command

```bash
export HF_HOME="$WS/hf_cache" HF_HUB_DISABLE_TELEMETRY=1 UV_CACHE_DIR="$WS/uv_cache" \
       TRITON_CACHE_DIR="$WS/cache/triton" TORCHINDUCTOR_CACHE_DIR="$WS/cache/inductor" \
       PYTHONIOENCODING=utf-8
# add HF_HUB_OFFLINE=1 once weights are downloaded, so nothing is fetched by surprise
```
Ollaya: `OLLAYA_MODELS`, `OLLAYA_LOG_DIR` inside the workspace and its own port if the user's desktop Ollaya
already holds 11435. Whisper reuses `~/.cache/whisper` if the app already downloaded the model; otherwise pass
`download_root`.

## Windows + NVIDIA notes (measured on RTX 3080 Ti, 12 GB, CUDA 13 driver)

- PyTorch cu130 wheels work. `torch.compile` needs Triton: either skip it (decider: replace `eng._fwd_impl`
  with `eng._fwd_eager`) or install `triton-windows` (3.7.x worked with torch 2.14).
- Qwen3.5-based models fall back to slow reference kernels without `flash-linear-attention` (pure Python
  package) + Triton. With `triton-windows` they ran ~35% faster; the first call compiles for ~30 s, later
  runs use the cache. Training backward through those kernels also worked.
- `bitsandbytes` 0.50 has Windows CUDA wheels; `AdamW8bit` works.
- `llama.cpp`: take the `cuda-12.4` Windows zip (+ the cudart zip) unless the driver supports the newer CUDA.
  Since build b11361 `llama-server` serves `/v1/systemone` for laya, lev, julia-1, openjev and kev GGUF files.
- WDDM: no per-process GPU share. Limit memory with `torch.cuda.set_per_process_memory_fraction` and compute
  by resting between micro-batches. Check who holds VRAM with the
  `\GPU Process Memory(*)\Dedicated Usage` performance counter (nvidia-smi shows N/A per process).
- A game next to the model changes everything: measure latency and VRAM with it running. When VRAM runs out
  the driver spills to system RAM silently and both the game and the model slow down.

## Cleanup checklist (end of every session)

1. No workspace processes left (`Get-Process | ? Path -like "*<workspace>*"`), servers stopped, VRAM back.
2. No strays you created outside the workspace (`~/.triton`, `~/.ollaya`, `%LOCALAPPDATA%\llama.cpp`, HF token
   caches). Remove only what this session created; other folders may belong to the user's own tools.
3. Report the workspace size.
