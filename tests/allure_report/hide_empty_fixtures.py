"""Hides the pytest fixtures that say nothing from the Allure results.

allure-pytest lists every fixture a test uses in "Set up" and "Tear down":
tmp_path, monkeypatch, anyio_backend, and pytest's own cleanup lambdas. Only a
fixture with steps inside, or one that failed, tells the reader something, so
the rest is removed before `allure generate`. A teardown keeps the name of its
fixture without pytest's "::1" suffix.

Usage: python tests/allure_report/hide_empty_fixtures.py allure-results
"""

import json
import sys
from pathlib import Path


def fixture_says_something(fixture: dict) -> bool:
    has_steps = fixture.get("steps", []) != []
    failed = fixture.get("status") in ("failed", "broken")
    return has_steps or failed


def name_without_suffix(fixture_name: str) -> str:
    return fixture_name.split("::")[0]


def hide_empty_fixtures(results_folder: Path) -> None:
    for container_file in results_folder.glob("*-container.json"):
        container = json.loads(container_file.read_text(encoding="utf-8"))

        container["befores"] = [
            fixture
            for fixture in container.get("befores", [])
            if fixture_says_something(fixture)
        ]
        container["afters"] = [
            fixture
            for fixture in container.get("afters", [])
            if fixture_says_something(fixture)
        ]
        for teardown in container["afters"]:
            teardown["name"] = name_without_suffix(teardown["name"])

        container_file.write_text(json.dumps(container), encoding="utf-8")


if __name__ == "__main__":
    hide_empty_fixtures(Path(sys.argv[1]))
