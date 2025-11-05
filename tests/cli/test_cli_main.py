from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_main_defaults_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: return a dummy command capturing args
    calls: list[dict] = []

    def fake_main(*, args: list[str], prog_name: str) -> None:  # click.Command.main signature
        calls.append({"args": args, "prog": prog_name})

    fake_get_command = lambda app: SimpleNamespace(main=fake_main)  # noqa: E731

    monkeypatch.setenv("FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER", "true")
    mod = importlib.import_module("birre.cli.main")
    monkeypatch.setattr(mod, "get_command", fake_get_command)

    # Act
    mod.main([])

    # Assert
    assert calls and calls[0]["args"] == ["run"]


def test_main_passes_help_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_main(*, args: list[str], prog_name: str) -> None:
        calls.append({"args": args, "prog": prog_name})

    fake_get_command = lambda app: SimpleNamespace(main=fake_main)  # noqa: E731

    mod = importlib.import_module("birre.cli.main")
    monkeypatch.setattr(mod, "get_command", fake_get_command)

    mod.main(["--help"])  # request help
    assert calls and calls[0]["args"] == ["--help"]


def test_main_treats_leading_flags_as_run_args(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_main(*, args: list[str], prog_name: str) -> None:
        calls.append({"args": args, "prog": prog_name})

    fake_get_command = lambda app: SimpleNamespace(main=fake_main)  # noqa: E731

    mod = importlib.import_module("birre.cli.main")
    monkeypatch.setattr(mod, "get_command", fake_get_command)

    mod.main(["-v", "--debug"])  # leading flag → routed to run
    assert calls and calls[0]["args"] == ["run", "-v", "--debug"]


def test_main_passes_through_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_main(*, args: list[str], prog_name: str) -> None:  # click.Command.main signature
        calls.append({"args": args, "prog": prog_name})

    fake_get_command = lambda app: SimpleNamespace(main=fake_main)  # noqa: E731

    mod = importlib.import_module("birre.cli.main")
    monkeypatch.setattr(mod, "get_command", fake_get_command)

    mod.main(["config", "show"])  # explicit subcommand path
    assert calls and calls[0]["args"] == ["config", "show"]


def test_main_help_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_main(*, args: list[str], prog_name: str) -> None:  # click.Command.main signature
        calls.append({"args": args, "prog": prog_name})

    fake_get_command = lambda app: SimpleNamespace(main=fake_main)  # noqa: E731

    mod = importlib.import_module("birre.cli.main")
    monkeypatch.setattr(mod, "get_command", fake_get_command)

    mod.main(["--help"])  # should pass through unchanged
    assert calls and calls[0]["args"] == ["--help"]
