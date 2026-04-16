#!/bin/bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed. Install it first." >&2
  exit 1
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  echo "에이전트 팀은 이미 실행 중입니다. (${SESSION_NAME})"
  exit 0
fi

"${ROOT_DIR}/scripts/start_agent_team_tmux.sh" --no-attach

echo "에이전트 팀을 켰습니다."
echo "tmux 세션: ${SESSION_NAME}"
