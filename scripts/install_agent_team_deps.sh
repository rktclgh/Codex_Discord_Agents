#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/agent_team/requirements.txt"

echo ""
echo "Installed agent team dependencies into ${VENV_DIR}"
echo "Next steps:"
echo "  1. cp .agent_team.env.example .agent_team.env"
echo "  2. Fill in DISCORD_BOT_TOKEN and your Discord channel IDs"
echo "  3. Recreate tmux session: ./scripts/start_agent_team_tmux.sh --recreate"
