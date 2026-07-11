import unittest
from unittest.mock import AsyncMock, Mock

from services.event_bus import EventBus


class EventBusTest(unittest.IsolatedAsyncioTestCase):
    def test_should_add_subscriber(self):
        mock = Mock()
        mock_event = type(mock)
        callables = mock.callable

        event_bus = EventBus()

        event_bus.subscribe(mock_event, callables)

        self.assertIn(mock_event, event_bus.subscribers)

    async def test_should_call_callable(self):
        mock_callable = AsyncMock()
        mock_event = Mock()

        event_bus = EventBus()

        event_bus.subscribe(type(mock_event), mock_callable)

        await event_bus.publish(mock_event)

        mock_callable.assert_called_with(mock_event)

    async def test_should_call_only_callables_for_types(self):
        event_type1 = type("str")
        event_type2 = type(123)

        mock1 = AsyncMock()
        mock2 = AsyncMock()

        event_bus = EventBus()

        event_bus.subscribe(event_type1, mock1)
        event_bus.subscribe(event_type2, mock2)

        await event_bus.publish("str")

        mock1.assert_called_once()
        mock2.assert_not_called()

    async def test_should_call_all_callables_for_type(self):
        event_type = type("str")

        callable1 = AsyncMock()
        callable2 = AsyncMock()

        event_bus = EventBus()

        event_bus.subscribe(event_type, callable1)
        event_bus.subscribe(event_type, callable2)

        await event_bus.publish("str")

        callable1.assert_called()
        callable2.assert_called()

    def test_should_add_callback_when_existing_type_already_registered(self):
        mock_event = Mock()

        callable1 = Mock()
        callable2 = Mock()

        event_bus = EventBus()

        event_bus.subscribe(type(mock_event), callable1)
        event_bus.subscribe(type(mock_event), callable2)

        self.assertIn(callable1, event_bus.subscribers[type(mock_event)])
        self.assertIn(callable2, event_bus.subscribers[type(mock_event)])
