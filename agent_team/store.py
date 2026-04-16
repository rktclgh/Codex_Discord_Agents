from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .config import ROLE_SPECS, ensure_runtime_layout

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def locked_file(path: Path, mode: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as fh:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield fh
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def atomic_write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


class TaskStore:
    def __init__(self) -> None:
        self.paths = ensure_runtime_layout()

    def load_tasks(self) -> Dict[str, Dict]:
        raw = self.paths["tasks"].read_text(encoding="utf-8").strip() or "{}"
        return json.loads(raw)

    def save_tasks(self, tasks: Dict[str, Dict]) -> None:
        atomic_write_json(self.paths["tasks"], tasks)

    def load_role_state(self) -> Dict[str, Dict]:
        raw = self.paths["role_state"].read_text(encoding="utf-8").strip() or "{}"
        return json.loads(raw)

    def save_role_state(self, role_state: Dict[str, Dict]) -> None:
        atomic_write_json(self.paths["role_state"], role_state)

    def append_jsonl(self, path: Path, payload: Dict) -> None:
        with locked_file(path, "a") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def append_event(self, event_type: str, task_id: Optional[str], message: str, **extra) -> Dict:
        payload = {
            "event_id": f"evt-{uuid.uuid4().hex[:12]}",
            "type": event_type,
            "task_id": task_id,
            "message": message,
            "created_at": now_iso(),
        }
        payload.update(extra)
        self.append_jsonl(self.paths["events"], payload)
        return payload

    def push_inbox(self, role: str, payload: Dict) -> Dict:
        if role not in ROLE_SPECS:
            raise KeyError(f"Unknown role: {role}")
        enriched = {
            "message_id": f"msg-{uuid.uuid4().hex[:12]}",
            "created_at": now_iso(),
            **payload,
        }
        self.append_jsonl(self.paths["inbox"] / f"{role}.jsonl", enriched)
        return enriched

    def push_outbox(self, role: str, payload: Dict) -> Dict:
        if role not in ROLE_SPECS:
            raise KeyError(f"Unknown role: {role}")
        enriched = {
            "message_id": f"out-{uuid.uuid4().hex[:12]}",
            "created_at": now_iso(),
            **payload,
        }
        self.append_jsonl(self.paths["outbox"] / f"{role}.jsonl", enriched)
        return enriched

    def _offset_path(self, kind: str, role: str) -> Path:
        return self.paths["offsets"] / f"{kind}-{role}.offset"

    def _last_offset(self, kind: str, role: str) -> int:
        offset_path = self._offset_path(kind, role)
        last_offset = 0
        if offset_path.exists():
            try:
                last_offset = int(offset_path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                last_offset = 0
        return last_offset

    def commit_stream_offset(self, kind: str, role: str, offset: int) -> None:
        offset_path = self._offset_path(kind, role)
        offset_path.write_text(str(offset), encoding="utf-8")

    def read_stream_since_offset(self, path: Path, kind: str, role: str) -> List[Dict]:
        last_offset = self._last_offset(kind, role)
        items: List[Dict] = []
        with path.open("r", encoding="utf-8") as fh:
            fh.seek(last_offset)
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    items.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
            new_offset = fh.tell()

        self.commit_stream_offset(kind, role, new_offset)
        return items

    def peek_stream_since_offset(self, path: Path, kind: str, role: str) -> List[Tuple[Dict, int]]:
        last_offset = self._last_offset(kind, role)
        items: List[Tuple[Dict, int]] = []
        with path.open("r", encoding="utf-8") as fh:
            fh.seek(last_offset)
            while True:
                line = fh.readline()
                if not line:
                    break
                end_offset = fh.tell()
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    items.append((json.loads(stripped), end_offset))
                except json.JSONDecodeError:
                    continue
        return items

    def read_inbox(self, role: str) -> List[Dict]:
        return self.read_stream_since_offset(self.paths["inbox"] / f"{role}.jsonl", "inbox", role)

    def read_outbox(self, role: str) -> List[Dict]:
        return self.read_stream_since_offset(self.paths["outbox"] / f"{role}.jsonl", "outbox", role)

    def peek_outbox(self, role: str) -> List[Tuple[Dict, int]]:
        return self.peek_stream_since_offset(self.paths["outbox"] / f"{role}.jsonl", "outbox", role)

    def create_task(
        self,
        title: str,
        source: str = "local",
        thread_id: Optional[str] = None,
        requester_user_id: Optional[str] = None,
    ) -> Dict:
        tasks = self.load_tasks()
        task_id = self._next_ticket_id(tasks)
        task = {
            "task_id": task_id,
            "title": title,
            "status": "open",
            "owner_role": "pm",
            "assigned_role": "pm",
            "source": source,
            "thread_id": thread_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "summary": title,
            "write_scope": [],
            "handoff_from": "user",
            "handoff_to": "pm",
            "labels": [],
            "requester_user_id": requester_user_id,
            "last_requester_user_id": requester_user_id,
        }
        tasks[task_id] = task
        self.save_tasks(tasks)
        self.append_event("task_created", task_id, title, from_role="user", to_role="pm")
        self.push_inbox(
            "pm",
            {
                "type": "task_created",
                "task_id": task_id,
                "from_role": "user",
                "to_role": "pm",
                "message": title,
            },
        )
        return task

    def _next_ticket_id(self, tasks: Dict[str, Dict]) -> str:
        max_ticket = 0
        for key in tasks.keys():
            if isinstance(key, str) and key.startswith("#"):
                try:
                    max_ticket = max(max_ticket, int(key[1:]))
                except ValueError:
                    continue
        return f"#{max_ticket + 1}"

    def set_task_requester(self, task_id: str, requester_user_id: Optional[str]) -> Dict:
        changes = {"last_requester_user_id": requester_user_id}
        task = self.get_task(task_id)
        if task and not task.get("requester_user_id") and requester_user_id:
            changes["requester_user_id"] = requester_user_id
        return self.update_task(task_id, **changes)

    def update_task(self, task_id: str, **changes) -> Dict:
        tasks = self.load_tasks()
        if task_id not in tasks:
            raise KeyError(f"Unknown task_id: {task_id}")
        tasks[task_id].update(changes)
        tasks[task_id]["updated_at"] = now_iso()
        self.save_tasks(tasks)
        return tasks[task_id]

    def handoff_task(self, task_id: str, from_role: str, to_role: str, message: str) -> Dict:
        task = self.update_task(task_id, assigned_role=to_role, handoff_from=from_role, handoff_to=to_role)
        self.append_event("task_handoff", task_id, message, from_role=from_role, to_role=to_role)
        self.push_inbox(
            to_role,
            {
                "type": "task_handoff",
                "task_id": task_id,
                "from_role": from_role,
                "to_role": to_role,
                "message": message,
            },
        )
        return task

    def set_role_heartbeat(self, role: str, status: str, note: str = "") -> None:
        role_state = self.load_role_state()
        existing = role_state.get(role, {})
        role_state[role] = {
            **existing,
            "status": status,
            "note": note,
            "updated_at": now_iso(),
        }
        self.save_role_state(role_state)

    def get_role_session(self, role: str) -> Optional[str]:
        role_state = self.load_role_state()
        state = role_state.get(role) or {}
        session_id = state.get("session_id")
        return session_id if isinstance(session_id, str) and session_id.strip() else None

    def set_role_session(self, role: str, session_id: Optional[str]) -> None:
        role_state = self.load_role_state()
        existing = role_state.get(role, {})
        role_state[role] = {
            **existing,
            "session_id": session_id,
            "updated_at": now_iso(),
        }
        self.save_role_state(role_state)

    def set_role_active_task(self, role: str, task_id: Optional[str], pid: Optional[int] = None) -> None:
        role_state = self.load_role_state()
        existing = role_state.get(role, {})
        role_state[role] = {
            **existing,
            "active_task_id": task_id,
            "active_pid": pid,
            "updated_at": now_iso(),
        }
        self.save_role_state(role_state)

    def clear_role_active_task(self, role: str) -> None:
        role_state = self.load_role_state()
        existing = role_state.get(role, {})
        role_state[role] = {
            **existing,
            "active_task_id": None,
            "active_pid": None,
            "updated_at": now_iso(),
        }
        self.save_role_state(role_state)

    def request_stop(self, task_id: str, role: str, requester_user_id: Optional[str] = None) -> Dict:
        task = self.update_task(
            task_id,
            status="stop_requested",
            stop_requested_for_role=role,
            last_requester_user_id=requester_user_id or self.get_task(task_id).get("last_requester_user_id"),
        )
        self.append_event(
            "task_stop_requested",
            task_id,
            f"Stop requested for {role}.",
            requested_role=role,
            requester_user_id=requester_user_id,
        )
        role_state = self.load_role_state()
        existing = role_state.get(role, {})
        role_state[role] = {
            **existing,
            "stop_requested_task_id": task_id,
            "stop_requested_at": now_iso(),
            "updated_at": now_iso(),
        }
        self.save_role_state(role_state)
        return task

    def is_stop_requested(self, role: str, task_id: Optional[str]) -> bool:
        if not task_id:
            return False
        role_state = self.load_role_state()
        state = role_state.get(role) or {}
        return state.get("stop_requested_task_id") == task_id

    def clear_stop_request(self, role: str, task_id: Optional[str] = None) -> None:
        role_state = self.load_role_state()
        existing = role_state.get(role, {})
        if task_id and existing.get("stop_requested_task_id") not in {None, task_id}:
            return
        role_state[role] = {
            **existing,
            "stop_requested_task_id": None,
            "stop_requested_at": None,
            "updated_at": now_iso(),
        }
        self.save_role_state(role_state)

    def list_tasks(self) -> Iterable[Dict]:
        return self.load_tasks().values()

    def get_task(self, task_id: str) -> Optional[Dict]:
        return self.load_tasks().get(task_id)

    def get_role_state(self, role: str) -> Dict:
        return (self.load_role_state().get(role) or {}).copy()

    def list_role_states(self) -> Dict[str, Dict]:
        return self.load_role_state()
