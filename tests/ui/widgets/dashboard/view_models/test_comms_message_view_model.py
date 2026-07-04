import unittest

from services.models.llm_response import LLMMessage, LLMResponse
from ui.widgets.dashboard.view_models.comms_message_view_model import (
    CommsMessageViewModel,
)


class TestCommsMessageViewModel(unittest.TestCase):
    def test_from_protocol_message_sets_content_and_flags(self):
        response = LLMResponse(message=LLMMessage(message="Systems nominal"))

        view_model = CommsMessageViewModel.from_protocol_message(response)

        self.assertEqual(view_model.content, "Systems nominal")
        self.assertFalse(view_model.is_user_message)
        self.assertFalse(view_model.is_action)

    def test_from_user_message_sets_content_and_user_flag(self):
        view_model = CommsMessageViewModel.from_user_message("Plot a course")

        self.assertEqual(view_model.content, "Plot a course")
        self.assertTrue(view_model.is_user_message)
        self.assertFalse(view_model.is_action)


if __name__ == "__main__":
    unittest.main()
