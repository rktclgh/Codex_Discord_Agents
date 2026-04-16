# Discord + tmux Multi-Agent MVP

## Goal
- Run a local multi-agent team from macOS without a database.
- Receive user instructions from Discord.
- Route each instruction to the right role agent.
- Let role agents report progress and handoffs back into Discord.
- Keep PM as the single final reporting surface.

## Non-Goal
- No SQL or persistent database in v1.
- No full autonomous peer-to-peer agent mesh.
- No direct attachment to the current Codex app thread.
- No hidden chain-of-thought logging.

## Core Idea
- `Discord bot/router` is the single gateway for inbound and outbound messages.
- `tmux` keeps one long-running process per role.
- `PM` acts as the team lead.
- A shared task list is stored in local files, not SQL.
- Each role has an inbox and outbox.
- PM publishes the final user-facing summary.

## Team Shape
- `PM`: main agent and final reporter
- `BE Lead`: backend architecture, task splitting, backend review
- `BE Dev`: backend implementation worker
- `FE Lead`: frontend architecture, task splitting, frontend review
- `FE Dev`: frontend implementation worker
- `QA`: failure prediction, Playwright verification, regression handoff
- `Security`: security review and exploitability handoff

## Why No SQL In v1
- Faster to implement
- Easier to inspect and debug locally
- Good enough for single-machine operation
- JSON and JSONL files are sufficient for:
  - shared task list
  - inbox/outbox queues
  - event logs
  - role status

## High-Level Architecture
```text
Discord
  -> Router Bot
  -> Local File State
  -> Role Inbox
  -> tmux role runners
  -> Role Outbox
  -> Router Bot
  -> Discord
```

## Runtime Components
### 1. Discord Router
- Receives Discord messages, mentions, or slash commands
- Decides whether the message is:
  - a new task
  - a role-specific instruction
  - a status query
  - a review request
- Writes normalized task events into local files
- Pushes messages into the correct role inbox
- Reads role outboxes and posts back into Discord

### 2. Role Runner
- One process per role
- Runs inside its own tmux window or pane
- Polls its inbox file
- Processes assigned packets only
- Emits structured updates into its outbox

### 3. Shared Task Store
- File-based state only
- Suggested files:
  - `runtime/tasks.json`
  - `runtime/events.jsonl`
  - `runtime/role-state.json`
  - `runtime/inbox/<role>.jsonl`
  - `runtime/outbox/<role>.jsonl`

## File Layout
```text
agent-team/
├── bot/
│   ├── discord_router.py
│   ├── command_parser.py
│   └── discord_client.py
├── orchestrator/
│   ├── task_store.py
│   ├── router.py
│   ├── schemas.py
│   └── event_log.py
├── runners/
│   ├── pm_runner.py
│   ├── be_lead_runner.py
│   ├── be_dev_runner.py
│   ├── fe_lead_runner.py
│   ├── fe_dev_runner.py
│   ├── qa_runner.py
│   └── security_runner.py
├── runtime/
│   ├── tasks.json
│   ├── role-state.json
│   ├── events.jsonl
│   ├── inbox/
│   └── outbox/
├── config/
│   ├── roles.json
│   ├── discord.json
│   └── routing.json
└── scripts/
    ├── start_tmux.sh
    ├── stop_tmux.sh
    └── reset_runtime.sh
```

## tmux Layout
### Recommended session
- Session name: `agent-team`

### Windows
1. `router`
   - Discord router bot
2. `pm`
   - PM runner
3. `backend`
   - split pane: `BE Lead`, `BE Dev`
4. `frontend`
   - split pane: `FE Lead`, `FE Dev`
5. `review`
   - split pane: `QA`, `Security`
6. `logs`
   - tail on `runtime/events.jsonl`

## Role Communication Model
### Rule 1. All communication passes through the router
- Discord does not talk directly to each role process
- Role processes do not talk directly to Discord
- Router is the only bridge

### Rule 2. All role-to-role handoffs become task events
- No invisible cross-talk
- Every important step becomes an event in `events.jsonl`

### Rule 3. PM is the final reporting surface
- Users can query any role
- Final summary still comes from PM unless explicitly bypassed

## Shared Task List
### Purpose
- Act like the blue `Shared Task List` in your diagram
- Central source of truth for what exists, who owns it, and what is blocked

### Minimal task schema
```json
{
  "task_id": "TASK-20260416-001",
  "title": "Fix payment callback session expiry issue",
  "status": "in_progress",
  "owner_role": "fe-lead",
  "assigned_role": "fe-dev",
  "parent_task_id": null,
  "source": "discord",
  "priority": "P1",
  "thread_id": "discord-thread-id",
  "created_at": "2026-04-16T14:30:00+09:00",
  "updated_at": "2026-04-16T14:34:00+09:00",
  "summary": "Payment callback should recover from expired access token.",
  "write_scope": [
    "vlainter_FE/vlainter/src/pages/content/PointChargeCallbackPage.jsx",
    "vlainter_FE/vlainter/src/lib/paymentApi.js"
  ],
  "handoff_from": "pm",
  "handoff_to": "fe-lead",
  "labels": ["payment", "auth", "callback"]
}
```

## Event Log
### Why JSONL
- append-only
- easy to inspect with `tail -f`
- easy to replay later

### Event types
- `task_created`
- `task_handoff`
- `task_claimed`
- `task_started`
- `task_blocked`
- `task_review_requested`
- `task_review_completed`
- `task_completed`
- `risk_reported`
- `status_summary`

### Example event
```json
{
  "event_id": "evt-00123",
  "task_id": "TASK-20260416-001",
  "type": "task_handoff",
  "from_role": "qa",
  "to_role": "be-lead",
  "message": "Reproduced duplicate refund edge case after timeout.",
  "created_at": "2026-04-16T14:35:10+09:00",
  "metadata": {
    "severity": "P1",
    "repro_steps": 4
  }
}
```

## Inbox/Outbox Model
### Inbox
- Each role has one input queue file:
  - `runtime/inbox/pm.jsonl`
  - `runtime/inbox/be-lead.jsonl`
  - etc.

### Outbox
- Each role has one output queue file:
  - `runtime/outbox/pm.jsonl`
  - `runtime/outbox/be-lead.jsonl`
  - etc.

### Runner behavior
1. Poll inbox
2. Claim unprocessed item
3. Work
4. Write structured updates to outbox
5. Router reads outbox and sends to Discord

## Discord Design
### Option A. One command channel + per-task threads
- Best for keeping noise low
- Recommended

Channels:
- `#agent-hub`
- `#pm-report`

Flow:
- User creates task in `#agent-hub`
- Router creates a thread per task
- All role updates for that task go to that thread
- PM summary also goes to `#pm-report`

### Option B. One channel per role
- More dramatic visually
- Harder to follow for a single feature

Channels:
- `#pm`
- `#backend`
- `#frontend`
- `#qa`
- `#security`

## Recommended Discord Commands
### New task
```text
/task "결제 콜백 세션 만료 문제 수정"
```

### Ask a specific role
```text
@qa 이 기능의 장애 시나리오 먼저 뽑아줘
@security 이 설계 공격면 검토해줘
@be-lead QA 이슈 바탕으로 작업 분배해줘
```

### Status
```text
/status TASK-20260416-001
```

### PM summary
```text
/pm-report TASK-20260416-001
```

## Routing Rules
### PM
- Default entrypoint for new user requests
- Creates or updates the shared task list
- Sends architecture work to leads
- Sends document tasks to Notion workflows when requested

### QA
- Uses Playwright or other test skills where useful
- Reports reproducible failure packets back to leads
- Does not directly assign coding work to developers

### Security
- Reviews active or new code paths
- Hands implementation issues to `BE Lead` or `FE Lead`

### Leads
- Claim packets from shared task list
- Split work
- Review worker outputs
- Push reviewed status to PM

### Developers
- Only work inside assigned packets
- Return finished work to their lead

## Role Skill Guidance
### PM
- Use Notion workflows for:
  - specs
  - reports
  - implementation plans
  - durable knowledge capture

### QA
- Use Playwright and other test skills for:
  - browser reproduction
  - end-to-end verification
  - screenshots
  - failure confirmation

## Example End-to-End Flow
### 1. User asks in Discord
```text
/task 모바일 결제 콜백에서 세션 만료 시 결제 확인 실패 문제 해결해줘
```

### 2. Router creates task thread and task file entry
- `task_created`

### 3. PM processes
- Writes problem statement
- Creates packets
- Sends one packet to `FE Lead`
- Sends one packet to `QA`

### 4. QA processes
- Uses Playwright to reproduce
- Writes repro packet
- Hands packet to `FE Lead`

### 5. FE Lead processes
- Splits fix into FE Dev packet
- Reviews result
- Sends reviewed status to PM

### 6. PM posts summary
- root cause
- current status
- risks
- next actions

## Local Persistence Strategy
### Good enough for v1
- `tasks.json`: current task states
- `events.jsonl`: append-only history
- `role-state.json`: runner health and heartbeat

### Recovery after restart
- Router reloads `tasks.json`
- Runners resume reading inbox files
- Any incomplete task remains `open` or `in_progress`

## Security Notes
- Do not log chain-of-thought
- Do not dump secrets into Discord
- Sanitize stack traces before posting externally
- Keep Discord bot token in local env vars or ignored config
- Keep role output concise and operational

## Operational Limits
- This is a local single-machine system
- If the Mac sleeps or turns off, all role runners stop
- Router downtime means Discord messages will queue only at Discord, not locally
- File-based state can drift if multiple processes write unsafely

## File Locking Recommendation
- Use simple file locks when writing:
  - `fcntl` on macOS/Linux
  - or atomic write through temp file + rename

## Why This MVP Is Still Worth It
- Fastest path to a working agent-team feeling
- No database setup
- Easy to inspect everything
- Easy to replace JSON storage with SQLite later if needed

## Suggested Implementation Order
1. Build Discord router
2. Build file-based task store
3. Build PM runner only
4. Add QA and Security runners
5. Add BE Lead and FE Lead
6. Add developer runners
7. Add per-task Discord thread support
8. Add nicer status and summary commands

## First Build Scope
- One Discord channel
- One router
- `PM`, `QA`, `Security`, `BE Lead`, `FE Lead` only
- JSON file task store
- tmux runner layout
- PM final summary command

## Nice Later Additions
- Web UI monitor
- SQLite migration
- message deduplication ids
- slash command permissions
- avatars per role
- task templates
- retry queue
- summary snapshots
