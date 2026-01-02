"""Linux system monitoring for ReOS.

This module provides read-only system surveillance capabilities for Ubuntu/Linux:
- Process monitoring (ps, top-like info)
- Docker container/image status
- Systemd service status
- System resources (disk, memory, CPU)
- Network connections and ports
- System logs via journalctl
- User sessions and logins

All operations are read-only and safe for server management.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SystemMonitorError(RuntimeError):
    """Error accessing system information."""

    pass


def _run_command(
    cmd: list[str],
    *,
    timeout: int = 30,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return the result."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemMonitorError(f"Command timed out: {' '.join(cmd)}") from exc
    except FileNotFoundError as exc:
        raise SystemMonitorError(f"Command not found: {cmd[0]}") from exc


def _command_exists(cmd: str) -> bool:
    """Check if a command exists on the system."""
    return shutil.which(cmd) is not None


# =============================================================================
# Process Monitoring
# =============================================================================


@dataclass(frozen=True)
class ProcessInfo:
    """Information about a running process."""

    pid: int
    ppid: int
    user: str
    cpu_percent: float
    mem_percent: float
    vsz_kb: int
    rss_kb: int
    stat: str
    started: str
    command: str


def list_processes(
    *,
    sort_by: str = "cpu",
    limit: int = 50,
    user: str | None = None,
    filter_command: str | None = None,
) -> list[ProcessInfo]:
    """List running processes.

    Args:
        sort_by: Sort by 'cpu', 'mem', 'pid', or 'time'.
        limit: Maximum number of processes to return.
        user: Filter by username.
        filter_command: Filter by command substring.

    Returns:
        List of ProcessInfo objects.
    """
    # Build ps command with custom format
    cmd = [
        "ps",
        "axo",
        "pid,ppid,user,%cpu,%mem,vsz,rss,stat,lstart,args",
        "--no-headers",
    ]

    result = _run_command(cmd)
    if result.returncode != 0:
        raise SystemMonitorError(f"ps failed: {result.stderr}")

    processes: list[ProcessInfo] = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue

        # Parse the fixed-width ps output
        # lstart is like "Mon Jan 20 10:30:00 2025" (24 chars after stat)
        parts = line.split()
        if len(parts) < 10:
            continue

        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            proc_user = parts[2]
            cpu = float(parts[3])
            mem = float(parts[4])
            vsz = int(parts[5])
            rss = int(parts[6])
            stat = parts[7]
            # lstart is 5 fields: Day Mon DD HH:MM:SS YYYY
            started = " ".join(parts[8:13])
            command = " ".join(parts[13:])
        except (ValueError, IndexError):
            continue

        # Apply filters
        if user and proc_user != user:
            continue
        if filter_command and filter_command.lower() not in command.lower():
            continue

        processes.append(
            ProcessInfo(
                pid=pid,
                ppid=ppid,
                user=proc_user,
                cpu_percent=cpu,
                mem_percent=mem,
                vsz_kb=vsz,
                rss_kb=rss,
                stat=stat,
                started=started,
                command=command[:200],  # Truncate long commands
            )
        )

    # Sort
    if sort_by == "cpu":
        processes.sort(key=lambda p: p.cpu_percent, reverse=True)
    elif sort_by == "mem":
        processes.sort(key=lambda p: p.mem_percent, reverse=True)
    elif sort_by == "pid":
        processes.sort(key=lambda p: p.pid)
    elif sort_by == "time":
        processes.sort(key=lambda p: p.started, reverse=True)

    return processes[:limit]


def get_process_details(pid: int) -> dict[str, Any]:
    """Get detailed information about a specific process.

    Args:
        pid: Process ID.

    Returns:
        Dict with process details.
    """
    proc_path = Path(f"/proc/{pid}")
    if not proc_path.exists():
        raise SystemMonitorError(f"Process {pid} not found")

    details: dict[str, Any] = {"pid": pid}

    # Read cmdline
    try:
        cmdline = (proc_path / "cmdline").read_text()
        details["cmdline"] = cmdline.replace("\x00", " ").strip()
    except OSError:
        details["cmdline"] = None

    # Read status
    try:
        status_text = (proc_path / "status").read_text()
        for line in status_text.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()
                if key in ("name", "state", "ppid", "uid", "gid", "threads", "vmrss", "vmsize"):
                    details[key] = value
    except OSError:
        pass

    # Read cwd
    try:
        details["cwd"] = os.readlink(proc_path / "cwd")
    except OSError:
        details["cwd"] = None

    # Read exe
    try:
        details["exe"] = os.readlink(proc_path / "exe")
    except OSError:
        details["exe"] = None

    # Read fd count
    try:
        fd_path = proc_path / "fd"
        details["open_files"] = len(list(fd_path.iterdir()))
    except OSError:
        details["open_files"] = None

    # Read environ (first 10 vars)
    try:
        environ = (proc_path / "environ").read_text()
        env_vars = environ.split("\x00")[:10]
        details["environment_sample"] = [e for e in env_vars if e]
    except OSError:
        details["environment_sample"] = None

    return details


# =============================================================================
# Docker Monitoring
# =============================================================================


def docker_available() -> bool:
    """Check if Docker is available."""
    return _command_exists("docker")


def list_containers(*, all_containers: bool = False) -> list[dict[str, Any]]:
    """List Docker containers.

    Args:
        all_containers: If True, include stopped containers.

    Returns:
        List of container info dicts.
    """
    if not docker_available():
        raise SystemMonitorError("Docker is not installed")

    cmd = ["docker", "ps", "--format", "json"]
    if all_containers:
        cmd.append("-a")

    result = _run_command(cmd)
    if result.returncode != 0:
        raise SystemMonitorError(f"docker ps failed: {result.stderr}")

    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            container = json.loads(line)
            containers.append({
                "id": container.get("ID", ""),
                "name": container.get("Names", ""),
                "image": container.get("Image", ""),
                "status": container.get("Status", ""),
                "state": container.get("State", ""),
                "ports": container.get("Ports", ""),
                "created": container.get("CreatedAt", ""),
            })
        except json.JSONDecodeError:
            continue

    return containers


def list_docker_images() -> list[dict[str, Any]]:
    """List Docker images."""
    if not docker_available():
        raise SystemMonitorError("Docker is not installed")

    cmd = ["docker", "images", "--format", "json"]
    result = _run_command(cmd)
    if result.returncode != 0:
        raise SystemMonitorError(f"docker images failed: {result.stderr}")

    images = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            image = json.loads(line)
            images.append({
                "id": image.get("ID", ""),
                "repository": image.get("Repository", ""),
                "tag": image.get("Tag", ""),
                "size": image.get("Size", ""),
                "created": image.get("CreatedAt", ""),
            })
        except json.JSONDecodeError:
            continue

    return images


def get_container_stats() -> list[dict[str, Any]]:
    """Get resource usage stats for running containers."""
    if not docker_available():
        raise SystemMonitorError("Docker is not installed")

    cmd = ["docker", "stats", "--no-stream", "--format", "json"]
    result = _run_command(cmd)
    if result.returncode != 0:
        raise SystemMonitorError(f"docker stats failed: {result.stderr}")

    stats = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            stat = json.loads(line)
            stats.append({
                "container": stat.get("Name", ""),
                "cpu_percent": stat.get("CPUPerc", ""),
                "mem_usage": stat.get("MemUsage", ""),
                "mem_percent": stat.get("MemPerc", ""),
                "net_io": stat.get("NetIO", ""),
                "block_io": stat.get("BlockIO", ""),
                "pids": stat.get("PIDs", ""),
            })
        except json.JSONDecodeError:
            continue

    return stats


def get_container_logs(container: str, *, lines: int = 100) -> str:
    """Get recent logs from a container.

    Args:
        container: Container name or ID.
        lines: Number of log lines to retrieve.

    Returns:
        Log output as string.
    """
    if not docker_available():
        raise SystemMonitorError("Docker is not installed")

    cmd = ["docker", "logs", "--tail", str(min(lines, 1000)), container]
    result = _run_command(cmd)
    # docker logs outputs to stderr for some logs
    return result.stdout + result.stderr


# =============================================================================
# Systemd Monitoring
# =============================================================================


def systemd_available() -> bool:
    """Check if systemd is available."""
    return _command_exists("systemctl")


def list_services(
    *,
    state: str | None = None,
    type_filter: str = "service",
) -> list[dict[str, Any]]:
    """List systemd services.

    Args:
        state: Filter by state ('running', 'failed', 'inactive', etc.).
        type_filter: Unit type to list (default 'service').

    Returns:
        List of service info dicts.
    """
    if not systemd_available():
        raise SystemMonitorError("systemd is not available")

    cmd = ["systemctl", "list-units", f"--type={type_filter}", "--all", "--no-pager", "--output=json"]
    if state:
        cmd.append(f"--state={state}")

    result = _run_command(cmd)
    if result.returncode != 0:
        # Fallback to non-JSON output
        return _parse_systemctl_text_output(type_filter, state)

    try:
        units = json.loads(result.stdout)
        return [
            {
                "unit": u.get("unit", ""),
                "load": u.get("load", ""),
                "active": u.get("active", ""),
                "sub": u.get("sub", ""),
                "description": u.get("description", ""),
            }
            for u in units
        ]
    except json.JSONDecodeError:
        return _parse_systemctl_text_output(type_filter, state)


def _parse_systemctl_text_output(type_filter: str, state: str | None) -> list[dict[str, Any]]:
    """Fallback parser for systemctl text output."""
    cmd = ["systemctl", "list-units", f"--type={type_filter}", "--all", "--no-pager", "--no-legend"]
    if state:
        cmd.append(f"--state={state}")

    result = _run_command(cmd)
    services = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 4)
        if len(parts) >= 4:
            services.append({
                "unit": parts[0],
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
                "description": parts[4] if len(parts) > 4 else "",
            })
    return services


def get_service_status(service: str) -> dict[str, Any]:
    """Get detailed status of a systemd service.

    Args:
        service: Service name (with or without .service suffix).

    Returns:
        Dict with service status details.
    """
    if not systemd_available():
        raise SystemMonitorError("systemd is not available")

    if not service.endswith(".service"):
        service = f"{service}.service"

    cmd = ["systemctl", "show", service, "--no-pager"]
    result = _run_command(cmd)

    status: dict[str, Any] = {"unit": service}
    for line in result.stdout.strip().split("\n"):
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Only include useful fields
            if key in (
                "ActiveState",
                "SubState",
                "LoadState",
                "Description",
                "MainPID",
                "ExecMainStartTimestamp",
                "MemoryCurrent",
                "CPUUsageNSec",
                "TasksCurrent",
                "Restart",
                "RestartUSec",
                "FragmentPath",
                "Result",
            ):
                status[key.lower()] = value

    return status


def get_failed_services() -> list[dict[str, Any]]:
    """Get list of failed systemd services."""
    return list_services(state="failed")


# =============================================================================
# System Resources
# =============================================================================


def get_disk_usage() -> list[dict[str, Any]]:
    """Get disk usage for mounted filesystems."""
    cmd = ["df", "-h", "--output=source,fstype,size,used,avail,pcent,target"]
    result = _run_command(cmd)
    if result.returncode != 0:
        raise SystemMonitorError(f"df failed: {result.stderr}")

    disks = []
    lines = result.stdout.strip().split("\n")
    for line in lines[1:]:  # Skip header
        parts = line.split()
        if len(parts) >= 7:
            # Skip pseudo filesystems
            if parts[1] in ("tmpfs", "devtmpfs", "squashfs", "overlay"):
                continue
            disks.append({
                "filesystem": parts[0],
                "type": parts[1],
                "size": parts[2],
                "used": parts[3],
                "available": parts[4],
                "use_percent": parts[5],
                "mounted_on": parts[6],
            })

    return disks


def get_memory_info() -> dict[str, Any]:
    """Get memory usage information."""
    try:
        meminfo = Path("/proc/meminfo").read_text()
    except OSError as exc:
        raise SystemMonitorError(f"Failed to read /proc/meminfo: {exc}") from exc

    info: dict[str, Any] = {}
    for line in meminfo.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower().replace("(", "_").replace(")", "")
            value = value.strip()
            if key in (
                "memtotal",
                "memfree",
                "memavailable",
                "buffers",
                "cached",
                "swaptotal",
                "swapfree",
                "shmem",
                "slab",
            ):
                info[key] = value

    # Calculate usage percentage
    try:
        total = int(info.get("memtotal", "0 kB").split()[0])
        available = int(info.get("memavailable", "0 kB").split()[0])
        if total > 0:
            info["used_percent"] = round((total - available) / total * 100, 1)
    except (ValueError, IndexError):
        pass

    return info


def get_cpu_info() -> dict[str, Any]:
    """Get CPU information."""
    info: dict[str, Any] = {}

    # Get CPU model from /proc/cpuinfo
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        for line in cpuinfo.split("\n"):
            if line.startswith("model name"):
                info["model"] = line.split(":")[1].strip()
                break
        info["cores"] = cpuinfo.count("processor\t:")
    except OSError:
        pass

    # Get load average
    try:
        loadavg = Path("/proc/loadavg").read_text().split()
        info["load_1min"] = float(loadavg[0])
        info["load_5min"] = float(loadavg[1])
        info["load_15min"] = float(loadavg[2])
    except (OSError, IndexError, ValueError):
        pass

    # Get uptime
    try:
        uptime_seconds = float(Path("/proc/uptime").read_text().split()[0])
        days, remainder = divmod(int(uptime_seconds), 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        info["uptime"] = f"{days}d {hours}h {minutes}m"
        info["uptime_seconds"] = uptime_seconds
    except (OSError, ValueError, IndexError):
        pass

    return info


def get_system_overview() -> dict[str, Any]:
    """Get a comprehensive system overview."""
    overview: dict[str, Any] = {}

    # Hostname
    try:
        overview["hostname"] = Path("/etc/hostname").read_text().strip()
    except OSError:
        overview["hostname"] = "unknown"

    # OS info
    try:
        os_release = Path("/etc/os-release").read_text()
        for line in os_release.split("\n"):
            if line.startswith("PRETTY_NAME="):
                overview["os"] = line.split("=")[1].strip().strip('"')
                break
    except OSError:
        overview["os"] = "Linux"

    # Kernel
    result = _run_command(["uname", "-r"])
    overview["kernel"] = result.stdout.strip()

    # Add CPU, memory, disk summaries
    overview["cpu"] = get_cpu_info()
    overview["memory"] = get_memory_info()
    overview["disks"] = get_disk_usage()

    return overview


# =============================================================================
# Network Monitoring
# =============================================================================


def get_network_connections(
    *,
    state: str | None = None,
    protocol: str | None = None,
) -> list[dict[str, Any]]:
    """Get network connections.

    Args:
        state: Filter by state ('LISTEN', 'ESTABLISHED', etc.).
        protocol: Filter by protocol ('tcp', 'udp').

    Returns:
        List of connection info dicts.
    """
    cmd = ["ss", "-tunapH"]  # TCP, UDP, numeric, all, processes, no header
    result = _run_command(cmd)
    if result.returncode != 0:
        # Fallback to netstat
        return _get_connections_netstat(state, protocol)

    connections = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 5:
            continue

        proto = parts[0]
        conn_state = parts[1]
        local = parts[4] if len(parts) > 4 else ""
        remote = parts[5] if len(parts) > 5 else ""
        process = parts[6] if len(parts) > 6 else ""

        # Apply filters
        if protocol and proto.lower() != protocol.lower():
            continue
        if state and conn_state.upper() != state.upper():
            continue

        connections.append({
            "protocol": proto,
            "state": conn_state,
            "local_address": local,
            "remote_address": remote,
            "process": process,
        })

    return connections


def _get_connections_netstat(state: str | None, protocol: str | None) -> list[dict[str, Any]]:
    """Fallback to netstat for connection listing."""
    cmd = ["netstat", "-tuanp"]
    result = _run_command(cmd)

    connections = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split()
        if len(parts) < 6:
            continue
        if parts[0] not in ("tcp", "tcp6", "udp", "udp6"):
            continue

        proto = parts[0]
        local = parts[3]
        remote = parts[4]
        conn_state = parts[5] if proto.startswith("tcp") else "STATELESS"
        process = parts[6] if len(parts) > 6 else ""

        if protocol and not proto.startswith(protocol):
            continue
        if state and conn_state != state:
            continue

        connections.append({
            "protocol": proto,
            "state": conn_state,
            "local_address": local,
            "remote_address": remote,
            "process": process,
        })

    return connections


def get_listening_ports() -> list[dict[str, Any]]:
    """Get all listening ports."""
    return get_network_connections(state="LISTEN")


def get_network_interfaces() -> list[dict[str, Any]]:
    """Get network interface information."""
    cmd = ["ip", "-j", "addr", "show"]
    result = _run_command(cmd)

    try:
        interfaces = json.loads(result.stdout)
        return [
            {
                "name": iface.get("ifname", ""),
                "state": iface.get("operstate", ""),
                "mac": iface.get("address", ""),
                "addresses": [
                    {
                        "family": addr.get("family", ""),
                        "address": addr.get("local", ""),
                        "prefix": addr.get("prefixlen", ""),
                    }
                    for addr in iface.get("addr_info", [])
                ],
            }
            for iface in interfaces
        ]
    except json.JSONDecodeError:
        # Fallback to text parsing
        return _parse_ip_addr_text()


def _parse_ip_addr_text() -> list[dict[str, Any]]:
    """Parse ip addr output as text."""
    cmd = ["ip", "addr", "show"]
    result = _run_command(cmd)

    interfaces = []
    current: dict[str, Any] = {}

    for line in result.stdout.split("\n"):
        if re.match(r"^\d+:", line):
            if current:
                interfaces.append(current)
            parts = line.split(":")
            current = {
                "name": parts[1].strip().split("@")[0],
                "state": "UP" if "UP" in line else "DOWN",
                "addresses": [],
            }
        elif "link/ether" in line:
            current["mac"] = line.split()[1]
        elif "inet " in line:
            parts = line.split()
            current["addresses"].append({
                "family": "inet",
                "address": parts[1].split("/")[0],
                "prefix": parts[1].split("/")[1] if "/" in parts[1] else "",
            })
        elif "inet6 " in line:
            parts = line.split()
            current["addresses"].append({
                "family": "inet6",
                "address": parts[1].split("/")[0],
                "prefix": parts[1].split("/")[1] if "/" in parts[1] else "",
            })

    if current:
        interfaces.append(current)

    return interfaces


# =============================================================================
# Logs and Users
# =============================================================================


def get_journal_logs(
    *,
    unit: str | None = None,
    priority: str | None = None,
    since: str | None = None,
    lines: int = 100,
    grep: str | None = None,
) -> list[dict[str, Any]]:
    """Get system logs from journalctl.

    Args:
        unit: Filter by systemd unit.
        priority: Filter by priority ('emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug').
        since: Time filter (e.g., '1 hour ago', 'today', '2025-01-20').
        lines: Maximum number of log lines.
        grep: Filter logs by pattern.

    Returns:
        List of log entry dicts.
    """
    if not _command_exists("journalctl"):
        raise SystemMonitorError("journalctl not available")

    cmd = ["journalctl", "--no-pager", "-o", "json", "-n", str(min(lines, 1000))]

    if unit:
        cmd.extend(["-u", unit])
    if priority:
        cmd.extend(["-p", priority])
    if since:
        cmd.extend(["--since", since])
    if grep:
        cmd.extend(["-g", grep])

    result = _run_command(cmd, timeout=60)

    logs = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            logs.append({
                "timestamp": entry.get("__REALTIME_TIMESTAMP", ""),
                "unit": entry.get("_SYSTEMD_UNIT", ""),
                "priority": entry.get("PRIORITY", ""),
                "message": entry.get("MESSAGE", ""),
                "pid": entry.get("_PID", ""),
            })
        except json.JSONDecodeError:
            continue

    return logs


def get_logged_in_users() -> list[dict[str, Any]]:
    """Get currently logged in users."""
    cmd = ["who", "-u"]
    result = _run_command(cmd)

    users = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 5:
            users.append({
                "user": parts[0],
                "tty": parts[1],
                "login_time": " ".join(parts[2:4]),
                "idle": parts[4] if len(parts) > 4 else "",
                "pid": parts[5] if len(parts) > 5 else "",
            })

    return users


def get_last_logins(*, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent login history."""
    cmd = ["last", "-n", str(min(limit, 100)), "-F"]
    result = _run_command(cmd)

    logins = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip() or line.startswith("wtmp") or line.startswith("reboot"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            logins.append({
                "user": parts[0],
                "tty": parts[1],
                "host": parts[2] if not parts[2].startswith("Mon") else "",
                "login_time": " ".join(parts[3:8]) if len(parts) > 7 else "",
            })

    return logins


def get_system_status() -> dict[str, Any]:
    """Get a comprehensive system status summary."""
    status: dict[str, Any] = {}

    # Basic info
    status["overview"] = get_system_overview()

    # Counts
    try:
        status["process_count"] = len(list_processes(limit=10000))
    except SystemMonitorError:
        status["process_count"] = None

    try:
        status["listening_ports"] = len(get_listening_ports())
    except SystemMonitorError:
        status["listening_ports"] = None

    try:
        status["logged_in_users"] = len(get_logged_in_users())
    except SystemMonitorError:
        status["logged_in_users"] = None

    # Docker
    status["docker_available"] = docker_available()
    if status["docker_available"]:
        try:
            status["container_count"] = len(list_containers())
        except SystemMonitorError:
            status["container_count"] = None

    # Failed services
    try:
        failed = get_failed_services()
        status["failed_services"] = len(failed)
        status["failed_service_names"] = [s["unit"] for s in failed[:5]]
    except SystemMonitorError:
        status["failed_services"] = None

    return status
