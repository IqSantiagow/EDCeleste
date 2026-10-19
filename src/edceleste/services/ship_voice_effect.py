"""The ship effect: makes Celeste sound like the ship computer of Elite Dangerous.

It is one fixed chain, nothing to set. The owner chose it by ear (round Q of
the listening tests, Pocket TTS next to recordings of the game). The dry voice
goes through:
1. four tone steps: much more bass, less mud, more presence, more air,
2. a chorus that makes two ears out of the one voice: each ear hears the voice
   with three copies of it that wander in time, the wandering of the right ear
   is a quarter of a turn ahead of the left one's (the vibration of the game's
   voice),
3. the room the game adds, a different echo in each ear.

ShipVoiceEffect makes one reply: give it the pieces of the voice in order with
process(), then call finish() for what still rings. Every step keeps its state
between pieces, so the pieces together sound the same as the whole reply made
at once. Make a new ShipVoiceEffect for every reply.
"""

import math

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

# The tone of the voice, in this order: (step, corner or centre in Hz, gain in dB)
TONE_STEPS = [
    ("bass_shelf", 250.0, 20.0),
    ("bell", 350.0, -5.0),
    ("bell", 3000.0, 4.0),
    ("treble_shelf", 6000.0, 3.0),
]
BELL_WIDTH_Q = 1.0
# The chorus: every ear hears the voice mixed with copies of it. Copy number i
# is the voice delayed by CHORUS_DELAY_MS + CHORUS_SWING_MS * sin(2 pi * speed * t
# + its phase), so its delay swings between 18 and 22 ms, CHORUS_SPEED_HZ times
# a second.
CHORUS_DELAY_MS = 20.0
CHORUS_SWING_MS = 2.0
CHORUS_SPEED_HZ = 1.5
CHORUS_SHARE_OF_COPIES = 0.7  # chosen by ear, the first recipe had 0.5
LEFT_EAR_COPY_PHASES = [0.0, 2 * math.pi / 3, 4 * math.pi / 3]
RIGHT_EAR_COPY_PHASES = [phase + math.pi / 2 for phase in LEFT_EAR_COPY_PHASES]
# The room the game puts the voice in, per octave band
GAME_ROOM_BANDS_HZ = [125, 250, 500, 1000, 2000, 4000, 8000]
GAME_ROOM_LEVEL_DB = [-29.51, -15.28, -5.74, -0.87, -0.69, -5.19, -14.38]
GAME_ROOM_DECAY_SECONDS = [1.553, 1.012, 0.736, 0.597, 0.542, 0.549, 0.621]
GAME_ROOM_SECONDS = 0.5
GAME_ROOM_STRENGTH = 0.35
# How long the chain rings after the last word at the most: the room + the chorus
TAIL_SECONDS = 0.6


def build_tone_section(
    step: str, hz: float, gain_db: float, sample_rate: int
) -> np.ndarray:
    """One second order section of the Audio EQ Cookbook (R. Bristow-Johnson),
    as an array of shape (1, 6) for scipy's sosfilt: the three numerator
    numbers, then 1.0, then the two other denominator numbers, all divided by
    the first denominator number. step "bass_shelf" changes everything below hz
    by gain_db, "treble_shelf" everything above hz (both with slope 1), "bell"
    changes the tones around hz by gain_db with the width BELL_WIDTH_Q. gain_db
    above 0 makes the tones louder, below 0 quieter. hz must be under half of
    sample_rate; that is not checked here, ToneFilter leaves such steps out.
    Raises ValueError for another step."""
    a = 10 ** (gain_db / 40)
    angle = 2 * math.pi * hz / sample_rate
    cos = math.cos(angle)
    if step == "bell":
        alpha = math.sin(angle) / (2 * BELL_WIDTH_Q)
        top = [1 + alpha * a, -2 * cos, 1 - alpha * a]
        bottom = [1 + alpha / a, -2 * cos, 1 - alpha / a]
    elif step in ("bass_shelf", "treble_shelf"):
        root = 2 * math.sqrt(a) * (math.sin(angle) / 2 * math.sqrt(2))
        if step == "bass_shelf":
            top = [
                a * ((a + 1) - (a - 1) * cos + root),
                2 * a * ((a - 1) - (a + 1) * cos),
                a * ((a + 1) - (a - 1) * cos - root),
            ]
            bottom = [
                (a + 1) + (a - 1) * cos + root,
                -2 * ((a - 1) + (a + 1) * cos),
                (a + 1) + (a - 1) * cos - root,
            ]
        else:
            top = [
                a * ((a + 1) + (a - 1) * cos + root),
                -2 * a * ((a - 1) + (a + 1) * cos),
                a * ((a + 1) + (a - 1) * cos - root),
            ]
            bottom = [
                (a + 1) - (a - 1) * cos + root,
                2 * ((a - 1) - (a + 1) * cos),
                (a + 1) - (a - 1) * cos - root,
            ]
    else:
        raise ValueError(f"Unknown tone step: {step}")
    return np.array([[value / bottom[0] for value in top + bottom]])


class ToneFilter:
    """The four tone steps of TONE_STEPS in a row, for one mono voice. Keeps the
    memory of the filter between pieces, so the pieces together sound like the
    whole voice."""

    def __init__(self, sample_rate: int) -> None:
        """Builds one section for every step of TONE_STEPS whose corner is under
        half of sample_rate (a step above that cannot be made and is left out),
        and starts with an empty memory. Needs a sample_rate above 500 Hz, the
        lowest corner is 250 Hz, otherwise there is no step left and numpy
        raises ValueError."""
        self.sections = np.concatenate(
            [
                build_tone_section(step, hz, gain_db, sample_rate)
                for step, hz, gain_db in TONE_STEPS
                if hz < sample_rate / 2
            ]
        )
        self.memory = np.zeros((self.sections.shape[0], 2))

    def process(self, audio: np.ndarray) -> np.ndarray:
        """Filters the piece and remembers the state of the filter for the next
        one. audio is mono (a 1-D float array, never an empty one). Out: a new
        float64 array of the same length, the input is not changed."""
        audio, self.memory = sosfilt(self.sections, audio, zi=self.memory)
        return audio


class Chorus:
    """Mono in, mono out. For one ear: the voice mixed with copies of itself,
    one copy for every phase. Copy i is the voice read from its own past with
    the delay CHORUS_DELAY_MS + CHORUS_SWING_MS * sin(angle + phase_i), where
    the angle turns CHORUS_SPEED_HZ times a second (linear interpolation
    between samples). Out = (1 - CHORUS_SHARE_OF_COPIES) * voice +
    CHORUS_SHARE_OF_COPIES * the mean of the copies. The dry part is not
    delayed. Keeps the angle and the end of the voice between pieces."""

    def __init__(self, phases: list[float], sample_rate: int) -> None:
        """phases are the starting angles of the copies, in radians, one number
        per copy. Starts with the angle 0 and a silent past."""
        self.phases = phases
        self.sample_rate = sample_rate
        self.delay_samples = CHORUS_DELAY_MS / 1000 * sample_rate
        self.swing_samples = CHORUS_SWING_MS / 1000 * sample_rate
        self.angle = 0.0
        self.history_length = int(self.delay_samples + self.swing_samples) + 4
        self.history = np.zeros(self.history_length)

    def process(self, audio: np.ndarray) -> np.ndarray:
        """The piece (mono) mixed with its copies, as many samples as in. Reads
        the copies from the earlier pieces too, then keeps the end of the voice
        and the angle for the next piece. An empty piece comes back as it is."""
        if len(audio) == 0:
            return audio
        angles = self.angle + (
            2
            * math.pi
            * CHORUS_SPEED_HZ
            / self.sample_rate
            * np.arange(1, len(audio) + 1)
        )
        self.angle = float(angles[-1] % (2 * math.pi))
        heard = np.concatenate([self.history, audio])
        positions = len(self.history) + np.arange(len(audio))
        copies = np.zeros(len(audio))
        for phase in self.phases:
            delays = self.delay_samples + self.swing_samples * np.sin(angles + phase)
            copies += np.interp(positions - delays, np.arange(len(heard)), heard)
        self.history = heard[-self.history_length :]
        return (
            1 - CHORUS_SHARE_OF_COPIES
        ) * audio + CHORUS_SHARE_OF_COPIES * copies / len(self.phases)


class GameRoom:
    """Stereo in, stereo out. The room the game puts the voice in: each ear has
    its own echo of 0.5 s made of noise in octave bands, each band fading at its
    own pace and as loud as GAME_ROOM_LEVEL_DB says. The echoes are noise from
    fixed seeds, so the room sounds the same every time."""

    def __init__(self, sample_rate: int) -> None:
        """Makes the echo of each ear (number 0 the left ear, number 1 the right
        ear) from noise with fixed seeds (51, 52), each seed given to its own
        numpy generator, so the global random state is not touched. Each echo is
        the sum of octave bands (GAME_ROOM_BANDS_HZ), each band fading at the pace
        of GAME_ROOM_DECAY_SECONDS and scaled so that the mean power of its
        spectrum is GAME_ROOM_LEVEL_DB, then cut after GAME_ROOM_SECONDS with a
        fade of 20 ms and scaled by GAME_ROOM_STRENGTH. A band that does not fit
        in the sample rate is left out (when every band is left out the echoes
        are silent)."""
        length = max(int(GAME_ROOM_SECONDS * sample_rate), 1)
        times = np.arange(length) / sample_rate
        fade_length = min(int(0.02 * sample_rate), length)
        fade = np.ones(length)
        fade[length - fade_length :] = (
            np.cos(np.linspace(0, np.pi / 2, fade_length)) ** 2
        )
        frequencies = np.fft.rfftfreq(length, 1 / sample_rate)
        highest_hz = 0.95 * sample_rate / 2
        self.echoes = []
        for seed in (51, 52):
            noise = np.random.default_rng(seed).standard_normal(length)
            echo = np.zeros(length)
            for centre_hz, level_db, decay_seconds in zip(
                GAME_ROOM_BANDS_HZ, GAME_ROOM_LEVEL_DB, GAME_ROOM_DECAY_SECONDS
            ):
                low_hz = centre_hz / 2**0.5
                high_hz = min(centre_hz * 2**0.5, highest_hz)
                if low_hz >= high_hz:
                    continue  # this band does not fit in this sample rate
                band_filter = butter(
                    4, (low_hz, high_hz), "bandpass", fs=sample_rate, output="sos"
                )
                band = sosfilt(band_filter, noise) * np.exp(
                    -6.9 * times / decay_seconds
                )
                inside = (frequencies >= low_hz) & (frequencies < high_hz)
                band_power = np.mean(np.abs(np.fft.rfft(band)[inside]) ** 2)
                echo += band * np.sqrt(10 ** (level_db / 10) / band_power)
            self.echoes.append(GAME_ROOM_STRENGTH * echo * fade)
        self.still_ringing = [np.zeros(0), np.zeros(0)]

    def voice_of_one_ear_through_its_echo(
        self, ear: int, voice: np.ndarray
    ) -> np.ndarray:
        """Only the ringing, without the dry voice: the voice of one ear (mono)
        through the echo of that ear (ear 0 the left, 1 the right). Out: exactly
        as many samples as in, made of the ringing of this piece plus what the
        echo still rings from the earlier pieces. The ringing that goes beyond
        the end of this piece is not in the output, it is kept for the next
        piece. ear must be 0 or 1: another number raises IndexError, except -1
        and -2, which Python counts from the end and which do not raise, so do
        not pass them."""
        ringing = fftconvolve(voice, self.echoes[ear])
        ringing[: len(self.still_ringing[ear])] += self.still_ringing[ear]
        self.still_ringing[ear] = ringing[len(voice) :]
        return ringing[: len(voice)]

    def process(self, audio: np.ndarray) -> np.ndarray:
        """The stereo piece (samples x 2, float, never an empty one) with the room
        added, as a new float64 array with as many rows as in: each ear is its
        own voice plus the ringing of its own echo. The ringing that goes beyond
        the end of the piece (up to GAME_ROOM_SECONDS after the last word) is not
        in the output: it is kept and added to the pieces that follow. After the
        last piece the ShipVoiceEffect feeds the room with silence in finish()
        to get it out."""
        return np.stack(
            [
                audio[:, 0] + self.voice_of_one_ear_through_its_echo(0, audio[:, 0]),
                audio[:, 1] + self.voice_of_one_ear_through_its_echo(1, audio[:, 1]),
            ],
            axis=1,
        )


class ShipVoiceEffect:
    """The effect of one reply. See the module description."""

    def __init__(self, sample_rate: int) -> None:
        """Builds every step for this sample rate, in the order of the chain: the
        tone filter (mono), the chorus of the left ear and the chorus of the
        right ear (both read the same mono voice), and the game room (stereo).
        Makes the noise of the room, which takes a moment, and processes
        nothing yet. The object is for one reply."""
        self.sample_rate = sample_rate
        self.tone = ToneFilter(sample_rate)
        self.left_ear_chorus = Chorus(LEFT_EAR_COPY_PHASES, sample_rate)
        self.right_ear_chorus = Chorus(RIGHT_EAR_COPY_PHASES, sample_rate)
        self.room = GameRoom(sample_rate)

    def process(self, audio: np.ndarray) -> np.ndarray:
        """The next piece of the voice in, the same piece with the effect out.
        Pieces must come in order, from one thread at a time, and not after
        finish().

        audio is mono (samples) or a 2-D array (samples x columns, normally 2,
        mixed down to mono by the mean of its columns first), any float type, at
        the sample rate of the constructor (not checked). Out: stereo
        (samples x 2) float32 with as many rows as audio has samples, clipped to
        -1..1. The bass comes out much louder (up to 20 dB), the middle tones of
        speech 3 to 5 dB quieter (the chorus shares half of the voice with its
        copies), and the peaks of speech come out as high as they went in or up
        to 3.5 dB lower (measured on the research recordings, so a voice that
        goes in near full scale can be clipped). An empty piece gives an empty
        stereo array of shape (0, 2). The sound of the last words keeps
        ringing: it is not in this piece, finish() gives it."""
        voice = audio.mean(axis=1) if audio.ndim == 2 else audio
        voice = voice.astype(np.float64)
        if len(voice) == 0:
            return np.zeros((0, 2), dtype=np.float32)
        voice = self.tone.process(voice)
        ears = np.column_stack(
            [self.left_ear_chorus.process(voice), self.right_ear_chorus.process(voice)]
        )
        return np.clip(self.room.process(ears), -1.0, 1.0).astype(np.float32)

    def finish(self) -> np.ndarray:
        """What still rings after the last piece: always TAIL_SECONDS of silence
        put through the whole chain (the room ringing, the chorus delay), as
        stereo float32 like process() gives, so it is never empty. The end of it
        is near silent but not exact zeros. Call it once, after the last piece:
        the chain goes on from its state, so a second call would give the quiet
        rest of the first and then silence."""
        silence = np.zeros(int(TAIL_SECONDS * self.sample_rate))
        return self.process(silence)
