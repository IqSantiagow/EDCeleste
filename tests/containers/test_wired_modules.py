import unittest
from pathlib import Path

from edceleste.containers.main_container import MODULES_USING_PROVIDE

PACKAGE_FOLDER = Path(__file__).parents[2] / "src" / "edceleste"


def module_name_of(python_file: Path) -> str:
    relative_path = python_file.relative_to(PACKAGE_FOLDER.parent).with_suffix("")
    return ".".join(relative_path.parts)


def modules_that_use_provide() -> set[str]:
    return {
        module_name_of(python_file)
        for python_file in PACKAGE_FOLDER.rglob("*.py")
        if "Provide[" in python_file.read_text(encoding="utf-8")
    }


class TestModulesUsingProvide(unittest.TestCase):
    def test_every_module_with_provide_is_wired(self):
        """A module left out of the wiring gets the Provide marker instead of
        the real object, and only crashes once that screen is opened."""
        missing_modules = modules_that_use_provide() - set(MODULES_USING_PROVIDE)

        self.assertEqual(missing_modules, set())

    def test_every_wired_module_still_uses_provide(self):
        stale_modules = set(MODULES_USING_PROVIDE) - modules_that_use_provide()

        self.assertEqual(stale_modules, set())


if __name__ == "__main__":
    unittest.main()
