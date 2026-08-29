from edceleste.protocols.llm_protocol import LLMProtocol


class LLMSendMessageUseCase:
    def __init__(self, llm_protocol: LLMProtocol) -> None:
        self.llm_protocol = llm_protocol

    def __call__(self, message: str) -> None:
        self.llm_protocol.add_llm_request_to_queue(message)
