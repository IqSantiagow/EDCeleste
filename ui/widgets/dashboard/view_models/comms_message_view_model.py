from dataclasses import dataclass

from adapters.message_block import AgentText, SystemMessage, ToolCall, ToolResult
from services.models.llm_stream_item import LLMStreamItem

# Must match the keys of WidgetCommsEntry._TITLES and the classes in ui/css.tcss.
USER_COMMAND_ENTRY = "user-command"
LLM_RESPONSE_ENTRY = "llm-response"
SYSTEM_MESSAGE_ENTRY = "system-message"
LLM_ACTION_ENTRY = "llm-action"
LLM_ERROR_ENTRY = "llm-error"


@dataclass
class CommsMessageViewModel:
    content: str
    entry_type: str

    @classmethod
    def from_user_message(cls, message: str) -> "CommsMessageViewModel":
        return cls(content=message, entry_type=USER_COMMAND_ENTRY)

    @classmethod
    def from_message_block(cls, block: LLMStreamItem) -> "CommsMessageViewModel | None":
        """Thinking and successful ToolResult are not shown in COMMS - return None."""
        if isinstance(block, AgentText):
            return cls(content=block.content, entry_type=LLM_RESPONSE_ENTRY)

        if isinstance(block, SystemMessage):
            return cls(content=block.content, entry_type=SYSTEM_MESSAGE_ENTRY)

        if isinstance(block, ToolCall):
            return cls(
                content=f"{block.tool_name} {block.input}",
                entry_type=LLM_ACTION_ENTRY,
            )

        if isinstance(block, ToolResult) and block.is_error:
            return cls(content=str(block.content), entry_type=LLM_ERROR_ENTRY)

        return None
