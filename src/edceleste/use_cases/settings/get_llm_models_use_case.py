from edceleste.protocols.llm_protocol import LLMProtocol


class GetLlmModelsUseCase:
    def __init__(self, llm_protocol: LLMProtocol):
        self.llm_protocol = llm_protocol

    def __call__(self, provider_type: str) -> list[str]:
        return self.llm_protocol.get_models(provider_type)
