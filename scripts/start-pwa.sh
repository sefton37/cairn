#!/usr/bin/env bash
# Start Talking Rock with PWA support over Tailscale.
#
# Tailscale serve handles HTTPS termination — uvicorn runs plain HTTP.
# Ensure 'tailscale serve --bg 8010' is already running before starting.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Verify tailscale serve is active
if ! tailscale serve status 2>/dev/null | grep -q "proxy"; then
    echo "ERROR: tailscale serve is not running."
    echo "Start it with: tailscale serve --bg 8010"
    exit 1
fi

HOSTNAME="$(tailscale status --json | python3 -c \
    'import json,sys; d=json.load(sys.stdin); print(d["Self"]["DNSName"].rstrip("."))')"

echo "Talking Rock PWA available at: https://${HOSTNAME}/app/"
echo "Tailscale proxying HTTPS -> http://127.0.0.1:8010"

# Use PYTHONPATH to find the reos package in src/ and activate the venv
export PYTHONPATH="${PROJECT_DIR}/src"
export VIRTUAL_ENV="${PROJECT_DIR}/.venv"
export PATH="${VIRTUAL_ENV}/bin:${PATH}"

exec python3 -m uvicorn reos.app:app --host 0.0.0.0 --port 8010 --log-level info
