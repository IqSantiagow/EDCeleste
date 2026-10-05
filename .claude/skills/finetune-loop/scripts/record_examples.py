"""Record real spoken examples from the user, one prompt at a time, through the same
speech-to-text the app uses.

The user runs it in their own terminal (it reads single key presses; Windows: msvcrt,
elsewhere: termios):
    python record_examples.py --prompts prompts.json --out <workspace>/recordings \\
        --stt_model tiny.en [--input_device 3]

prompts.json: a list of {"id", "category", "intent", "what", "hint"}. "what" says
WHAT to say (in the user's language), "hint" says HOW (short, full sentence, in a
hurry...). The user speaks in their own words.
Output: <out>/recordings.csv
(prompt_id;category;intent;transcription;reference_text;wav_file;recorded_at) plus
one .wav per take. reference_text starts empty: fill it later with what was really
said, if the recordings will also train the speech-to-text model.
Quit any time; running again continues with the prompts not recorded yet. Prompts
keep their order from the file.
"""

import argparse
import csv
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
import whisper

SAMPLE_RATE = 16_000


def read_key() -> str:
    if sys.platform == "win32":
        import msvcrt

        key = msvcrt.getwch()
    else:
        import termios
        import tty

        settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            key = sys.stdin.read(1)
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
    return {"\r": "enter", "\n": "enter", " ": "space"}.get(key, key.lower())


def wait_for_key(allowed_keys: str) -> str:
    while True:
        key = read_key()
        if key in allowed_keys.split():
            return key


def record_until_space(input_device) -> np.ndarray:
    recorded_frames = []

    def keep_frames(indata, frames, time_info, status):
        recorded_frames.append(indata[:, 0].copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        device=input_device,
        callback=keep_frames,
    ):
        wait_for_key("space enter")
    return (
        np.concatenate(recorded_frames)
        if recorded_frames
        else np.zeros(0, dtype=np.float32)
    )


def save_take(
    out_dir: Path, prompt: dict, transcription: str, audio: np.ndarray
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_name = f"{prompt['id']}.wav"
    with wave.open(str(out_dir / wav_name), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    csv_file = out_dir / "recordings.csv"
    is_new_file = not csv_file.exists()
    with csv_file.open("a", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter=";")
        if is_new_file:
            writer.writerow(
                [
                    "prompt_id",
                    "category",
                    "intent",
                    "transcription",
                    "reference_text",
                    "wav_file",
                    "recorded_at",
                ]
            )
        writer.writerow(
            [
                prompt["id"],
                prompt["category"],
                prompt["intent"],
                transcription,
                "",
                wav_name,
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )


def done_prompt_ids(out_dir: Path) -> set:
    csv_file = out_dir / "recordings.csv"
    if not csv_file.exists():
        return set()
    with csv_file.open(encoding="utf-8", newline="") as file:
        return {row["prompt_id"] for row in csv.DictReader(file, delimiter=";")}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--stt_model", default="tiny.en")
    parser.add_argument("--input_device", type=int, default=None)
    args = parser.parse_args()

    out_dir = Path(args.out)
    prompts = json.loads(Path(args.prompts).read_text(encoding="utf-8"))
    done = done_prompt_ids(out_dir)
    todo = [prompt for prompt in prompts if prompt["id"] not in done]
    print(f"Loading Whisper {args.stt_model}...")
    whisper_model = whisper.load_model(args.stt_model)
    microphone_name = sd.query_devices(args.input_device, kind="input")["name"]
    print(f"Microphone: {microphone_name}. Done {len(done)} of {len(prompts)}.\n")

    for number, prompt in enumerate(todo, start=len(done) + 1):
        print("-" * 70)
        print(f"[{number}/{len(prompts)}] {prompt['category']}")
        print(f"  {prompt['what']}")
        print(f"  style: {prompt['hint']}")
        while True:
            print("  SPACE = record   S = skip   Q = quit", flush=True)
            key = wait_for_key("space enter s q")
            if key == "q":
                print("Saved. Run again to continue.")
                return
            if key == "s":
                break
            print("  * recording... SPACE = stop", flush=True)
            audio = record_until_space(args.input_device)
            if len(audio) < SAMPLE_RATE * 0.3:
                print("  too short, again")
                continue
            transcription = (
                whisper_model.transcribe(audio, fp16=False).get("text", "").strip()
            )
            if not transcription:
                print("  heard nothing, again")
                continue
            print(f'  heard: "{transcription}"')
            print("  ENTER = save   R = record again   S = skip   Q = quit", flush=True)
            key = wait_for_key("enter r s q")
            if key == "enter":
                save_take(out_dir, prompt, transcription, audio)
                print("  saved")
                break
            if key == "s":
                break
            if key == "q":
                print("Saved. Run again to continue.")
                return
    print("\nAll prompts recorded. Thank you!")


if __name__ == "__main__":
    main()
