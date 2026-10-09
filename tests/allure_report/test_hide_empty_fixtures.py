import json
import tempfile
import unittest
from pathlib import Path

from tests.allure_report.hide_empty_fixtures import hide_empty_fixtures

ONE_STEP = [{"name": "A fake keyboard", "status": "passed"}]


class TestHideEmptyFixtures(unittest.TestCase):
    def setUp(self):
        temp_folder = tempfile.TemporaryDirectory()
        self.addCleanup(temp_folder.cleanup)
        self.results_folder = Path(temp_folder.name)
        self.container_file = self.results_folder / "abc-container.json"

    def write_container(self, befores: list[dict], afters: list[dict]) -> None:
        container = {"uuid": "abc", "befores": befores, "afters": afters}
        self.container_file.write_text(json.dumps(container), encoding="utf-8")

    def read_container(self) -> dict:
        return json.loads(self.container_file.read_text(encoding="utf-8"))

    def test_should_hide_a_passed_fixture_without_steps(self):
        self.write_container(
            befores=[{"name": "tmp_path", "status": "passed"}],
            afters=[{"name": "tmp_path::1", "status": "passed"}],
        )

        hide_empty_fixtures(self.results_folder)

        self.assertEqual(self.read_container()["befores"], [])
        self.assertEqual(self.read_container()["afters"], [])

    def test_should_hide_pytest_cleanup_lambdas_without_a_status(self):
        self.write_container(befores=[], afters=[{"name": "monkeypatch::<lambda>"}])

        hide_empty_fixtures(self.results_folder)

        self.assertEqual(self.read_container()["afters"], [])

    def test_should_keep_a_fixture_with_steps(self):
        fixture_with_steps = {
            "name": "EDCeleste faked",
            "status": "passed",
            "steps": ONE_STEP,
        }
        self.write_container(befores=[fixture_with_steps], afters=[])

        hide_empty_fixtures(self.results_folder)

        self.assertEqual(self.read_container()["befores"], [fixture_with_steps])

    def test_should_keep_a_failed_or_broken_fixture_without_steps(self):
        failed_fixture = {"name": "tmp_path", "status": "failed"}
        broken_fixture = {"name": "monkeypatch", "status": "broken"}
        self.write_container(befores=[failed_fixture, broken_fixture], afters=[])

        hide_empty_fixtures(self.results_folder)

        self.assertEqual(
            self.read_container()["befores"], [failed_fixture, broken_fixture]
        )

    def test_should_name_a_kept_teardown_like_its_fixture(self):
        self.write_container(
            befores=[],
            afters=[
                {"name": "EDCeleste faked::1", "status": "passed", "steps": ONE_STEP}
            ],
        )

        hide_empty_fixtures(self.results_folder)

        self.assertEqual(self.read_container()["afters"][0]["name"], "EDCeleste faked")

    def test_should_leave_test_results_untouched(self):
        result_file = self.results_folder / "abc-result.json"
        result_file.write_text('{"name": "a test", "steps": []}', encoding="utf-8")

        hide_empty_fixtures(self.results_folder)

        self.assertEqual(
            result_file.read_text(encoding="utf-8"), '{"name": "a test", "steps": []}'
        )
