from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic_ai import ToolReturn


@dataclass
class McpTool:
    """A tool the LLM can call, as found by the tool register.

    - name: the tool name the LLM sees and calls.
    - readable_name: shown in COMMS instead of name, e.g. "Perform Game Action".
    - param_name: the argument of func whose value COMMS shows next to
      readable_name, e.g. "action".
    - func: pydantic_ai builds the tool schema from its signature and sends its
      docstring to the LLM, so that docstring is written for the LLM.
    """

    name: str
    readable_name: str
    param_name: str
    func: Callable[..., Awaitable[ToolReturn]]
