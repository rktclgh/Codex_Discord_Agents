#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
STATE_FILE="${RUNTIME_DIR}/sleep-guard.state"

if ! command -v pmset >/dev/null 2>&1; then
  echo "pmset 명령을 찾을 수 없습니다." >&2
  exit 1
fi

if pmset -g | grep -q "disablesleep[[:space:]]*1"; then
  echo "sleep 방지: ON"
  echo "모드: 시스템 잠자기 차단 + 화면 꺼짐 허용"
  if [[ -f "${STATE_FILE}" ]]; then
    cat "${STATE_FILE}"
  fi
else
  echo "sleep 방지: OFF"
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  echo "tmux 세션: ON (${SESSION_NAME})"
else
  echo "tmux 세션: OFF (${SESSION_NAME})"
fi
