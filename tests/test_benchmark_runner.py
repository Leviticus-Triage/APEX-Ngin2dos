from __future__ import annotations

import importlib

import benchmark_runner as runner
from cli import build_parser, main


def test_benchmark_runner_reexports() -> None:
    assert runner.run_attack is not None
    assert runner.run_apex_scaled is not None
    assert runner.DEFAULT_HOST == "127.0.0.1"


def test_campaign_modules_import_cleanly() -> None:
    import campaigns

    for name in campaigns.__all__:
        assert callable(getattr(campaigns, name)), f"{name} is not callable"


def test_campaign_submodules_import() -> None:
    for mod in (
        "campaigns.apex",
        "campaigns.full",
        "campaigns.multiprocess",
        "campaigns.special",
        "campaigns.waves",
    ):
        importlib.import_module(mod)


def test_cli_parser_modes() -> None:
    parser = build_parser()
    args = parser.parse_args(["--host", "127.0.0.1", "--mode", "burst", "--connections", "1"])
    assert args.mode == "burst"
    assert args.connections == 1


def test_cli_refuses_remote_without_flag() -> None:
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["--host", "203.0.113.10", "--mode", "burst"])
    assert exc.value.code == 2
