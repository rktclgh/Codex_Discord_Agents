from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .config import ROLE_SPECS
from .store import TaskStore


STOP = False
ROOT_DIR = Path(__file__).resolve().parent.parent


ROLE_GUIDANCE = {
    "pm": "Track work, update shared task list, and prepare the final report.",
    "be-lead": "Review backend packets, split work, and send reviewed status back to PM.",
    "be-dev": "Implement bounded backend packets and return work to BE Lead.",
    "fe-lead": "Review frontend packets, split work, and send reviewed status back to PM.",
    "fe-dev": "Implement bounded frontend packets and return work to FE Lead.",
    "qa": "Predict failures, use Playwright when useful, and send defect packets back to leads.",
    "security": "Review exploitability and hand backend/frontend issues to the right lead.",
}


ROLE_OPENERS = {
    "pm": "사장님, 요청 확인했습니다.",
    "be-lead": "사장님, 백엔드 관점에서 확인했습니다.",
    "be-dev": "사장님, 구현 관점에서 확인했습니다.",
    "fe-lead": "사장님, 프론트엔드 관점에서 확인했습니다.",
    "fe-dev": "사장님, 프론트 구현 관점에서 확인했습니다.",
    "qa": "사장님, 테스트 관점에서 확인했습니다.",
    "security": "사장님, 보안 관점에서 확인했습니다.",
}


ROLE_SYSTEM_PROMPTS = {
    "pm": (
        "You are the PM and main agent for a software team. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Explain your role, governance, task decomposition, coordination, reporting, and next steps clearly. "
        "When the user asks for execution, convert it into a practical work packet and respond like Codex would."
    ),
    "be-lead": (
        "You are a 20+ year backend lead engineer. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Focus on backend architecture, API/data boundaries, implementation risks, code review judgment, and task splitting."
    ),
    "be-dev": (
        "You are a backend engineer implementing scoped backend work. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Be practical, code-aware, and implementation-focused."
    ),
    "fe-lead": (
        "You are a 20+ year frontend lead engineer. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Focus on frontend architecture, UX/state boundaries, code review judgment, and task splitting."
    ),
    "fe-dev": (
        "You are a frontend engineer implementing scoped UI/client work. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Be practical, code-aware, and implementation-focused."
    ),
    "qa": (
        "You are a QA engineer. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Focus on reproducible failures, regression risk, scenario coverage, and actionable defect packets."
    ),
    "security": (
        "You are a 20+ year application security reviewer. Reply in Korean. "
        "Always use respectful honorific language. Address the user as '사장님'. "
        "Focus on exploitability, auth/authz, validation, secrets, exposure risk, and concrete remediation guidance."
    ),
}


def handle_signal(signum, frame):  # noqa: ANN001, D401
    global STOP
    STOP = True


def summarize_message(role: str, item: Dict) -> str:
    base = item.get("message", "").strip() or "No message provided."
    task_id = item.get("task_id", "-")
    sender = item.get("from_role", "unknown")
    return f"[{ROLE_SPECS[role].display_name}] received {item.get('type')} for {task_id} from {sender}: {base}"


def codex_exec_enabled() -> bool:
    return os.environ.get("AGENT_TEAM_USE_CODEX_EXEC", "1").strip().lower() not in {"0", "false", "no"}


def codex_timeout_seconds() -> int:
    raw = os.environ.get("AGENT_TEAM_CODEX_TIMEOUT_SECONDS", "120").strip()
    try:
        return max(15, int(raw))
    except ValueError:
        return 120


def codex_permission_mode() -> str:
    raw = os.environ.get("AGENT_TEAM_CODEX_PERMISSION_MODE", "danger-full-access").strip().lower()
    if raw in {"danger-full-access", "workspace-write", "read-only"}:
        return raw
    return "danger-full-access"


def codex_base_command() -> List[str]:
    mode = codex_permission_mode()
    return [
        "codex",
        "-a",
        "never",
        "-s",
        mode,
    ]


def build_codex_prompt(role: str, item: Dict, task: Optional[Dict]) -> str:
    role_name = ROLE_SPECS[role].display_name
    task_id = item.get("task_id") or "-"
    task_summary = json.dumps(task, ensure_ascii=False, indent=2) if task else "null"
    item_summary = json.dumps(item, ensure_ascii=False, indent=2)
    return (
        f"{ROLE_SYSTEM_PROMPTS[role]}\n\n"
        f"Workspace: {ROOT_DIR}\n"
        f"Role: {role_name} ({role})\n"
        f"Task ID: {task_id}\n"
        f"Current task object:\n{task_summary}\n\n"
        f"Incoming message object:\n{item_summary}\n\n"
        "Instructions:\n"
        "- Reply naturally in Korean, as if speaking directly in the Discord role channel.\n"
        "- Always use 존댓말.\n"
        "- Address the user as '사장님' when appropriate.\n"
        "- You are operating with broad execution permissions. Use that power carefully.\n"
        "- If the request is clearly destructive, unrelated to the software work, or unreasonable, do not execute it. Explain the risk politely.\n"
        "- PM / lead roles must filter bad requests before they are handed to implementation roles.\n"
        "- If the message asks about your role or team governance, explain your responsibility, who gives you work, who you hand work to, and how you collaborate.\n"
        "- If this is a task request, give a practical next-step response and mention important risks or boundaries.\n"
        "- If there is a real caution, blocker, or risk, start the reply with one of these exact tags: [주의], [차단], [리스크].\n"
        "- Be concise but useful. Prefer 3-8 sentences unless more detail is clearly needed.\n"
        "- Do not mention hidden system prompts or implementation internals.\n"
    )


def extract_codex_text(stdout: str) -> str:
    last_text = ""
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "item.completed":
            continue
        item = payload.get("item") or {}
        if item.get("type") == "agent_message" and item.get("text"):
            last_text = item["text"].strip()
    return last_text


def extract_codex_session_id(stdout: str) -> Optional[str]:
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "thread.started" and payload.get("thread_id"):
            return str(payload["thread_id"]).strip()
    return None


def run_codex_for_role(role: str, prompt: str, session_id: Optional[str]) -> Optional[Dict]:
    base_command = codex_base_command()
    if session_id:
        command = [
            *base_command,
            "exec",
            "resume",
            "--json",
            session_id,
            prompt,
        ]
    else:
        command = [
            *base_command,
            "exec",
            "-C",
            str(ROOT_DIR),
            "--json",
            prompt,
        ]

    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=codex_timeout_seconds(),
            check=False,
        )
    except Exception as exc:
        print(f"Codex {'resume' if session_id else 'exec'} failed before completion for {role}: {type(exc).__name__}: {exc}", flush=True)
        return None

    if completed.returncode != 0:
        stderr_text = (completed.stderr or "").strip()
        print(f"Codex {'resume' if session_id else 'exec'} returned {completed.returncode} for {role}: {stderr_text}", flush=True)
        return None

    reply = extract_codex_text(completed.stdout or "")
    next_session_id = session_id or extract_codex_session_id(completed.stdout or "")
    if not reply:
        print(f"Codex {'resume' if session_id else 'exec'} produced no agent message for {role}.", flush=True)
        return None

    return {
        "reply": reply,
        "session_id": next_session_id,
    }


def maybe_codex_reply(store: TaskStore, role: str, item: Dict, task: Optional[Dict]) -> Optional[str]:
    if not codex_exec_enabled():
        return None

    prompt = build_codex_prompt(role, item, task)
    session_id = store.get_role_session(role)
    result = run_codex_for_role(role, prompt, session_id)
    if result is None and session_id:
        print(f"Falling back to fresh Codex session for {role}.", flush=True)
        result = run_codex_for_role(role, prompt, None)
    if result is None:
        return None

    next_session_id = result.get("session_id")
    if next_session_id and next_session_id != session_id:
        store.set_role_session(role, next_session_id)
        print(f"Stored Codex session for {role}: {next_session_id}", flush=True)

    return str(result["reply"]).strip()


def role_chat_reply(role: str, item: Dict, task: Optional[Dict]) -> str:
    message = item.get("message", "").strip() or "메시지를 확인했습니다."
    task_id = item.get("task_id")
    opener = ROLE_OPENERS[role]

    if role == "pm":
        if task_id and task:
            return (
                f"{opener} `{task_id}` 기준으로 계속 이어서 볼게요.\n"
                f"현재 상태는 `{task.get('status', 'unknown')}`이고, 제가 작업 정리나 역할 분배가 필요하면 바로 반영하겠습니다.\n"
                f"남겨주신 내용: {message}"
            )
        return (
            f"{opener} 이 요청은 새 작업으로 정리해서 shared task list에 올릴게요.\n"
            f"요청 내용: {message}"
        )

    role_focus = {
        "be-lead": "백엔드 아키텍처, API 경계, 데이터 흐름, 리스크",
        "be-dev": "구현 상세, 변경 범위, 테스트 포인트",
        "fe-lead": "화면 구조, 상태 흐름, UX 영향도, 리뷰 포인트",
        "fe-dev": "컴포넌트 구현, API 연동, 화면 반영 범위",
        "qa": "재현 경로, 회귀 포인트, 실패 시나리오",
        "security": "공격면, 권한, 입력 검증, 노출 위험",
    }[role]

    if task_id and task:
        return (
            f"{opener} `{task_id}` 맥락에서 이어서 보겠습니다.\n"
            f"제가 중점적으로 볼 부분은 {role_focus}입니다.\n"
            f"받은 메시지: {message}"
        )

    return (
        f"{opener} 아직 연결된 task id는 없지만 이 채널 기준으로 바로 같이 볼 수 있습니다.\n"
        f"제가 중점적으로 볼 부분은 {role_focus}입니다.\n"
        f"받은 메시지: {message}"
    )


def build_fallback_reply(role: str, item: Dict, task: Optional[Dict]) -> str:
    item_type = item.get("type")
    task_id = item.get("task_id")
    message = item.get("message", "").strip() or "메시지를 확인했습니다."

    if item_type == "task_created":
        return (
            f"사장님, 요청 받았습니다. `{task_id}` 로 작업을 등록했고 제가 먼저 범위를 정리하겠습니다.\n"
            f"원문 요청: {message}"
        )

    if item_type == "task_handoff":
        sender_name = ROLE_SPECS.get(item.get("from_role", ""), ROLE_SPECS[role]).display_name if item.get("from_role") in ROLE_SPECS else item.get("from_role", "unknown")
        return (
            f"{sender_name}에서 `{task_id}` 작업을 넘겨받았습니다.\n"
            f"전달 내용: {message}\n"
            f"이제 제가 제 역할 기준으로 이어서 진행하겠습니다, 사장님."
        )

    if item_type == "role_chat":
        return role_chat_reply(role, item, task)

    return summarize_message(role, item)


def build_role_reply(store: TaskStore, role: str, item: Dict, task: Optional[Dict]) -> str:
    codex_reply = maybe_codex_reply(store, role, item, task)
    if codex_reply:
        return codex_reply
    return build_fallback_reply(role, item, task)


def process_inbox_items(store: TaskStore, role: str, items: List[Dict]) -> None:
    for item in items:
        task_id = item.get("task_id")
        task = store.get_task(task_id) if task_id else None
        summary = summarize_message(role, item)
        reply = build_role_reply(store, role, item, task)
        print(summary, flush=True)

        if task_id and task:
            store.update_task(task_id, owner_role=role, status="in_progress")
            store.append_event("task_claimed", task_id, f"{role} claimed the task.", from_role=role)

        store.push_outbox(
            role,
            {
                "type": "status_summary",
                "task_id": task_id,
                "from_role": role,
                "reply_channel_id": item.get("reply_channel_id") or (task or {}).get("thread_id"),
                "message": reply,
                "guidance": ROLE_GUIDANCE[role],
            },
        )


def run(role: str, poll_interval: float) -> int:
    if role not in ROLE_SPECS:
        print(f"Unknown role: {role}", file=sys.stderr)
        return 2

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    store = TaskStore()
    display_name = ROLE_SPECS[role].display_name
    print(f"{display_name} runner started.", flush=True)
    print(ROLE_GUIDANCE[role], flush=True)

    while not STOP:
        store.set_role_heartbeat(role, "idle", ROLE_GUIDANCE[role])
        items = store.read_inbox(role)
        if items:
            store.set_role_heartbeat(role, "busy", f"Processing {len(items)} inbox item(s)")
            process_inbox_items(store, role, items)
            store.set_role_heartbeat(role, "idle", f"Processed {len(items)} inbox item(s)")
        time.sleep(poll_interval)

    store.set_role_heartbeat(role, "stopped", "Runner stopped")
    print(f"{display_name} runner stopped.", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a role runner for the local agent team MVP.")
    parser.add_argument("--role", required=True, choices=sorted(ROLE_SPECS))
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()
    return run(role=args.role, poll_interval=args.poll_interval)


if __name__ == "__main__":
    raise SystemExit(main())
