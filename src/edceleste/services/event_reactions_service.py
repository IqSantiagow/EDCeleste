from edceleste.services.event_bus import EventBus
from edceleste.services.models.event_reaction_event import EventReactionEvent
from edceleste.services.models.game_events import GameEvent
from edceleste.services.models.journal_event import JournalEvent
from edceleste.services.models.settings_model import (
    EventReactionModel,
    SettingsIssueModel,
    SettingsModel,
)
from edceleste.services.settings_service import SettingsService


class EventReactionsService:
    def __init__(self, event_bus: EventBus, settings_service: SettingsService) -> None:
        self.event_bus = event_bus
        self.settings_service = settings_service
        self.event_bus.subscribe(GameEvent, self.process_event)
        self.reload_service()

    async def process_event(self, event: JournalEvent) -> None:
        if self.settings.event_reactions.reactions.get(event.event, False):
            await self.event_bus.publish(EventReactionEvent(event=event))

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        if not isinstance(new_settings.event_reactions, EventReactionModel):
            return SettingsIssueModel(
                section="event_reactions",
                field="event_reactions",
                message=(
                    "Event reaction settings must be a mapping of event name to bool."
                ),
            )
        return None

    def reload_service(self) -> None:
        self.settings = self.settings_service.get_settings()
