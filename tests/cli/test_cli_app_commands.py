from __future__ import annotations

import importlib
from pathlib import Path

from typer.testing import CliRunner

app_mod = importlib.import_module("birre.cli.app")


def test_version_uses_pyproject(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    # Point PROJECT_ROOT to a temp dir with a pyproject.toml
    proj = tmp_path
    (proj / "README.md").write_text("# readme", encoding="utf-8")
    (proj / "pyproject.toml").write_text("[project]\nversion='9.9.9'\n", encoding="utf-8")

    monkeypatch.setattr(app_mod, "PROJECT_ROOT", proj)

    runner = CliRunner()
    result = runner.invoke(app_mod.app, ["version"], color=False)
    assert result.exit_code == 0
    assert result.stdout.strip()  # prints discovered package version


def test_readme_prints_readme(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    proj = tmp_path
    (proj / "README.md").write_text("hello world", encoding="utf-8")
    monkeypatch.setattr(app_mod, "PROJECT_ROOT", proj)

    runner = CliRunner()
    result = runner.invoke(app_mod.app, ["readme"], color=False)
    assert result.exit_code == 0
    assert "hello world" in result.stdout


def test_version_handles_missing_pyproject(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(app_mod, "PROJECT_ROOT", tmp_path)
    runner = CliRunner()
    result = runner.invoke(app_mod.app, ["version"], color=False)
    assert result.exit_code == 0
    assert result.stdout.strip()  # still prints installed package version


def test_readme_missing_raises(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(app_mod, "PROJECT_ROOT", tmp_path)
    runner = CliRunner()
    result = runner.invoke(app_mod.app, ["readme"], color=False)
    assert result.exit_code != 0


def test_banner_helpers_return_text() -> None:
    b = app_mod._banner()
    k = app_mod._keyboard_interrupt_banner()
    from rich.text import Text

    assert isinstance(b, Text) and isinstance(k, Text)


def test_version_uses_metadata(monkeypatch) -> None:  # noqa: ANN001
    import importlib

    app_mod = importlib.import_module("birre.cli.app")

    # Force metadata.version path
    class _Meta:
        class PackageNotFoundError(Exception):
            pass

        @staticmethod
        def version(name: str) -> str:  # noqa: D401
            return "9.9.9"

    monkeypatch.setattr(app_mod, "PROJECT_ROOT", Path("/__does_not_exist__"))
    # Patch importlib.metadata used inside the command function
    monkeypatch.setattr(importlib, "metadata", _Meta, raising=True)

    runner = CliRunner()
    result = runner.invoke(app_mod.app, ["version"], color=False)
    assert result.exit_code == 0 and result.stdout.strip() == "9.9.9"


def test_version_pyproject_unknown(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    # pyproject exists but without project.version → prints "unknown"
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    import importlib

    app_mod = importlib.import_module("birre.cli.app")
    monkeypatch.setattr(app_mod, "PROJECT_ROOT", tmp_path)
    runner = CliRunner()
    result = runner.invoke(app_mod.app, ["version"], color=False)
    assert result.exit_code == 0 and result.stdout.strip() == "unknown"
