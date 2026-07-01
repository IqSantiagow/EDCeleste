import unittest
from unittest.mock import patch

import anthropic
import httpx
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.llm_service import LLMService
from services.llm_service import SYSTEM_PROMPT


class LLMServiceTest(unittest.TestCase):
    def setUp(self):
        model_patcher = patch("langchain_anthropic.ChatAnthropic.invoke")

        self.test_game_state = "Test game state"

        self.mock_model = model_patcher.start()

        self.addCleanup(model_patcher.stop)

        self.llm_service = LLMService(api_key="")

        self.mock_model.side_effect = [
            AIMessage("Test output 1"),
            AIMessage("Test output 2"),
        ]

    def test_should_receive_a_message(self):
        message = "Test message"

        response = self.llm_service.send_and_receive_message(
            message, self.test_game_state
        )

        self.assertEqual(response, "Test output 1")

    def test_should_add_message_to_conv_history(self):
        message1 = "Test message 1"
        message2 = "Test message 2"

        self.llm_service.send_and_receive_message(message1, self.test_game_state)
        self.llm_service.send_and_receive_message(message2, self.test_game_state)

        self.assertIn(HumanMessage(content=message1), self.llm_service.conversation)
        self.assertIn(HumanMessage(content=message2), self.llm_service.conversation)
        self.assertIn(AIMessage(content="Test output 1"), self.llm_service.conversation)
        self.assertIn(AIMessage(content="Test output 2"), self.llm_service.conversation)

    def test_should_add_state_and_prompt_to_each_request(self):
        message1 = "Test message 1"

        self.llm_service.send_and_receive_message(message1, self.test_game_state)

        conv_history = [call.args[0] for call in self.mock_model.mock_calls]

        all_messages = [msg for msg_list in conv_history for msg in msg_list]

        self.assertIn(
            SystemMessage(content=self.test_game_state, role="system"), all_messages
        )
        self.assertIn(SystemMessage(content=SYSTEM_PROMPT, role="system"), all_messages)

    def test_should_return_true_when_token_count_succeeds(self):
        with patch(
            "langchain_anthropic.ChatAnthropic.get_num_tokens_from_messages"
        ) as mock_get_num_tokens:
            mock_get_num_tokens.return_value = 42

            result = self.llm_service.get_llm_healthcheck()

            self.assertTrue(result)

    def test_should_return_false_when_anthropic_api_error_is_raised(self):
        api_error = anthropic.APIError(
            "boom",
            request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
            body=None,
        )

        with patch(
            "langchain_anthropic.ChatAnthropic.get_num_tokens_from_messages"
        ) as mock_get_num_tokens:
            mock_get_num_tokens.side_effect = api_error

            result = self.llm_service.get_llm_healthcheck()

            self.assertFalse(result)
