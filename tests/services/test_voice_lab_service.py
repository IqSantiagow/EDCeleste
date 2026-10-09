import math
import unittest
from unittest.mock import Mock

import numpy as np
from scipy.signal import sosfreqz

from edceleste.services.models.settings_model import VoiceLabModel
from edceleste.services.settings_service import SettingsService
from edceleste.services.voice_lab_service import VoiceLabService

SAMPLE_RATE = 24000


def make_noise(seconds: float = 1.0, loudness: float = 0.1) -> np.ndarray:
    sample_count = int(seconds * SAMPLE_RATE)
    return loudness * np.random.default_rng(7).standard_normal(sample_count)


def high_vs_middle_tones_db(audio: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(audio)) ** 2
    frequencies = np.fft.rfftfreq(len(audio), 1 / SAMPLE_RATE)
    high = spectrum[(frequencies > 9000) & (frequencies < 11500)].mean()
    middle = spectrum[(frequencies > 500) & (frequencies < 2000)].mean()
    return 10 * np.log10(high / middle)


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio**2)))


def apply_effects_with(
    samples: np.ndarray, sample_rate: int, voice_lab: VoiceLabModel
) -> np.ndarray:
    settings_handler = Mock(spec=SettingsService)
    settings_handler.get_settings.return_value.tts.voice_lab = voice_lab
    return VoiceLabService(settings_handler).apply_effects(samples, sample_rate)


def make_service() -> VoiceLabService:
    return VoiceLabService(Mock(spec=SettingsService))


def make_click(seconds: float = 1.0) -> np.ndarray:
    click = np.zeros(int(seconds * SAMPLE_RATE))
    click[0] = 1.0
    return click


def make_tone(hz: float, loudness: float, seconds: float = 1.0) -> np.ndarray:
    times = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return loudness * np.sin(2 * math.pi * hz * times)


def filter_gain_db(sos: np.ndarray, hz: float) -> float:
    _, response = sosfreqz(sos, worN=[hz], fs=SAMPLE_RATE)
    return float(20 * np.log10(abs(response[0])))


class VoiceLabServiceTest(unittest.TestCase):
    def test_returns_the_samples_untouched_when_switched_off(self):
        samples = make_noise()

        result = apply_effects_with(samples, SAMPLE_RATE, VoiceLabModel(enabled=False))

        self.assertIs(result, samples)

    def test_all_sliders_at_zero_keep_the_voice_mono_and_as_long(self):
        samples = make_noise()
        voice_lab = VoiceLabModel(clarity=0, reverb=0, stereo_width=0)

        result = apply_effects_with(samples, SAMPLE_RATE, voice_lab)

        self.assertEqual(result.shape, samples.shape)

    def test_clarity_at_half_boosts_the_high_tones_by_about_15_db(self):
        samples = make_noise()
        dull = apply_effects_with(
            samples, SAMPLE_RATE, VoiceLabModel(clarity=0, reverb=0, stereo_width=0)
        )
        clear = apply_effects_with(
            samples, SAMPLE_RATE, VoiceLabModel(clarity=0.5, reverb=0, stereo_width=0)
        )

        boost_db = high_vs_middle_tones_db(clear) - high_vs_middle_tones_db(dull)

        self.assertGreater(boost_db, 13)
        self.assertLess(boost_db, 16)

    def test_stereo_width_makes_two_different_ears_that_add_up_to_the_mono_voice(self):
        samples = make_noise()
        mono = apply_effects_with(samples, SAMPLE_RATE, VoiceLabModel(stereo_width=0))

        stereo = apply_effects_with(
            samples, SAMPLE_RATE, VoiceLabModel(stereo_width=0.5)
        )

        self.assertEqual(stereo.shape, (len(mono), 2))
        self.assertFalse(np.allclose(stereo[:, 0], stereo[:, 1]))
        np.testing.assert_allclose(stereo.mean(axis=1), mono, atol=1e-6)

    def test_reverb_keeps_ringing_and_fading_after_the_last_word(self):
        samples = make_noise(seconds=1.0)

        result = apply_effects_with(
            samples, SAMPLE_RATE, VoiceLabModel(reverb=0.5, stereo_width=0)
        )

        tail = result[len(samples) :]
        self.assertEqual(len(tail), int(0.6 * SAMPLE_RATE))
        tenth_of_a_second = SAMPLE_RATE // 10
        first_part_of_tail = rms(tail[:tenth_of_a_second])
        last_part_of_tail = rms(tail[-tenth_of_a_second:])
        self.assertGreater(first_part_of_tail, 0)
        self.assertLess(last_part_of_tail, first_part_of_tail / 10)

    def test_never_goes_past_full_scale(self):
        samples = np.clip(make_noise(loudness=1.0), -1, 1)
        voice_lab = VoiceLabModel(clarity=1, reverb=1, stereo_width=1)

        result = apply_effects_with(samples, SAMPLE_RATE, voice_lab)

        self.assertLessEqual(np.abs(result).max(), 1.0)

    def test_a_stereo_input_is_treated_as_one_voice(self):
        samples = make_noise()
        same_in_both_ears = np.stack([samples, samples], axis=1)

        from_stereo = apply_effects_with(
            same_in_both_ears, SAMPLE_RATE, VoiceLabModel()
        )
        from_mono = apply_effects_with(samples, SAMPLE_RATE, VoiceLabModel())

        np.testing.assert_allclose(from_stereo, from_mono)

    def test_works_when_the_sample_rate_is_too_low_for_the_clarity_boost(self):
        low_sample_rate = 8000
        samples = make_noise()[:low_sample_rate]

        result = apply_effects_with(samples, low_sample_rate, VoiceLabModel())

        self.assertTrue(np.isfinite(result).all())

    def test_gives_float32_samples_ready_for_the_speaker(self):
        result = apply_effects_with(make_noise(), SAMPLE_RATE, VoiceLabModel())

        self.assertEqual(result.dtype, np.float32)

    def test_with_every_slider_at_zero_a_quiet_voice_comes_out_2_db_quieter(self):
        # 2 kHz is far above the bass boost, and the voice is too quiet to compress
        samples = make_tone(2000, loudness=0.01)
        voice_lab = VoiceLabModel(clarity=0, reverb=0, stereo_width=0)

        result = apply_effects_with(samples, SAMPLE_RATE, voice_lab)

        change_db = 20 * math.log10(rms(result) / rms(samples))
        self.assertAlmostEqual(change_db, -2.0, delta=0.02)

    def test_the_approved_ship_sound_stays_exactly_the_same(self):
        # Recorded from the sound approved by ear in issue #181 (every slider at 0.5).
        # A change here means Celeste sounds different; re-record only on purpose.
        samples = make_noise(seconds=0.5)

        result = apply_effects_with(samples, SAMPLE_RATE, VoiceLabModel())

        positions = [100, 2000, 6000, 11000, 13000, 20000]
        left_ear = [-0.0667405874, -0.0998590514, -0.1190891266, -0.0391889177]
        left_ear += [-0.0051988419, -0.0002429020]
        right_ear = [0.1954831481, 0.0297166910, 0.0568163246, 0.0053032208]
        right_ear += [0.0013672439, -0.0003222208]
        self.assertEqual(result.shape, (26400, 2))
        np.testing.assert_allclose(result[positions, 0], left_ear, rtol=0, atol=1e-7)
        np.testing.assert_allclose(result[positions, 1], right_ear, rtol=0, atol=1e-7)


class BoostTest(unittest.TestCase):
    def test_skips_a_corner_at_the_highest_tone_the_sample_rate_can_hold(self):
        samples = make_noise()
        highest_tone_hz = SAMPLE_RATE / 2

        result = make_service().boost(
            samples, "treble", highest_tone_hz, 10, SAMPLE_RATE
        )

        self.assertIs(result, samples)

    def test_boosts_a_corner_just_below_the_highest_tone(self):
        samples = make_noise()
        corner_hz = SAMPLE_RATE / 2 * 0.8

        result = make_service().boost(samples, "treble", corner_hz, 10, SAMPLE_RATE)

        self.assertGreater(rms(result), rms(samples))


class ShelfFilterTest(unittest.TestCase):
    # The full boost far from the corner and half of it at the corner come from the
    # Audio EQ Cookbook; the points in between were measured from the approved sound.
    def test_bass_shelf_lifts_low_tones_by_the_gain_and_leaves_high_ones(self):
        bass_shelf = make_service().shelf_filter("bass", 250, 4, SAMPLE_RATE)

        expected_gain_db = {20: 4.0, 125: 3.758, 250: 2.0, 500: 0.241, 8000: 0.0}
        for hz, gain_db in expected_gain_db.items():
            with self.subTest(hz=hz):
                self.assertAlmostEqual(
                    filter_gain_db(bass_shelf, hz), gain_db, delta=0.002
                )

    def test_treble_shelf_lifts_high_tones_by_the_gain_and_leaves_low_ones(self):
        treble_shelf = make_service().shelf_filter("treble", 7100, 15, SAMPLE_RATE)

        expected_gain_db = {1000: 0.002, 3550: 0.44, 7100: 7.5, 9000: 13.219, 11900: 15}
        for hz, gain_db in expected_gain_db.items():
            with self.subTest(hz=hz):
                self.assertAlmostEqual(
                    filter_gain_db(treble_shelf, hz), gain_db, delta=0.002
                )


class CompressTest(unittest.TestCase):
    THRESHOLD = 0.1  # -20 dBFS

    def test_leaves_a_voice_below_the_threshold_untouched(self):
        quiet_voice = np.full(SAMPLE_RATE, 0.05)

        result = make_service().compress(quiet_voice, SAMPLE_RATE)

        np.testing.assert_allclose(result, quiet_voice)

    def test_a_voice_4_times_over_the_threshold_comes_out_only_4_to_the_quarter_over(
        self,
    ):
        loud_voice = np.full(SAMPLE_RATE, 0.4)

        result = make_service().compress(loud_voice, SAMPLE_RATE)

        self.assertAlmostEqual(result[-1], self.THRESHOLD * 4 ** (1 / 4), places=6)

    def test_follows_the_loudness_over_about_20_ms(self):
        loud_voice = np.full(SAMPLE_RATE, 0.4)

        result = make_service().compress(loud_voice, SAMPLE_RATE)

        # after 20 ms the measured power has reached 1 - 1/e of the real one
        measured_level = math.sqrt(0.4**2 * (1 - math.exp(-1)))
        times_over = measured_level / self.THRESHOLD
        expected_sample = 0.4 * times_over ** (1 / 4 - 1)
        twenty_ms = int(0.02 * SAMPLE_RATE)
        self.assertAlmostEqual(result[twenty_ms], expected_sample, delta=0.001)


class AddReverbTest(unittest.TestCase):
    def setUp(self):
        self.click = make_click()
        self.with_reverb = make_service().add_reverb(self.click, 0.6, 0.12, SAMPLE_RATE)
        self.room_echo = self.with_reverb - self.click

    def test_the_echo_is_as_loud_as_the_mix_says(self):
        self.assertAlmostEqual(np.sum(self.room_echo**2), 0.12**2, places=9)

    def test_the_echo_rings_like_noise_not_like_a_smooth_fade(self):
        share_of_positive_samples = np.mean(
            self.room_echo[: int(0.6 * SAMPLE_RATE)] > 0
        )

        self.assertGreater(share_of_positive_samples, 0.45)
        self.assertLess(share_of_positive_samples, 0.55)

    def test_the_echo_fades_by_60_db_over_the_reverb_time(self):
        tenth_of_a_second = SAMPLE_RATE // 10
        first_tenth = rms(self.room_echo[:tenth_of_a_second])
        second_tenth = rms(self.room_echo[tenth_of_a_second : 2 * tenth_of_a_second])

        # -60 dB over 0.6 s is a fade of e^-6.9 over 0.6 s
        expected_fade = math.exp(-6.9 * 0.1 / 0.6)
        self.assertAlmostEqual(second_tenth / first_tenth, expected_fade, delta=0.02)

    def test_the_echo_stops_after_the_reverb_time(self):
        after_reverb = self.room_echo[int(0.6 * SAMPLE_RATE) :]

        self.assertLess(np.abs(after_reverb).max(), 1e-9)


class SpreadToStereoTest(unittest.TestCase):
    def setUp(self):
        self.click = make_click()
        self.stereo = make_service().spread_to_stereo(self.click, 0.47, SAMPLE_RATE)
        self.side = self.stereo[:, 0] - self.click
        self.reflection_positions = np.nonzero(np.abs(self.side) > 1e-9)[0]

    def test_the_right_ear_gets_the_reflections_with_the_opposite_sign(self):
        np.testing.assert_allclose(self.stereo[:, 1], self.click - self.side)

    def test_the_reflections_are_as_loud_as_the_width(self):
        self.assertAlmostEqual(np.sqrt(np.sum(self.side**2)), 0.47, places=9)

    def test_the_reflections_come_from_walls_half_a_ms_to_4_ms_away(self):
        reflection_ms = self.reflection_positions / SAMPLE_RATE * 1000

        self.assertGreaterEqual(reflection_ms.min(), 0.5)
        self.assertLess(reflection_ms.min(), 1.0)
        self.assertLessEqual(reflection_ms.max(), 4.0)

    def test_some_reflections_add_and_some_subtract(self):
        reflections = self.side[self.reflection_positions]

        self.assertTrue((reflections > 0).any())
        self.assertTrue((reflections < 0).any())

    def test_farther_walls_reflect_quieter(self):
        # each reflection is e^(-ms / 2) loud; two walls at almost the same distance
        # with opposite signs nearly cancel out, so only the clear ones are checked
        clear_positions = self.reflection_positions[
            np.abs(self.side[self.reflection_positions]) > 0.01
        ]
        reflection_ms = clear_positions / SAMPLE_RATE * 1000
        loudness_without_fade = np.abs(self.side[clear_positions]) * np.exp(
            reflection_ms / 2
        )

        np.testing.assert_allclose(
            loudness_without_fade, np.median(loudness_without_fade), rtol=0.03
        )


if __name__ == "__main__":
    unittest.main()
