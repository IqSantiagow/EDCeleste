import asyncio
import unittest

from edceleste.services.models.service_status import ServiceState, ServiceStatus
from edceleste.services.service_status_stream import ServiceStatusStream


async def _next_status(stream) -> ServiceStatus:
    """The next item of the stream, or a failure after one second, so a test
    that waits for a status that never comes does not hang."""
    return await asyncio.wait_for(stream.__anext__(), timeout=1)


class ServiceStatusStreamTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.first_status = ServiceStatus(ServiceState.OFF, "Not checked yet")
        self.status_stream = ServiceStatusStream(self.first_status)

    async def test_stream_yields_the_first_status_at_once(self):
        stream = self.status_stream.stream_latest_status_then_every_new_one()
        self.addAsyncCleanup(stream.aclose)

        self.assertEqual(await _next_status(stream), self.first_status)

    async def test_stream_yields_a_status_set_while_listening(self):
        stream = self.status_stream.stream_latest_status_then_every_new_one()
        self.addAsyncCleanup(stream.aclose)
        await _next_status(stream)

        self.status_stream.set_status(ServiceState.ERROR, "bad key")

        self.assertEqual(
            await _next_status(stream), ServiceStatus(ServiceState.ERROR, "bad key")
        )

    async def test_a_late_listener_gets_only_the_latest_status(self):
        self.status_stream.set_status(ServiceState.ERROR, "bad key")
        self.status_stream.set_status(ServiceState.OK, "works again")
        stream = self.status_stream.stream_latest_status_then_every_new_one()
        self.addAsyncCleanup(stream.aclose)

        self.assertEqual(
            await _next_status(stream), ServiceStatus(ServiceState.OK, "works again")
        )
        self.status_stream.set_status(ServiceState.OFF, "switched off")
        self.assertEqual(
            await _next_status(stream), ServiceStatus(ServiceState.OFF, "switched off")
        )

    async def test_two_listeners_both_get_every_status(self):
        first_stream = self.status_stream.stream_latest_status_then_every_new_one()
        second_stream = self.status_stream.stream_latest_status_then_every_new_one()
        self.addAsyncCleanup(first_stream.aclose)
        self.addAsyncCleanup(second_stream.aclose)
        await _next_status(first_stream)
        await _next_status(second_stream)

        self.status_stream.set_status(ServiceState.OK, "works")

        expected_status = ServiceStatus(ServiceState.OK, "works")
        self.assertEqual(await _next_status(first_stream), expected_status)
        self.assertEqual(await _next_status(second_stream), expected_status)

    async def test_a_listener_that_stopped_is_removed(self):
        stream = self.status_stream.stream_latest_status_then_every_new_one()
        await _next_status(stream)
        self.assertEqual(len(self.status_stream.queues_of_listeners), 1)

        await stream.aclose()

        self.assertEqual(self.status_stream.queues_of_listeners, [])


if __name__ == "__main__":
    unittest.main()
