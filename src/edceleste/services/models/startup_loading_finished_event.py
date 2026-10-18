from pydantic import BaseModel


class StartupLoadingFinishedEvent(BaseModel):
    """
    Published once by the game watcher, after it has read everything the game
    had already written when the app started (journal, Status.json,
    Market.json). From then on the game files are followed live.
    """
