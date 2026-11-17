import unittest
from unittest.mock import Mock

from pydantic_ai import ToolReturn

from edceleste.adapters.tools.tool_register import ToolRegister


class FakeToolGroup:
    def __init__(self):
        # A service the group holds: it must never be taken for a tool
        self.service = Mock()
        self.service.readable_name = "Looks like a tool"

    @ToolRegister.register_tool(
        name="first_tool", readable_name="First Tool", param_name="first"
    )
    async def first_tool(self, first: str) -> ToolReturn:
        return ToolReturn(return_value=first)

    @ToolRegister.register_tool(
        name="second_tool", readable_name="Second Tool", param_name="second"
    )
    async def second_tool(self, second: str) -> ToolReturn:
        return ToolReturn(return_value=second)

    async def not_a_tool(self) -> None:
        return None


class TestToolRegister(unittest.IsolatedAsyncioTestCase):
    def test_should_return_every_marked_method_of_a_group(self):
        tools = ToolRegister(groups=[FakeToolGroup()]).get_tools()

        self.assertEqual(
            [(tool.name, tool.readable_name, tool.param_name) for tool in tools],
            [
                ("first_tool", "First Tool", "first"),
                ("second_tool", "Second Tool", "second"),
            ],
        )

    def test_should_ignore_methods_that_are_not_marked(self):
        tool_names = [
            tool.name for tool in ToolRegister(groups=[FakeToolGroup()]).get_tools()
        ]

        self.assertNotIn("not_a_tool", tool_names)

    def test_should_not_take_a_service_of_the_group_for_a_tool(self):
        tools = ToolRegister(groups=[FakeToolGroup()]).get_tools()

        self.assertEqual(len(tools), 2)

    def test_should_collect_the_tools_of_all_groups(self):
        tools = ToolRegister(groups=[FakeToolGroup(), FakeToolGroup()]).get_tools()

        self.assertEqual(len(tools), 4)

    def test_should_return_no_tools_when_there_are_no_groups(self):
        self.assertEqual(ToolRegister(groups=[]).get_tools(), [])

    async def test_should_hand_out_the_method_bound_to_its_group(self):
        tool = ToolRegister(groups=[FakeToolGroup()]).get_tools()[0]

        result = await tool.func("hello")

        self.assertEqual(result.return_value, "hello")


if __name__ == "__main__":
    unittest.main()
