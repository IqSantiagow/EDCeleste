import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage as SdkUserMessage,
)

from edceleste.adapters.claude_agent_sdk import ClaudeAgentSDK, NormalizedSdkMcpTool
from edceleste.services.models.message_block import (
    AgentText,
    Thinking,
    ToolCall,
    ToolResult,
)

TEST_MODEL = "claude-haiku-4-5-20251001"
TEST_SYSTEM_PROMPT = "You are Celeste."


class FakeTool:
    """Minimal ToolProtocol implementation, so no real keybind service is needed."""

    def __init__(
        self,
        readable_name: str = "Perform game action",
        name: str = "perform_game_action",
        param_name: str = "action",
    ) -> None:
        self.readable_name = readable_name
        self.name = name
        self.param_name = param_name
        self.description = "Performs a game action in Elite Dangerous."
        self.parameters: dict[str, Any] = {
            "type": "object",
            "properties": {"action": {"type": "string"}},
        }
        self.execute = AsyncMock(return_value={"is_error": False})


def _make_assistant_message(blocks: list) -> AssistantMessage:
    return AssistantMessage(content=blocks, model=TEST_MODEL)


def _make_user_message(content) -> SdkUserMessage:
    return SdkUserMessage(content=content)


def _make_result_message() -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="session",
    )


class TestNormalizedSdkMcpTool(unittest.TestCase):
    def test_should_keep_base_tool_fields_and_readable_metadata(self):
        async def handler(arguments: dict[str, Any]) -> dict[str, Any]:
            return {"is_error": False}

        schema = {"type": "object", "properties": {}}

        tool = NormalizedSdkMcpTool(
            readable_name="Perform game action",
            param_name="action",
            name="perform_game_action",
            description="Performs a game action.",
            input_schema=schema,
            handler=handler,
        )

        self.assertEqual(tool.name, "perform_game_action")
        self.assertEqual(tool.description, "Performs a game action.")
        self.assertEqual(tool.input_schema, schema)
        self.assertIs(tool.handler, handler)
        self.assertEqual(tool.readable_name, "Perform game action")
        self.assertEqual(tool.param_name, "action")


class TestClaudeAgentSDKSetup(unittest.TestCase):
    def setUp(self):
        self.sdk = ClaudeAgentSDK(model=TEST_MODEL, system_prompt=TEST_SYSTEM_PROMPT)
        self.tool = FakeTool()

        # The real MCP server spawns machinery we do not want in a unit test.
        server_patcher = patch(
            "edceleste.adapters.claude_agent_sdk.create_sdk_mcp_server"
        )
        self.mock_create_server = server_patcher.start()
        self.addCleanup(server_patcher.stop)
        self.mock_create_server.return_value = "mcp-server"

    def test_should_start_without_tools_and_without_mcp_server(self):
        self.assertEqual(self.sdk.tools, [])
        self.assertIsNone(self.sdk.mcp_server)

    def test_should_convert_tool_protocol_to_normalized_sdk_tool(self):
        converted_tools = self.sdk.convert_tools([self.tool])  # type: ignore

        self.assertEqual(len(converted_tools), 1)

        converted_tool = converted_tools[0]
        self.assertEqual(converted_tool.readable_name, "Perform game action")
        self.assertEqual(converted_tool.name, "perform_game_action")
        self.assertEqual(converted_tool.param_name, "action")
        self.assertEqual(converted_tool.description, self.tool.description)
        self.assertEqual(converted_tool.input_schema, self.tool.parameters)
        self.assertIs(converted_tool.handler, self.tool.execute)

    def test_should_return_empty_list_for_no_tools(self):
        self.assertEqual(self.sdk.convert_tools([]), [])

    def test_should_build_options_without_mcp_server_when_no_tools_registered(self):
        options = self.sdk.build_options()

        self.assertEqual(options.mcp_servers, {})
        self.assertEqual(options.allowed_tools, [])
        self.assertEqual(options.model, TEST_MODEL)
        self.assertEqual(options.system_prompt, TEST_SYSTEM_PROMPT)

    def test_should_expose_registered_tools_under_game_mcp_prefix(self):
        self.sdk.register_tools([self.tool])  # type: ignore

        options = self.sdk.build_options()

        self.assertEqual(options.mcp_servers, {"game": "mcp-server"})
        self.assertEqual(options.allowed_tools, ["mcp__game__perform_game_action"])

    def test_should_store_converted_tools_and_create_mcp_server(self):
        self.sdk.register_tools([self.tool])  # type: ignore

        self.assertEqual(len(self.sdk.tools), 1)
        self.assertEqual(self.sdk.tools[0].name, "perform_game_action")
        self.assertEqual(self.sdk.mcp_server, "mcp-server")
        self.mock_create_server.assert_called_once_with(
            name="game_actions", tools=self.sdk.tools
        )

    def test_should_replace_previously_registered_tools(self):
        # reload_service registers tools again, the old ones must not pile up.
        self.sdk.register_tools([self.tool])  # type: ignore
        self.sdk.register_tools([FakeTool(name="other_action")])  # type: ignore

        self.assertEqual(len(self.sdk.tools), 1)
        self.assertEqual(self.sdk.tools[0].name, "other_action")


class TestClaudeAgentSDKExecuteQuery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sdk = ClaudeAgentSDK(model=TEST_MODEL, system_prompt=TEST_SYSTEM_PROMPT)

        query_patcher = patch("edceleste.adapters.claude_agent_sdk.query")
        self.mock_query = query_patcher.start()
        self.addCleanup(query_patcher.stop)

    def _make_query_yielding(self, messages: list):
        async def fake_query(prompt: str, options):
            for message in messages:
                yield message

        self.mock_query.side_effect = fake_query

    async def _collect_yielded_blocks(self, messages: list) -> list:
        self._make_query_yielding(messages)

        return [block async for block in self.sdk.execute_query("Test prompt")]

    async def test_should_pass_prompt_and_options_to_query(self):
        await self._collect_yielded_blocks([])

        self.assertEqual(self.mock_query.call_args.kwargs["prompt"], "Test prompt")
        self.assertEqual(self.mock_query.call_args.kwargs["options"].model, TEST_MODEL)
        self.assertEqual(
            self.mock_query.call_args.kwargs["options"].system_prompt,
            TEST_SYSTEM_PROMPT,
        )

    async def test_should_yield_agent_text_for_text_block(self):
        blocks = await self._collect_yielded_blocks(
            [_make_assistant_message([TextBlock(text="Hello Commander")])]
        )

        self.assertEqual(blocks, [AgentText(content="Hello Commander")])

    async def test_should_yield_thinking_for_thinking_block(self):
        blocks = await self._collect_yielded_blocks(
            [
                _make_assistant_message(
                    [ThinkingBlock(thinking="Checking fuel", signature="sig")]
                )
            ]
        )

        self.assertEqual(blocks, [Thinking(content="Checking fuel")])

    async def test_should_yield_tool_call_for_tool_use_block(self):
        blocks = await self._collect_yielded_blocks(
            [
                _make_assistant_message(
                    [
                        ToolUseBlock(
                            id="tool-1",
                            name="mcp__game__perform_game_action",
                            input={"action": "Boost"},
                        )
                    ]
                )
            ]
        )

        self.assertEqual(
            blocks,
            [
                ToolCall(
                    tool_readable_name="mcp__game__perform_game_action",
                    tool_name="perform_game_action",
                    param_name=None,
                    input={"action": "Boost"},
                )
            ],
        )

    async def test_should_yield_tool_result_from_user_message(self):
        # Tool results arrive on the user message, not on the assistant one.
        blocks = await self._collect_yielded_blocks(
            [
                _make_user_message(
                    [
                        ToolResultBlock(
                            tool_use_id="tool-1",
                            content="keybind missing",
                            is_error=True,
                        )
                    ]
                )
            ]
        )

        self.assertEqual(blocks, [ToolResult(content="keybind missing", is_error=True)])

    async def test_should_treat_missing_is_error_as_success(self):
        blocks = await self._collect_yielded_blocks(
            [
                _make_user_message(
                    [
                        ToolResultBlock(
                            tool_use_id="tool-1",
                            content="Performed game action",
                            is_error=None,
                        )
                    ]
                )
            ]
        )

        self.assertEqual(blocks[0].is_error, False)

    async def test_should_skip_messages_of_other_types(self):
        blocks = await self._collect_yielded_blocks(
            [
                _make_result_message(),
                _make_assistant_message([TextBlock(text="Hello Commander")]),
            ]
        )

        self.assertEqual(blocks, [AgentText(content="Hello Commander")])

    async def test_should_skip_user_message_with_plain_string_content(self):
        # A string content is iterable, so without the guard it would be
        # walked character by character.
        blocks = await self._collect_yielded_blocks(
            [_make_user_message("Plain text prompt")]
        )

        self.assertEqual(blocks, [])

    async def test_should_yield_blocks_in_order_for_mixed_stream(self):
        blocks = await self._collect_yielded_blocks(
            [
                _make_assistant_message(
                    [
                        ThinkingBlock(thinking="Checking fuel", signature="sig"),
                        TextBlock(text="Boosting now"),
                        ToolUseBlock(
                            id="tool-1",
                            name="mcp__game__perform_game_action",
                            input={"action": "Boost"},
                        ),
                    ]
                )
            ]
        )

        self.assertEqual(
            [type(block) for block in blocks], [Thinking, AgentText, ToolCall]
        )


class TestClaudeAgentSDKToolNormalization(unittest.TestCase):
    def setUp(self):
        self.sdk = ClaudeAgentSDK(model=TEST_MODEL, system_prompt=TEST_SYSTEM_PROMPT)

        server_patcher = patch(
            "edceleste.adapters.claude_agent_sdk.create_sdk_mcp_server"
        )
        self.mock_create_server = server_patcher.start()
        self.addCleanup(server_patcher.stop)

        self.sdk.register_tools([FakeTool()])  # type: ignore

    def test_should_strip_mcp_prefix_and_use_readable_name_of_registered_tool(self):
        tool_call = self.sdk._normalize_tool_to_readable_name_and_input(
            ToolUseBlock(
                id="tool-1",
                name="mcp__game__perform_game_action",
                input={"action": "Boost"},
            )
        )

        self.assertEqual(
            tool_call,
            ToolCall(
                tool_readable_name="Perform game action",
                tool_name="perform_game_action",
                param_name="action",
                input={"action": "Boost"},
            ),
        )

    def test_should_fall_back_to_raw_name_when_tool_is_not_registered(self):
        tool_call = self.sdk._normalize_tool_to_readable_name_and_input(
            ToolUseBlock(
                id="tool-2", name="mcp__game__unknown_action", input={"action": "Boost"}
            )
        )

        self.assertEqual(tool_call.tool_name, "unknown_action")
        self.assertEqual(tool_call.tool_readable_name, "mcp__game__unknown_action")
        self.assertIsNone(tool_call.param_name)


if __name__ == "__main__":
    unittest.main()
