"""System State Indexer for ReOS.

This module collects and indexes system state information daily,
providing RAG (Retrieval-Augmented Generation) context for the LLM.

The indexer captures:
- Hardware info (CPU, RAM, disk, GPU)
- OS and kernel version
- Installed packages (key packages, not exhaustive)
- Running services
- Network configuration
- User environment
- Container status
- Recent system events

The snapshot is stored in SQLite and refreshed once per day (or on demand).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import linux_tools
from .db import Database

logger = logging.getLogger(__name__)


@dataclass
class SystemSnapshot:
    """A point-in-time snapshot of system state."""

    snapshot_id: str
    captured_at: str
    hostname: str = ""
    os_info: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, Any] = field(default_factory=dict)
    network: dict[str, Any] = field(default_factory=dict)
    services: list[dict[str, Any]] = field(default_factory=list)
    packages: dict[str, Any] = field(default_factory=dict)
    containers: dict[str, Any] = field(default_factory=dict)
    users: list[dict[str, Any]] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    storage: list[dict[str, Any]] = field(default_factory=list)
    recent_logs: list[str] = field(default_factory=list)


class SystemIndexer:
    """Collects and stores daily system state snapshots."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the system_snapshots table if it doesn't exist."""
        conn = self._db.connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_snapshots (
                id TEXT PRIMARY KEY,
                captured_at TEXT NOT NULL,
                date TEXT NOT NULL,
                hostname TEXT,
                data_json TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_date ON system_snapshots(date DESC)"
        )
        conn.commit()

    def needs_refresh(self) -> bool:
        """Check if we need a new snapshot today."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self._db._execute(
            "SELECT id FROM system_snapshots WHERE date = ? LIMIT 1",
            (today,),
        ).fetchone()
        return row is None

    def get_latest_snapshot(self) -> SystemSnapshot | None:
        """Get the most recent system snapshot."""
        row = self._db._execute(
            "SELECT * FROM system_snapshots ORDER BY captured_at DESC LIMIT 1"
        ).fetchone()

        if row is None:
            return None

        data = json.loads(row["data_json"])
        return SystemSnapshot(
            snapshot_id=row["id"],
            captured_at=row["captured_at"],
            hostname=row["hostname"] or "",
            os_info=data.get("os_info", {}),
            hardware=data.get("hardware", {}),
            network=data.get("network", {}),
            services=data.get("services", []),
            packages=data.get("packages", {}),
            containers=data.get("containers", {}),
            users=data.get("users", []),
            environment=data.get("environment", {}),
            storage=data.get("storage", []),
            recent_logs=data.get("recent_logs", []),
        )

    def get_today_snapshot(self) -> SystemSnapshot | None:
        """Get today's snapshot if it exists."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self._db._execute(
            "SELECT * FROM system_snapshots WHERE date = ? LIMIT 1",
            (today,),
        ).fetchone()

        if row is None:
            return None

        data = json.loads(row["data_json"])
        return SystemSnapshot(
            snapshot_id=row["id"],
            captured_at=row["captured_at"],
            hostname=row["hostname"] or "",
            os_info=data.get("os_info", {}),
            hardware=data.get("hardware", {}),
            network=data.get("network", {}),
            services=data.get("services", []),
            packages=data.get("packages", {}),
            containers=data.get("containers", {}),
            users=data.get("users", []),
            environment=data.get("environment", {}),
            storage=data.get("storage", []),
            recent_logs=data.get("recent_logs", []),
        )

    def capture_snapshot(self) -> SystemSnapshot:
        """Capture a new system state snapshot."""
        import uuid

        now = datetime.now(UTC)
        snapshot_id = f"snap_{now.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

        logger.info("Capturing system state snapshot...")

        snapshot = SystemSnapshot(
            snapshot_id=snapshot_id,
            captured_at=now.isoformat(),
        )

        # Collect all information
        snapshot.hostname = self._get_hostname()
        snapshot.os_info = self._get_os_info()
        snapshot.hardware = self._get_hardware_info()
        snapshot.network = self._get_network_info()
        snapshot.services = self._get_services()
        snapshot.packages = self._get_packages()
        snapshot.containers = self._get_containers()
        snapshot.users = self._get_users()
        snapshot.environment = self._get_environment()
        snapshot.storage = self._get_storage()
        snapshot.recent_logs = self._get_recent_logs()

        # Store in database
        self._store_snapshot(snapshot)

        logger.info("System snapshot captured: %s", snapshot_id)
        return snapshot

    def _store_snapshot(self, snapshot: SystemSnapshot) -> None:
        """Store a snapshot in the database."""
        now = datetime.now(UTC)
        today = now.strftime("%Y-%m-%d")

        data = {
            "os_info": snapshot.os_info,
            "hardware": snapshot.hardware,
            "network": snapshot.network,
            "services": snapshot.services,
            "packages": snapshot.packages,
            "containers": snapshot.containers,
            "users": snapshot.users,
            "environment": snapshot.environment,
            "storage": snapshot.storage,
            "recent_logs": snapshot.recent_logs,
        }

        summary = self._generate_summary(snapshot)

        self._db._execute(
            """
            INSERT INTO system_snapshots
            (id, captured_at, date, hostname, data_json, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.captured_at,
                today,
                snapshot.hostname,
                json.dumps(data, default=str),
                summary,
                now.isoformat(),
            ),
        )
        self._db.connect().commit()

    def _generate_summary(self, snapshot: SystemSnapshot) -> str:
        """Generate a human-readable summary of the snapshot."""
        lines = []

        # OS
        os_info = snapshot.os_info
        if os_info:
            lines.append(f"OS: {os_info.get('distro', 'Linux')} {os_info.get('version', '')}")
            if os_info.get("kernel"):
                lines.append(f"Kernel: {os_info['kernel']}")

        # Hardware
        hw = snapshot.hardware
        if hw:
            if hw.get("cpu_model"):
                lines.append(f"CPU: {hw['cpu_model']}")
            if hw.get("memory_total_gb"):
                lines.append(f"RAM: {hw['memory_total_gb']:.1f} GB")

        # Storage summary
        if snapshot.storage:
            total_gb = sum(s.get("total_gb", 0) for s in snapshot.storage)
            free_gb = sum(s.get("free_gb", 0) for s in snapshot.storage)
            lines.append(f"Storage: {free_gb:.0f} GB free of {total_gb:.0f} GB")

        # Services
        running = [s for s in snapshot.services if s.get("active")]
        if running:
            lines.append(f"Services: {len(running)} running")

        # Containers
        if snapshot.containers.get("containers"):
            lines.append(f"Containers: {len(snapshot.containers['containers'])} running")

        return "\n".join(lines)

    def _get_hostname(self) -> str:
        """Get the system hostname."""
        try:
            import socket
            return socket.gethostname()
        except Exception:
            return os.environ.get("HOSTNAME", "unknown")

    def _get_os_info(self) -> dict[str, Any]:
        """Get OS and kernel information."""
        info: dict[str, Any] = {}

        # Read /etc/os-release
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if "=" in line:
                        key, _, value = line.strip().partition("=")
                        value = value.strip('"')
                        if key == "NAME":
                            info["distro"] = value
                        elif key == "VERSION_ID":
                            info["version"] = value
                        elif key == "ID":
                            info["id"] = value
                        elif key == "ID_LIKE":
                            info["family"] = value
        except Exception as e:
            logger.debug("Could not read /etc/os-release: %s", e)

        # Kernel version
        try:
            result = subprocess.run(
                ["uname", "-r"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["kernel"] = result.stdout.strip()
        except Exception as e:
            logger.debug("Could not get kernel version: %s", e)

        # Architecture
        try:
            result = subprocess.run(
                ["uname", "-m"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["arch"] = result.stdout.strip()
        except Exception as e:
            logger.debug("Could not get architecture: %s", e)

        # Uptime
        try:
            sys_info = linux_tools.get_system_info()
            info["uptime"] = sys_info.uptime
        except Exception as e:
            logger.debug("Could not get uptime: %s", e)

        return info

    def _get_hardware_info(self) -> dict[str, Any]:
        """Get hardware information."""
        info: dict[str, Any] = {}

        try:
            sys_info = linux_tools.get_system_info()
            info["cpu_model"] = sys_info.cpu_model
            info["cpu_cores"] = sys_info.cpu_cores
            info["memory_total_gb"] = round(sys_info.memory_total_mb / 1024, 2)
            info["memory_used_gb"] = round(sys_info.memory_used_mb / 1024, 2)
            info["memory_percent"] = round(
                (sys_info.memory_used_mb / sys_info.memory_total_mb) * 100, 1
            ) if sys_info.memory_total_mb > 0 else 0
        except Exception as e:
            logger.debug("Could not get system info: %s", e)

        # GPU info (basic)
        try:
            result = subprocess.run(
                ["lspci"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                gpus = []
                for line in result.stdout.splitlines():
                    if "VGA" in line or "3D" in line or "Display" in line:
                        gpus.append(line.split(": ", 1)[-1] if ": " in line else line)
                if gpus:
                    info["gpus"] = gpus
        except Exception as e:
            logger.debug("Could not get GPU info: %s", e)

        return info

    def _get_network_info(self) -> dict[str, Any]:
        """Get network configuration."""
        try:
            return linux_tools.get_network_info()
        except Exception as e:
            logger.debug("Could not get network info: %s", e)
            return {}

    def _get_services(self) -> list[dict[str, Any]]:
        """Get list of ALL running services."""
        try:
            services = linux_tools.list_services(show_inactive=False)
            # Include ALL running services - no limit
            return [
                {
                    "name": s.name,
                    "description": s.description,
                    "active": s.active,
                    "enabled": s.enabled,
                }
                for s in services
            ]
        except Exception as e:
            logger.debug("Could not list services: %s", e)
            return []

    def _get_packages(self) -> dict[str, Any]:
        """Get ALL installed packages."""
        info: dict[str, Any] = {
            "manager": None,
            "installed": [],  # Full list of installed packages
            "total_count": 0,
        }

        try:
            pm = linux_tools.detect_package_manager()
            info["manager"] = pm

            if pm is None:
                return info

            # Get full package list based on package manager
            list_cmds = {
                "apt": ["dpkg-query", "-W", "-f=${Package}\n"],
                "dnf": ["rpm", "-qa", "--qf", "%{NAME}\n"],
                "yum": ["rpm", "-qa", "--qf", "%{NAME}\n"],
                "pacman": ["pacman", "-Qq"],
                "zypper": ["rpm", "-qa", "--qf", "%{NAME}\n"],
                "apk": ["apk", "list", "-I"],
            }

            if pm in list_cmds:
                try:
                    result = subprocess.run(
                        list_cmds[pm],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        packages = []
                        for line in result.stdout.strip().splitlines():
                            pkg = line.strip()
                            if pkg:
                                # For apk, strip version info
                                if pm == "apk" and " " in pkg:
                                    pkg = pkg.split()[0]
                                packages.append(pkg)
                        info["installed"] = sorted(packages)
                        info["total_count"] = len(packages)
                except Exception as e:
                    logger.debug("Could not list packages: %s", e)

        except Exception as e:
            logger.debug("Could not get package info: %s", e)

        return info

    def _get_containers(self) -> dict[str, Any]:
        """Get container runtime, ALL containers, and ALL images."""
        info: dict[str, Any] = {
            "runtime": None,
            "running_containers": [],
            "all_containers": [],
            "images": [],
        }

        try:
            runtime = linux_tools.detect_container_runtime()
            info["runtime"] = runtime

            if runtime:
                # Get ALL containers (running and stopped)
                all_containers = linux_tools.list_containers(all_containers=True)
                info["all_containers"] = all_containers

                # Also track just running ones for quick reference
                info["running_containers"] = [
                    c for c in all_containers
                    if c.get("status", "").lower().startswith("up")
                ]

                # Get ALL images
                images = linux_tools.list_container_images()
                info["images"] = images

        except Exception as e:
            logger.debug("Could not get container info: %s", e)

        return info

    def _get_users(self) -> list[dict[str, Any]]:
        """Get list of users."""
        try:
            users = linux_tools.list_users(system_users=False)
            return users[:20]  # Limit to 20 users
        except Exception as e:
            logger.debug("Could not list users: %s", e)
            return []

    def _get_environment(self) -> dict[str, Any]:
        """Get environment information."""
        try:
            return linux_tools.get_environment_info()
        except Exception as e:
            logger.debug("Could not get environment info: %s", e)
            return {}

    def _get_storage(self) -> list[dict[str, Any]]:
        """Get storage/disk information."""
        storage = []

        # Common mount points to check
        mount_points = ["/", "/home", "/var", "/tmp", "/opt"]

        for path in mount_points:
            if os.path.exists(path):
                try:
                    info = linux_tools.get_disk_usage(path)
                    storage.append({
                        "path": path,
                        "total_gb": info.total_gb,
                        "used_gb": info.used_gb,
                        "free_gb": info.free_gb,
                        "percent_used": info.percent_used,
                    })
                except Exception as e:
                    logger.debug("Could not get disk usage for %s: %s", path, e)

        return storage

    def _get_recent_logs(self) -> list[str]:
        """Get recent important log entries."""
        logs = []

        try:
            # Get recent boot messages
            entries = linux_tools.get_boot_logs(current_boot=True, lines=20)
            for entry in entries[:10]:
                if isinstance(entry, dict):
                    logs.append(f"[boot] {entry.get('message', '')}")
                else:
                    logs.append(f"[boot] {entry}")
        except Exception as e:
            logger.debug("Could not get boot logs: %s", e)

        try:
            # Get failed services
            failed = linux_tools.get_failed_services()
            for svc in failed[:5]:
                if isinstance(svc, dict):
                    logs.append(f"[failed] {svc.get('name', 'unknown')}: {svc.get('description', '')}")
        except Exception as e:
            logger.debug("Could not get failed services: %s", e)

        return logs

    def cleanup_old_snapshots(self, keep_days: int = 30) -> int:
        """Remove snapshots older than keep_days."""
        cutoff = (datetime.now(UTC) - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        cursor = self._db._execute(
            "DELETE FROM system_snapshots WHERE date < ?",
            (cutoff,),
        )
        self._db.connect().commit()
        return cursor.rowcount


def build_rag_context(snapshot: SystemSnapshot) -> str:
    """Build RAG context string from a system snapshot.

    This creates a comprehensive system state summary for the LLM,
    including ALL services, packages, and containers.
    """
    lines = []
    lines.append("=== SYSTEM STATE (as of {}) ===".format(
        snapshot.captured_at[:10] if snapshot.captured_at else "unknown"
    ))
    lines.append("")

    # Hostname and OS
    if snapshot.hostname:
        lines.append(f"Hostname: {snapshot.hostname}")

    os_info = snapshot.os_info
    if os_info:
        distro = os_info.get("distro", "Linux")
        version = os_info.get("version", "")
        kernel = os_info.get("kernel", "")
        arch = os_info.get("arch", "")
        lines.append(f"OS: {distro} {version} ({arch})")
        if kernel:
            lines.append(f"Kernel: {kernel}")
        if os_info.get("uptime"):
            lines.append(f"Uptime: {os_info['uptime']}")

    lines.append("")

    # Hardware
    hw = snapshot.hardware
    if hw:
        if hw.get("cpu_model"):
            cores = hw.get("cpu_cores", "")
            cores_str = f" ({cores} cores)" if cores else ""
            lines.append(f"CPU: {hw['cpu_model']}{cores_str}")
        if hw.get("memory_total_gb"):
            used = hw.get("memory_used_gb", 0)
            total = hw["memory_total_gb"]
            pct = hw.get("memory_percent", 0)
            lines.append(f"Memory: {used:.1f} GB / {total:.1f} GB ({pct:.0f}% used)")
        if hw.get("gpus"):
            for gpu in hw["gpus"]:
                lines.append(f"GPU: {gpu}")

    lines.append("")

    # Storage
    if snapshot.storage:
        lines.append("STORAGE:")
        for disk in snapshot.storage:
            path = disk.get("path", "/")
            free = disk.get("free_gb", 0)
            total = disk.get("total_gb", 0)
            pct = disk.get("percent_used", 0)
            lines.append(f"  {path}: {free:.0f} GB free / {total:.0f} GB ({pct:.0f}% used)")

    lines.append("")

    # Network
    net = snapshot.network
    if net:
        interfaces = net.get("interfaces", [])
        if interfaces:
            lines.append("NETWORK INTERFACES:")
            for iface in interfaces:
                name = iface.get("name", "")
                addrs = iface.get("addresses", [])
                addr_str = ", ".join(addrs) if addrs else "no IP"
                lines.append(f"  {name}: {addr_str}")

    lines.append("")

    # ALL Services
    if snapshot.services:
        running = [s for s in snapshot.services if s.get("active")]
        lines.append(f"RUNNING SERVICES ({len(running)} total):")
        for svc in running:
            name = svc.get("name", "")
            desc = svc.get("description", "")
            enabled = "enabled" if svc.get("enabled") else "disabled"
            if desc:
                lines.append(f"  {name}: {desc} [{enabled}]")
            else:
                lines.append(f"  {name} [{enabled}]")

    lines.append("")

    # ALL Packages
    pkgs = snapshot.packages
    if pkgs:
        pm = pkgs.get("manager", "unknown")
        installed = pkgs.get("installed", [])
        total = pkgs.get("total_count", len(installed))
        lines.append(f"INSTALLED PACKAGES ({pm}, {total} total):")
        if installed:
            # Group into lines of ~10 packages each for readability
            chunk_size = 10
            for i in range(0, len(installed), chunk_size):
                chunk = installed[i:i + chunk_size]
                lines.append(f"  {', '.join(chunk)}")

    lines.append("")

    # ALL Containers
    containers = snapshot.containers
    if containers.get("runtime"):
        runtime = containers["runtime"]
        running_containers = containers.get("running_containers", [])
        all_containers = containers.get("all_containers", [])
        images = containers.get("images", [])

        lines.append(f"CONTAINER RUNTIME: {runtime}")
        lines.append("")

        if running_containers:
            lines.append(f"RUNNING CONTAINERS ({len(running_containers)}):")
            for c in running_containers:
                name = c.get("name", c.get("id", "unknown"))
                image = c.get("image", "")
                status = c.get("status", "")
                lines.append(f"  {name}: {image} [{status}]")
        else:
            lines.append("RUNNING CONTAINERS: none")

        # Show stopped containers separately
        stopped = [c for c in all_containers if c not in running_containers]
        if stopped:
            lines.append("")
            lines.append(f"STOPPED CONTAINERS ({len(stopped)}):")
            for c in stopped:
                name = c.get("name", c.get("id", "unknown"))
                image = c.get("image", "")
                status = c.get("status", "")
                lines.append(f"  {name}: {image} [{status}]")

        if images:
            lines.append("")
            lines.append(f"CONTAINER IMAGES ({len(images)}):")
            for img in images:
                if isinstance(img, dict):
                    repo = img.get("repository", img.get("name", "unknown"))
                    tag = img.get("tag", "latest")
                    size = img.get("size", "")
                    size_str = f" ({size})" if size else ""
                    lines.append(f"  {repo}:{tag}{size_str}")
                else:
                    lines.append(f"  {img}")

    lines.append("")

    # Users
    if snapshot.users:
        lines.append("USERS:")
        for user in snapshot.users:
            username = user.get("username", "")
            uid = user.get("uid", "")
            groups = user.get("groups", [])
            groups_str = f" (groups: {', '.join(groups)})" if groups else ""
            if uid:
                lines.append(f"  {username} (uid={uid}){groups_str}")
            else:
                lines.append(f"  {username}{groups_str}")

    # Recent issues
    if snapshot.recent_logs:
        failed = [log for log in snapshot.recent_logs if "[failed]" in log]
        if failed:
            lines.append("")
            lines.append("RECENT ISSUES:")
            for log in failed:
                lines.append(f"  {log}")

    lines.append("")
    lines.append("=== END SYSTEM STATE ===")

    return "\n".join(lines)


def get_or_refresh_context(db: Database) -> str:
    """Get today's system context, refreshing if needed.

    This is the main entry point for the agent to get system context.
    It automatically captures a new snapshot if one doesn't exist for today.
    """
    indexer = SystemIndexer(db)

    # Check if we need a fresh snapshot
    if indexer.needs_refresh():
        logger.info("Daily system snapshot needed, capturing...")
        snapshot = indexer.capture_snapshot()
    else:
        snapshot = indexer.get_today_snapshot()

    if snapshot is None:
        return ""

    return build_rag_context(snapshot)
