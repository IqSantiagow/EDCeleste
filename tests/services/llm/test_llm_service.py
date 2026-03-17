import unittest
from unittest.mock import patch, Mock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.llm_service import LLMService
from services.llm_service import SYSTEM_PROMPT


class LLMServiceTest(unittest.TestCase):
    def setUp(self):
        model_patcher = patch("langchain_anthropic.ChatAnthropic.invoke")

        self.test_game_state = "Test game state"

        self.game_state_mock = Mock()

        self.game_state_mock.get_game_state_projection.return_value = (
            self.test_game_state
        )

        self.mock_model = model_patcher.start()

        self.addCleanup(model_patcher.stop)

        self.llm_service = LLMService(game_state=self.game_state_mock, api_key="")

        self.mock_model.side_effect = [
            AIMessage("Test output 1"),
            AIMessage("Test output 2"),
        ]

    def test_should_receive_a_message(self):
        message = "Test message"

        response = self.llm_service.send_and_receive_message(message)

        self.assertEqual(response, "Test output 1")

    def test_should_add_message_to_conv_history(self):
        message1 = "Test message 1"
        message2 = "Test message 2"

        self.llm_service.send_and_receive_message(message1)
        self.llm_service.send_and_receive_message(message2)

        self.assertIn(HumanMessage(content=message1), self.llm_service.conversation)
        self.assertIn(HumanMessage(content=message2), self.llm_service.conversation)
        self.assertIn(AIMessage(content="Test output 1"), self.llm_service.conversation)
        self.assertIn(AIMessage(content="Test output 2"), self.llm_service.conversation)

    def test_should_add_state_and_prompt_to_each_request(self):
        message1 = "Test message 1"

        self.llm_service.send_and_receive_message(message1)

        conv_history = [call.args[0] for call in self.mock_model.mock_calls]

        all_messages = [msg for msg_list in conv_history for msg in msg_list]

        self.assertIn(
            SystemMessage(content=self.test_game_state, role="system"), all_messages
        )
        self.assertIn(SystemMessage(content=SYSTEM_PROMPT, role="system"), all_messages)
