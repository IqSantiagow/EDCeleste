from protocols.game_state_protocol import GameStateProtocol
from protocols.llm_protocol import LLMProtocol


class LLMSendMessageUseCase:
    def __init__(
        self, llm_protocol: LLMProtocol, game_state_reader: GameStateProtocol
    ) -> None:
        self.llm_protocol = llm_protocol
        self.game_state_reader = game_state_reader

    async def __call__(self, message: str) -> None:
        game_state = self.game_state_reader.get_game_state_projection()
        await self.llm_protocol.send_message(message, game_state)
