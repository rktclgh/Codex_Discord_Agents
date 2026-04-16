from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Optional

from .config import ROLE_SPECS, all_roles, discord_channel_map
from .git_ops import commit_task_changes
from .store import TaskStore

ROOT_DIR = Path(__file__).resolve().parent.parent

HELP_TEXT = """Commands:
  !task <title>
  !handoff <task_id> <from_role> <to_role> <message>
  !scope <task_id> <path> [path...]
  !review-done <task_id> <commit_message>
  !status [task_id]
  !roles
  !health
  !help
"""


def print_status(store: TaskStore, task_id: Optional[str]) -> None:
    if task_id:
        task = store.get_task(task_id)
        if not task:
            print(f"Task not found: {task_id}")
            return
        print(task)
        return

    tasks = sorted(store.list_tasks(), key=lambda item: item["created_at"])
    if not tasks:
        print("No tasks yet.")
        return
    for task in tasks:
        print(f"{task['task_id']} | {task['status']} | owner={task['owner_role']} | assigned={task['assigned_role']} | {task['title']}")


def drain_outboxes(store: TaskStore) -> None:
    for role in all_roles():
        for message in store.read_outbox(role):
            task_id = message.get("task_id", "-")
            print(f"[outbox:{ROLE_SPECS[role].display_name}] {task_id} :: {message.get('message', '')}")


def format_help_message() -> str:
    return (
        "**Codex Discord Agents 전체 도움말**\n"
        "\n"
        "**1. 공통 명령어**\n"
        "`!help`\n"
        "- 사용 가능한 명령과 채널 동작을 전부 보여줍니다.\n"
        "\n"
        "`!roles`\n"
        "- 역할 구조와 기본 거버넌스를 보여줍니다.\n"
        "\n"
        "`!health`\n"
        "- 현재 라우팅 수, task 수, 역할별 session/상태를 보여줍니다.\n"
        "\n"
        "`!status`\n"
        "- 전체 task 목록을 간단히 보여줍니다.\n"
        "\n"
        "`!status <task_id>`\n"
        "- 특정 task의 상세 상태를 보여줍니다.\n"
        "\n"
        "**2. Task 생성 / 협업 명령어**\n"
        "`!task <title>`\n"
        "- 새 task를 만들고 PM에게 전달합니다.\n"
        "- 예시: `!task 결제 콜백 세션 만료 문제 분석해 주세요`\n"
        "\n"
        "`!handoff <task_id> <from_role> <to_role> <message>`\n"
        "- 수동 handoff를 수행합니다.\n"
        "- 예시: `!handoff TASK-20260416-123456-abcd pm qa 재현 시나리오 먼저 정리해 주세요`\n"
        "\n"
        "`!scope <task_id> <path> [path...]`\n"
        "- 해당 task의 write scope를 등록합니다.\n"
        "- 예시: `!scope TASK-20260416-123456-abcd agent_team/discord_router.py README.md`\n"
        "\n"
        "`!review-done <task_id> <commit_message>`\n"
        "- 리드가 검토 완료를 선언하고, 등록된 write scope만 현재 브랜치에 자동 커밋합니다.\n"
        "- 주로 `#백엔드`, `#프론트엔드` 채널에서 사용합니다.\n"
        "- 예시: `!review-done TASK-20260416-123456-abcd [fix] Discord help 명령 개선`\n"
        "\n"
        "**3. 채널별 자연어 대화**\n"
        "- `#라우터`: PM 진입점 + Router Feed 관찰용\n"
        "- `#pm`: PM과 직접 대화\n"
        "- `#백엔드`: 기본적으로 BE Lead가 받음\n"
        "- `#프론트엔드`: 기본적으로 FE Lead가 받음\n"
        "- `#qa`: QA가 받음\n"
        "- `#보안`: Security가 받음\n"
        "\n"
        "각 채널에서는 `!task` 없이 자연어로 바로 요청하셔도 됩니다.\n"
        "- 예시: `결제 콜백 세션 만료 문제를 작업 단위로 쪼개 주세요.`\n"
        "- 예시: `TASK-20260416-123456-abcd 기준으로 재현 시나리오를 정리해 주세요.`\n"
        "\n"
        "**4. 참고 규칙**\n"
        "- 메시지에 `TASK-...`를 포함하면 기존 task 맥락을 이어서 대화합니다.\n"
        "- `[주의]`, `[차단]`, `[리스크]`로 시작하는 응답은 오너를 자동 멘션합니다.\n"
        "- `#라우터` 채널에는 다른 채널의 주요 업데이트가 `Router Feed`로 함께 올라옵니다."
    )


def format_roles_message() -> str:
    lines = ["**역할 구조**"]
    for role in ROLE_SPECS.values():
        lines.append(f"`{role.key}` / {role.display_name}: {role.summary}")
    lines.append("")
    lines.append("기본 거버넌스:")
    lines.append("- PM이 작업을 정리하고 공유 task list를 관리합니다.")
    lines.append("- BE Lead / FE Lead가 구현 범위를 분해하고 리뷰합니다.")
    lines.append("- QA는 장애 지점과 회귀 시나리오를 찾아 리드에게 전달합니다.")
    lines.append("- Security는 보안 리스크를 찾아 리드와 PM에게 공유합니다.")
    return "\n".join(lines)


def format_health_message(store: TaskStore, incoming_channel_roles: dict[int, str], outgoing_role_channels: dict[str, int]) -> str:
    lines = ["**현재 운영 상태**"]
    lines.append(f"- incoming route 수: `{len(incoming_channel_roles)}`")
    lines.append(f"- outgoing route 수: `{len(outgoing_role_channels)}`")

    tasks = list(store.list_tasks())
    open_tasks = [task for task in tasks if task.get("status") not in {"done", "closed"}]
    lines.append(f"- 전체 task 수: `{len(tasks)}`")
    lines.append(f"- 진행중 task 수: `{len(open_tasks)}`")
    lines.append("")
    lines.append("역할 상태:")

    for role in all_roles():
        state = store.get_role_state(role)
        session_flag = "있음" if state.get("session_id") else "없음"
        status = state.get("status") or "unknown"
        note = state.get("note") or "-"
        lines.append(
            f"- {ROLE_SPECS[role].display_name}: status=`{status}`, session=`{session_flag}`, note=`{note}`"
        )

    return "\n".join(lines)


def processing_ack_message(role: str, task_id: str, is_new_task: bool = False) -> str:
    role_name = ROLE_SPECS[role].display_name
    if is_new_task:
        return (
            f"사장님, 요청 확인했습니다. `{task_id}` 로 등록했고 지금 처리 중입니다.\n"
            f"담당 역할: {role_name}\n"
            "잠시만 기다려 주시면 결과를 정리해서 바로 올리겠습니다."
        )
    return (
        f"사장님, 요청 확인했습니다. `{task_id}` 기준으로 지금 처리 중입니다.\n"
        f"담당 역할: {role_name}\n"
        "잠시만 기다려 주시면 결과를 정리해서 바로 올리겠습니다."
    )


TASK_ID_PATTERN = re.compile(r"(TASK-\d{8}-\d{6}-[a-z0-9]{4})", re.IGNORECASE)
ALERT_TAG_PATTERN = re.compile(r"^\[(주의|차단|리스크)\]")


def extract_task_id(content: str, store: TaskStore) -> Optional[str]:
    match = TASK_ID_PATTERN.search(content or "")
    if not match:
        return None
    task_id = match.group(1)
    return task_id if store.get_task(task_id) else None


def is_alert_message(message_text: str) -> bool:
    return bool(ALERT_TAG_PATTERN.match((message_text or "").strip()))


def mention_for_task(task: Optional[dict], payload: dict) -> Optional[str]:
    explicit_owner = os.environ.get("DISCORD_OWNER_USER_ID", "").strip()
    if explicit_owner:
        return f"<@{explicit_owner}>"

    candidate = (
        payload.get("requester_user_id")
        or (task or {}).get("last_requester_user_id")
        or (task or {}).get("requester_user_id")
    )
    if candidate:
        return f"<@{candidate}>"
    return None


def completion_mention_for_task(task: Optional[dict], payload: dict) -> Optional[str]:
    if not payload.get("notify_owner"):
        return None
    return mention_for_task(task, payload)


def run_local_repl() -> int:
    store = TaskStore()
    print("Agent Team Router (local mode)")
    print("Discord bot token not configured or discord.py not installed.")
    print("You can still create and route tasks locally from this pane.")
    print(format_help_message())

    while True:
        drain_outboxes(store)
        try:
            raw = input("router> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        if raw in {"quit", "exit"}:
            break
        if raw == "help":
            print(format_help_message())
            continue
        if raw == "roles":
            print(format_roles_message())
            continue
        if raw == "health":
            print(format_health_message(store, {}, {}))
            continue
        if raw.startswith("task "):
            title = raw[5:].strip()
            if not title:
                print("Task title is required.")
                continue
            task = store.create_task(title, source="local-repl")
            print(f"Created task: {task['task_id']}")
            continue
        if raw.startswith("handoff "):
            try:
                _, task_id, from_role, to_role, message = raw.split(" ", 4)
            except ValueError:
                print("Usage: handoff <task_id> <from_role> <to_role> <message>")
                continue
            try:
                store.handoff_task(task_id, from_role, to_role, message)
                print(f"Handed off {task_id} -> {to_role}")
            except KeyError as exc:
                print(str(exc))
            continue
        if raw.startswith("scope "):
            try:
                _, task_id, path_blob = raw.split(" ", 2)
            except ValueError:
                print("Usage: scope <task_id> <path> [path...]")
                continue
            task = store.get_task(task_id)
            if not task:
                print(f"Task not found: {task_id}")
                continue
            scope = [part for part in path_blob.split(" ") if part.strip()]
            store.update_task(task_id, write_scope=scope)
            print(f"Updated scope for {task_id}: {scope}")
            continue
        if raw.startswith("status"):
            parts = raw.split(" ", 1)
            print_status(store, parts[1].strip() if len(parts) == 2 else None)
            continue

        print("Unknown command.")
        print(format_help_message())

    return 0


def run_discord_bot() -> int:
    try:
        import discord
        from discord.ext import tasks
    except ImportError:
        print("discord.py is not installed. Falling back to local mode.")
        return run_local_repl()

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("DISCORD_BOT_TOKEN is missing. Falling back to local mode.")
        return run_local_repl()

    store = TaskStore()
    channel_config = discord_channel_map()
    incoming_channel_roles = channel_config["incoming"]
    outgoing_role_channels = channel_config["outgoing"]
    named_channels = channel_config["named"]
    fallback_channel_id = int(os.environ.get("DISCORD_CHANNEL_ID")) if os.environ.get("DISCORD_CHANNEL_ID") else None
    if not outgoing_role_channels and not fallback_channel_id:
        print("No Discord channel mapping is configured. Falling back to local mode.")
        return run_local_repl()

    intents = discord.Intents.default()
    intents.message_content = True

    class AgentTeamBot(discord.Client):
        async def send_router_broadcast(
            self,
            source_role: str,
            task_id: str,
            message_text: str,
            target_channel_id: Optional[int],
            mention_text: Optional[str] = None,
        ) -> None:
            router_channel_id = named_channels.get("router")
            if not router_channel_id:
                return
            if target_channel_id and int(router_channel_id) == int(target_channel_id):
                return

            router_channel = await self.resolve_channel(int(router_channel_id))
            if router_channel is None:
                return

            target_label = "unknown"
            for role, channel_id in outgoing_role_channels.items():
                if int(channel_id) == int(target_channel_id or 0):
                    target_label = ROLE_SPECS[role].display_name
                    break

            header = f"**Router Feed** `{task_id}`" if task_id and task_id != "-" else "**Router Feed**"
            body = (
                f"{header}\n"
                f"역할: {ROLE_SPECS[source_role].display_name}\n"
                f"전달 채널: {target_label}\n"
                f"{message_text}"
            )
            if mention_text:
                body = f"{mention_text}\n{body}"
            await router_channel.send(body)

        async def resolve_channel(self, channel_id: int):
            channel = self.get_channel(channel_id)
            if channel is not None:
                return channel
            try:
                channel = await self.fetch_channel(channel_id)
                return channel
            except Exception as exc:  # pragma: no cover - runtime diagnostic path
                print(f"Failed to resolve channel {channel_id}: {type(exc).__name__}: {exc}", flush=True)
                return None

        async def setup_hook(self) -> None:
            self.outbox_loop.start()

        async def on_ready(self) -> None:
            print(f"Logged in as {self.user}", flush=True)
            print(f"Guild count: {len(self.guilds)}", flush=True)
            for guild in self.guilds:
                print(f"Guild: {guild.name} ({guild.id})", flush=True)
                for channel in guild.text_channels:
                    print(f"  Text channel: {channel.name} ({channel.id})", flush=True)
            for channel_id, role in sorted(incoming_channel_roles.items()):
                print(f"Incoming route: channel {channel_id} -> {role}", flush=True)
            for role, channel_id in sorted(outgoing_role_channels.items()):
                print(f"Outgoing route: {role} -> channel {channel_id}", flush=True)

        async def on_message(self, message: discord.Message) -> None:
            if message.author.bot:
                return

            content = (message.content or "").strip()
            channel_name = getattr(message.channel, "name", "unknown")
            channel_role = incoming_channel_roles.get(message.channel.id)

            if channel_role and not content.startswith("!"):
                print(f"Received chat in #{channel_name} for role {channel_role}: {content}", flush=True)
                task_id = extract_task_id(content, store)

                if channel_role == "pm" and task_id is None:
                    task = store.create_task(
                        content,
                        source="discord-chat",
                        thread_id=str(message.channel.id),
                        requester_user_id=str(message.author.id),
                    )
                    await message.reply(processing_ack_message("pm", task["task_id"], is_new_task=True))
                    return

                if task_id:
                    store.set_task_requester(task_id, str(message.author.id))

                store.push_inbox(
                    channel_role,
                    {
                        "type": "role_chat",
                        "task_id": task_id,
                        "from_role": "user",
                        "to_role": channel_role,
                        "message": content,
                        "reply_channel_id": str(message.channel.id),
                        "requester_user_id": str(message.author.id),
                    },
                )
                await message.reply(processing_ack_message(channel_role, task_id or "-", is_new_task=False))
                return

            if not content.startswith("!"):
                return

            print(f"Received command in #{getattr(message.channel, 'name', 'unknown')}: {content}", flush=True)

            try:
                if content.startswith("!task "):
                    title = content[6:].strip()
                    task = store.create_task(
                        title,
                        source="discord",
                        thread_id=str(message.channel.id),
                        requester_user_id=str(message.author.id),
                    )
                    await message.reply(f"Created task `{task['task_id']}` and routed it to PM.")
                    return

                if content == "!help":
                    await message.reply(format_help_message())
                    return

                if content == "!roles":
                    await message.reply(format_roles_message())
                    return

                if content == "!health":
                    await message.reply(format_health_message(store, incoming_channel_roles, outgoing_role_channels))
                    return

                if content.startswith("!scope "):
                    try:
                        _, task_id, path_blob = content.split(" ", 2)
                    except ValueError:
                        await message.reply("Usage: `!scope <task_id> <path> [path...]`")
                        return
                    task = store.get_task(task_id)
                    if not task:
                        await message.reply("Task not found.")
                        return
                    store.set_task_requester(task_id, str(message.author.id))
                    scope = [part for part in path_blob.split(" ") if part.strip()]
                    store.update_task(task_id, write_scope=scope)
                    await message.reply(f"`{task_id}` write scope를 업데이트했습니다.\n" + "\n".join(f"- `{path}`" for path in scope))
                    return

                if content.startswith("!review-done "):
                    try:
                        _, task_id, review_note = content.split(" ", 2)
                    except ValueError:
                        await message.reply("Usage: `!review-done <task_id> <commit_message>`")
                        return

                    if channel_role not in {"be-lead", "fe-lead"}:
                        await message.reply("이 명령은 현재 백엔드 리드/프론트엔드 리드 채널에서만 사용할 수 있습니다.")
                        return

                    task = store.get_task(task_id)
                    if not task:
                        await message.reply("Task not found.")
                        return
                    store.set_task_requester(task_id, str(message.author.id))

                    commit_result = commit_task_changes(ROOT_DIR, task, channel_role, review_note)
                    result_status = commit_result.get("status")

                    if result_status == "no_scope":
                        await message.reply(
                            f"`{task_id}` 는 아직 write scope가 없습니다. 먼저 `!scope {task_id} <path> [path...]` 로 범위를 등록해 주세요."
                        )
                        return

                    if result_status == "no_changes":
                        await message.reply(
                            f"`{task_id}` 범위에는 아직 커밋할 변경이 없습니다.\n"
                            f"브랜치: `{commit_result.get('branch', '-')}`"
                        )
                        return

                    if result_status == "error":
                        await message.reply(
                            f"`{task_id}` 자동 커밋에 실패했습니다.\n"
                            f"사유: {commit_result.get('message', 'unknown error')}"
                        )
                        return

                    store.update_task(
                        task_id,
                        status="review_completed",
                        owner_role=channel_role,
                        assigned_role=channel_role,
                        last_review_by=channel_role,
                        last_review_note=review_note,
                        last_commit_hash=commit_result.get("commit_hash"),
                        last_commit_branch=commit_result.get("branch"),
                    )
                    store.append_event(
                        "task_review_completed",
                        task_id,
                        review_note,
                        from_role=channel_role,
                        commit_hash=commit_result.get("commit_hash"),
                        branch=commit_result.get("branch"),
                    )
                    store.push_inbox(
                        "pm",
                        {
                            "type": "task_handoff",
                            "task_id": task_id,
                            "from_role": channel_role,
                            "to_role": "pm",
                            "message": (
                                f"리드 검토가 완료되어 자동 커밋했습니다. "
                                f"branch={commit_result.get('branch')} "
                                f"commit={commit_result.get('commit_hash')} "
                                f"scope={', '.join(commit_result.get('scope', []))}"
                            ),
                            "reply_channel_id": str(message.channel.id),
                        },
                    )
                    await message.reply(
                        f"`{task_id}` 리드 검토 완료를 반영해 현재 브랜치에 자동 커밋했습니다.\n"
                        f"브랜치: `{commit_result.get('branch')}`\n"
                        f"커밋: `{commit_result.get('commit_hash')}`\n"
                        f"메시지: `{commit_result.get('commit_message')}`"
                    )
                    return

                if content.startswith("!handoff "):
                    try:
                        _, task_id, from_role, to_role, handoff_message = content.split(" ", 4)
                        store.handoff_task(task_id, from_role, to_role, handoff_message)
                        await message.reply(f"Handed off `{task_id}` to `{to_role}`.")
                    except ValueError:
                        await message.reply("Usage: `!handoff <task_id> <from_role> <to_role> <message>`")
                    except KeyError as exc:
                        await message.reply(str(exc))
                    return

                if content.startswith("!status"):
                    parts = content.split(" ", 1)
                    task_id = parts[1].strip() if len(parts) == 2 else None
                    if task_id:
                        task = store.get_task(task_id)
                        await message.reply(f"```json\n{task}\n```" if task else "Task not found.")
                    else:
                        tasks = list(store.list_tasks())
                        lines = [
                            f"{task['task_id']} | {task['status']} | owner={task['owner_role']} | assigned={task['assigned_role']} | {task['title']}"
                            for task in tasks
                        ]
                        await message.reply("\n".join(lines) if lines else "No tasks yet.")
            except Exception as exc:  # pragma: no cover - runtime diagnostic path
                print(f"Command handling failed: {type(exc).__name__}: {exc}", flush=True)
                try:
                    await message.channel.send(f"Command failed: {type(exc).__name__}: {exc}")
                except Exception:
                    pass

        @tasks.loop(seconds=2)
        async def outbox_loop(self) -> None:
            for role in all_roles():
                for payload, end_offset in store.peek_outbox(role):
                    target_channel_id = payload.get("reply_channel_id") or outgoing_role_channels.get(role) or fallback_channel_id
                    if not target_channel_id:
                        print(f"No target channel for role {role}; skipping outbox message.", flush=True)
                        continue
                    channel = await self.resolve_channel(int(target_channel_id))
                    if channel is None:
                        continue
                    task_id = payload.get("task_id", "-")
                    header = f"**{ROLE_SPECS[role].display_name}**"
                    if task_id and task_id != "-":
                        header = f"{header} `{task_id}`"
                    task = store.get_task(task_id) if task_id and task_id != "-" else None
                    mention_text = None
                    if is_alert_message(payload.get("message", "")):
                        mention_text = mention_for_task(task, payload)
                    if mention_text is None:
                        mention_text = completion_mention_for_task(task, payload)
                    body = f"{header}\n{payload.get('message', '')}"
                    if mention_text:
                        body = f"{mention_text}\n{body}"
                    try:
                        await channel.send(body)
                        await self.send_router_broadcast(
                            source_role=role,
                            task_id=task_id,
                            message_text=payload.get("message", ""),
                            target_channel_id=int(target_channel_id),
                            mention_text=mention_text,
                        )
                        store.commit_stream_offset("outbox", role, end_offset)
                        print(f"Posted outbox update for {task_id} from {role}", flush=True)
                    except Exception as exc:  # pragma: no cover - runtime diagnostic path
                        print(f"Outbox send failed for {task_id} from {role}: {type(exc).__name__}: {exc}", flush=True)
    bot = AgentTeamBot(intents=intents)
    bot.run(token)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Router for the local Discord + tmux MVP.")
    parser.add_argument("--mode", choices=("auto", "local", "discord"), default="auto")
    args = parser.parse_args()

    if args.mode == "local":
        return run_local_repl()
    if args.mode == "discord":
        return run_discord_bot()
    return run_discord_bot()


if __name__ == "__main__":
    raise SystemExit(main())
