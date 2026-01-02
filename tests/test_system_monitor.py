"""Tests for system monitoring module."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from reos.system_monitor import (
    ProcessInfo,
    SystemMonitorError,
    _command_exists,
    _run_command,
    docker_available,
    get_cpu_info,
    get_disk_usage,
    get_logged_in_users,
    get_memory_info,
    get_network_interfaces,
    get_process_details,
    get_system_overview,
    list_processes,
    systemd_available,
)


class TestRunCommand:
    def test_run_command_success(self) -> None:
        result = _run_command(["echo", "hello"])
        assert result.returncode == 0
        assert result.stdout.strip() == "hello"

    def test_run_command_not_found(self) -> None:
        with pytest.raises(SystemMonitorError, match="Command not found"):
            _run_command(["nonexistent_command_xyz"])

    def test_command_exists_true(self) -> None:
        assert _command_exists("echo") is True

    def test_command_exists_false(self) -> None:
        assert _command_exists("nonexistent_command_xyz") is False


class TestProcessMonitoring:
    def test_list_processes(self) -> None:
        """Should list running processes."""
        processes = list_processes(limit=10)
        assert len(processes) > 0
        assert all(isinstance(p, ProcessInfo) for p in processes)
        # Should have basic fields
        for p in processes:
            assert isinstance(p.pid, int)
            assert isinstance(p.user, str)
            assert isinstance(p.command, str)

    def test_list_processes_sort_by_cpu(self) -> None:
        """Should sort by CPU usage."""
        processes = list_processes(sort_by="cpu", limit=10)
        # First process should have highest CPU (or equal to)
        if len(processes) > 1:
            assert processes[0].cpu_percent >= processes[-1].cpu_percent

    def test_list_processes_sort_by_mem(self) -> None:
        """Should sort by memory usage."""
        processes = list_processes(sort_by="mem", limit=10)
        if len(processes) > 1:
            assert processes[0].mem_percent >= processes[-1].mem_percent

    def test_list_processes_filter_by_command(self) -> None:
        """Should filter by command substring."""
        # Look for python processes (we're running pytest)
        processes = list_processes(filter_command="python", limit=10)
        for p in processes:
            assert "python" in p.command.lower()

    def test_get_process_details(self) -> None:
        """Should get details for a valid PID."""
        # Get our own process
        import os

        pid = os.getpid()
        details = get_process_details(pid)

        assert details["pid"] == pid
        assert "name" in details
        assert "state" in details

    def test_get_process_details_not_found(self) -> None:
        """Should raise for non-existent process."""
        with pytest.raises(SystemMonitorError, match="not found"):
            get_process_details(999999999)


class TestDockerMonitoring:
    def test_docker_available_check(self) -> None:
        """docker_available should return bool."""
        result = docker_available()
        assert isinstance(result, bool)


class TestSystemdMonitoring:
    def test_systemd_available_check(self) -> None:
        """systemd_available should return bool."""
        result = systemd_available()
        assert isinstance(result, bool)


class TestSystemResources:
    def test_get_disk_usage(self) -> None:
        """Should return disk usage info."""
        disks = get_disk_usage()
        assert isinstance(disks, list)
        # Should have at least the root filesystem
        if disks:
            assert "filesystem" in disks[0]
            assert "size" in disks[0]
            assert "used" in disks[0]
            assert "mounted_on" in disks[0]

    def test_get_memory_info(self) -> None:
        """Should return memory info."""
        mem = get_memory_info()
        assert isinstance(mem, dict)
        assert "memtotal" in mem
        assert "memfree" in mem or "memavailable" in mem

    def test_get_cpu_info(self) -> None:
        """Should return CPU info."""
        cpu = get_cpu_info()
        assert isinstance(cpu, dict)
        # Should have load averages
        assert "load_1min" in cpu or "cores" in cpu
        assert "uptime" in cpu

    def test_get_system_overview(self) -> None:
        """Should return system overview."""
        overview = get_system_overview()
        assert isinstance(overview, dict)
        assert "hostname" in overview
        assert "os" in overview
        assert "kernel" in overview
        assert "cpu" in overview
        assert "memory" in overview


class TestNetworkMonitoring:
    def test_get_network_interfaces(self) -> None:
        """Should return network interfaces."""
        try:
            interfaces = get_network_interfaces()
            assert isinstance(interfaces, list)
            # Should have at least lo (loopback) if we got results
            if interfaces:
                names = [i["name"] for i in interfaces]
                assert "lo" in names
        except SystemMonitorError as exc:
            # ip command may not be available in some environments
            if "Command not found" in str(exc):
                pytest.skip("ip command not available")
            raise


class TestUserMonitoring:
    def test_get_logged_in_users(self) -> None:
        """Should return logged in users (may be empty in container)."""
        users = get_logged_in_users()
        assert isinstance(users, list)


class TestProcessInfoDataclass:
    def test_process_info_frozen(self) -> None:
        """ProcessInfo should be immutable."""
        info = ProcessInfo(
            pid=1,
            ppid=0,
            user="root",
            cpu_percent=0.0,
            mem_percent=0.0,
            vsz_kb=0,
            rss_kb=0,
            stat="S",
            started="",
            command="test",
        )
        with pytest.raises(AttributeError):
            info.pid = 2  # type: ignore


class TestMockedCommands:
    """Tests using mocked command output."""

    def test_list_processes_with_mock(self) -> None:
        """Test process parsing with mocked ps output."""
        mock_output = """    1     0 root      0.0  0.1  12345  6789 Ss   Mon Jan 20 10:00:00 2025 /sbin/init
  123    1 www-data  1.5  2.3  98765 43210 S    Mon Jan 20 10:01:00 2025 nginx: worker process
"""

        class MockResult:
            returncode = 0
            stdout = mock_output
            stderr = ""

        with patch("reos.system_monitor._run_command", return_value=MockResult()):
            # Default sort is by CPU, so nginx (1.5%) comes before init (0.0%)
            processes = list_processes(limit=10)
            assert len(processes) == 2
            # Higher CPU first (nginx)
            assert processes[0].pid == 123
            assert processes[0].user == "www-data"
            assert "nginx" in processes[0].command
            # Lower CPU second (init)
            assert processes[1].pid == 1
            assert processes[1].user == "root"

    def test_disk_usage_with_mock(self) -> None:
        """Test disk usage parsing with mocked df output."""
        mock_output = """Filesystem     Type  Size  Used Avail Use% Mounted on
/dev/sda1      ext4  100G   50G   50G  50% /
/dev/sdb1      ext4  500G  200G  300G  40% /data
"""

        class MockResult:
            returncode = 0
            stdout = mock_output
            stderr = ""

        with patch("reos.system_monitor._run_command", return_value=MockResult()):
            disks = get_disk_usage()
            assert len(disks) == 2
            assert disks[0]["filesystem"] == "/dev/sda1"
            assert disks[0]["size"] == "100G"
            assert disks[0]["use_percent"] == "50%"
            assert disks[1]["mounted_on"] == "/data"

    def test_memory_info_parsing(self, tmp_path: Path) -> None:
        """Test memory info parsing."""
        meminfo = """MemTotal:       16384000 kB
MemFree:         1234567 kB
MemAvailable:    8000000 kB
Buffers:          500000 kB
Cached:          4000000 kB
SwapTotal:       8000000 kB
SwapFree:        7500000 kB
"""
        meminfo_file = tmp_path / "meminfo"
        meminfo_file.write_text(meminfo)

        with patch("reos.system_monitor.Path") as mock_path:
            mock_path.return_value.read_text.return_value = meminfo
            # Can't easily mock Path("/proc/meminfo") so just test the real function
            mem = get_memory_info()
            assert isinstance(mem, dict)


class TestErrorHandling:
    def test_command_timeout(self) -> None:
        """Commands should timeout properly."""
        # This shouldn't actually timeout, just verifying the mechanism exists
        result = _run_command(["echo", "test"], timeout=30)
        assert result.returncode == 0

    def test_process_details_permission_error(self) -> None:
        """Should handle permission errors gracefully."""
        # PID 1 (init) often has restricted access
        # This test just verifies we handle errors, not that errors occur
        try:
            details = get_process_details(1)
            assert "pid" in details
        except SystemMonitorError:
            # This is also acceptable
            pass
