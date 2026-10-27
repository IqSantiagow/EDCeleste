from dataclasses import dataclass

from edceleste.services.models.message_block import (
    AgentText,
    SystemMessage,
)
from edceleste.services.models.llm_stream_item import LLMStreamItem

# Must match the keys of WidgetCommsEntry._TITLES and the classes in ui/css.tcss.
USER_COMMAND_ENTRY = "user-command"
LLM_RESPONSE_ENTRY = "llm-response"
SYSTEM_MESSAGE_ENTRY = "system-message"


@dataclass
class CommsMessageViewModel:
    content: str
    entry_type: str

    @classmethod
    def from_user_message(cls, message: str) -> "CommsMessageViewModel":
        """The pilot's own line in COMMS, shown by DashboardScreen right after
        the pilot sends it, before the LLM answers."""
        return cls(content=message, entry_type=USER_COMMAND_ENTRY)

    @classmethod
    def from_message_block(cls, block: LLMStreamItem) -> "CommsMessageViewModel | None":
        """Picks the COMMS entry type for one block from the LLM stream.

        - AgentText -> Celeste's reply.
        - SystemMessage -> system line (e.g. "Game state is not set").
        - Anything else (ToolCall, ToolResult, Thinking, LLMStatus) -> None, so
          the caller shows nothing. Tool calls and results are only written to
          the log file by LLMService, a failed tool reaches the pilot as
          Celeste's own sentence.
        """
        if isinstance(block, AgentText):
            return cls(content=block.content, entry_type=LLM_RESPONSE_ENTRY)

        if isinstance(block, SystemMessage):
            return cls(content=block.content, entry_type=SYSTEM_MESSAGE_ENTRY)

        return None
