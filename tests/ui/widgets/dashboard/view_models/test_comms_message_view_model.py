import unittest

from services.models.llm_response import LLMResponse, LLMResponseSource
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class TestCommsMessageViewModel(unittest.TestCase):
    def test_from_protocol_message_sets_content_and_flags(self):
        response = LLMResponse(message="Systems nominal")

        view_model = CommsMessageViewModel.from_protocol_message(response)

        self.assertEqual(view_model.content, "Systems nominal")
        self.assertFalse(view_model.is_user_message)
        self.assertFalse(view_model.is_action)

    def test_from_protocol_message_sets_is_system_message_true_for_system_source(self):
        response = LLMResponse(message="Game state is not set.")
        response.source = LLMResponseSource.SYSTEM

        view_model = CommsMessageViewModel.from_protocol_message(response)

        self.assertTrue(view_model.is_system_message)

    def test_from_protocol_message_sets_is_system_message_false_for_llm_source(self):
        response = LLMResponse(message="Systems nominal")

        view_model = CommsMessageViewModel.from_protocol_message(response)

        self.assertFalse(view_model.is_system_message)

    def test_from_user_message_sets_content_and_user_flag(self):
        view_model = CommsMessageViewModel.from_user_message("Plot a course")

        self.assertEqual(view_model.content, "Plot a course")
        self.assertTrue(view_model.is_user_message)
        self.assertFalse(view_model.is_action)


if __name__ == "__main__":
    unittest.main()
