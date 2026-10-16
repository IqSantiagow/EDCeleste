import re

# Short replies the pilot hears after a command. They are spoken ahead of time
# in the voice of a profile, so playing one is just opening a file. One text per
# one-shot action, several per toggle (done, already done, unavailable).
# A new text added here is missing in the folders of the old profiles, so the
# app speaks it live until the replies are made again.
REPLY_TEXTS = [
    # Toggles
    "Flight assist on",
    "Flight assist off",
    "Flight assist already on",
    "Flight assist already off",
    "Hardpoints deployed",
    "Hardpoints retracted",
    "Hardpoints already deployed",
    "Hardpoints already retracted",
    "Hardpoints unavailable",
    "Landing gear deployed",
    "Landing gear retracted",
    "Landing gear already deployed",
    "Landing gear already retracted",
    "Landing gear unavailable",
    "Cargo scoop deployed",
    "Cargo scoop retracted",
    "Cargo scoop already deployed",
    "Cargo scoop already retracted",
    "Cargo scoop unavailable",
    "Lights on",
    "Lights off",
    "Lights already on",
    "Lights already off",
    "Night vision on",
    "Night vision off",
    "Night vision already on",
    "Night vision already off",
    # Flight
    "Boosting",
    "Engaging supercruise",
    "Jumping to the next system",
    "Engaging frame shift drive",
    "Throttle zero",
    "Throttle fifty percent",
    "Throttle seventy five percent",
    "Full throttle",
    # Power distribution
    "More power to engines",
    "More power to weapons",
    "More power to systems",
    "Power distribution reset",
    # Targeting
    "Target selected",
    "Next target",
    "Previous target",
    "Highest threat targeted",
    "Next subsystem",
    "Previous subsystem",
    "Next fire group",
    "Previous fire group",
    # Defence and utilities
    "Shield cell used",
    "Chaff launched",
    "Heat sink launched",
    "Cargo jettisoned",
    # Panels, maps and scanners
    "Cockpit focused",
    "Navigation panel opened",
    "Comms panel opened",
    "Role panel opened",
    "Systems panel opened",
    "Quick comms opened",
    "Galaxy map opened",
    "System map opened",
    "Full spectrum scanner ready",
    "Radar range increased",
    "Radar range decreased",
]


def build_reply_wav_file_name(text: str) -> str:
    """The name of the wav file of a reply text, e.g. "Landing gear deployed" ->
    "landing_gear_deployed.wav". Only the file name as a str, no folder.

    1. Lower case.
    2. Every run of characters that are not a-z or 0-9 becomes one "_". Letters
       with accents (ą, é) count as such characters.
    3. "_" at the start and at the end is cut, and ".wav" is added.

    Two texts that differ only in case or punctuation get the same name, and a
    text without a-z and 0-9 gives ".wav". REPLY_TEXTS has neither (a unit test
    checks it). Saving the replies and playing them must both use this function,
    or the files are not found. Touches no disk."""
    words = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return f"{words}.wav"
