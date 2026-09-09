import unittest

from edceleste.services.models.cold_start_status import ColdStartStatus
from edceleste.use_cases.system_check.system_check_use_case import SystemCheckUseCase


class FakeService:
    def __init__(self, statuses=None, error=None):
        self._statuses = statuses or []
        self._error = error

    async def cold_start(self):
        for status in self._statuses:
            yield status
        if self._error is not None:
            raise self._error


def _make_status(service: str, completed: bool = True, message: str | None = None):
    return ColdStartStatus(
        service=service, message=message, is_critical=False, completed=completed
    )


class TestSystemCheckUseCase(unittest.IsolatedAsyncioTestCase):
    async def test_yields_service_name_paired_with_each_status_from_cold_start(self):
        status = _make_status("settings")
        use_case = SystemCheckUseCase(services={"settings": FakeService([status])})

        results = [item async for item in use_case()]

        self.assertEqual(results, [("settings", status)])

    async def test_yields_statuses_from_multiple_services_in_order(self):
        settings_status = _make_status("settings")
        llm_status = _make_status("llm")
        use_case = SystemCheckUseCase(
            services={
                "settings": FakeService([settings_status]),
                "llm": FakeService([llm_status]),
            }
        )

        results = [item async for item in use_case()]

        self.assertEqual(
            results,
            [("settings", settings_status), ("llm", llm_status)],
        )

    async def test_service_names_returns_keys_of_services_dict(self):
        use_case = SystemCheckUseCase(
            services={"settings": FakeService(), "llm": FakeService()}
        )

        self.assertEqual(use_case.service_names, ["settings", "llm"])

    async def test_propagates_exception_raised_inside_a_services_cold_start(self):
        use_case = SystemCheckUseCase(
            services={"settings": FakeService(error=RuntimeError("boom"))}
        )

        with self.assertRaises(RuntimeError):
            async for _ in use_case():
                pass


if __name__ == "__main__":
    unittest.main()
