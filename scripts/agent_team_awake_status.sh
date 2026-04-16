#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
PID_FILE="${RUNTIME_DIR}/caffeinate.pid"

if [[ -f "${PID_FILE}" ]]; then
  pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
else
  pid=""
fi

if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
  echo "sleep 방지: ON (PID: ${pid})"
else
  echo "sleep 방지: OFF"
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  echo "tmux 세션: ON (${SESSION_NAME})"
else
  echo "tmux 세션: OFF (${SESSION_NAME})"
fi
