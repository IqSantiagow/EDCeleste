"""Voice Lab: effects that make Celeste sound like she speaks inside the ship.

The numbers were fitted to the voice clip Celeste is cloned from (issue #181).
With every slider at 0.5 the cloned voice has the same brightness, reverb,
loudness spread and stereo width as that clip.
"""

import math

import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, sosfilt

from edceleste.services.settings_service import SettingsService

BASS_BOOST_DB = 4.0
BASS_BELOW_HZ = 250.0
MAX_TREBLE_BOOST_DB = 30.0
TREBLE_ABOVE_HZ = 7100.0
COMPRESSOR_THRESHOLD_DB = -20.0
COMPRESSOR_RATIO = 4.0
SHORTEST_REVERB_SECONDS = 0.3
EXTRA_REVERB_SECONDS = 0.6
MAX_REVERB_MIX = 0.24
MAX_STEREO_WIDTH = 0.94
# the boosts make the voice louder; this keeps the loudness the same as without effects
VOLUME_CORRECTION_DB = -2.0


class VoiceLabService:
    def __init__(self, settings_service: SettingsService) -> None:
        """Keeps no settings of its own. apply_effects() reads them on every
        call, so a slider change is heard on the next sentence without a
        reload."""
        self.__settings_service = settings_service

    def apply_effects(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """Mono or stereo samples in. Out: mono, or stereo (samples x 2) when stereo
        width is above 0, longer by the time the reverb rings after the last word.

        Voice Lab switched off -> the very same samples come back untouched.
        Otherwise, in this order:
        1. mixes stereo down to mono,
        2. with reverb above 0, adds silence at the end, so the reverb has time
           to ring out,
        3. boosts the bass, then the treble (as much as clarity says),
        4. compresses the loud parts,
        5. adds reverb and spreads to stereo, each only when its slider is
           above 0,
        6. turns the volume down by VOLUME_CORRECTION_DB and clips to -1..1 as
           float32.
        Called by the TTS service right before the audio is played.
        """
        voice_lab = self.__settings_service.get_settings().tts.voice_lab
        if not voice_lab.enabled:
            return samples

        voice = samples.mean(axis=1) if samples.ndim == 2 else samples
        voice = voice.astype(np.float64)
        reverb_seconds = (
            SHORTEST_REVERB_SECONDS + EXTRA_REVERB_SECONDS * voice_lab.reverb
        )
        if voice_lab.reverb > 0:
            silence_for_reverb = np.zeros(int(reverb_seconds * sample_rate))
            voice = np.concatenate([voice, silence_for_reverb])

        voice = self.boost(voice, "bass", BASS_BELOW_HZ, BASS_BOOST_DB, sample_rate)
        voice = self.boost(
            voice,
            "treble",
            TREBLE_ABOVE_HZ,
            MAX_TREBLE_BOOST_DB * voice_lab.clarity,
            sample_rate,
        )
        voice = self.compress(voice, sample_rate)
        if voice_lab.reverb > 0:
            voice = self.add_reverb(
                voice, reverb_seconds, MAX_REVERB_MIX * voice_lab.reverb, sample_rate
            )
        if voice_lab.stereo_width > 0:
            voice = self.spread_to_stereo(
                voice, MAX_STEREO_WIDTH * voice_lab.stereo_width, sample_rate
            )

        voice = voice * 10 ** (VOLUME_CORRECTION_DB / 20)
        return np.clip(voice, -1.0, 1.0).astype(np.float32)

    def boost(
        self, voice: np.ndarray, kind: str, hz: float, gain_db: float, sample_rate: int
    ) -> np.ndarray:
        """Makes everything below ("bass") or above ("treble") `hz` louder
        by `gain_db`. When `hz` is too high for the sample rate the voice comes
        back unchanged."""
        if hz >= sample_rate / 2:
            return voice  # no such tone at this sample rate
        return sosfilt(self.shelf_filter(kind, hz, gain_db, sample_rate), voice)

    def shelf_filter(
        self, kind: str, hz: float, gain_db: float, sample_rate: int
    ) -> np.ndarray:
        """Shelf from the Audio EQ Cookbook (R. Bristow-Johnson), slope 1, as "sos".
        "treble" gives a high shelf, any other kind gives a low (bass) shelf."""
        a = 10 ** (gain_db / 40)
        angle = 2 * math.pi * hz / sample_rate
        cos = math.cos(angle)
        root = 2 * math.sqrt(a) * math.sin(angle) / 2 * math.sqrt(2)
        if kind == "treble":
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
        return np.array([[value / bottom[0] for value in top + bottom]])

    def compress(self, voice: np.ndarray, sample_rate: int) -> np.ndarray:
        """Evens out loud and quiet words: above the threshold the level grows
        COMPRESSOR_RATIO times slower."""
        smoothing = math.exp(-1 / (0.02 * sample_rate))  # follows the level ~20 ms
        power = lfilter([1 - smoothing], [1, -smoothing], voice**2)
        level = np.sqrt(np.maximum(power, 1e-12))
        times_over_threshold = np.maximum(
            level / 10 ** (COMPRESSOR_THRESHOLD_DB / 20), 1
        )
        return voice * times_over_threshold ** (1 / COMPRESSOR_RATIO - 1)

    def add_reverb(
        self, voice: np.ndarray, seconds: float, mix: float, sample_rate: int
    ) -> np.ndarray:
        """The voice ringing in a small metal room: convolved with noise that fades
        by 60 dB over `seconds`; the walls swallow only the very highs.
        The noise has a fixed seed, so the room sounds the same every time.
        The output keeps the input length, the tail is cut off."""
        times = np.arange(int(seconds * sample_rate)) / sample_rate
        room_echo = np.random.default_rng(0).standard_normal(len(times))
        room_echo *= np.exp(-6.9 * times / seconds)
        walls_swallow_above_hz = min(8000, sample_rate / 2 * 0.9)
        walls = butter(
            1, walls_swallow_above_hz, "lowpass", fs=sample_rate, output="sos"
        )
        room_echo = sosfilt(walls, room_echo)
        room_echo /= np.sqrt(np.sum(room_echo**2))
        return voice + mix * fftconvolve(voice, room_echo)[: len(voice)]

    def spread_to_stereo(
        self, voice: np.ndarray, width: float, sample_rate: int
    ) -> np.ndarray:
        """A few very short reflections (0.5-4 ms, like cabin walls next to the head)
        are added to the left ear and subtracted from the right one. Each ear sounds
        a bit different, so the voice is wide, and left + right is still the plain
        voice: a mono speaker does not sound hollow. The reflections come from a
        fixed seed, so the cabin is the same every time."""
        random = np.random.default_rng(1)
        reflections = np.zeros(round(0.004 * sample_rate) + 1)
        for delay_ms in random.uniform(0.5, 4.0, 12):
            sign = random.choice([-1, 1])
            delay_samples = round(delay_ms / 1000 * sample_rate)
            reflections[delay_samples] += sign * math.exp(-delay_ms / 2)
        reflections *= width / np.sqrt(np.sum(reflections**2))
        side = fftconvolve(voice, reflections)[: len(voice)]
        return np.stack([voice + side, voice - side], axis=1)
