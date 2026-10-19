import unittest

import numpy as np

from edceleste.services.ship_voice_effect import (
    GAME_ROOM_SECONDS,
    TAIL_SECONDS,
    GameRoom,
    ShipVoiceEffect,
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
        result = ShipVoiceEffect(SAMPLE_RATE).process(make_speech_like_noise(1.0))

        correlation = np.corrcoef(result[:, 0], result[:, 1])[0, 1]

        self.assertLess(correlation, 0.95)

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
