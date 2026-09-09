import unittest
from unittest.mock import Mock

from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.ui.screens.system_check.system_check_repository import (
    SystemCheckRepository,
)


async def _status_stream(items):
    for item in items:
        yield item


class TestSystemCheckRepository(unittest.IsolatedAsyncioTestCase):
    def _make_repository(self, system_check_use_case=None):
        return SystemCheckRepository(
            system_check_use_case=system_check_use_case or Mock()
        )

    async def test_run_system_check_delegates_to_use_case_and_yields_its_items(self):
        status = ColdStartStatus(
            service="settings", message=None, is_critical=True, completed=True
        )
        system_check_use_case = Mock(
            return_value=_status_stream([("settings", status)])
        )
        repository = self._make_repository(system_check_use_case=system_check_use_case)

        results = [item async for item in repository.run_system_check()]

        self.assertEqual(results, [("settings", status)])
        system_check_use_case.assert_called_once()

    def test_get_service_names_delegates_to_use_case(self):
        system_check_use_case = Mock()
        system_check_use_case.service_names = ["settings", "llm"]
        repository = self._make_repository(system_check_use_case=system_check_use_case)

        result = repository.get_service_names()

        self.assertEqual(result, ["settings", "llm"])


if __name__ == "__main__":
    unittest.main()
