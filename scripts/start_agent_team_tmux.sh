#!/bin/bash

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKSPACE_ROOT="${AGENT_TEAM_WORKSPACE_ROOT:-$(cd "${ROOT_DIR}/.." && pwd)}"
SESSION_NAME="${TMUX_AGENT_SESSION:-agent-team}"
RUNTIME_DIR="${TMUX_AGENT_RUNTIME_DIR:-${ROOT_DIR}/.codex-tmp/agent-team}"
VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
PYTHON_CMD="python3"
ENV_FILE="${ROOT_DIR}/.agent_team.env"
ATTACH_AFTER_START=true
RECREATE_SESSION=false

usage() {
  cat <<'EOF'
Usage: ./scripts/start_agent_team_tmux.sh [--no-attach] [--recreate]

Options:
  --no-attach   Create the tmux session without attaching to it
  --recreate    Kill the existing session first, then rebuild it
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-attach)
      ATTACH_AFTER_START=false
      shift
      ;;
    --recreate)
      RECREATE_SESSION=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed. Install it first." >&2
  exit 1
fi

if [[ -x "${VENV_PYTHON}" ]]; then
  PYTHON_CMD="${VENV_PYTHON}"
fi

mkdir -p "${RUNTIME_DIR}/inbox" "${RUNTIME_DIR}/outbox"

if [[ ! -f "${RUNTIME_DIR}/tasks.json" ]]; then
  printf '{}\n' > "${RUNTIME_DIR}/tasks.json"
fi

if [[ ! -f "${RUNTIME_DIR}/role-state.json" ]]; then
  printf '{}\n' > "${RUNTIME_DIR}/role-state.json"
fi

touch "${RUNTIME_DIR}/events.jsonl"

ROLES=(
  "pm"
  "be-lead"
  "be-dev"
  "fe-lead"
  "fe-dev"
  "qa"
  "security"
  "research"
)

for role in "${ROLES[@]}"; do
  touch "${RUNTIME_DIR}/inbox/${role}.jsonl"
  touch "${RUNTIME_DIR}/outbox/${role}.jsonl"
done

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  if [[ "${RECREATE_SESSION}" == "true" ]]; then
    tmux kill-session -t "${SESSION_NAME}"
  else
    echo "tmux session '${SESSION_NAME}' already exists."
    if [[ "${ATTACH_AFTER_START}" == "true" ]]; then
      exec tmux attach-session -t "${SESSION_NAME}"
    fi
    exit 0
  fi
fi

send_role_banner() {
  local target="$1"
  local role_name="$2"
  local hint="$3"

  tmux send-keys -t "${target}" "clear" C-m
  tmux send-keys -t "${target}" "printf '\n[%s]\n%s\nRuntime: %s\nWorkspace: %s\n\n' '${role_name}' '${hint}' '${RUNTIME_DIR}' '${WORKSPACE_ROOT}'" C-m
}

runner_command() {
  local module="$1"
  shift
  if [[ -f "${ENV_FILE}" ]]; then
    printf "set -a; source '%s'; set +a; PYTHONPATH='%s' '%s' -m %s %s" \
      "${ENV_FILE}" "${ROOT_DIR}" "${PYTHON_CMD}" "${module}" "$*"
  else
    printf "PYTHONPATH='%s' '%s' -m %s %s" \
      "${ROOT_DIR}" "${PYTHON_CMD}" "${module}" "$*"
  fi
}

tmux new-session -d -s "${SESSION_NAME}" -n router -c "${ROOT_DIR}"
tmux set-option -t "${SESSION_NAME}" mouse on
tmux set-option -t "${SESSION_NAME}" remain-on-exit on
tmux set-window-option -t "${SESSION_NAME}" pane-border-status top

send_role_banner "${SESSION_NAME}:router" "Router" "Discord router / orchestrator entrypoint"
tmux send-keys -t "${SESSION_NAME}:router" "$(runner_command agent_team.discord_router --mode auto)" C-m

tmux new-window -t "${SESSION_NAME}" -n pm -c "${ROOT_DIR}"
send_role_banner "${SESSION_NAME}:pm" "PM" "Main agent (team lead) / shared task list owner"
tmux send-keys -t "${SESSION_NAME}:pm" "$(runner_command agent_team.runner --role pm)" C-m

tmux new-window -t "${SESSION_NAME}" -n backend -c "${ROOT_DIR}"
tmux split-window -h -t "${SESSION_NAME}:backend" -c "${ROOT_DIR}"
tmux select-layout -t "${SESSION_NAME}:backend" even-horizontal
send_role_banner "${SESSION_NAME}:backend.0" "BE Lead" "20+ year backend lead / packet split / backend review"
send_role_banner "${SESSION_NAME}:backend.1" "BE Dev" "Backend implementation worker / returns work to BE Lead"
tmux send-keys -t "${SESSION_NAME}:backend.0" "$(runner_command agent_team.runner --role be-lead)" C-m
tmux send-keys -t "${SESSION_NAME}:backend.1" "$(runner_command agent_team.runner --role be-dev)" C-m
tmux select-pane -t "${SESSION_NAME}:backend.0" -T "BE Lead"
tmux select-pane -t "${SESSION_NAME}:backend.1" -T "BE Dev"

tmux new-window -t "${SESSION_NAME}" -n frontend -c "${ROOT_DIR}"
tmux split-window -h -t "${SESSION_NAME}:frontend" -c "${ROOT_DIR}"
tmux select-layout -t "${SESSION_NAME}:frontend" even-horizontal
send_role_banner "${SESSION_NAME}:frontend.0" "FE Lead" "20+ year frontend lead / packet split / frontend review"
send_role_banner "${SESSION_NAME}:frontend.1" "FE Dev" "Frontend implementation worker / returns work to FE Lead"
tmux send-keys -t "${SESSION_NAME}:frontend.0" "$(runner_command agent_team.runner --role fe-lead)" C-m
tmux send-keys -t "${SESSION_NAME}:frontend.1" "$(runner_command agent_team.runner --role fe-dev)" C-m
tmux select-pane -t "${SESSION_NAME}:frontend.0" -T "FE Lead"
tmux select-pane -t "${SESSION_NAME}:frontend.1" -T "FE Dev"

tmux new-window -t "${SESSION_NAME}" -n review -c "${ROOT_DIR}"
tmux split-window -h -t "${SESSION_NAME}:review" -c "${ROOT_DIR}"
tmux select-layout -t "${SESSION_NAME}:review" even-horizontal
send_role_banner "${SESSION_NAME}:review.0" "QA" "Failure prediction / Playwright / regression handoff"
send_role_banner "${SESSION_NAME}:review.1" "Security" "20+ year security reviewer / exploitability handoff"
tmux send-keys -t "${SESSION_NAME}:review.0" "$(runner_command agent_team.runner --role qa)" C-m
tmux send-keys -t "${SESSION_NAME}:review.1" "$(runner_command agent_team.runner --role security)" C-m
tmux select-pane -t "${SESSION_NAME}:review.0" -T "QA"
tmux select-pane -t "${SESSION_NAME}:review.1" -T "Security"

tmux new-window -t "${SESSION_NAME}" -n research -c "${ROOT_DIR}"
send_role_banner "${SESSION_NAME}:research" "Research" "Web search / latest libraries / official docs"
tmux send-keys -t "${SESSION_NAME}:research" "$(runner_command agent_team.runner --role research)" C-m

tmux new-window -t "${SESSION_NAME}" -n logs -c "${ROOT_DIR}"
tmux split-window -v -t "${SESSION_NAME}:logs" -c "${ROOT_DIR}"
tmux select-layout -t "${SESSION_NAME}:logs" even-vertical
tmux send-keys -t "${SESSION_NAME}:logs.0" "clear" C-m
tmux send-keys -t "${SESSION_NAME}:logs.0" "echo '[events.jsonl]'; tail -n 30 -f '${RUNTIME_DIR}/events.jsonl'" C-m
tmux send-keys -t "${SESSION_NAME}:logs.1" "clear" C-m
tmux send-keys -t "${SESSION_NAME}:logs.1" "echo '[runtime]'; while true; do clear; printf 'tasks.json\n----------\n'; cat '${RUNTIME_DIR}/tasks.json'; printf '\n\nrole-state.json\n---------------\n'; cat '${RUNTIME_DIR}/role-state.json'; sleep 2; done" C-m
tmux select-pane -t "${SESSION_NAME}:logs.0" -T "Events"
tmux select-pane -t "${SESSION_NAME}:logs.1" -T "Runtime"

tmux select-window -t "${SESSION_NAME}:router"

echo "Created tmux session '${SESSION_NAME}'."
echo "Runtime directory: ${RUNTIME_DIR}"

if [[ "${ATTACH_AFTER_START}" == "true" ]]; then
  exec tmux attach-session -t "${SESSION_NAME}"
fi
