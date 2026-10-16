import unittest

from edceleste.services.models.reply_texts import REPLY_TEXTS, build_reply_wav_file_name


class TestReplyWavFileName(unittest.TestCase):
    def test_lowercases_and_joins_the_words_with_underscores(self):
        self.assertEqual(
            build_reply_wav_file_name("Landing gear deployed"),
            "landing_gear_deployed.wav",
        )

    def test_drops_punctuation_and_edge_underscores(self):
        self.assertEqual(
            build_reply_wav_file_name("  Hello, Commander! "), "hello_commander.wav"
        )


class TestReplyTexts(unittest.TestCase):
    def test_every_reply_text_has_its_own_file_name(self):
        file_names = [build_reply_wav_file_name(text) for text in REPLY_TEXTS]

        self.assertEqual(len(set(file_names)), len(REPLY_TEXTS))


if __name__ == "__main__":
    unittest.main()
