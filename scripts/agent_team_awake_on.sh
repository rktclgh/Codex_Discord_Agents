#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
PID_FILE="${RUNTIME_DIR}/caffeinate.pid"
LOG_FILE="${RUNTIME_DIR}/caffeinate.log"

mkdir -p "${RUNTIME_DIR}"

if ! command -v caffeinate >/dev/null 2>&1; then
  echo "caffeinate 명령을 찾을 수 없습니다." >&2
  exit 1
fi

if [[ -f "${PID_FILE}" ]]; then
  existing_pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "잠자기 방지가 이미 켜져 있습니다. (PID: ${existing_pid})"
    if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
      echo "tmux 세션 '${SESSION_NAME}' 도 실행 중입니다."
    fi
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

if ! tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  "${ROOT_DIR}/scripts/start_agent_team_tmux.sh" --no-attach
fi

nohup caffeinate -dimsu >"${LOG_FILE}" 2>&1 &
pid=$!
echo "${pid}" > "${PID_FILE}"

echo "잠자기 방지를 켰습니다. (PID: ${pid})"
echo "tmux 세션: ${SESSION_NAME}"
echo "로그: ${LOG_FILE}"
