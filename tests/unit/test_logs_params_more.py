from __future__ import annotations

from birre.cli.commands import logs as logs_mod


def test_validate_logs_show_params_accepts_valid_format() -> None:
    fmt = logs_mod._validate_logs_show_params(
        tail=10, since=None, last=None, format_override="text"
    )
    assert fmt == "text"


def test_resolve_start_timestamp_since_valid() -> None:
    ts = logs_mod._resolve_start_timestamp("2025-11-01T00:00:00+00:00", None)
    assert isinstance(ts, float)
