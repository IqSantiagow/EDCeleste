from collections.abc import AsyncIterator
from typing import Any, Callable, Coroutine, Protocol

import asyncio
import numpy as np

# Who is heard first when several speeches wait for the speaker: the smaller
# number goes first. A speech that is playing is never interrupted by this.
PRIORITY_ANSWER = 0  # an answer to the pilot (LLM, fast command, settings screen)
PRIORITY_REACTION = 1  # Celeste reacts to a change in the game


class SpeakerProtocol(Protocol):
    def queue_speech(
        self,
        speak: Callable[[], Coroutine[Any, Any, None]],
        priority: int,
        max_wait_seconds: float | None = None,
    ) -> asyncio.Future:
        """The only way to make Celeste say anything. Puts speak (a coroutine
        function that plays the sound with play_clip() or play_pieces_from()) in
        the speech queue and returns at once. Speeches are played one by one:
        the smallest priority number first (PRIORITY_ANSWER before
        PRIORITY_REACTION), the oldest first among equal ones. A speech that is
        playing is never cut by another one.

        Returns a future that is done when the speech has been played, dropped
        (it waited longer than max_wait_seconds, or stop_speaking() was called)
        or has failed. A caller that does not wait just ignores it. The error
        of speak is in the future and in the log. max_wait_seconds None means
        the speech never expires. Needs a running event loop."""
        ...

    async def play_clip(self, samples: np.ndarray, sample_rate: int) -> None:
        """Plays the whole audio (mono or stereo floats between -1 and 1) on the
        speaker and returns when it has played, or when stop_speaking() cut it.
        Only for code run by queue_speech(). Errors of the sound system are
        raised."""
        ...

    async def play_pieces_from(
        self, pieces: AsyncIterator[np.ndarray], sample_rate: int
    ) -> None:
        """Plays the pieces of audio as they come out of the iterator, so the
        first sound is heard before the rest is made. Returns when the last
        piece has played, or when stop_speaking() cut it (the rest is never
        asked for). Only for code run by queue_speech(). An error of the
        iterator is raised; the speaker is told that nothing more comes, so it
        plays the pieces it already has and stops."""
        ...

    def stop_speaking(self) -> None:
        """Celeste goes silent at once: what she is saying is cut off and
        everything waiting in the speech queue is dropped (the future of every
        dropped speech ends with the result None). Speech queued after the call
        is played normally, when the call was made on the event loop. Can be
        called from any thread, but from another thread the waiting speeches are
        dropped a moment later, on the event loop, so a speech queued in that
        moment is dropped too."""
        ...
