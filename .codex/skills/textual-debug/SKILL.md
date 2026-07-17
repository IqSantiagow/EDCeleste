---
name: textual-debug
description: Runs the Textual app in debug mode — debug console and app run in parallel on port 7342.
---

Run the Textual app in debug mode by starting the Textual console and the app in parallel.

## Steps

1. Start the Textual debug console in the background with EVENT filtering:
   ```
   textual console -x EVENT --port 7342
   ```

2. In parallel, run the app in dev mode (don't wait for the console to finish):
   ```
   textual run --dev --port 7342 app.py
   ```

Run both commands as background processes (`run_in_background: true`) so they run at the same time. Start the console first, wait a moment (a few seconds), then start the app — so the console is ready before the app connects.

Once the processes are running, tell the user that:
- the Textual console is listening on port 7342 (with EVENT filtering)
- the app is running in `--dev` mode and sending logs to the console
- to stop it — they should close both processes (Ctrl+C in the respective terminals)
