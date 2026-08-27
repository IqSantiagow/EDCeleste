from typing import Any


class TextContent:
    def __init__(self, text: str, content_type: str = "text") -> None:
        self.type = content_type
        self.text = text

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "text": self.text,
        }


class ToolResult:
    def __init__(self, content: TextContent, is_error: bool) -> None:
        self.content = content
        self.is_error = is_error

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": [self.content.to_dict()],
            "is_error": self.is_error,
        }
