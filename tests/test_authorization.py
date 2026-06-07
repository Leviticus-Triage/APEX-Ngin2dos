from __future__ import annotations

import json
from pathlib import Path

import pytest
from authorization import (
    MIN_SCOPE_LENGTH,
    check_authorization,
    check_host_allowed,
    is_lab_host,
    load_allowlist,
    reject_message,
)


@pytest.fixture
def allowlist_path(tmp_path: Path) -> Path:
    path = tmp_path / "allowed_targets.json"
    path.write_text(
        json.dumps([{"host": "lab.example.com", "note": "test lab"}]),
        encoding="utf-8",
    )
    return path


def test_load_allowlist_missing_returns_empty(tmp_path: Path) -> None:
    assert load_allowlist(tmp_path / "missing.json") == []


def test_check_host_allowed_without_allowlist(tmp_path: Path) -> None:
    ok, msg = check_host_allowed("example.com", tmp_path / "missing.json")
    assert ok is True
    assert "No allowlist" in msg


def test_check_host_allowed_enforces_list(allowlist_path: Path) -> None:
    ok, _ = check_host_allowed("lab.example.com", allowlist_path)
    assert ok is True

    ok, msg = check_host_allowed("evil.example.com", allowlist_path)
    assert ok is False
    assert "not listed" in msg


def test_check_authorization_requires_confirmation(allowlist_path: Path) -> None:
    err = check_authorization(
        authorization_confirmed=False,
        scope_description="Ticket INT-12345",
        host="lab.example.com",
        allowlist_path=allowlist_path,
    )
    assert err is not None
    assert "authorization_confirmed" in err


def test_check_authorization_requires_scope_length(allowlist_path: Path) -> None:
    err = check_authorization(
        authorization_confirmed=True,
        scope_description="short",
        host="lab.example.com",
        allowlist_path=allowlist_path,
    )
    assert err is not None
    assert str(MIN_SCOPE_LENGTH) in err


def test_check_authorization_passes_for_allowed_target(allowlist_path: Path) -> None:
    err = check_authorization(
        authorization_confirmed=True,
        scope_description="Ticket INT-12345 lab",
        host="lab.example.com",
        allowlist_path=allowlist_path,
    )
    assert err is None


def test_is_lab_host() -> None:
    assert is_lab_host("127.0.0.1") is True
    assert is_lab_host("localhost") is True
    assert is_lab_host("203.0.113.10") is False


def test_reject_message_prefix() -> None:
    assert reject_message("denied").startswith("REJECTED:")
