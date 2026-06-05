#!/usr/bin/env python3
"""IIS apex_iis_mp runner — executes on Windows, prints command on Linux."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from attack_config import IisApexPreset

BENCH = Path(__file__).resolve().parent
PS1 = BENCH / "iis_apex_orchestrator.ps1"


def build_powershell_cmd(host: str, port: int, preset: str = "8gb") -> str:
    return (
        f'powershell -ExecutionPolicy Bypass -File "{PS1}" '
        f'-TargetHost {host} -Port {port} -Preset {preset}'
    )


def build_powershell_command(
    host: str,
    port: int,
    preset: IisApexPreset | str = "8gb",
    scope_description: str = "",
) -> str:
    del scope_description
    preset_name = preset.preset if isinstance(preset, IisApexPreset) else preset
    return build_powershell_cmd(host, port, preset_name)


def run_iis_apex_mp(host: str, port: int = 443, preset: str = "8gb") -> str:
    cmd = build_powershell_cmd(host, port, preset)
    if sys.platform != "win32":
        return (
            "IIS apex_iis_mp requires Windows.\n"
            f"Run on Windows Server:\n\n  {cmd}\n"
        )
    proc = subprocess.run(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(PS1),
            "-TargetHost",
            host,
            "-Port",
            str(port),
            "-Preset",
            preset,
        ],
        capture_output=True,
        text=True,
        timeout=7200,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return f"EXIT {proc.returncode}\n{out}"


def run_on_windows(host: str, port: int, preset: IisApexPreset) -> tuple[int, str]:
    out = run_iis_apex_mp(host, port, preset.preset)
    code = 0
    if out.startswith("EXIT "):
        try:
            code = int(out.split("\n", 1)[0].replace("EXIT ", ""))
        except ValueError:
            code = 1
    return code, out


if __name__ == "__main__":
    print(run_iis_apex_mp(sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"))
