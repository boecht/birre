import os
from pathlib import Path

import logging
import pytest

from src.config import LoggingSettings, resolve_birre_settings, resolve_logging_settings


CONFIG_WARNING = "Avoid storing bitsight.api_key in config.toml; prefer config.local.toml, environment variables, or CLI overrides."


def write_config(path: Path, *, include_api_key: bool) -> None:
    bitsight_block = ["[bitsight]"]
    if include_api_key:
        bitsight_block.append('api_key = "config-key"')
    else:
        bitsight_block.append("# api_key intentionally omitted")
    bitsight_block.append('subscription_folder = "API"')
    bitsight_block.append('subscription_type = "continuous_monitoring"')

    runtime_block = [
        "[runtime]",
        "skip_startup_checks = false",
        "debug = false",
    ]

    path.write_text(
        "\n".join(bitsight_block + ["", *runtime_block]) + "\n", encoding="utf-8"
    )


def write_local_config(path: Path, *, api_key: str) -> None:
    path.write_text(
        "\n".join(
            [
                "[bitsight]",
                f'api_key = "{api_key}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_warns_only_when_base_config_defines_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "config.toml"
    write_config(base, include_api_key=True)

    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["api_key"] == "config-key"
    assert settings["warnings"] == [CONFIG_WARNING]


def test_local_only_api_key_does_not_emit_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "config.toml"
    local = tmp_path / "config.local.toml"
    write_config(base, include_api_key=False)
    write_local_config(local, api_key="local-key")

    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["api_key"] == "local-key"
    assert settings["warnings"] == []


def test_cli_arg_overrides_env_and_sets_debug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "config.toml"
    write_config(base, include_api_key=False)

    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.setenv("BIRRE_DEBUG", "false")

    settings = resolve_birre_settings(
        config_path=str(base),
        api_key_arg="cli-key",
        debug_arg=True,
    )

    assert settings["api_key"] == "cli-key"
    assert os.environ["DEBUG"] == "true"

    # Calling again with debug disabled should drop the DEBUG env var
    resolve_birre_settings(
        config_path=str(base), api_key_arg="cli-key", debug_arg=False
    )
    assert "DEBUG" not in os.environ


def test_resolve_logging_settings_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / "config.toml"
    write_config(base, include_api_key=False)
    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)
    write_local_config(tmp_path / "config.local.toml", api_key="test")

    logging_settings = resolve_logging_settings(
        config_path=str(base),
        level_override="DEBUG",
        format_override="json",
        file_override=str(tmp_path / "logs" / "birre.log"),
        max_bytes_override=4096,
        backup_count_override=2,
    )

    assert isinstance(logging_settings, LoggingSettings)
    assert logging_settings.level == logging.DEBUG
    assert logging_settings.format == "json"
    assert logging_settings.file_path and logging_settings.file_path.endswith(
        "birre.log"
    )
    assert logging_settings.max_bytes == 4096
    assert logging_settings.backup_count == 2
