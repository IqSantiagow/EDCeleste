# EDCeleste

LLM-powered terminal-like copilot for Elite Dangerous with voice interface.

Celeste is an AI companion that reacts to in-game events in real-time using STT, TTS, and LLM services to sound like a human co-pilot. She can answer questions, react to events via keystrokes or game actions, and fetch data from EDMC, Galnet, and other E:D API resources.

> **Status:** Early development - core journal watching and event parsing are in place.

## Setup

**Requirements:** Python 3.12+, Elite Dangerous (PC)

```bash
git clone https://https://github.com/IqSantiagow/EDCeleste
cd EDCeleste
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
```

Copy and edit the config file:

```bash
cp config.example.yaml config.yaml
```

Set `main_path` to your Elite Dangerous journal directory (typically `C:\Users\<you>\Saved Games\Frontier Developments\Elite Dangerous`).

## Usage

```bash
python app.py
```

## Project Structure

```
EDCeleste/
├── app.py                 # Entry point
├── config/                # Config loading (YAML + Pydantic)
├── services/              # Core services (journal watcher, etc.)
│   └── models/            # Pydantic models for journal events
├── ui/                    # UI layer (planned)
├── tools/                 # Tool integrations (planned)
└── tests/                 # Tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
