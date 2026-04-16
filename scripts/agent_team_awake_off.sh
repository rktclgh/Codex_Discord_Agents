#!/bin/bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
STATE_FILE="${RUNTIME_DIR}/sleep-guard.state"

if ! command -v pmset >/dev/null 2>&1; then
  echo "pmset 명령을 찾을 수 없습니다." >&2
  exit 1
fi

if ! command -v osascript >/dev/null 2>&1; then
  echo "osascript 명령을 찾을 수 없습니다." >&2
  exit 1
fi

osascript -e 'do shell script "pmset -a disablesleep 0" with administrator privileges'
rm -f "${STATE_FILE}"
echo "잠자기 방지를 껐습니다."
