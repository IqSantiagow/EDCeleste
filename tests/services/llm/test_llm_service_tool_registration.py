import unittest
from unittest.mock import Mock, patch

from pydantic_ai import ToolReturn

from edceleste.services.event_bus import EventBus
from edceleste.services.llm_service import LLMService
from edceleste.services.settings_service import SettingsService


class FakeTool:
    """Minimal ToolProtocol implementation, so no real game services are needed."""

    readable_name = "Fake Tool"
    param_name = "thing"
    name = "fake_tool"

    async def execute(self, thing: str) -> ToolReturn:
        """Does a fake thing"""
        return ToolReturn(return_value=thing, metadata={"is_error": False})


class TestLLMServiceToolRegistration(unittest.TestCase):
    def setUp(self):
        self.tool = FakeTool()
        self.llm_service = LLMService(
            event_bus=EventBus(),
            settings_service=Mock(spec=SettingsService),
            tools=[self.tool],
        )

    def test_should_build_one_pydantic_ai_tool_per_registered_tool(self):
        built_tools = self.llm_service.build_tools()

        self.assertEqual([tool.name for tool in built_tools], ["fake_tool"])

    def test_should_take_tool_description_from_the_docstring(self):
        built_tool = self.llm_service.build_tools()[0]

        self.assertEqual(built_tool.description, "Does a fake thing")

    def test_should_build_tool_arguments_from_the_execute_signature(self):
        built_tool = self.llm_service.build_tools()[0]

        self.assertEqual(built_tool.function_schema.json_schema["required"], ["thing"])

    def test_should_find_registered_tool_by_its_name(self):
        self.assertIs(self.llm_service.find_tool("fake_tool"), self.tool)

    def test_should_return_none_for_a_tool_that_is_not_registered(self):
        self.assertIsNone(self.llm_service.find_tool("not_a_tool"))

    def test_should_hand_the_tools_to_the_agent_on_reload(self):
        with (
            patch("edceleste.services.llm_service.Agent") as mock_agent,
            patch.object(LLMService, "determine_provider"),
            patch.object(LLMService, "build_model"),
        ):
            self.llm_service.reload_service()

        registered_tools = mock_agent.call_args.kwargs["tools"]

        self.assertEqual([tool.name for tool in registered_tools], ["fake_tool"])


if __name__ == "__main__":
    unittest.main()
