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
  task <title>
  handoff <task_id> <from_role> <to_role> <message>
  scope <task_id> <path> [path...]
  review-done <task_id> <commit_message>
  status [task_id]
  roles
  help
  quit
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


def run_local_repl() -> int:
    store = TaskStore()
    print("Agent Team Router (local mode)")
    print("Discord bot token not configured or discord.py not installed.")
    print("You can still create and route tasks locally from this pane.")
    print(HELP_TEXT)

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
            print(HELP_TEXT)
            continue
        if raw == "roles":
            for role in ROLE_SPECS.values():
                print(f"{role.key}: {role.display_name} - {role.summary}")
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
        print(HELP_TEXT)

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
                    store.create_task(
                        content,
                        source="discord-chat",
                        thread_id=str(message.channel.id),
                        requester_user_id=str(message.author.id),
                    )
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
                    mention_text = mention_for_task(task, payload) if is_alert_message(payload.get("message", "")) else None
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
