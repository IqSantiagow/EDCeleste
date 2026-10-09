import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

from edceleste.services.models.settings_model import (
    LLMModel,
    PathModel,
    SettingsModel,
    SttModel,
    TTSModel,
)
from edceleste.services.settings_service import SettingsService

VALID_CONFIG_YAML = """
paths:
  journal_path: C:/j
  keybindings_path: C:/k
tts:
  provider:
    type: edge
    voice: en-GB-SoniaNeural
  volume: 1.0
llm:
  system_prompt: sp
  user_prompt: up
stt:
  model: tiny.en
"""

CONFIG_YAML_WITHOUT_LLM_AND_STT = """
paths:
  journal_path: C:/j
  keybindings_path: C:/k
tts:
  provider:
    type: edge
    voice: en-GB-SoniaNeural
  volume: 1.0
"""


def _make_settings(system_prompt: str = "sp", journal_path: str = "C:/j"):
    return SettingsModel(
        paths=PathModel(journal_path=journal_path, keybindings_path="C:/k"),
        tts=TTSModel(volume=1.0),
        llm=LLMModel(system_prompt=system_prompt, user_prompt="up"),
        stt=SttModel(model="tiny.en"),
    )


def _read_saved_system_prompt() -> str:
    saved_config = yaml.safe_load(Path("config.yaml").read_text())
    return saved_config["llm"]["system_prompt"]


class SettingsServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # SettingsService reads "config.yaml" from the current folder. Every test
        # runs in its own empty temp folder, so the real config.yaml is never touched.
        temp_folder = tempfile.TemporaryDirectory()
        self.addCleanup(temp_folder.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(temp_folder.name)

    def test_get_settings_raises_before_load(self):
        service = SettingsService()

        with self.assertRaises(RuntimeError):
            service.get_settings()

    def test_load_settings_populates_settings_from_yaml(self):
        Path("config.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService()

        service.load_settings()

        self.assertEqual(service.get_settings().llm.system_prompt, "sp")

    def test_load_settings_creates_config_from_example_and_raises_when_missing(self):
        Path("config-example.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService()

        with self.assertRaises(FileNotFoundError):
            service.load_settings()

        self.assertEqual(Path("config.yaml").read_text(), VALID_CONFIG_YAML)

    @patch("edceleste.services.settings_service.shutil.copyfile")
    def test_load_settings_raises_runtime_error_when_copy_from_example_fails(
        self, mock_copy
    ):
        service = SettingsService()

        with self.assertRaises(RuntimeError):
            service.load_settings()

        mock_copy.assert_called_once_with(
            Path("config-example.yaml"), Path("config.yaml")
        )

    def test_load_settings_raises_runtime_error_on_invalid_yaml_schema(self):
        Path("config.yaml").write_text(CONFIG_YAML_WITHOUT_LLM_AND_STT)
        service = SettingsService()

        with self.assertRaises(RuntimeError):
            service.load_settings()

    def test_save_settings_writes_yaml_when_one_section_changed(self):
        Path("config.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService()
        service.settings = _make_settings(system_prompt="old")
        new_settings = _make_settings(system_prompt="new")

        service.save_settings(new_settings)

        self.assertEqual(_read_saved_system_prompt(), "new")
        self.assertEqual(service.get_settings().llm.system_prompt, "new")

    def test_save_settings_creates_config_yaml_from_example_when_missing(self):
        Path("config-example.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService()
        service.settings = _make_settings(system_prompt="old")
        new_settings = _make_settings(system_prompt="new")

        service.save_settings(new_settings)

        self.assertEqual(_read_saved_system_prompt(), "new")

    # --- custom config path ---

    def test_load_settings_reads_the_given_config_path(self):
        Path("other").mkdir()
        Path("other/my-config.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService(config_path=Path("other/my-config.yaml"))

        service.load_settings()

        self.assertEqual(service.get_settings().paths.journal_path, "C:/j")

    def test_save_settings_writes_only_to_the_given_config_path(self):
        Path("other").mkdir()
        Path("other/my-config.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService(config_path=Path("other/my-config.yaml"))
        service.settings = _make_settings(system_prompt="old")

        service.save_settings(_make_settings(system_prompt="new"))

        saved_config = yaml.safe_load(Path("other/my-config.yaml").read_text())
        self.assertEqual(saved_config["llm"]["system_prompt"], "new")
        self.assertFalse(Path("config.yaml").exists())

    def test_load_settings_copies_the_given_example_when_config_is_missing(self):
        Path("my-example.yaml").write_text(VALID_CONFIG_YAML)
        service = SettingsService(
            config_path=Path("my-config.yaml"),
            example_config_path=Path("my-example.yaml"),
        )

        with self.assertRaises(FileNotFoundError):
            service.load_settings()

        self.assertEqual(Path("my-config.yaml").read_text(), VALID_CONFIG_YAML)

    # --- cold_start ---

    async def test_cold_start_yields_pending_status_first(self):
        service = SettingsService()
        service.load_settings = Mock()

        # ColdStartStatus is mutated in place and re-yielded on completion, so
        # the pending status must be inspected right after this first yield -
        # collecting every yield into a list first would show the mutated,
        # already-completed object instead.
        first_status = await service.cold_start().__anext__()

        self.assertEqual(first_status.service, "settings")
        self.assertTrue(first_status.is_critical)
        self.assertFalse(first_status.completed)
        self.assertIsNone(first_status.message)

    async def test_cold_start_yields_completed_status_when_load_settings_succeeds(self):
        service = SettingsService()
        service.load_settings = Mock()

        statuses = [status async for status in service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertIsNone(last_status.message)

    async def test_cold_start_yields_error_message_when_load_settings_fails(self):
        service = SettingsService()
        service.load_settings = Mock(side_effect=RuntimeError("config.yaml is broken"))

        statuses = [status async for status in service.cold_start()]

        last_status = statuses[-1]
        self.assertTrue(last_status.completed)
        self.assertEqual(last_status.message, "config.yaml is broken")


if __name__ == "__main__":
    unittest.main()
