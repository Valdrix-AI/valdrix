from unittest.mock import patch

from app.shared.core.system_resources import (
    safe_cpu_percent,
    safe_virtual_memory,
    safe_disk_usage,
)


def test_safe_cpu_percent_non_blocking():
    with patch(
        "app.shared.core.system_resources.psutil.cpu_percent", return_value=12.5
    ) as mock_cpu:
        value = safe_cpu_percent()

    assert value == 12.5
    mock_cpu.assert_called_once_with(interval=None)


def test_safe_virtual_memory_calls_psutil():
    with patch(
        "app.shared.core.system_resources.psutil.virtual_memory", return_value="mem"
    ) as mock_vm:
        value = safe_virtual_memory()

    assert value == "mem"
    mock_vm.assert_called_once_with()


def test_safe_disk_usage_calls_psutil():
    with patch(
        "app.shared.core.system_resources.psutil.disk_usage", return_value="disk"
    ) as mock_disk:
        value = safe_disk_usage("/")

    assert value == "disk"
    mock_disk.assert_called_once_with("/")
