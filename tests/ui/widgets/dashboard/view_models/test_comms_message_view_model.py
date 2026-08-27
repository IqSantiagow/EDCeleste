import unittest

from services.models.message_block import (
    AgentText,
    SystemMessage,
    Thinking,
    ToolCall,
    ToolResult,
)
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class TestCommsMessageViewModel(unittest.TestCase):
    def test_from_message_block_maps_agent_text_to_llm_response(self):
        view_model = CommsMessageViewModel.from_message_block(
            AgentText(content="Systems nominal")
        )

        self.assertEqual(view_model.content, "Systems nominal")
        self.assertEqual(view_model.entry_type, "llm-response")

    def test_from_message_block_maps_system_message_to_system_entry(self):
        view_model = CommsMessageViewModel.from_message_block(
            SystemMessage(content="Game state is not set.")
        )

        self.assertEqual(view_model.content, "Game state is not set.")
        self.assertEqual(view_model.entry_type, "system-message")

    def test_from_message_block_maps_tool_call_to_action_entry(self):
        view_model = CommsMessageViewModel.from_message_block(
            ToolCall(
                tool_readable_name="Perform game action",
                tool_name="perform_game_action",
                param_name="action",
                input={"action": "ToggleFlightAssist"},
            )
        )

        self.assertEqual(
            view_model.content,
            "Perform game action -> ToggleFlightAssist",
        )
        self.assertEqual(view_model.entry_type, "llm-action")

    def test_from_message_block_maps_failed_tool_result_to_error_entry(self):
        view_model = CommsMessageViewModel.from_message_block(
            ToolResult(content="Keybind not available", is_error=True)
        )

        self.assertEqual(view_model.content, "Keybind not available")
        self.assertEqual(view_model.entry_type, "llm-error")

    def test_from_message_block_skips_successful_tool_result(self):
        view_model = CommsMessageViewModel.from_message_block(
            ToolResult(content="Performed game action", is_error=False)
        )

        self.assertIsNone(view_model)

    def test_from_message_block_skips_thinking(self):
        view_model = CommsMessageViewModel.from_message_block(
            Thinking(content="Let me check the fuel level")
        )

        self.assertIsNone(view_model)

    def test_from_user_message_sets_content_and_user_command_entry(self):
        view_model = CommsMessageViewModel.from_user_message("Plot a course")

        self.assertEqual(view_model.content, "Plot a course")
        self.assertEqual(view_model.entry_type, "user-command")


if __name__ == "__main__":
    unittest.main()
