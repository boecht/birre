from __future__ import annotations

from pathlib import Path

import click
import pytest

import birre.cli.validation as v


def test_require_file_exists_errors(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        v.require_file_exists(None, param_hint="--file")
    missing = tmp_path / "nope.txt"
    with pytest.raises(Exception):
        v.require_file_exists(missing, param_hint="--file")


def test_parse_toml_file_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("= not toml", encoding="utf-8")
    with pytest.raises(Exception):
        v.parse_toml_file(bad, param_hint="--config")


def test_toml_parse_context_converts_exception() -> None:
    with pytest.raises(Exception):
        with v.toml_parse_context(param_hint="--config"):
            import tomllib

            tomllib.loads("= not toml")


def test_require_parameter_and_abort(capsys) -> None:  # noqa: ANN001
    with pytest.raises(Exception):
        v.require_parameter(None, param_hint="--x")
    with pytest.raises(Exception):
        v.require_parameter("  ", param_hint="--x")

    with pytest.raises(click.exceptions.Exit):
        v.abort_with_message("boom", exit_code=2)
