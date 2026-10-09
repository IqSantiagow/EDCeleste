from typing import Any, Protocol

from pydantic_ai import ToolReturn


class ToolProtocol(Protocol):
    """A tool the LLM can call. LLMService wraps execute in pydantic_ai.Tool.

    - name: the tool name the LLM sees and calls.
    - readable_name: shown in COMMS instead of name, e.g. "Perform Game
      Action".
    - param_name: the execute argument whose value COMMS shows next to
      readable_name, e.g. "action".
    """

    readable_name: str
    param_name: str
    name: str

    async def execute(self, *args: Any, **kwargs: Any) -> ToolReturn:
        """pydantic_ai builds the tool schema from the implementation's own
        execute: the arguments from its signature and the description from its
        docstring. So that docstring is written for the LLM, and this one is
        never sent.

        Expected failures (feature off, no key) are returned, not raised:
        a ToolReturn with metadata={"is_error": True}, so COMMS shows them as
        an error and the LLM can tell the pilot. A raised exception ends the
        whole LLM turn.
        """
        ...
