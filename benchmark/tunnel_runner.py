"""Subprocess helpers that honor active tunnel/proxychains configuration."""
from __future__ import annotations

import os
import subprocess
from typing import Any

from tunnel import merge_subprocess_env, wrap_subprocess_argv


def run(
    argv: list[str],
    *,
    cwd: str | None = None,
    capture_output: bool = False,
    text: bool = True,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    wrapped = wrap_subprocess_argv(argv)
    merged_env = merge_subprocess_env(env or os.environ.copy())
    return subprocess.run(
        wrapped,
        cwd=cwd,
        capture_output=capture_output,
        text=text,
        timeout=timeout,
        env=merged_env,
    )


def popen(
    argv: list[str],
    *,
    cwd: str | None = None,
    stdout: Any = None,
    stderr: Any = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    wrapped = wrap_subprocess_argv(argv)
    merged_env = merge_subprocess_env(env or os.environ.copy())
    return subprocess.Popen(wrapped, cwd=cwd, stdout=stdout, stderr=stderr, env=merged_env)
