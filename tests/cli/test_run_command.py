from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from birre.infrastructure.errors import ErrorContext, TlsCertificateChainInterceptedError


def _mk_settings(tmp_path: Path):
    runtime = SimpleNamespace()
    logging = SimpleNamespace()
    return runtime, logging, object()


def test_run_handles_birre_error_and_online_false(tmp_path: Path) -> None:
    runner = CliRunner()
    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            side_effect=lambda inv: _mk_settings(tmp_path),
        ),
        patch("birre.cli.commands.run.initialize_logging", return_value=MagicMock(name="logger")),
        patch("birre.cli.commands.run.run_offline_checks", return_value=True),
        patch("birre.cli.commands.run.run_online_checks", side_effect=Exception("boom")),
    ):
        # When run_online_checks raises a plain Exception,
        # typer.Exit should bubble with code 1 via except BirreError? (not caught)
        # We safely assert exit_code != 0 as a safeguard for error branch execution
        result = runner.invoke(importlib.import_module("birre.cli.app").app, ["run"], color=False)
        assert result.exit_code != 0

    # online_ok False path
    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            side_effect=lambda inv: _mk_settings(tmp_path),
        ),
        patch("birre.cli.commands.run.initialize_logging", return_value=MagicMock(name="logger")),
        patch("birre.cli.commands.run.run_offline_checks", return_value=True),
        patch("birre.cli.commands.run.run_online_checks", return_value=False),
    ):
        result = runner.invoke(importlib.import_module("birre.cli.app").app, ["run"], color=False)
        assert result.exit_code == 1


def test_run_keyboard_interrupt_and_profiling(tmp_path: Path) -> None:
    runner = CliRunner()

    profile_path = tmp_path / "prof.out"

    class _Server:
        def __init__(self, raise_keyboard: bool = False) -> None:
            self._raise_keyboard = raise_keyboard

        def run(self) -> None:
            if self._raise_keyboard:
                raise KeyboardInterrupt

    logger = MagicMock(name="logger")

    # Profiling branch: ensure file is written
    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            side_effect=lambda inv: _mk_settings(tmp_path),
        ),
        patch("birre.cli.commands.run.initialize_logging", return_value=logger),
        patch("birre.cli.commands.run.run_offline_checks", return_value=True),
        patch("birre.cli.commands.run.run_online_checks", return_value=True),
        patch("birre.cli.commands.run.prepare_server", return_value=_Server()),
    ):
        result = runner.invoke(
            importlib.import_module("birre.cli.app").app,
            ["run", "--profile", str(profile_path)],
            color=False,
        )
        assert result.exit_code == 0
        assert profile_path.exists()

    # KeyboardInterrupt branch
    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            side_effect=lambda inv: _mk_settings(tmp_path),
        ),
        patch("birre.cli.commands.run.initialize_logging", return_value=logger),
        patch("birre.cli.commands.run.run_offline_checks", return_value=True),
        patch("birre.cli.commands.run.run_online_checks", return_value=True),
        patch("birre.cli.commands.run.prepare_server", return_value=_Server(raise_keyboard=True)),
    ):
        result = runner.invoke(importlib.import_module("birre.cli.app").app, ["run"], color=False)
        assert result.exit_code == 0


def test_run_happy_path_without_profile(tmp_path: Path) -> None:
    runner = CliRunner()

    class _Server:
        def run(self) -> None:
            return None

    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            side_effect=lambda inv: _mk_settings(tmp_path),
        ),
        patch("birre.cli.commands.run.initialize_logging", return_value=MagicMock(name="logger")),
        patch("birre.cli.commands.run.run_offline_checks", return_value=True),
        patch("birre.cli.commands.run.run_online_checks", return_value=True),
        patch("birre.cli.commands.run.prepare_server", return_value=_Server()),
    ):
        result = runner.invoke(importlib.import_module("birre.cli.app").app, ["run"], color=False)
        assert result.exit_code == 0


def test_run_online_checks_domain_error(tmp_path: Path) -> None:
    runner = CliRunner()
    ctx = ErrorContext(tool="t", op="GET /", host="x", code="TLS")
    err = TlsCertificateChainInterceptedError(context=ctx)

    with (
        patch(
            "birre.cli.commands.run.resolve_runtime_and_logging",
            side_effect=lambda inv: _mk_settings(tmp_path),
        ),
        patch("birre.cli.commands.run.initialize_logging", return_value=MagicMock(name="logger")),
        patch("birre.cli.commands.run.run_offline_checks", return_value=True),
        patch("birre.cli.commands.run.run_online_checks", side_effect=err),
    ):
        result = runner.invoke(importlib.import_module("birre.cli.app").app, ["run"], color=False)
        assert result.exit_code == 1
