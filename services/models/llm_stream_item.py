from services.models.message_block import (
    AgentText,
    SystemMessage,
    Thinking,
    ToolCall,
    ToolResult,
)
from services.models.llm_status import LLMStatus

LLMStreamItem = AgentText | ToolCall | ToolResult | Thinking | SystemMessage | LLMStatus
