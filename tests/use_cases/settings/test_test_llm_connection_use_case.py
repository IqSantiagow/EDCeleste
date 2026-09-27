import unittest
from unittest.mock import AsyncMock, Mock

from edceleste.protocols.llm_protocol import LLMProtocol
from edceleste.services.models.settings_model import LLMProviderModel
from edceleste.use_cases.settings.test_llm_connection_use_case import (
    TestLlmConnectionUseCase,
)


class TestTestLlmConnectionUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_should_test_the_edited_provider_and_return_the_error(self):
        # The pilot checks a key before saving it, so the not yet saved
        # provider has to reach the service.
        llm_protocol = Mock(spec=LLMProtocol)
        llm_protocol.test_connection = AsyncMock(return_value="401 Unauthorized")
        use_case = TestLlmConnectionUseCase(llm_protocol)
        provider = LLMProviderModel(type="openai", model="gpt-4o", api_key="bad")

        result = await use_case(provider)

        self.assertEqual(result, "401 Unauthorized")
        llm_protocol.test_connection.assert_awaited_once_with(provider)

    async def test_should_return_none_when_the_connection_works(self):
        llm_protocol = Mock(spec=LLMProtocol)
        llm_protocol.test_connection = AsyncMock(return_value=None)
        use_case = TestLlmConnectionUseCase(llm_protocol)

        result = await use_case(LLMProviderModel(type="openai", model="gpt-4o"))

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
