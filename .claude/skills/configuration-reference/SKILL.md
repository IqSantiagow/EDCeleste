---
name: configuration-reference
description: Reference for EDCeleste configuration — the .env bootstrap file (AppConfig) and config.yaml user settings (SettingsService / SettingsModel): every key for paths, llm, tts (with ship_effect), stt, event_reactions and game_actions, and how settings load. Use when reading, adding or changing a setting, debugging startup config errors, or writing tests that touch settings.
---

Two independent, both-gitignored config sources.

## `.env` (copy from `.env-example`)

Process bootstrap, loaded via Pydantic-settings (`AppConfig` in `config/config.py`). Only `logging`:

- `LOGGING__LEVEL` — `DEBUG` | `INFO` | `WARNING` | `ERROR` | `CRITICAL` (required)

## `config.yaml` (copy from `config-example.yaml`)

User/runtime settings, loaded via `services/settings_service.py` (`SettingsService`) into `SettingsModel` (`services/models/settings_model.py`):

- `paths.journal_path` / `paths.keybindings_path`
- `llm.provider` — `type` (any provider name in `SUPPORTED_LLM_PROVIDER_TYPES`, `services/models/settings_model.py`), `model`, `api_key` and an optional `base_url` for providers without a public endpoint (ollama, vllm, azure).
- `llm.system_prompt` — used to build the LLM agent
- `llm.instinct` — `enabled` and `device` (`auto` | `cuda` | `cpu`) of Instinct, the local fast-command model. `InstinctService` downloads it on first use to `%LOCALAPPDATA%\EDCeleste\models` and loads it; its repo and revision are fixed in `decision_model_download_service.py`. It decides commands only when the model runs on the GPU (on the CPU every message goes to the LLM) and only when `game_actions.enabled` is on.
- `llm.user_prompt` (reserved, not wired into `LLMService` yet)
- `tts.provider` — `edge` (`voice`), `chatterbox` (`profile`, `exaggeration`, `cfg_weight`, `device`, `nano`) or `pocket` (`profile`; CPU only, `PocketTTSProvider`); `tts.volume` is `0.0`–`1.0`. Voice profiles live in `%LOCALAPPDATA%\EDCeleste\voices\<provider>\` (`chatterbox`, `pocket`)
- `tts.ship_effect` — `true` | `false` (default `true`): the ship effect for every engine, one fixed chain with nothing to set (`ShipVoiceEffect` in `services/ship_voice_effect.py`, made new for every reply; `TTSService` puts every piece of a streamed voice through it as the piece is made, and a voice that is made whole through it right before `sd.play`). An old `tts.voice_lab` block in a config.yaml is ignored
- `tts.play_ship_replies` — `true` | `false` (default `true`): the one switch for every prepared reply of Celeste (checked at the top of `TTSService.speak_reply`): the replies after a command ("Throttle zero") and the lines of the game she says when the game state shows them ("Landing gear deployed" when Status.json reports the change, "Docking request granted" when the journal writes it). Off leaves all of it to the ship voice of the game; the text still goes to COMMS
- `stt.enabled` / `stt.model` / `stt.input_device`
- `event_reactions.reactions` — per-journal-event booleans for automatic replies
- `game_actions.enabled` — safety toggle for the `PerformGameAction` tool (default `false`)

## Loading

`SettingsService.load_settings()` runs eagerly the first time the DI container resolves it (`containers/main_container.py`), before any service needing a bootstrap value is built. If `config.yaml` is missing, it's auto-created from `config-example.yaml` and startup fails with `FileNotFoundError` asking you to edit it and restart.

Both paths are constructor arguments of `SettingsService` (`config_path`, `example_config_path`) — tests always pass a temp folder, never the real `config.yaml`.
