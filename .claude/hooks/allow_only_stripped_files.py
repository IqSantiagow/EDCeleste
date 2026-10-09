"""PreToolUse hook of the blind-signature-reader agent.

The agent may only Read the stripped copies in signature_check/stripped/. Every
other tool and every other path is blocked with exit code 2, so the agent cannot
peek at the real code, git or the terminal.

If this file is missing or crashes, Python itself exits with 2 or 1. Exit 2
blocks too, so a broken hook rather blocks than lets the agent through.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STRIPPED_FOLDER = REPO_ROOT / "signature_check" / "stripped"


def block(reason: str) -> None:
    """Exit code 2 makes Claude Code refuse the tool call and show the reason to
    the agent."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    """Reads the tool call from stdin and lets through only Read of a file
    inside signature_check/stripped/, plus SubagentHandback, the tool the agent
    hands its report back with (without it the report never arrives). The path
    is resolved first, so "..", symlinks or a different spelling cannot leave
    the folder."""
    tool_call = json.load(sys.stdin)
    tool_name = tool_call.get("tool_name")
    if tool_name == "SubagentHandback":
        return
    if tool_name != "Read":
        block(f"{tool_name} is not allowed. You may only Read the stripped files.")

    file_path = tool_call.get("tool_input", {}).get("file_path", "")
    requested_file = Path(file_path).resolve()
    if not requested_file.is_relative_to(STRIPPED_FOLDER.resolve()):
        block(f"{file_path} is outside {STRIPPED_FOLDER}. Read only the given files.")


if __name__ == "__main__":
    main()
