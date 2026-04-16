from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RUNTIME_DIR = ROOT_DIR / ".codex-tmp" / "agent-team"


@dataclass(frozen=True)
class RoleSpec:
    key: str
    display_name: str
    summary: str


ROLE_SPECS: Dict[str, RoleSpec] = {
    "pm": RoleSpec("pm", "PM", "Main agent (team lead) / final report owner"),
    "be-lead": RoleSpec("be-lead", "BE Lead", "20+ year backend lead / review + task split"),
    "be-dev": RoleSpec("be-dev", "BE Dev", "Backend implementation worker"),
    "fe-lead": RoleSpec("fe-lead", "FE Lead", "20+ year frontend lead / review + task split"),
    "fe-dev": RoleSpec("fe-dev", "FE Dev", "Frontend implementation worker"),
    "qa": RoleSpec("qa", "QA", "Failure prediction / Playwright / regression handoff"),
    "security": RoleSpec("security", "Security", "20+ year security review / exploitability handoff"),
}


def runtime_dir() -> Path:
    override = os.environ.get("TMUX_AGENT_RUNTIME_DIR")
    return Path(override).expanduser().resolve() if override else DEFAULT_RUNTIME_DIR


def runtime_paths() -> Dict[str, Path]:
    base = runtime_dir()
    return {
        "base": base,
        "tasks": base / "tasks.json",
        "events": base / "events.jsonl",
        "role_state": base / "role-state.json",
        "inbox": base / "inbox",
        "outbox": base / "outbox",
        "offsets": base / "offsets",
    }


def ensure_runtime_layout() -> Dict[str, Path]:
    paths = runtime_paths()
    paths["base"].mkdir(parents=True, exist_ok=True)
    paths["inbox"].mkdir(parents=True, exist_ok=True)
    paths["outbox"].mkdir(parents=True, exist_ok=True)
    paths["offsets"].mkdir(parents=True, exist_ok=True)
    for role in ROLE_SPECS:
        (paths["inbox"] / f"{role}.jsonl").touch(exist_ok=True)
        (paths["outbox"] / f"{role}.jsonl").touch(exist_ok=True)
    if not paths["tasks"].exists():
        paths["tasks"].write_text("{}\n", encoding="utf-8")
    if not paths["role_state"].exists():
        paths["role_state"].write_text("{}\n", encoding="utf-8")
    paths["events"].touch(exist_ok=True)
    return paths


def all_roles() -> List[str]:
    return list(ROLE_SPECS.keys())


def role_env_key(role: str) -> str:
    normalized = role.upper().replace("-", "_")
    return f"DISCORD_{normalized}_CHANNEL_ID"


def parse_channel_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def discord_channel_map() -> Dict[str, Dict]:
    incoming: Dict[int, str] = {}
    outgoing: Dict[str, int] = {}
    named: Dict[str, int] = {}

    router_channel = parse_channel_id(os.environ.get("DISCORD_ROUTER_CHANNEL_ID")) or parse_channel_id(os.environ.get("DISCORD_CHANNEL_ID"))
    pm_channel = parse_channel_id(os.environ.get("DISCORD_PM_CHANNEL_ID"))
    backend_channel = parse_channel_id(os.environ.get("DISCORD_BACKEND_CHANNEL_ID"))
    frontend_channel = parse_channel_id(os.environ.get("DISCORD_FRONTEND_CHANNEL_ID"))
    qa_channel = parse_channel_id(os.environ.get("DISCORD_QA_CHANNEL_ID"))
    security_channel = parse_channel_id(os.environ.get("DISCORD_SECURITY_CHANNEL_ID"))

    if router_channel:
        incoming[router_channel] = "pm"
        named["router"] = router_channel

    if pm_channel:
        incoming[pm_channel] = "pm"
        outgoing["pm"] = pm_channel
        named["pm"] = pm_channel

    if backend_channel:
        incoming[backend_channel] = "be-lead"
        outgoing["be-lead"] = backend_channel
        outgoing["be-dev"] = backend_channel
        named["backend"] = backend_channel

    if frontend_channel:
        incoming[frontend_channel] = "fe-lead"
        outgoing["fe-lead"] = frontend_channel
        outgoing["fe-dev"] = frontend_channel
        named["frontend"] = frontend_channel

    if qa_channel:
        incoming[qa_channel] = "qa"
        outgoing["qa"] = qa_channel
        named["qa"] = qa_channel

    if security_channel:
        incoming[security_channel] = "security"
        outgoing["security"] = security_channel
        named["security"] = security_channel

    # Fine-grained per-role overrides win over shared channels.
    for role in ROLE_SPECS:
        role_channel = parse_channel_id(os.environ.get(role_env_key(role)))
        if role_channel:
            incoming[role_channel] = role
            outgoing[role] = role_channel

    return {
        "incoming": incoming,
        "outgoing": outgoing,
        "named": named,
    }
