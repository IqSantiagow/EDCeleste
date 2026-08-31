import unittest
from unittest.mock import Mock

from edceleste.use_cases.settings.get_available_device_use_case import (
    GetAvailableDeviceUseCase,
)


class TestGetAvailableDeviceUseCase(unittest.TestCase):
    def test_should_return_cuda_when_device_detection_protocol_reports_cuda(self):
        protocol = Mock()
        protocol.get_available_device.return_value = "cuda"
        use_case = GetAvailableDeviceUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, "cuda")
        protocol.get_available_device.assert_called_once()

    def test_should_return_cpu_when_device_detection_protocol_reports_cpu(self):
        protocol = Mock()
        protocol.get_available_device.return_value = "cpu"
        use_case = GetAvailableDeviceUseCase(protocol)  # type: ignore

        result = use_case()

        self.assertEqual(result, "cpu")


if __name__ == "__main__":
    unittest.main()
