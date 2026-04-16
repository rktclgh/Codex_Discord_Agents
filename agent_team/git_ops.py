from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List


COMMIT_PREFIX_PATTERN = re.compile(r"^\[[a-z]+\]\s+", re.IGNORECASE)


def _run_git(root_dir: Path, args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root_dir),
        capture_output=True,
        text=True,
        check=False,
    )


def _normalize_scope(root_dir: Path, paths: List[str]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for raw in paths:
        candidate = raw.strip()
        if not candidate:
            continue
        resolved = (root_dir / candidate).resolve()
        try:
            resolved.relative_to(root_dir.resolve())
        except ValueError:
            continue
        relative = resolved.relative_to(root_dir.resolve()).as_posix()
        if relative not in seen:
            seen.add(relative)
            normalized.append(relative)
    return normalized


def _normalize_commit_message(task_id: str, review_note: str) -> str:
    cleaned = review_note.strip() or f"lead review complete for {task_id}"
    if COMMIT_PREFIX_PATTERN.match(cleaned):
        return cleaned
    return f"[chore] {cleaned}"


def commit_task_changes(root_dir: Path, task: Dict, reviewer_role: str, review_note: str) -> Dict:
    branch_proc = _run_git(root_dir, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch_proc.returncode != 0:
        return {
            "status": "error",
            "message": branch_proc.stderr.strip() or "현재 브랜치 정보를 읽지 못했습니다.",
        }

    branch = branch_proc.stdout.strip()
    if not branch or branch == "HEAD":
        return {
            "status": "error",
            "message": "detached HEAD 상태에서는 자동 커밋을 진행하지 않습니다.",
        }

    scope = _normalize_scope(root_dir, list(task.get("write_scope") or []))
    if not scope:
        return {
            "status": "no_scope",
            "message": "이 작업에는 write scope가 등록되어 있지 않습니다.",
        }

    status_proc = _run_git(root_dir, ["status", "--porcelain", "--", *scope])
    if status_proc.returncode != 0:
        return {
            "status": "error",
            "message": status_proc.stderr.strip() or "작업 범위의 변경 사항을 확인하지 못했습니다.",
        }

    if not status_proc.stdout.strip():
        return {
            "status": "no_changes",
            "message": "등록된 작업 범위에는 아직 커밋할 변경 사항이 없습니다.",
            "branch": branch,
            "scope": scope,
        }

    add_proc = _run_git(root_dir, ["add", "--", *scope])
    if add_proc.returncode != 0:
        return {
            "status": "error",
            "message": add_proc.stderr.strip() or "작업 범위를 stage하지 못했습니다.",
            "branch": branch,
            "scope": scope,
        }

    commit_message = _normalize_commit_message(task.get("task_id", "TASK"), review_note)
    commit_proc = _run_git(root_dir, ["commit", "-m", commit_message])
    if commit_proc.returncode != 0:
        return {
            "status": "error",
            "message": commit_proc.stderr.strip() or commit_proc.stdout.strip() or "자동 커밋에 실패했습니다.",
            "branch": branch,
            "scope": scope,
            "commit_message": commit_message,
        }

    hash_proc = _run_git(root_dir, ["rev-parse", "HEAD"])
    commit_hash = hash_proc.stdout.strip() if hash_proc.returncode == 0 else ""

    return {
        "status": "committed",
        "branch": branch,
        "scope": scope,
        "commit_message": commit_message,
        "commit_hash": commit_hash,
        "reviewer_role": reviewer_role,
    }
