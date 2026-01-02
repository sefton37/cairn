"""System monitoring utilities for Linux.

Provides information about:
- systemd services with human-readable descriptions
- Running processes with resource usage
- Docker/Podman containers
- System resource utilization (CPU, memory, disk)
- Overall system status summary
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SystemdService:
    """Represents a systemd service with human-readable info."""

    unit: str
    load_state: str
    active_state: str
    sub_state: str
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "load_state": self.load_state,
            "active_state": self.active_state,
            "sub_state": self.sub_state,
            "description": self.description,
        }


@dataclass
class ProcessInfo:
    """Represents a running process."""

    pid: int
    user: str
    cpu_percent: float
    mem_percent: float
    vsz_kb: int
    rss_kb: int
    tty: str
    stat: str
    started: str
    time: str
    command: str
    friendly_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "user": self.user,
            "cpu_percent": self.cpu_percent,
            "mem_percent": self.mem_percent,
            "vsz_kb": self.vsz_kb,
            "rss_kb": self.rss_kb,
            "tty": self.tty,
            "stat": self.stat,
            "started": self.started,
            "time": self.time,
            "command": self.command,
            "friendly_name": self.friendly_name,
        }


@dataclass
class ContainerInfo:
    """Represents a Docker/Podman container."""

    id: str
    name: str
    image: str
    status: str
    ports: str
    created: str
    runtime: str  # "docker" or "podman"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "status": self.status,
            "ports": self.ports,
            "created": self.created,
            "runtime": self.runtime,
        }


@dataclass
class ResourceUsage:
    """System resource utilization."""

    cpu_percent: float
    cpu_count: int
    memory_total_mb: int
    memory_used_mb: int
    memory_percent: float
    swap_total_mb: int
    swap_used_mb: int
    swap_percent: float
    disk_total_gb: float
    disk_used_gb: float
    disk_percent: float
    load_avg_1: float
    load_avg_5: float
    load_avg_15: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "cpu_count": self.cpu_count,
            "memory_total_mb": self.memory_total_mb,
            "memory_used_mb": self.memory_used_mb,
            "memory_percent": self.memory_percent,
            "swap_total_mb": self.swap_total_mb,
            "swap_used_mb": self.swap_used_mb,
            "swap_percent": self.swap_percent,
            "disk_total_gb": self.disk_total_gb,
            "disk_used_gb": self.disk_used_gb,
            "disk_percent": self.disk_percent,
            "load_avg_1": self.load_avg_1,
            "load_avg_5": self.load_avg_5,
            "load_avg_15": self.load_avg_15,
        }


# Process name to friendly description mapping
PROCESS_DESCRIPTIONS: dict[str, str] = {
    "systemd": "System and Service Manager",
    "init": "System Init Process",
    "kthreadd": "Kernel Thread Daemon",
    "ksoftirqd": "Kernel Soft IRQ Handler",
    "kworker": "Kernel Worker Thread",
    "migration": "CPU Migration Thread",
    "rcu_sched": "Read-Copy-Update Scheduler",
    "watchdog": "Hardware Watchdog",
    "bash": "Bash Shell",
    "zsh": "Z Shell",
    "fish": "Fish Shell",
    "sh": "POSIX Shell",
    "python": "Python Interpreter",
    "python3": "Python 3 Interpreter",
    "node": "Node.js Runtime",
    "npm": "Node Package Manager",
    "java": "Java Virtual Machine",
    "docker": "Docker Daemon",
    "dockerd": "Docker Engine Daemon",
    "containerd": "Container Runtime",
    "podman": "Podman Container Engine",
    "nginx": "Nginx Web Server",
    "apache2": "Apache HTTP Server",
    "httpd": "Apache HTTP Server",
    "postgres": "PostgreSQL Database",
    "mysql": "MySQL Database",
    "mysqld": "MySQL Database Server",
    "redis-server": "Redis In-Memory Store",
    "mongod": "MongoDB Database",
    "sshd": "SSH Daemon",
    "ssh": "SSH Client",
    "cron": "Cron Job Scheduler",
    "rsyslogd": "System Logging Service",
    "journald": "Systemd Journal",
    "NetworkManager": "Network Manager",
    "dbus-daemon": "D-Bus Message Bus",
    "udevd": "Device Manager",
    "systemd-udevd": "Systemd Device Manager",
    "pulseaudio": "PulseAudio Sound Server",
    "pipewire": "PipeWire Media Server",
    "Xorg": "X.Org Display Server",
    "Xwayland": "X11 on Wayland",
    "gnome-shell": "GNOME Desktop Shell",
    "plasmashell": "KDE Plasma Shell",
    "code": "Visual Studio Code",
    "firefox": "Firefox Browser",
    "chrome": "Google Chrome",
    "chromium": "Chromium Browser",
    "slack": "Slack Messaging",
    "discord": "Discord",
    "spotify": "Spotify Music",
    "git": "Git Version Control",
    "vim": "Vim Editor",
    "nvim": "Neovim Editor",
    "emacs": "Emacs Editor",
    "tmux": "Terminal Multiplexer",
    "screen": "GNU Screen",
    "htop": "Interactive Process Viewer",
    "top": "Process Viewer",
    "ps": "Process Status",
    "grep": "Pattern Search",
    "find": "File Search",
    "tail": "File Tail",
    "cat": "Concatenate Files",
    "less": "File Pager",
    "more": "File Pager",
    "tar": "Archive Utility",
    "gzip": "Compression Utility",
    "curl": "URL Transfer Tool",
    "wget": "Network Downloader",
    "pip": "Python Package Manager",
    "cargo": "Rust Package Manager",
    "rustc": "Rust Compiler",
    "gcc": "GNU C Compiler",
    "g++": "GNU C++ Compiler",
    "make": "Build Automation",
    "cmake": "Cross-Platform Build System",
    "ollama": "Ollama LLM Runner",
    "tauri": "Tauri Framework",
}


def _run_command(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", 127
    except Exception as e:
        return "", str(e), 1


def _get_friendly_process_name(command: str) -> str:
    """Get a human-friendly name for a process based on its command."""
    if not command:
        return "Unknown Process"

    # Extract the base command name
    parts = command.split()
    if not parts:
        return "Unknown Process"

    cmd = parts[0]
    # Handle paths like /usr/bin/python3
    base_name = os.path.basename(cmd)

    # Check for exact match
    if base_name in PROCESS_DESCRIPTIONS:
        return PROCESS_DESCRIPTIONS[base_name]

    # Check for partial matches (e.g., python3.11 -> python3)
    for key, desc in PROCESS_DESCRIPTIONS.items():
        if base_name.startswith(key):
            return desc

    # Check if it's a kernel thread
    if command.startswith("[") and command.endswith("]"):
        return f"Kernel Thread: {command[1:-1]}"

    # Return the base command name as fallback
    return base_name


def get_systemd_services() -> list[SystemdService]:
    """Get list of systemd services with descriptions."""
    stdout, _, rc = _run_command(
        ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"]
    )

    if rc != 0:
        return []

    services = []
    lines = stdout.strip().split("\n")

    for line in lines:
        # Skip empty lines and header
        if not line.strip() or line.startswith("UNIT"):
            continue

        # Parse the line - format is: UNIT LOAD ACTIVE SUB DESCRIPTION
        # The description can contain spaces
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue

        unit = parts[0]
        load_state = parts[1]
        active_state = parts[2]
        sub_state = parts[3]
        description = parts[4] if len(parts) > 4 else unit

        # Only include .service units
        if not unit.endswith(".service"):
            continue

        services.append(
            SystemdService(
                unit=unit,
                load_state=load_state,
                active_state=active_state,
                sub_state=sub_state,
                description=description,
            )
        )

    return services


def get_running_processes(limit: int = 50) -> list[ProcessInfo]:
    """Get list of running processes sorted by CPU usage."""
    # Use ps with specific format to get detailed process info
    stdout, _, rc = _run_command(
        [
            "ps",
            "aux",
            "--sort=-pcpu",
        ]
    )

    if rc != 0:
        return []

    processes = []
    lines = stdout.strip().split("\n")

    for i, line in enumerate(lines):
        if i == 0:  # Skip header
            continue
        if len(processes) >= limit:
            break

        parts = line.split(None, 10)
        if len(parts) < 11:
            continue

        try:
            command = parts[10]
            processes.append(
                ProcessInfo(
                    pid=int(parts[1]),
                    user=parts[0],
                    cpu_percent=float(parts[2]),
                    mem_percent=float(parts[3]),
                    vsz_kb=int(parts[4]),
                    rss_kb=int(parts[5]),
                    tty=parts[6],
                    stat=parts[7],
                    started=parts[8],
                    time=parts[9],
                    command=command,
                    friendly_name=_get_friendly_process_name(command),
                )
            )
        except (ValueError, IndexError):
            continue

    return processes


def get_containers() -> list[ContainerInfo]:
    """Get list of Docker and Podman containers."""
    containers = []

    # Try Docker first
    docker_stdout, _, docker_rc = _run_command(
        [
            "docker",
            "ps",
            "-a",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.CreatedAt}}",
        ]
    )

    if docker_rc == 0 and docker_stdout.strip():
        for line in docker_stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                containers.append(
                    ContainerInfo(
                        id=parts[0][:12],
                        name=parts[1],
                        image=parts[2],
                        status=parts[3],
                        ports=parts[4],
                        created=parts[5],
                        runtime="docker",
                    )
                )

    # Try Podman
    podman_stdout, _, podman_rc = _run_command(
        [
            "podman",
            "ps",
            "-a",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}\t{{.Created}}",
        ]
    )

    if podman_rc == 0 and podman_stdout.strip():
        for line in podman_stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                containers.append(
                    ContainerInfo(
                        id=parts[0][:12],
                        name=parts[1],
                        image=parts[2],
                        status=parts[3],
                        ports=parts[4],
                        created=parts[5],
                        runtime="podman",
                    )
                )

    return containers


def get_resource_usage() -> ResourceUsage:
    """Get current system resource utilization."""
    # CPU info from /proc/stat
    cpu_percent = 0.0
    cpu_count = os.cpu_count() or 1

    try:
        with open("/proc/stat") as f:
            first_line = f.readline()
            # cpu  user nice system idle iowait irq softirq steal guest guest_nice
            parts = first_line.split()[1:]
            if len(parts) >= 4:
                total = sum(int(p) for p in parts)
                idle = int(parts[3])
                if total > 0:
                    cpu_percent = round(100.0 * (total - idle) / total, 1)
    except (FileNotFoundError, ValueError, IndexError):
        pass

    # Memory info from /proc/meminfo
    mem_total = 0
    mem_available = 0
    swap_total = 0
    swap_free = 0

    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1])
                elif line.startswith("SwapTotal:"):
                    swap_total = int(line.split()[1])
                elif line.startswith("SwapFree:"):
                    swap_free = int(line.split()[1])
    except (FileNotFoundError, ValueError, IndexError):
        pass

    mem_used = mem_total - mem_available
    mem_percent = round(100.0 * mem_used / mem_total, 1) if mem_total > 0 else 0.0
    swap_used = swap_total - swap_free
    swap_percent = round(100.0 * swap_used / swap_total, 1) if swap_total > 0 else 0.0

    # Disk usage for root filesystem
    disk_total_gb = 0.0
    disk_used_gb = 0.0
    disk_percent = 0.0

    try:
        stat = os.statvfs("/")
        disk_total = stat.f_blocks * stat.f_frsize
        disk_free = stat.f_bfree * stat.f_frsize
        disk_used = disk_total - disk_free
        disk_total_gb = round(disk_total / (1024**3), 1)
        disk_used_gb = round(disk_used / (1024**3), 1)
        disk_percent = round(100.0 * disk_used / disk_total, 1) if disk_total > 0 else 0.0
    except OSError:
        pass

    # Load average from /proc/loadavg
    load_1, load_5, load_15 = 0.0, 0.0, 0.0
    try:
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            if len(parts) >= 3:
                load_1 = float(parts[0])
                load_5 = float(parts[1])
                load_15 = float(parts[2])
    except (FileNotFoundError, ValueError, IndexError):
        pass

    return ResourceUsage(
        cpu_percent=cpu_percent,
        cpu_count=cpu_count,
        memory_total_mb=mem_total // 1024,
        memory_used_mb=mem_used // 1024,
        memory_percent=mem_percent,
        swap_total_mb=swap_total // 1024,
        swap_used_mb=swap_used // 1024,
        swap_percent=swap_percent,
        disk_total_gb=disk_total_gb,
        disk_used_gb=disk_used_gb,
        disk_percent=disk_percent,
        load_avg_1=load_1,
        load_avg_5=load_5,
        load_avg_15=load_15,
    )


def get_system_summary() -> dict[str, Any]:
    """Get overall system status summary."""
    # Hostname
    hostname = "unknown"
    try:
        with open("/etc/hostname") as f:
            hostname = f.read().strip()
    except FileNotFoundError:
        try:
            hostname = os.uname().nodename
        except Exception:
            pass

    # OS info
    os_name = "Linux"
    os_version = ""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    os_name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION="):
                    os_version = line.split("=", 1)[1].strip().strip('"')
    except FileNotFoundError:
        pass

    # Kernel version
    kernel = ""
    try:
        kernel = os.uname().release
    except Exception:
        pass

    # Uptime from /proc/uptime
    uptime_seconds = 0
    try:
        with open("/proc/uptime") as f:
            uptime_seconds = int(float(f.read().split()[0]))
    except (FileNotFoundError, ValueError, IndexError):
        pass

    uptime_days = uptime_seconds // 86400
    uptime_hours = (uptime_seconds % 86400) // 3600
    uptime_mins = (uptime_seconds % 3600) // 60
    uptime_str = f"{uptime_days}d {uptime_hours}h {uptime_mins}m"

    # Count processes
    process_count = 0
    try:
        process_count = len([d for d in os.listdir("/proc") if d.isdigit()])
    except OSError:
        pass

    # Get resource usage for quick summary
    resources = get_resource_usage()

    # Count running services
    services = get_systemd_services()
    running_services = sum(1 for s in services if s.active_state == "active")

    # Count containers
    containers = get_containers()
    running_containers = sum(1 for c in containers if "Up" in c.status)

    return {
        "hostname": hostname,
        "os_name": os_name,
        "os_version": os_version,
        "kernel": kernel,
        "uptime": uptime_str,
        "uptime_seconds": uptime_seconds,
        "process_count": process_count,
        "service_count": len(services),
        "running_services": running_services,
        "container_count": len(containers),
        "running_containers": running_containers,
        "cpu_percent": resources.cpu_percent,
        "memory_percent": resources.memory_percent,
        "disk_percent": resources.disk_percent,
        "load_avg": f"{resources.load_avg_1:.2f}, {resources.load_avg_5:.2f}, {resources.load_avg_15:.2f}",
    }
