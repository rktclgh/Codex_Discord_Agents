#!/bin/bash

set -euo pipefail

SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed." >&2
  exit 1
fi

if ! tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  echo "tmux session '${SESSION_NAME}' does not exist. Start it first." >&2
  exit 1
fi

exec tmux attach-session -t "${SESSION_NAME}"
