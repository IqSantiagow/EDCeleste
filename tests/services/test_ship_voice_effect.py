import unittest
from unittest import mock

import numpy as np

from edceleste.services import ship_voice_effect
from edceleste.services.ship_voice_effect import (
    DISTORTION_LOUDNESS_FIX,
    GAME_ROOM_SECONDS,
    GRAIN_DELAY_MS,
    GRAIN_RATE_HZ,
    GRAIN_SHARE_OF_GRAINS,
    GRAIN_SPRAY_MS,
    OUTPUT_GAIN,
    TAIL_SECONDS,
    GameRoom,
    GrainDelay,
    SeededRandom,
    ShipVoiceEffect,
    distort,
)

SAMPLE_RATE = 24000


def make_speech_like_noise(seconds: float, seed: int = 1, level: float = 0.1):
    """Noise that is as loud as speech and has the whole band, float32 mono."""
    count = int(seconds * SAMPLE_RATE)
    noise = np.random.default_rng(seed).standard_normal(count) * level
    return noise.astype(np.float32)


def make_stereo_noise(seconds: float, seed: int = 5) -> np.ndarray:
    mono = make_speech_like_noise(seconds, seed).astype(np.float64)
    return np.stack([mono, mono], axis=1)


def play_in_pieces(effect: ShipVoiceEffect, voice: np.ndarray, piece_length: int):
    pieces = [
        effect.process(voice[start : start + piece_length])
        for start in range(0, len(voice), piece_length)
    ]
    return np.concatenate(pieces)


class TestShipVoiceEffect(unittest.TestCase):
    def test_pieces_together_sound_the_same_as_the_whole_voice(self):
        voice = make_speech_like_noise(1.0)
        whole = ShipVoiceEffect(SAMPLE_RATE).process(voice)

        for piece_seconds in (0.2, 0.48):
            with self.subTest(piece_seconds=piece_seconds):
                in_pieces = play_in_pieces(
                    ShipVoiceEffect(SAMPLE_RATE),
                    voice,
                    int(piece_seconds * SAMPLE_RATE),
                )

                np.testing.assert_allclose(in_pieces, whole, atol=1e-5)

    def test_the_tail_after_pieces_is_the_same_as_the_tail_after_the_whole_voice(
        self,
    ):
        voice = make_speech_like_noise(0.6)
        whole_effect = ShipVoiceEffect(SAMPLE_RATE)
        whole_effect.process(voice)
        piece_effect = ShipVoiceEffect(SAMPLE_RATE)
        play_in_pieces(piece_effect, voice, int(0.2 * SAMPLE_RATE))

        np.testing.assert_allclose(
            piece_effect.finish(), whole_effect.finish(), atol=1e-5
        )

    def test_output_is_stereo_float32_of_the_same_length_as_the_piece(self):
        voice = make_speech_like_noise(0.3)

        result = ShipVoiceEffect(SAMPLE_RATE).process(voice)

        self.assertEqual(result.shape, (len(voice), 2))
        self.assertEqual(result.dtype, np.float32)

    def test_an_empty_piece_gives_an_empty_stereo_piece(self):
        result = ShipVoiceEffect(SAMPLE_RATE).process(np.zeros(0, dtype=np.float32))

        self.assertEqual(result.shape, (0, 2))
        self.assertEqual(result.dtype, np.float32)

    def test_a_stereo_input_is_mixed_down_to_mono_first(self):
        left = make_speech_like_noise(0.3, seed=1)
        right = make_speech_like_noise(0.3, seed=2)

        from_stereo = ShipVoiceEffect(SAMPLE_RATE).process(
            np.stack([left, right], axis=1)
        )
        from_the_mean = ShipVoiceEffect(SAMPLE_RATE).process((left + right) / 2)

        np.testing.assert_allclose(from_stereo, from_the_mean, atol=1e-6)

    def test_a_float64_piece_gives_the_same_as_the_same_piece_in_float32(self):
        voice = make_speech_like_noise(0.3)

        from_float32 = ShipVoiceEffect(SAMPLE_RATE).process(voice)
        from_float64 = ShipVoiceEffect(SAMPLE_RATE).process(voice.astype(np.float64))

        np.testing.assert_allclose(from_float64, from_float32, atol=1e-6)

    def test_finish_gives_a_tail_that_dies_away(self):
        effect = ShipVoiceEffect(SAMPLE_RATE)
        effect.process(make_speech_like_noise(0.5))

        tail = effect.finish()

        self.assertEqual(tail.shape, (int(TAIL_SECONDS * SAMPLE_RATE), 2))
        first_part = np.sqrt(np.mean(tail[: SAMPLE_RATE // 10] ** 2))
        last_part = np.sqrt(np.mean(tail[-SAMPLE_RATE // 10 :] ** 2))
        self.assertGreater(first_part, 0)
        self.assertLess(last_part, first_part / 100)

    def test_finish_is_silent_when_no_voice_was_given(self):
        tail = ShipVoiceEffect(SAMPLE_RATE).finish()

        self.assertEqual(tail.shape, (int(TAIL_SECONDS * SAMPLE_RATE), 2))
        self.assertEqual(float(np.abs(tail).max()), 0.0)

    def test_a_new_effect_does_not_hear_the_voice_of_an_earlier_one(self):
        first_effect = ShipVoiceEffect(SAMPLE_RATE)
        first_effect.process(make_speech_like_noise(0.5))
        second_effect = ShipVoiceEffect(SAMPLE_RATE)

        self.assertEqual(float(np.abs(second_effect.finish()).max()), 0.0)

    def test_the_same_input_always_gives_the_same_output(self):
        voice = make_speech_like_noise(0.5)

        first = ShipVoiceEffect(SAMPLE_RATE).process(voice)
        second = ShipVoiceEffect(SAMPLE_RATE).process(voice)

        np.testing.assert_array_equal(first, second)

    def test_the_output_stays_between_minus_one_and_one(self):
        loud_voice = np.sign(make_speech_like_noise(0.3)) * np.float32(1.0)

        result = ShipVoiceEffect(SAMPLE_RATE).process(loud_voice)

        self.assertLessEqual(float(np.abs(result).max()), 1.0)
        self.assertEqual(float(np.abs(result).max()), 1.0)

    def test_the_two_ears_are_not_identical(self):
        # With four copies in the chorus and a right ear a quarter of a turn
        # ahead, both ears hear the same copies: only the room tells them apart.
        result = ShipVoiceEffect(SAMPLE_RATE).process(make_speech_like_noise(1.0))

        difference = np.abs(result[:, 0] - result[:, 1]).max()

        self.assertGreater(float(difference), 1e-3)

    def test_the_clean_voice_is_mixed_in_without_the_effect_or_the_room(self):
        voice = make_speech_like_noise(0.5)

        with mock.patch.object(ship_voice_effect, "EFFECT_SHARE_OF_VOICE", 0.0):
            result = ShipVoiceEffect(SAMPLE_RATE).process(voice)

        expected = OUTPUT_GAIN * voice
        np.testing.assert_allclose(result[:, 0], expected, atol=1e-6)
        np.testing.assert_allclose(result[:, 1], expected, atol=1e-6)

    def test_the_voice_with_the_effect_goes_through_the_room_and_the_clean_one_does_not(
        self,
    ):
        voice = make_speech_like_noise(0.5)

        with mock.patch.object(ship_voice_effect, "EFFECT_SHARE_OF_VOICE", 1.0):
            effect = ShipVoiceEffect(SAMPLE_RATE)
            effect.process(voice)
            tail_of_the_effect_only = effect.finish()
        with mock.patch.object(ship_voice_effect, "EFFECT_SHARE_OF_VOICE", 0.0):
            effect = ShipVoiceEffect(SAMPLE_RATE)
            effect.process(voice)
            tail_of_the_clean_voice_only = effect.finish()

        self.assertGreater(float(np.abs(tail_of_the_effect_only).max()), 0.0)
        self.assertEqual(float(np.abs(tail_of_the_clean_voice_only).max()), 0.0)

    def test_speech_comes_out_about_as_loud_as_it_went_in(self):
        voice = make_speech_like_noise(2.0, level=0.15)

        result = ShipVoiceEffect(SAMPLE_RATE).process(voice)

        voice_rms = np.sqrt(np.mean(voice[SAMPLE_RATE:] ** 2))
        result_rms = np.sqrt(np.mean(result[SAMPLE_RATE:] ** 2))
        self.assertGreater(result_rms, voice_rms * 0.7)
        self.assertLess(result_rms, voice_rms * 1.3)

    def test_every_sample_rate_of_the_providers_works(self):
        for sample_rate in (16000, 22050, 24000, 44100, 48000):
            with self.subTest(sample_rate=sample_rate):
                voice = (
                    np.random.default_rng(3).standard_normal(sample_rate // 4) * 0.1
                ).astype(np.float32)
                effect = ShipVoiceEffect(sample_rate)

                result = effect.process(voice)
                tail = effect.finish()

                self.assertEqual(result.shape, (len(voice), 2))
                self.assertTrue(np.isfinite(result).all())
                self.assertTrue(np.isfinite(tail).all())
                self.assertEqual(len(tail), int(TAIL_SECONDS * sample_rate))


class TestDistort(unittest.TestCase):
    def test_silence_stays_silence(self):
        result = distort(np.zeros(100))

        self.assertEqual(float(np.abs(result).max()), 0.0)

    def test_a_very_loud_voice_never_gets_above_the_loudness_fix(self):
        loud = np.array([-50.0, -1.0, 1.0, 50.0])

        result = distort(loud)

        self.assertLessEqual(float(np.abs(result).max()), DISTORTION_LOUDNESS_FIX)
        np.testing.assert_allclose(
            result, DISTORTION_LOUDNESS_FIX * np.sign(loud), atol=1e-2
        )

    def test_a_very_quiet_voice_is_made_louder_in_a_straight_line(self):
        quiet = np.array([-1e-4, 1e-4])

        result = distort(quiet)

        self.assertGreater(float(result[1] / quiet[1]), 1.0)
        self.assertAlmostEqual(float(result[0]), -float(result[1]), places=12)

    def test_it_does_not_change_the_input(self):
        voice = make_speech_like_noise(0.1).astype(np.float64)
        copy = voice.copy()

        distort(voice)

        np.testing.assert_array_equal(voice, copy)


class TestSeededRandom(unittest.TestCase):
    def test_gives_the_numbers_of_the_voice_laboratory(self):
        # Taken from the uniformGenerator of the laboratory (dsp.js), seed 7.
        random = SeededRandom(7)

        numbers = [random.next_fraction() for _ in range(5)]

        np.testing.assert_allclose(
            numbers,
            [0.011704753383131523, 0.061958257792992924, 0.9769076327847066,
             0.6990287057824832, 0.5214452686436434],
            atol=1e-15,
        )  # fmt: skip

    def test_the_same_seed_gives_the_same_numbers_and_another_seed_others(self):
        first = [SeededRandom(51).next_fraction() for _ in range(3)]
        again = [SeededRandom(51).next_fraction() for _ in range(3)]
        other = [SeededRandom(52).next_fraction() for _ in range(3)]

        self.assertEqual(first, again)
        self.assertNotEqual(first, other)

    def test_numbers_stay_above_zero_and_below_one(self):
        random = SeededRandom(1)

        numbers = [random.next_fraction() for _ in range(10000)]

        self.assertGreater(min(numbers), 0.0)
        self.assertLess(max(numbers), 1.0)


class TestGrainDelay(unittest.TestCase):
    def test_an_impulse_is_heard_at_once_and_again_after_the_delay_of_the_grains(self):
        impulse = np.zeros(3000)
        impulse[0] = 1.0

        result = GrainDelay(SAMPLE_RATE).process(impulse)

        # Taken from grainDelay of the laboratory (dsp.js), seed 7.
        self.assertAlmostEqual(float(result[0]), 1 - GRAIN_SHARE_OF_GRAINS, places=9)
        self.assertAlmostEqual(float(result[518]), 0.0668060, places=6)
        self.assertAlmostEqual(float(result[900]), 0.0834447, places=6)
        first_echo = int(GRAIN_DELAY_MS / 1000 * SAMPLE_RATE)
        self.assertEqual(float(np.abs(result[1:first_echo]).max()), 0.0)
        last_echo = int((GRAIN_DELAY_MS + GRAIN_SPRAY_MS) / 1000 * SAMPLE_RATE)
        self.assertGreater(float(np.abs(result[first_echo:last_echo]).max()), 0.0)

    def test_pieces_together_sound_the_same_as_the_whole_voice(self):
        voice = make_speech_like_noise(1.0).astype(np.float64)
        whole = GrainDelay(SAMPLE_RATE).process(voice)

        for piece_length in (700, 3333, 4800):
            with self.subTest(piece_length=piece_length):
                grains = GrainDelay(SAMPLE_RATE)
                in_pieces = np.concatenate(
                    [
                        grains.process(voice[start : start + piece_length])
                        for start in range(0, len(voice), piece_length)
                    ]
                )

                np.testing.assert_allclose(in_pieces, whole, atol=1e-12)

    def test_it_gives_as_many_samples_as_it_gets(self):
        voice = make_speech_like_noise(0.37).astype(np.float64)

        result = GrainDelay(SAMPLE_RATE).process(voice)

        self.assertEqual(result.shape, voice.shape)
        self.assertTrue(np.isfinite(result).all())

    def test_an_empty_piece_comes_back_empty(self):
        result = GrainDelay(SAMPLE_RATE).process(np.zeros(0))

        self.assertEqual(len(result), 0)

    def test_silence_stays_silence(self):
        result = GrainDelay(SAMPLE_RATE).process(np.zeros(5000))

        self.assertEqual(float(np.abs(result).max()), 0.0)

    def test_the_feedback_plays_the_grains_again(self):
        impulse = np.zeros(6000)
        impulse[0] = 1.0
        after_the_longest_delay = int(
            (GRAIN_DELAY_MS + GRAIN_SPRAY_MS) / 1000 * SAMPLE_RATE
        ) + int(SAMPLE_RATE / GRAIN_RATE_HZ)

        with_feedback = GrainDelay(SAMPLE_RATE).process(impulse)
        with mock.patch.object(ship_voice_effect, "GRAIN_FEEDBACK", 0.0):
            without_feedback = GrainDelay(SAMPLE_RATE).process(impulse)

        # The second round of grains reads what the first round played. The first
        # round is over after the longest delay and one grain, the second is not.
        self.assertEqual(
            float(np.abs(without_feedback[after_the_longest_delay:]).max()), 0.0
        )
        self.assertGreater(
            float(np.abs(with_feedback[after_the_longest_delay:]).max()), 0.0
        )

    def test_every_sample_rate_of_the_providers_works(self):
        for sample_rate in (16000, 22050, 24000, 44100, 48000):
            with self.subTest(sample_rate=sample_rate):
                voice = np.random.default_rng(3).standard_normal(sample_rate // 2)

                result = GrainDelay(sample_rate).process(voice)

                self.assertEqual(result.shape, voice.shape)
                self.assertTrue(np.isfinite(result).all())


class TestGameRoom(unittest.TestCase):
    def test_the_game_room_rings_and_stops_at_half_a_second(self):
        room = GameRoom(SAMPLE_RATE)
        impulse = np.zeros((SAMPLE_RATE * 2, 2))
        impulse[0] = 1.0

        result = room.process(impulse)

        room_end = int(GAME_ROOM_SECONDS * SAMPLE_RATE)
        self.assertGreater(float(np.abs(result[100 : room_end - 480, 0]).max()), 0.0)
        self.assertLess(float(np.abs(result[room_end:, 0]).max()), 1e-12)

    def test_the_game_room_keeps_the_ringing_between_pieces(self):
        voice = make_stereo_noise(0.6)
        whole = GameRoom(SAMPLE_RATE).process(voice)

        room = GameRoom(SAMPLE_RATE)
        in_pieces = np.concatenate(
            [
                room.process(voice[start : start + 4800])
                for start in range(0, len(voice), 4800)
            ]
        )

        np.testing.assert_allclose(in_pieces, whole, atol=1e-9)

    def test_the_game_room_gives_every_ear_its_own_echo(self):
        room = GameRoom(SAMPLE_RATE)
        impulse = np.zeros((SAMPLE_RATE, 2))
        impulse[0] = 1.0

        result = room.process(impulse)

        self.assertGreater(float(np.abs(result[100:, 0] - result[100:, 1]).max()), 0.0)


if __name__ == "__main__":
    unittest.main()
