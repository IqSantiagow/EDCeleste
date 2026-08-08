import unittest

from pydantic import ValidationError

from services.models.settings_model import TTSModel


def _make_tts_model() -> TTSModel:
    return TTSModel(voice="en-GB-SoniaNeural", volume=1.0)


class TestTTSModel(unittest.TestCase):
    def test_assigning_valid_volume_updates_the_field(self):
        tts_model = _make_tts_model()

        tts_model.volume = 0.5

        self.assertEqual(tts_model.volume, 0.5)

    def test_assigning_out_of_range_volume_raises_validation_error(self):
        tts_model = _make_tts_model()

        with self.assertRaises(ValidationError):
            tts_model.volume = 1.5


if __name__ == "__main__":
    unittest.main()
