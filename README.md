# EDCeleste

LLM-powered terminal-like copilot for Elite Dangerous with voice interface.

Celeste is an AI companion that reacts to in-game events in real-time using STT, TTS, and LLM services to sound like a human co-pilot. She can answer questions, react to events via keystrokes or game actions, and fetch data from EDMC, Galnet, and other E:D API resources.

> **Status:** Early development - core journal watching and event parsing are in place.

## Setup

**Requirements:** Python 3.12+, Elite Dangerous (PC)

```bash
git clone https://github.com/IqSantiagow/EDCeleste
cd EDCeleste
python -m venv .venv
.venv/Scripts/activate     # Windows
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

Copy and edit the env file:

```bash
cp .env-example .env
```

Set `ED__MAIN_PATH` to your Elite Dangerous journal directory (typically `C:\Users\<you>\Saved Games\Frontier Developments\Elite Dangerous`) and `LLM__ANTHROPIC_API_KEY` to your Anthropic API key.

## Usage

```bash
python app.py
```

## Debugging
Run console in separate terminal to see logs and events:
```bash
textual console -x EVENT --port 5000
```
Run app in dev mode to see logs and events:
```bash
textual run --dev --port 5000 app.py 
```

## Project Structure

```
EDCeleste/
├── app.py                 # Entry point
├── config/                # Config loading (pydantic-settings + .env)
├── projection/             # Event projections (fuel, location, player, game state)
├── services/              # Core services (journal watcher, event bus, LLM, etc.)
│   ├── event_bus.py       # Pub/sub event bus
│   └── models/            # Pydantic models for journal events
├── ui/                    # UI layer (planned)
├── tools/                 # Tool integrations (planned)
└── tests/                 # Tests
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
