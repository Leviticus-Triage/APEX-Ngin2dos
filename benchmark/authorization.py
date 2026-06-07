"""Authorization gates for MCP, CLI, and benchmark harness."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MIN_SCOPE_LENGTH = 12
REJECTED_PREFIX = "REJECTED"

# Lab-only defaults — never point at production infrastructure.
DEFAULT_LAB_HOST = "127.0.0.1"
DEFAULT_LAB_PORT = 8443


def load_allowlist(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def check_host_allowed(host: str, allowlist_path: Path) -> tuple[bool, str]:
    entries = load_allowlist(allowlist_path)
    if not entries:
        return True, "No allowlist configured — authorization_confirmed is required."
    host_l = host.strip().lower()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        allowed = str(entry.get("host", "")).strip().lower()
        if allowed and (host_l == allowed or host_l.endswith("." + allowed)):
            return True, f"Target allowed by allowlist: {allowed}"
    return (
        False,
        f"Host '{host}' is not listed in {allowlist_path}. "
        "Add an entry or remove the allowlist file for lab-only use.",
    )


def is_lab_host(host: str) -> bool:
    host_l = host.strip().lower()
    return host_l in {"127.0.0.1", "localhost", "::1"}


def check_authorization(
    authorization_confirmed: bool,
    scope_description: str,
    host: str,
    allowlist_path: Path,
) -> str | None:
    if not authorization_confirmed:
        return (
            "authorization_confirmed must be true "
            "(written permission required for this target)."
        )
    if len(scope_description.strip()) < MIN_SCOPE_LENGTH:
        return (
            f"scope_description too short (min. {MIN_SCOPE_LENGTH} characters, "
            "e.g. customer/ticket/scope reference)."
        )
    ok, msg = check_host_allowed(host, allowlist_path)
    if not ok:
        return msg
    return None


def reject_message(reason: str) -> str:
    return f"{REJECTED_PREFIX}: {reason}"
