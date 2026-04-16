from __future__ import annotations

import argparse
import json
from typing import Optional

from .config import ROLE_SPECS
from .store import TaskStore


def cmd_task(store: TaskStore, title: str) -> int:
    task = store.create_task(title, source="cli")
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def cmd_handoff(store: TaskStore, task_id: str, from_role: str, to_role: str, message: str) -> int:
    task = store.handoff_task(task_id, from_role, to_role, message)
    print(json.dumps(task, ensure_ascii=False, indent=2))
    return 0


def cmd_status(store: TaskStore, task_id: Optional[str]) -> int:
    if task_id:
        task = store.get_task(task_id)
        if not task:
            print(f"Task not found: {task_id}")
            return 1
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return 0

    tasks = sorted(store.list_tasks(), key=lambda item: item["created_at"])
    print(json.dumps(tasks, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Local CLI for the file-based agent team runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    task_parser = subparsers.add_parser("task")
    task_parser.add_argument("title")

    handoff_parser = subparsers.add_parser("handoff")
    handoff_parser.add_argument("task_id")
    handoff_parser.add_argument("from_role", choices=sorted(ROLE_SPECS))
    handoff_parser.add_argument("to_role", choices=sorted(ROLE_SPECS))
    handoff_parser.add_argument("message")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("task_id", nargs="?")

    args = parser.parse_args()
    store = TaskStore()

    if args.command == "task":
        return cmd_task(store, args.title)
    if args.command == "handoff":
        return cmd_handoff(store, args.task_id, args.from_role, args.to_role, args.message)
    if args.command == "status":
        return cmd_status(store, args.task_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
