# Vendored: pocket-tts-onnx

This folder is a copy of the Python package **pocket-tts-onnx** by thewh1teagle,
which runs Kyutai's Pocket TTS on ONNX Runtime without torch.

- Source: https://github.com/thewh1teagle/pocket-tts-onnx
- Commit: `9860fc0` (2026-09-12, "Fetch models from the Hub with PocketTTS.from_pretrained")
- Licence: CC BY 4.0, see `LICENSE` (the model it runs, Kyutai's Pocket TTS, is CC BY 4.0 too)
- Files: `__init__.py`, `audio.py`, `g2p.py`, `hub.py`, `text.py`, `tts.py`, copied
  byte for byte. The exporter (`export/`) is left out, it needs torch.

Do not edit these files. To update, copy the files of a newer commit over them
and change the commit above. They are left out of ruff, mypy, coverage and
mutation tests (see `pyproject.toml`). The app uses only `PocketTTS` through
`edceleste/services/tts_providers/pocket_tts_provider.py`, which downloads a
fixed revision of the model itself, so `hub.py`, `g2p.py` and the Hebrew and
phoneme code stay unused.

The package is a top-level package (not inside `edceleste`) because its files
import each other as `pocket_tts_onnx.*`, and they must stay unchanged.
