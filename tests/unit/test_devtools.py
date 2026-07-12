"""Tests for developer command shortcuts."""

from __future__ import annotations

import pytest

from birre import devtools


def test_megalint_runs_default_checks_before_manual_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """MegaLinter runs the complete default hook set before manual hooks."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        devtools.subprocess,
        "call",
        lambda command: calls.append(command) or 0,
    )

    with pytest.raises(SystemExit) as exit_info:
        devtools.megalint()

    assert exit_info.value.code == 0
    assert calls == [
        ["pre-commit", "run", "--all-files"],
        ["pre-commit", "run", "megalinter", "--all-files", "--hook-stage", "manual"],
    ]


def test_megalint_stops_when_default_checks_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manual hooks do not run after a failing default hook set."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        devtools.subprocess,
        "call",
        lambda command: calls.append(command) or 1,
    )

    with pytest.raises(SystemExit) as exit_info:
        devtools.megalint()

    assert exit_info.value.code == 1
    assert calls == [["pre-commit", "run", "--all-files"]]


def test_todo_check_reports_markers_and_colored_help(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The TODO shortcut reports markers and retains colored command guidance."""
    (tmp_path / "notes.md").write_text("> **TODO:** Document this workflow.\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    devtools.todo_check()

    captured = capsys.readouterr()
    assert "TODO marker(s)" in captured.out
    assert "notes.md:1: > **TODO:** Document this workflow." in captured.out
    assert "\033[1;34m" in captured.err
    assert "\033[32muv run megalint\033[0m" in captured.err
