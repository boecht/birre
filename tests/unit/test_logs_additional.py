from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from birre.cli.commands import logs as logs_mod


def test_invalid_since_and_format_raises() -> None:
    with pytest.raises(Exception):
        logs_mod._resolve_start_timestamp("not-timestamp", None)
    with pytest.raises(Exception):
        logs_mod._validate_logs_show_params(1, None, None, "xml")


def test_logs_show_file_not_found(tmp_path: Path) -> None:
    def _fake_resolver(**_):  # noqa: ANN001
        return SimpleNamespace(), SimpleNamespace(
            file_path=str(tmp_path / "missing.log"), format="text"
        )

    outs: list[str] = []

    class _C:
        def print(self, *args, **kwargs):  # noqa: ANN001
            outs.append(" ".join(str(a) for a in args))

    orig = logs_mod._resolve_logging_settings_from_cli
    try:
        logs_mod._resolve_logging_settings_from_cli = _fake_resolver  # type: ignore[assignment]
        logs_mod._cmd_logs_show(tmp_path / "c.toml", None, None, 10, None, None, None, _C())  # type: ignore[arg-type]
    finally:
        logs_mod._resolve_logging_settings_from_cli = orig  # type: ignore[assignment]
    assert any("not found" in s.lower() for s in outs)


def test_text_line_level_detection() -> None:
    ln = "2025-11-01T00:00:00Z ERROR something happened"
    entry = logs_mod._parse_text_log_line(ln)
    assert entry.level and entry.timestamp
