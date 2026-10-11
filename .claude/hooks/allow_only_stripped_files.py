"""PreToolUse hook of the blind-signature-reader agent.

The agent may only Read the stripped copies in signature_check/stripped/ and Write
its report files into signature_check/reports/. Every other tool and every other
path is blocked with exit code 2, so the agent cannot peek at the real code, git
or the terminal.

The two folders belong to the checkout the session works in (the "cwd" of the hook
input), not to the checkout this file lives in. So a git worktree gets its own
folders, and the agent never reads the stale copies of another checkout.

If this file is missing, Python exits with 2 and that blocks. A crash inside the
hook would exit with 1, which does not block, so every crash is turned into a block.
"""

import json
import sys
from pathlib import Path

FALLBACK_REPO_ROOT = Path(__file__).resolve().parents[2]


def block(reason: str) -> None:
    """Exit code 2 makes Claude Code refuse the tool call and show the reason to
    the agent."""
    print(reason, file=sys.stderr)
    sys.exit(2)


def main() -> None:
    """Reads the tool call from stdin and lets through only Read of a file inside
    signature_check/stripped/ and Write of a file inside signature_check/reports/,
    plus SubagentHandback, the tool the agent hands its final message back with
    (without it the message never arrives). The folders are taken from the session's
    cwd, or from this file's checkout when the input has no cwd. The path is resolved
    first, so "..", symlinks or a different spelling cannot leave the folder."""
    tool_call = json.load(sys.stdin)
    tool_name = tool_call.get("tool_name")
    if tool_name == "SubagentHandback":
        return

    repo_root = Path(tool_call.get("cwd") or FALLBACK_REPO_ROOT).resolve()
    allowed_folder_per_tool = {
        "Read": repo_root / "signature_check" / "stripped",
        "Write": repo_root / "signature_check" / "reports",
    }
    if tool_name not in allowed_folder_per_tool:
        block(
            f"{tool_name} is not allowed. You may only Read the stripped files"
            " and Write your report files."
        )

    allowed_folder = allowed_folder_per_tool[tool_name]
    file_path = tool_call.get("tool_input", {}).get("file_path", "")
    requested_file = Path(file_path).resolve()
    if not requested_file.is_relative_to(allowed_folder.resolve()):
        block(f"{file_path} is outside {allowed_folder}. Use only the given folders.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        block(f"The hook could not check this tool call, so it is blocked: {error!r}")
