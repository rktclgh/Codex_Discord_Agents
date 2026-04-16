#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
STATE_FILE="${RUNTIME_DIR}/sleep-guard.state"

mkdir -p "${RUNTIME_DIR}"

if ! command -v pmset >/dev/null 2>&1; then
  echo "pmset 명령을 찾을 수 없습니다." >&2
  exit 1
fi

if ! command -v osascript >/dev/null 2>&1; then
  echo "osascript 명령을 찾을 수 없습니다." >&2
  exit 1
fi

if ! tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  "${ROOT_DIR}/scripts/start_agent_team_tmux.sh" --no-attach
fi

osascript -e 'do shell script "pmset -a disablesleep 1" with administrator privileges'
pmset displaysleepnow || true

cat > "${STATE_FILE}" <<EOF
mode=pmset-disablesleep
enabled_at=$(date '+%Y-%m-%d %H:%M:%S')
EOF

echo "잠자기 방지를 켰습니다."
echo "모드: 시스템 잠자기 차단 + 화면은 즉시 꺼짐"
echo "tmux 세션: ${SESSION_NAME}"
echo "설명: 잠자기 버튼을 눌러도 시스템이 최대한 자지 않도록 pmset disablesleep=1 을 사용합니다."
