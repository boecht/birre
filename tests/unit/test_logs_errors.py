from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from birre.cli.commands import logs as logs_mod


def test_logs_clear_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "err.log"
    path.write_text("x", encoding="utf-8")

    def _fake_resolver(**_: Any):
        return SimpleNamespace(), SimpleNamespace(file_path=str(path), format="text")

    called = {"write": 0}

    def _raise(*args, **kwargs):  # noqa: ANN001
        called["write"] += 1
        raise OSError("disk full")

    class _C:
        def print(self, *args, **kwargs):  # noqa: ANN001
            return None

    stdout = _C()
    orig_resolve = logs_mod._resolve_logging_settings_from_cli
    try:
        monkeypatch.setattr(logs_mod, "_resolve_logging_settings_from_cli", _fake_resolver)
        monkeypatch.setattr(Path, "write_text", _raise, raising=True)
        with pytest.raises(Exception):
            logs_mod._cmd_logs_clear(tmp_path / "c.toml", None, stdout)  # type: ignore[arg-type]
        assert called["write"] == 1
    finally:
        logs_mod._resolve_logging_settings_from_cli = orig_resolve  # type: ignore[assignment]


def test_logs_rotate_nonexistent_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "no.log"

    def _fake_resolver(**_: Any):
        return (
            SimpleNamespace(),
            SimpleNamespace(file_path=str(path), format="text", backup_count=2),
        )

    touched = {"count": 0}

    def _touch(self):  # noqa: ANN001
        touched["count"] += 1

    class _C:
        def print(self, *args, **kwargs):  # noqa: ANN001
            return None

    stdout = _C()
    orig_resolve = logs_mod._resolve_logging_settings_from_cli
    try:
        monkeypatch.setattr(logs_mod, "_resolve_logging_settings_from_cli", _fake_resolver)
        monkeypatch.setattr(logs_mod, "validate_path_exists", lambda p: False)
        monkeypatch.setattr(Path, "touch", _touch, raising=True)
        logs_mod._cmd_logs_rotate(tmp_path / "c.toml", None, 2, stdout)  # type: ignore[arg-type]
        assert touched["count"] >= 1
    finally:
        logs_mod._resolve_logging_settings_from_cli = orig_resolve  # type: ignore[assignment]
