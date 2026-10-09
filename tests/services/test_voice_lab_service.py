import unittest
from unittest.mock import Mock

import numpy as np

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


if __name__ == "__main__":
    unittest.main()
