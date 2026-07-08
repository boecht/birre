from __future__ import annotations

from pathlib import Path

import pytest
import typer

from birre.cli.commands import logs as logs_mod


def test_rotate_logs_with_backups(tmp_path: Path) -> None:
    base = tmp_path / "birre.log"
    base.write_text("a", encoding="utf-8")
    # create numbered backups .1 and .2 so shifting occurs
    (tmp_path / "birre.log.1").write_text("b", encoding="utf-8")
    (tmp_path / "birre.log.2").write_text("c", encoding="utf-8")

    logs_mod._rotate_logs(base, backup_count=2)  # type: ignore[attr-defined]

    # files should be shifted up one, and a new empty base created
    assert (tmp_path / "birre.log.3").exists()
    assert (tmp_path / "birre.log.2").read_text(encoding="utf-8") == "b"
    assert (tmp_path / "birre.log.1").exists()
    assert base.exists()


def test_parse_helpers_edge_cases() -> None:
    # _parse_iso_timestamp_to_epoch edge inputs
    assert logs_mod._parse_iso_timestamp_to_epoch(None) is None  # type: ignore[arg-type]
    assert logs_mod._parse_iso_timestamp_to_epoch("") is None
    assert logs_mod._parse_iso_timestamp_to_epoch("not-a-timestamp") is None

    # _parse_relative_duration edge inputs
    assert logs_mod._parse_relative_duration(None) is None  # type: ignore[arg-type]
    assert logs_mod._parse_relative_duration(" ") is None
    assert logs_mod._parse_relative_duration("10x") is None


def test_parse_json_without_level() -> None:
    entry = logs_mod._parse_json_log_line("{}")
    assert entry.level is None and entry.timestamp is None


def test_should_include_with_normalized_text_level() -> None:
    # When numeric level is missing, fallback to normalized_level string search
    parsed = logs_mod.LogViewLine(
        raw="INFO something happened",
        level=None,
        timestamp=None,
        json_data=None,
    )
    assert logs_mod._should_include_log_entry(
        parsed, level_threshold=20, normalized_level="INFO", start_timestamp=None
    )


def test_should_exclude_when_before_start_timestamp() -> None:
    parsed = logs_mod.LogViewLine(raw="x", level=30, timestamp=0.0, json_data=None)
    assert not logs_mod._should_include_log_entry(
        parsed, level_threshold=None, normalized_level=None, start_timestamp=1.0
    )


def test_display_when_no_matches(capsys) -> None:
    from rich.console import Console

    logs_mod._display_log_entries([], "text", Console(file=None))
    # Nothing should explode; rich prints to an internal file when None


def test_cmd_logs_clear_oserror(monkeypatch, tmp_path: Path, capsys) -> None:
    # Point logging settings to our temp file by stubbing resolver
    faux = tmp_path / "app.log"
    faux.write_text("x", encoding="utf-8")

    def _fake_resolve(**kwargs):  # type: ignore[no-untyped-def]
        class LS:  # minimal logging settings shape
            file_path = str(faux)

        return object(), LS(), object()

    monkeypatch.setattr(logs_mod, "resolve_runtime_and_logging", lambda *a, **k: _fake_resolve())

    # Raise on write_text to hit except path
    def _boom(*a, **k):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _boom, raising=True)
    from rich.console import Console

    with pytest.raises(typer.BadParameter):
        logs_mod._cmd_logs_clear(tmp_path / "cfg.toml", None, Console(file=None))


def test_cmd_logs_path_resolve_oserror(monkeypatch, tmp_path: Path) -> None:
    # Stub logging settings with a path that triggers resolve exception
    faux = tmp_path / "app.log"
    faux.write_text("x", encoding="utf-8")

    def _fake_resolve(**kwargs):  # type: ignore[no-untyped-def]
        class LS:
            file_path = str(faux)

        return object(), LS(), object()

    monkeypatch.setattr(logs_mod, "resolve_runtime_and_logging", lambda *a, **k: _fake_resolve())

    def _raise_oserror(self, *a, **k):  # type: ignore[no-untyped-def]
        raise OSError("bad path")

    monkeypatch.setattr(Path, "resolve", _raise_oserror, raising=True)
    from rich.console import Console

    # Should handle the OSError and still print
    logs_mod._cmd_logs_path(tmp_path / "cfg.toml", None, Console(file=None))
