from typing import AsyncGenerator

from edceleste.services.event_bus import EventBus
from edceleste.services.models.cold_start_status import ColdStartStatus
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
        """Only stores the dependencies and subscribes to the event bus. The
        settings are not read here, reload_service() reads them during
        cold_start() or after the settings change.

        Subscriptions:
        - GameEvent -> publish_reaction_if_enabled
        """
        self.event_bus = event_bus
        self.settings_service = settings_service
        self.event_bus.subscribe(GameEvent, self.publish_reaction_if_enabled)

    async def publish_reaction_if_enabled(self, event: JournalEvent) -> None:
        """Decides if Celeste should answer a game event on her own. When the
        pilot switched this event on in event_reactions, publishes an
        EventReactionEvent, which LLMService turns into an LLM request. Events
        missing from the settings count as switched off.

        Uses the settings read by the last reload_service(). Before the first
        reload_service() self.settings does not exist yet and this raises
        AttributeError, which the event bus logs and swallows.
        """
        if self.settings.event_reactions.reactions.get(event.event, False):
            await self.event_bus.publish(EventReactionEvent(event=event))

    def validate_settings(
        self, new_settings: SettingsModel
    ) -> SettingsIssueModel | None:
        """Only checks that event_reactions is an EventReactionModel. Unknown and
        missing event names are already fixed by the model validator, so they
        are not an issue here. Returns None when the settings are fine."""
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
        """Takes a copy of the current settings from SettingsService. Later
        settings changes are not seen until this runs again."""
        self.settings = self.settings_service.get_settings()

    async def cold_start(self) -> AsyncGenerator[ColdStartStatus, None]:
        """Startup check shown in the system check screen.

        1. Yields a "not completed" status, so the UI shows a spinner.
        2. Reads the settings (reload_service).
        3. Yields the status again with completed=True, and the error text in
           message when reading failed.
        Never raises. Not critical, the app starts even when it fails.
        """
        status = ColdStartStatus(
            service="event_reactions",
            message=None,
            is_critical=False,
            completed=False,
        )
        yield status
        try:
            self.reload_service()
            status.completed = True
            yield status
        except Exception as e:
            status.completed = True
            status.message = str(e)
            yield status
