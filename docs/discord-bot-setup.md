# Discord Bot Setup

## 1. Install Python dependencies
```bash
./scripts/install_agent_team_deps.sh
```

This creates a local virtual environment at `.venv` and installs `discord.py`.

## 2. Create local env file
```bash
cp .agent_team.env.example .agent_team.env
```

Fill in:
- `DISCORD_BOT_TOKEN`
- `DISCORD_ROUTER_CHANNEL_ID`
- `DISCORD_PM_CHANNEL_ID`
- `DISCORD_BACKEND_CHANNEL_ID`
- `DISCORD_FRONTEND_CHANNEL_ID`
- `DISCORD_QA_CHANNEL_ID`
- `DISCORD_SECURITY_CHANNEL_ID`
- `DISCORD_OWNER_USER_ID` if alert-level messages should always mention one specific account

Optional:
- `DISCORD_CHANNEL_ID` as a fallback/default PM channel
- fine-grained overrides such as `DISCORD_BE_LEAD_CHANNEL_ID`
- `AGENT_TEAM_USE_CODEX_EXEC=1` to let each role runner call real `codex exec`
- `AGENT_TEAM_CODEX_TIMEOUT_SECONDS=120` to cap per-message Codex runtime
- `AGENT_TEAM_CODEX_PERMISSION_MODE=danger-full-access` to run role Codex sessions without sandbox restrictions

## 3. Recreate the tmux team session
```bash
./scripts/start_agent_team_tmux.sh --recreate
```

The router window will automatically:
- load `.agent_team.env`
- use `.venv/bin/python` if available
- start in Discord mode when `discord.py` and env values exist

## 4. Recommended first test in Discord
In `#pm`, you can still post:

```text
!task 모바일 결제 콜백 테스트
```

Then check:
- router window
- PM window
- logs window

You can also talk naturally without `!task`:

- in `#pm`: any normal message becomes a PM request or an existing-task follow-up
- in `#router`: any normal message becomes a PM request entrypoint and replies go back to that router channel
- in `#backend`: any normal message goes to `BE Lead`
- in `#frontend`: any normal message goes to `FE Lead`
- in `#qa`: any normal message goes to `QA`
- in `#security`: any normal message goes to `Security`

## 5. Supported Discord commands
```text
!task <title>
!handoff <task_id> <from_role> <to_role> <message>
!scope <task_id> <path> [path...]
!review-done <task_id> <commit_message>
!status
!status <task_id>
```

`!review-done` is intended for lead channels.
- `#백엔드` / `#프론트엔드`에서 리드가 검토 완료를 선언할 때 사용합니다.
- 자동 커밋은 해당 task의 `write_scope`에 등록된 파일만 대상으로 합니다.
- `write_scope`가 없으면 커밋하지 않고 `!scope` 사용 안내를 반환합니다.

## 6. Current behavior
- Outbox messages are posted back to each role's mapped channel.
- The `#router` channel also receives a mirrored Router Feed for role updates sent to other channels, so you can watch cross-role issue sharing in one place.
- If a role reply starts with `[주의]`, `[차단]`, or `[리스크]`, the bot will mention the configured owner account in both the target role channel and the Router Feed.
- Shared channels are supported:
  - `backend` channel: `BE Lead` receives user messages by default, and both `BE Lead` / `BE Dev` can post back there.
  - `frontend` channel: `FE Lead` receives user messages by default, and both `FE Lead` / `FE Dev` can post back there.
- If you mention an existing `TASK-...` id in a natural-language message, the role continues that task context.

## 7. Current behavior and limitation
- With `AGENT_TEAM_USE_CODEX_EXEC=1`, each role runner calls local `codex exec`.
- Each role now stores its own Codex `session_id` and continues later messages with `codex exec resume`, so the role can keep a longer-running conversation context.
- Default permission mode is now `danger-full-access`, so permission prompts are minimized. Because of that, PM/lead roles are expected to reject unreasonable or unsafe requests before they are delegated.
- Context is currently persistent per role, not per task. That means `PM`, `BE Lead`, `QA` each remember their own thread, but they do not yet spawn separate persistent Codex sessions for every task automatically.
- The next upgrade would be task-scoped persistent sessions or `fork`-based subthreads when one role needs to branch into a deep investigation.
