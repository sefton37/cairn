"""Bash command execution with safety checks and natural language translation.

This module provides:
- Safe command execution with timeouts
- Dangerous command detection and warnings
- Common command templates for natural language translation
- Command history tracking
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CommandRisk(Enum):
    """Risk level for a command."""

    LOW = "low"  # Safe read-only commands
    MEDIUM = "medium"  # Commands that modify user data
    HIGH = "high"  # System-level commands, potentially destructive
    CRITICAL = "critical"  # Extremely dangerous, could break system


@dataclass
class CommandProposal:
    """A proposed command awaiting user approval."""

    proposal_id: str
    command: str
    description: str
    risk_level: CommandRisk
    warnings: list[str]
    created_at: datetime = field(default_factory=datetime.now)
    approved: bool = False
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "command": self.command,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "warnings": self.warnings,
            "created_at": self.created_at.isoformat(),
            "approved": self.approved,
            "executed": self.executed,
        }


@dataclass
class CommandResult:
    """Result of executing a command."""

    proposal_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "success": self.success,
        }


# Pattern-based risk detection
DANGEROUS_PATTERNS: list[tuple[str, CommandRisk, str]] = [
    # Critical - could destroy system or data
    (r"\brm\s+(-rf?|--recursive).*(/|~|\$HOME)", CommandRisk.CRITICAL, "Recursive delete on important directory"),
    (r"\brm\s+-rf?\s+/", CommandRisk.CRITICAL, "Deleting root filesystem"),
    (r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", CommandRisk.CRITICAL, "Fork bomb detected"),
    (r">\s*/dev/sd[a-z]", CommandRisk.CRITICAL, "Writing directly to disk device"),
    (r"dd\s+.*of=/dev/sd", CommandRisk.CRITICAL, "Direct disk write with dd"),
    (r"mkfs\.", CommandRisk.CRITICAL, "Filesystem format command"),
    (r"\bformat\b", CommandRisk.CRITICAL, "Format command"),

    # High risk - system-level changes
    (r"\bsudo\b", CommandRisk.HIGH, "Requires root privileges"),
    (r"\bsu\s+-?\s*$", CommandRisk.HIGH, "Switching to root user"),
    (r"\bchmod\s+777", CommandRisk.HIGH, "Setting world-writable permissions"),
    (r"\bchown\s+-R", CommandRisk.HIGH, "Recursive ownership change"),
    (r"\bsystemctl\s+(stop|disable|mask)", CommandRisk.HIGH, "Stopping/disabling system service"),
    (r"\bservice\s+\S+\s+stop", CommandRisk.HIGH, "Stopping system service"),
    (r"\bkill\s+-9", CommandRisk.HIGH, "Force killing process"),
    (r"\bkillall\b", CommandRisk.HIGH, "Killing all processes by name"),
    (r"\bpkill\b", CommandRisk.HIGH, "Killing processes by pattern"),
    (r"\biptables\b", CommandRisk.HIGH, "Modifying firewall rules"),
    (r"\bufw\s+(disable|delete|reset)", CommandRisk.HIGH, "Modifying firewall"),
    (r"\bnohup\b.*&", CommandRisk.HIGH, "Running persistent background process"),
    (r"\bcrontab\s+-[re]", CommandRisk.HIGH, "Modifying cron jobs"),
    (r"\bpasswd\b", CommandRisk.HIGH, "Changing password"),
    (r"\buseradd\b|\buserdel\b|\busermod\b", CommandRisk.HIGH, "User account modification"),
    (r"\bgroupadd\b|\bgroupdel\b|\bgroupmod\b", CommandRisk.HIGH, "Group modification"),
    (r">\s*/etc/", CommandRisk.HIGH, "Writing to system config"),
    (r"\bapt\s+(remove|purge|autoremove)", CommandRisk.HIGH, "Removing packages"),
    (r"\byum\s+(remove|erase)", CommandRisk.HIGH, "Removing packages"),
    (r"\bdnf\s+remove", CommandRisk.HIGH, "Removing packages"),
    (r"\bpacman\s+-R", CommandRisk.HIGH, "Removing packages"),

    # Medium risk - data modification
    (r"\brm\b", CommandRisk.MEDIUM, "Deleting files"),
    (r"\bmv\b", CommandRisk.MEDIUM, "Moving/renaming files"),
    (r"\bcp\s+-r", CommandRisk.MEDIUM, "Recursive file copy"),
    (r">\s*\S+", CommandRisk.MEDIUM, "File redirection (may overwrite)"),
    (r"\bchmod\b", CommandRisk.MEDIUM, "Changing file permissions"),
    (r"\bchown\b", CommandRisk.MEDIUM, "Changing file ownership"),
    (r"\bgit\s+push", CommandRisk.MEDIUM, "Pushing to remote repository"),
    (r"\bgit\s+reset\s+--hard", CommandRisk.MEDIUM, "Hard reset git history"),
    (r"\bgit\s+clean\s+-fd", CommandRisk.MEDIUM, "Removing untracked files"),
    (r"\bdocker\s+(rm|rmi|prune)", CommandRisk.MEDIUM, "Removing Docker resources"),
    (r"\bpodman\s+(rm|rmi|prune)", CommandRisk.MEDIUM, "Removing Podman resources"),
    (r"\bnpm\s+uninstall", CommandRisk.MEDIUM, "Removing npm packages"),
    (r"\bpip\s+uninstall", CommandRisk.MEDIUM, "Removing Python packages"),
]

# Safe read-only commands
SAFE_COMMANDS = {
    "ls", "ll", "la", "dir",
    "cat", "head", "tail", "less", "more",
    "grep", "egrep", "fgrep", "rg",
    "find", "locate", "which", "whereis", "type",
    "pwd", "cd",
    "ps", "top", "htop", "pgrep",
    "df", "du", "free",
    "whoami", "id", "who", "w", "users",
    "date", "cal", "uptime",
    "hostname", "uname",
    "ip", "ifconfig", "netstat", "ss",
    "ping", "traceroute", "nslookup", "dig", "host",
    "curl", "wget",  # read-only use
    "git status", "git log", "git diff", "git branch", "git remote",
    "docker ps", "docker images", "docker logs",
    "systemctl status", "systemctl list-units",
    "journalctl",
    "env", "printenv", "echo",
    "file", "stat", "wc",
    "sort", "uniq", "cut", "awk", "sed",  # when used for reading
    "man", "info", "help",
    "history",
}

# Common natural language to command mappings
COMMAND_TEMPLATES: dict[str, dict[str, Any]] = {
    "ip_address": {
        "patterns": [r"ip\s*address", r"my\s*ip", r"what.*ip", r"show.*ip"],
        "command": "ip addr show | grep -E 'inet ' | awk '{print $2}'",
        "description": "Show IP addresses of all network interfaces",
    },
    "public_ip": {
        "patterns": [r"public\s*ip", r"external\s*ip", r"internet\s*ip"],
        "command": "curl -s ifconfig.me || curl -s icanhazip.com",
        "description": "Get your public/external IP address",
    },
    "disk_space": {
        "patterns": [r"disk\s*(space|usage)", r"storage", r"how much space", r"free space"],
        "command": "df -h",
        "description": "Show disk space usage for all mounted filesystems",
    },
    "memory": {
        "patterns": [r"memory\s*(usage)?", r"ram", r"how much memory"],
        "command": "free -h",
        "description": "Show memory (RAM) usage",
    },
    "running_processes": {
        "patterns": [r"running\s*process", r"what.*running", r"process\s*list"],
        "command": "ps aux --sort=-%cpu | head -20",
        "description": "Show top 20 running processes by CPU usage",
    },
    "find_file": {
        "patterns": [r"find\s*(a\s*)?file", r"locate\s*file", r"where\s*is"],
        "command": "find . -name '{filename}' -type f 2>/dev/null | head -20",
        "description": "Find files matching a pattern",
        "requires": ["filename"],
    },
    "find_text": {
        "patterns": [r"find\s*text", r"search\s*(for|in)", r"grep\s*for", r"look\s*for.*in"],
        "command": "grep -rn '{pattern}' {path} 2>/dev/null | head -50",
        "description": "Search for text in files",
        "requires": ["pattern"],
        "optional": {"path": "."},
    },
    "open_ports": {
        "patterns": [r"open\s*ports?", r"listening\s*ports?", r"what.*port", r"network\s*ports?"],
        "command": "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null",
        "description": "Show listening network ports",
    },
    "services": {
        "patterns": [r"(list|show)\s*services?", r"running\s*services?", r"systemd\s*services?"],
        "command": "systemctl list-units --type=service --state=running",
        "description": "List running systemd services",
    },
    "stop_service": {
        "patterns": [r"stop\s*(the\s*)?(service|daemon)", r"disable.*service"],
        "command": "sudo systemctl stop {service_name}",
        "description": "Stop a systemd service",
        "requires": ["service_name"],
    },
    "start_service": {
        "patterns": [r"start\s*(the\s*)?(service|daemon)"],
        "command": "sudo systemctl start {service_name}",
        "description": "Start a systemd service",
        "requires": ["service_name"],
    },
    "disable_service": {
        "patterns": [r"disable.*auto.*start", r"prevent.*start", r"disable\s*service"],
        "command": "sudo systemctl disable {service_name}",
        "description": "Disable a service from starting at boot",
        "requires": ["service_name"],
    },
    "enable_service": {
        "patterns": [r"enable.*auto.*start", r"enable\s*service", r"start.*boot"],
        "command": "sudo systemctl enable {service_name}",
        "description": "Enable a service to start at boot",
        "requires": ["service_name"],
    },
    "kill_process": {
        "patterns": [r"kill\s*(the\s*)?process", r"stop\s*(the\s*)?process", r"terminate"],
        "command": "kill {pid}",
        "description": "Terminate a process by PID",
        "requires": ["pid"],
    },
    "kill_by_name": {
        "patterns": [r"kill.*by\s*name", r"kill\s*all\s*{name}"],
        "command": "pkill -f '{process_name}'",
        "description": "Kill processes matching a name pattern",
        "requires": ["process_name"],
    },
    "cpu_usage": {
        "patterns": [r"cpu\s*usage", r"cpu\s*load", r"processor"],
        "command": "top -bn1 | head -5 && echo '---' && ps aux --sort=-%cpu | head -10",
        "description": "Show CPU usage and top processes",
    },
    "docker_containers": {
        "patterns": [r"docker\s*container", r"running\s*container"],
        "command": "docker ps -a",
        "description": "List all Docker containers",
    },
    "docker_stop": {
        "patterns": [r"stop\s*docker", r"stop\s*container"],
        "command": "docker stop {container}",
        "description": "Stop a Docker container",
        "requires": ["container"],
    },
    "file_size": {
        "patterns": [r"file\s*size", r"how\s*big", r"size\s*of"],
        "command": "du -sh {path}",
        "description": "Show size of file or directory",
        "requires": ["path"],
    },
    "directory_contents": {
        "patterns": [r"list\s*(files|directory|folder)", r"what.*in\s*(this\s*)?(folder|directory|dir)"],
        "command": "ls -la {path}",
        "description": "List directory contents with details",
        "optional": {"path": "."},
    },
    "system_info": {
        "patterns": [r"system\s*info", r"about\s*(this\s*)?system", r"machine\s*info"],
        "command": "uname -a && echo '---' && cat /etc/os-release | head -5",
        "description": "Show system information",
    },
    "uptime": {
        "patterns": [r"uptime", r"how\s*long.*running", r"system\s*uptime"],
        "command": "uptime",
        "description": "Show system uptime",
    },
    "current_user": {
        "patterns": [r"current\s*user", r"who\s*am\s*i", r"logged\s*in\s*as"],
        "command": "whoami && id",
        "description": "Show current user and group information",
    },
    "environment": {
        "patterns": [r"environment\s*variable", r"env\s*var", r"show\s*env"],
        "command": "env | sort",
        "description": "Show environment variables",
    },
    "network_connections": {
        "patterns": [r"network\s*connection", r"active\s*connection", r"established\s*connection"],
        "command": "ss -tunap 2>/dev/null | head -30",
        "description": "Show active network connections",
    },
    "logs": {
        "patterns": [r"(system\s*)?logs?", r"journal", r"syslog"],
        "command": "journalctl -n 50 --no-pager",
        "description": "Show recent system logs",
    },
    "service_logs": {
        "patterns": [r"logs?\s*(for|of)\s*{service}", r"{service}\s*logs?"],
        "command": "journalctl -u {service_name} -n 50 --no-pager",
        "description": "Show logs for a specific service",
        "requires": ["service_name"],
    },
}


# In-memory storage for pending proposals
_pending_proposals: dict[str, CommandProposal] = {}


def analyze_command_risk(command: str) -> tuple[CommandRisk, list[str]]:
    """Analyze a command and return its risk level and any warnings."""
    warnings: list[str] = []
    max_risk = CommandRisk.LOW

    # Risk level ordering for comparison
    risk_order = {
        CommandRisk.LOW: 0,
        CommandRisk.MEDIUM: 1,
        CommandRisk.HIGH: 2,
        CommandRisk.CRITICAL: 3,
    }

    # Check first word against safe commands
    first_word = command.split()[0] if command.split() else ""
    if first_word in SAFE_COMMANDS:
        # Still check for dangerous patterns in arguments
        pass

    # Check against dangerous patterns
    for pattern, risk, warning in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            if risk_order[risk] > risk_order[max_risk]:
                max_risk = risk
            warnings.append(warning)

    # Check for pipes to dangerous commands
    if "|" in command:
        parts = command.split("|")
        for part in parts[1:]:  # Skip first part
            part = part.strip()
            if part.startswith("sh") or part.startswith("bash"):
                warnings.append("Piping to shell - could execute arbitrary code")
                max_risk = CommandRisk.HIGH
            if part.startswith("sudo"):
                warnings.append("Piping to sudo")
                max_risk = CommandRisk.HIGH

    # Check for command substitution
    if "$(" in command or "`" in command:
        warnings.append("Contains command substitution")
        if max_risk == CommandRisk.LOW:
            max_risk = CommandRisk.MEDIUM

    return max_risk, warnings


def create_proposal(command: str, description: str) -> CommandProposal:
    """Create a command proposal for user approval."""
    risk_level, warnings = analyze_command_risk(command)

    proposal = CommandProposal(
        proposal_id=str(uuid.uuid4()),
        command=command,
        description=description,
        risk_level=risk_level,
        warnings=warnings,
    )

    _pending_proposals[proposal.proposal_id] = proposal
    return proposal


def get_proposal(proposal_id: str) -> CommandProposal | None:
    """Get a pending proposal by ID."""
    return _pending_proposals.get(proposal_id)


def approve_proposal(proposal_id: str) -> CommandProposal | None:
    """Mark a proposal as approved."""
    proposal = _pending_proposals.get(proposal_id)
    if proposal:
        proposal.approved = True
    return proposal


def execute_proposal(
    proposal_id: str,
    timeout: int = 30,
    cwd: str | None = None,
) -> CommandResult | None:
    """Execute an approved proposal."""
    proposal = _pending_proposals.get(proposal_id)
    if not proposal:
        return None

    if not proposal.approved:
        return None

    if proposal.executed:
        return None

    proposal.executed = True

    import time
    start = time.time()

    try:
        result = subprocess.run(
            proposal.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "TERM": "dumb"},
        )

        duration_ms = int((time.time() - start) * 1000)

        return CommandResult(
            proposal_id=proposal_id,
            command=proposal.command,
            exit_code=result.returncode,
            stdout=result.stdout[:50000],  # Limit output size
            stderr=result.stderr[:10000],
            duration_ms=duration_ms,
            success=result.returncode == 0,
        )

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start) * 1000)
        return CommandResult(
            proposal_id=proposal_id,
            command=proposal.command,
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            duration_ms=duration_ms,
            success=False,
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return CommandResult(
            proposal_id=proposal_id,
            command=proposal.command,
            exit_code=-1,
            stdout="",
            stderr=str(e),
            duration_ms=duration_ms,
            success=False,
        )


def clear_old_proposals(max_age_seconds: int = 3600) -> int:
    """Clear proposals older than max_age_seconds. Returns count of cleared."""
    now = datetime.now()
    to_remove = []

    for pid, proposal in _pending_proposals.items():
        age = (now - proposal.created_at).total_seconds()
        if age > max_age_seconds:
            to_remove.append(pid)

    for pid in to_remove:
        del _pending_proposals[pid]

    return len(to_remove)


def suggest_command_from_intent(intent: str) -> dict[str, Any] | None:
    """Try to match natural language intent to a command template."""
    intent_lower = intent.lower()

    for template_name, template in COMMAND_TEMPLATES.items():
        for pattern in template["patterns"]:
            if re.search(pattern, intent_lower, re.IGNORECASE):
                return {
                    "template_name": template_name,
                    "command": template["command"],
                    "description": template["description"],
                    "requires": template.get("requires", []),
                    "optional": template.get("optional", {}),
                }

    return None


def build_command_from_template(
    template_name: str,
    params: dict[str, str] | None = None,
) -> str | None:
    """Build a command from a template with parameters."""
    template = COMMAND_TEMPLATES.get(template_name)
    if not template:
        return None

    command = template["command"]
    params = params or {}

    # Fill in required parameters
    for req in template.get("requires", []):
        if req not in params:
            return None
        command = command.replace("{" + req + "}", shlex.quote(params[req]))

    # Fill in optional parameters with defaults
    for opt, default in template.get("optional", {}).items():
        value = params.get(opt, default)
        command = command.replace("{" + opt + "}", shlex.quote(value))

    return command
