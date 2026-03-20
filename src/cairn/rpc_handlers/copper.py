"""Copper LAN Ollama coordinator — RPC proxy.

Thin synchronous HTTP proxy to the Copper service. All calls use httpx.Client
(not AsyncClient) because ui_rpc_server.py is a synchronous stdio loop.
No call should take longer than 5 seconds.

Auto-start: if Copper is not reachable and the user hasn't explicitly stopped it,
the handler will attempt to spawn `copper serve` as a background process.
"""
import logging
import os
import shutil
import subprocess
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_COPPER_BASE_URL = os.environ.get("COPPER_URL", "http://localhost:11400")
_copper_process: subprocess.Popen | None = None
_last_start_attempt: float = 0.0
_START_COOLDOWN = 10.0  # seconds between auto-start attempts


def _is_copper_reachable() -> bool:
    """Quick check if Copper is responding."""
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{_COPPER_BASE_URL}/api/status")
            return resp.status_code == 200
    except Exception:
        return False


def _ensure_copper_running() -> bool:
    """Start Copper if it's not running. Returns True if Copper is reachable."""
    global _copper_process, _last_start_attempt

    if _is_copper_reachable():
        return True

    # Don't retry too frequently
    now = time.monotonic()
    if now - _last_start_attempt < _START_COOLDOWN:
        return False

    _last_start_attempt = now

    # Check if our previous process is still alive
    if _copper_process is not None:
        if _copper_process.poll() is None:
            # Still running but not reachable yet — give it time
            return False
        # Process exited — clear it
        _copper_process = None

    # Find the copper executable
    copper_bin = shutil.which("copper")
    if copper_bin is None:
        # Try the Copper project's venv
        venv_bin = os.path.expanduser("~/dev/Copper/.venv/bin/copper")
        if os.path.isfile(venv_bin):
            copper_bin = venv_bin
        else:
            logger.warning("Cannot find 'copper' executable to auto-start")
            return False

    logger.info("Auto-starting Copper: %s serve", copper_bin)
    try:
        _copper_process = subprocess.Popen(
            [copper_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach from parent process group
        )
        # Give it a moment to bind the port
        time.sleep(1.0)
        return _is_copper_reachable()
    except Exception as exc:
        logger.warning("Failed to auto-start Copper: %s", exc)
        return False


def handle_copper_proxy(*, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch copper/* RPC methods to Copper's HTTP API."""
    # Strip the 'copper/' prefix
    sub = method.removeprefix("copper/")

    # Handle extract entirely within Cairn — no HTTP call needed.
    if sub == "modelfiles/extract":
        from .copper_extract import extract_system_prompt

        result = extract_system_prompt()
        result["copper_available"] = True
        return result

    # Auto-start Copper if not reachable
    if not _ensure_copper_running():
        return {"copper_available": False, "error": "Copper is starting up..."}

    try:
        with httpx.Client(timeout=5.0) as client:
            if sub == "status":
                resp = client.get(f"{_COPPER_BASE_URL}/api/status")
            elif sub == "nodes":
                resp = client.get(f"{_COPPER_BASE_URL}/api/nodes")
            elif sub == "models":
                resp = client.get(f"{_COPPER_BASE_URL}/api/tags")
            elif sub == "nodes/add":
                resp = client.post(f"{_COPPER_BASE_URL}/api/nodes", json=params)
            elif sub == "nodes/remove":
                name = params.get("name", "")
                resp = client.delete(f"{_COPPER_BASE_URL}/api/nodes/{name}")
            elif sub == "nodes/update":
                # Extract name separately so we don't mutate the caller's dict
                name = params.get("name", "")
                body = {k: v for k, v in params.items() if k != "name"}
                resp = client.patch(f"{_COPPER_BASE_URL}/api/nodes/{name}", json=body)
            elif sub == "pull":
                resp = client.post(f"{_COPPER_BASE_URL}/api/pull", json=params)
            elif sub == "tasks":
                resp = client.get(f"{_COPPER_BASE_URL}/api/tasks")
            elif sub.startswith("tasks/"):
                task_id = sub.removeprefix("tasks/")
                resp = client.get(f"{_COPPER_BASE_URL}/api/tasks/{task_id}")
            elif sub == "modelfiles":
                resp = client.get(f"{_COPPER_BASE_URL}/api/modelfiles")
            elif sub == "modelfiles/create":
                resp = client.post(f"{_COPPER_BASE_URL}/api/modelfiles", json=params)
            elif sub == "modelfiles/get":
                name = params.get("name", "")
                resp = client.get(f"{_COPPER_BASE_URL}/api/modelfiles/{name}")
            elif sub == "modelfiles/build":
                name = params.get("name", "")
                body = {k: v for k, v in params.items() if k != "name"}
                resp = client.post(f"{_COPPER_BASE_URL}/api/modelfiles/{name}/build", json=body)
            elif sub == "modelfiles/delete":
                name = params.get("name", "")
                resp = client.delete(f"{_COPPER_BASE_URL}/api/modelfiles/{name}")
            else:
                return {"error": f"Unknown copper method: {method}", "copper_available": True}

            result = resp.json()
            result["copper_available"] = True
            return result

    except (httpx.ConnectError, ConnectionRefusedError, httpx.TimeoutException) as exc:
        logger.debug("Copper not reachable: %s", exc)
        return {"copper_available": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("Copper proxy error: %s", exc)
        return {"copper_available": False, "error": str(exc)}
