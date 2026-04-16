#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
PID_FILE="${RUNTIME_DIR}/caffeinate.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "잠자기 방지 PID 파일이 없습니다. 이미 꺼져 있을 수 있습니다."
  exit 0
fi

pid="$(cat "${PID_FILE}" 2>/dev/null || true)"
if [[ -z "${pid}" ]]; then
  rm -f "${PID_FILE}"
  echo "PID 파일이 비어 있어 정리만 수행했습니다."
  exit 0
fi

if kill -0 "${pid}" 2>/dev/null; then
  kill "${pid}"
  echo "잠자기 방지를 껐습니다. (PID: ${pid})"
else
  echo "해당 PID(${pid})는 이미 종료된 상태입니다."
fi

rm -f "${PID_FILE}"
