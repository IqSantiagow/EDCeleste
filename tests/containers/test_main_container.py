import os
import tempfile
import unittest
from pathlib import Path

import yaml
from dependency_injector import providers

from edceleste.containers.main_container import Container
from edceleste.services.settings_service import SettingsService

CONFIG_EXAMPLE_FILE = Path(__file__).parents[2] / "config-example.yaml"


def write_config_yaml(folder: Path, journal_path: str, keybindings_path: str) -> Path:
    """Writes folder/config.yaml: a copy of config-example.yaml with only the two
    paths replaced, so the settings are valid and point where the test wants.
    Gives back the path of the new file."""
    config = yaml.safe_load(CONFIG_EXAMPLE_FILE.read_text(encoding="utf-8"))
    config["paths"]["journal_path"] = journal_path
    config["paths"]["keybindings_path"] = keybindings_path

    config_file = folder / "config.yaml"
    config_file.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_file


class TestMainContainer(unittest.TestCase):
    def setUp(self) -> None:
        """Gives every test its own empty temp folder, removed after the test,
        so the real config.yaml of the project is never touched."""
        temp_folder = tempfile.TemporaryDirectory()
        self.addCleanup(temp_folder.cleanup)
        self.temp_folder = Path(temp_folder.name)

    def go_to_temp_folder(self) -> None:
        """Makes the temp folder the current folder, because the container reads
        config.yaml from the current folder. The old folder comes back after the
        test, and before the temp folder is removed (cleanups run last in, first
        out)."""
        old_folder = os.getcwd()
        os.chdir(self.temp_folder)
        self.addCleanup(os.chdir, old_folder)

    def test_every_provider_of_the_container_can_be_built(self):
        """A wrong keyword or a missing dependency in one provider crashes only
        when something asks for that provider, maybe long after the change.
        Building all of them here shows it at once, with the name of every
        broken provider."""
        journal_folder = self.temp_folder / "journal"
        keybindings_folder = self.temp_folder / "bindings"
        journal_folder.mkdir()
        keybindings_folder.mkdir()
        config_file = write_config_yaml(
            self.temp_folder, str(journal_folder), str(keybindings_folder)
        )
        settings_service = SettingsService(config_path=config_file)
        settings_service.load_settings()
        container = Container()
        container.settings_service.override(providers.Object(settings_service))
        provider_names = [
            name
            for name, provider in Container.providers.items()
            if not isinstance(provider, providers.Configuration)
        ]

        built_provider_names = []
        errors_by_provider_name = {}
        for provider_name in provider_names:
            try:
                getattr(container, provider_name)()
                built_provider_names.append(provider_name)
            except Exception as error:
                errors_by_provider_name[provider_name] = (
                    f"{type(error).__name__}: {error}"
                )

        self.assertEqual(errors_by_provider_name, {})
        self.assertEqual(built_provider_names, provider_names)
        # The biggest provider, it pulls in most of the use cases. Proves the
        # loop above really built something.
        self.assertIn("settings_repository", built_provider_names)

    def test_settings_service_is_loaded_from_config_yaml_in_the_current_folder(self):
        """The first call for settings_service must already give the settings
        from the file, because journal_path and keybindings_path are read from
        them while other providers are built."""
        journal_path_from_the_file = "C:/journal-from-the-temp-config-yaml"
        write_config_yaml(self.temp_folder, journal_path_from_the_file, "C:/binds")
        self.go_to_temp_folder()

        settings_service = Container().settings_service()

        self.assertEqual(
            settings_service.get_settings().paths.journal_path,
            journal_path_from_the_file,
        )

    def test_container_does_not_start_when_config_yaml_is_missing(self):
        """A pilot without config.yaml gets the file made from the example and
        the message to edit it. The container must pass that error on, so the
        app stops instead of starting with example settings."""
        (self.temp_folder / "config-example.yaml").write_text(
            CONFIG_EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        self.go_to_temp_folder()

        # The text is the one of SettingsService.load_settings. Without it, a
        # missing config-example.yaml would raise FileNotFoundError too and the
        # test would pass for the wrong reason.
        with self.assertRaisesRegex(FileNotFoundError, "No config.yaml file found"):
            Container().settings_service()


if __name__ == "__main__":
    unittest.main()
