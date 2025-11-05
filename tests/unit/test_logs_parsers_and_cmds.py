from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from birre.cli.commands import logs as logs_mod


def test_parse_iso_timestamp_and_relative_duration() -> None:
    now = datetime.now(UTC)
    iso = now.isoformat()
    ts = logs_mod._parse_iso_timestamp_to_epoch(iso)
    assert isinstance(ts, float)
    assert abs(ts - now.timestamp()) < 2

    assert logs_mod._parse_iso_timestamp_to_epoch("invalid") is None

    assert logs_mod._parse_relative_duration("15m") == timedelta(minutes=15)
    assert logs_mod._parse_relative_duration("2h") == timedelta(hours=2)
    assert logs_mod._parse_relative_duration("1d") == timedelta(days=1)
    assert logs_mod._parse_relative_duration("bad") is None


def test_validate_and_resolve_start_timestamp() -> None:
    # since wins
    with pytest.raises(Exception):
        logs_mod._validate_logs_show_params(-1, None, None, None)
    with pytest.raises(Exception):
        logs_mod._validate_logs_show_params(10, "x", "y", None)

    assert logs_mod._validate_logs_show_params(10, None, None, "json") == "json"
    with pytest.raises(Exception):
        logs_mod._validate_logs_show_params(10, None, None, "weird")

    now = datetime.now(UTC)
    iso = now.isoformat()
    start = logs_mod._resolve_start_timestamp(iso, None)
    assert isinstance(start, float)

    start2 = logs_mod._resolve_start_timestamp(None, "30m")
    assert isinstance(start2, float)


def test_parse_log_lines_text_and_json() -> None:
    txt = "[2025-11-01T12:00:00+00:00] INFO birre starting"
    entry = logs_mod._parse_log_line(txt, "text")
    assert entry.timestamp and entry.level

    payload = {"timestamp": "2025-11-01T12:00:00Z", "level": "INFO", "event": "x"}
    json_line = json.dumps(payload)
    jentry = logs_mod._parse_log_line(json_line, "json")
    assert jentry.timestamp and jentry.level and jentry.json_data

    bad = logs_mod._parse_log_line("{not json}", "json")
    assert bad.json_data is None


def test_display_and_filters(tmp_path: Path) -> None:
    # Build a small JSON log file
    path = tmp_path / "app.log"
    records = [
        {"timestamp": "2025-11-01T12:00:00Z", "level": "INFO", "event": "start"},
        {"timestamp": "2025-11-01T12:10:00Z", "level": "WARNING", "event": "warn"},
        {"timestamp": "2025-11-01T12:20:00Z", "level": "ERROR", "event": "err"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    # Patch resolver to point at our file with json format
    def _fake_resolver(**_: Any):
        return SimpleNamespace(), SimpleNamespace(file_path=str(path), format="json")

    # Exercise show with level and tail
    out_lines: list[str] = []

    class _Console:
        def print(self, *args, **kwargs):  # noqa: ANN001
            out_lines.append(" ".join(str(a) for a in args))

        def print_json(self, *, data):  # noqa: ANN001
            out_lines.append(json.dumps(data))

    stdout = _Console()

    orig = logs_mod._resolve_logging_settings_from_cli
    try:
        logs_mod._resolve_logging_settings_from_cli = _fake_resolver  # type: ignore[assignment]
        logs_mod._cmd_logs_show(
            config=tmp_path / "config.toml",
            log_file=None,
            level="WARNING",
            tail=2,
            since=None,
            last=None,
            format_override="json",
            stdout_console=stdout,  # type: ignore[arg-type]
        )
    finally:
        logs_mod._resolve_logging_settings_from_cli = orig  # type: ignore[assignment]

    # Should include last two and honor level ≥ WARNING
    assert len(out_lines) == 2
    assert "warn" in out_lines[0] or "err" in out_lines[0]


def test_logs_clear_rotate_and_path(tmp_path: Path) -> None:
    log_file = tmp_path / "demo.log"
    log_file.write_text("hello", encoding="utf-8")

    # Fake resolver returning our file and defaults
    def _fake_resolver(**_: Any):
        return SimpleNamespace(), SimpleNamespace(
            file_path=str(log_file), format="text", backup_count=2
        )

    stdout_lines: list[str] = []

    class _Console:
        def print(self, *args, **kwargs):  # noqa: ANN001
            stdout_lines.append(" ".join(str(a) for a in args))

    stdout = _Console()

    orig = logs_mod._resolve_logging_settings_from_cli
    try:
        logs_mod._resolve_logging_settings_from_cli = _fake_resolver  # type: ignore[assignment]
        # clear
        logs_mod._cmd_logs_clear(config=tmp_path / "x.toml", log_file=None, stdout_console=stdout)  # type: ignore[arg-type]
        assert log_file.read_text(encoding="utf-8") == ""

        # write a couple of lines to rotate
        log_file.write_text("one\n", encoding="utf-8")
        logs_mod._cmd_logs_rotate(
            config=tmp_path / "x.toml",
            log_file=None,
            log_backup_count=1,
            stdout_console=stdout,  # type: ignore[arg-type]
        )
        assert (tmp_path / "demo.log.1").exists()

        # path
        logs_mod._cmd_logs_path(config=tmp_path / "x.toml", log_file=None, stdout_console=stdout)  # type: ignore[arg-type]
        assert any("Log file (absolute)" in line for line in stdout_lines)
    finally:
        logs_mod._resolve_logging_settings_from_cli = orig  # type: ignore[assignment]

    # Directly exercise rotate with backup_count <= 0 (truncate)
    log_file.write_text("SOME DATA", encoding="utf-8")
    logs_mod._rotate_logs(log_file, 0)
    assert log_file.read_text(encoding="utf-8") == ""


def test_logs_disabled_paths(tmp_path: Path) -> None:
    # Resolver returning no file logging
    def _fake_resolver(**_: Any):
        return SimpleNamespace(), SimpleNamespace(file_path="", format="json")

    outs: list[str] = []

    class _C:
        def print(self, *args, **kwargs):  # noqa: ANN001
            outs.append(" ".join(str(a) for a in args))

    stdout = _C()

    orig = logs_mod._resolve_logging_settings_from_cli
    try:
        logs_mod._resolve_logging_settings_from_cli = _fake_resolver  # type: ignore[assignment]
        logs_mod._cmd_logs_show(tmp_path / "c.toml", None, None, 10, None, None, None, stdout)  # type: ignore[arg-type]
        logs_mod._cmd_logs_path(tmp_path / "c.toml", None, stdout)  # type: ignore[arg-type]
        logs_mod._cmd_logs_clear(tmp_path / "c.toml", None, stdout)  # type: ignore[arg-type]
    finally:
        logs_mod._resolve_logging_settings_from_cli = orig  # type: ignore[assignment]
    assert any("disabled" in s.lower() for s in outs)


def test_should_include_log_entry_fallback_level() -> None:
    entry = logs_mod.LogViewLine(
        raw="something ERROR happened", level=None, timestamp=None, json_data=None
    )
    ok = logs_mod._should_include_log_entry(
        entry, level_threshold=30, normalized_level="ERROR", start_timestamp=None
    )
    assert ok is True
