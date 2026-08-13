from protocols.llm_protocol import LLMProtocol


class LLMSendMessageUseCase:
    def __init__(self, llm_protocol: LLMProtocol) -> None:
        self.llm_protocol = llm_protocol

    async def __call__(self, message: str) -> None:
        await self.llm_protocol.send_message(message)
