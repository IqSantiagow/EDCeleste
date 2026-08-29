from edceleste.services.models.message_block import (
    AgentText,
    SystemMessage,
    Thinking,
    ToolCall,
    ToolResult,
)
from edceleste.services.models.llm_status import LLMStatus

LLMStreamItem = AgentText | ToolCall | ToolResult | Thinking | SystemMessage | LLMStatus
