import os
from pathlib import Path

import logging
import pytest

from src.config import (
    DEFAULT_MAX_FINDINGS,
    DEFAULT_RISK_VECTOR_FILTER,
    LoggingSettings,
    resolve_birre_settings,
    resolve_logging_settings,
)
from src.constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME


CONFIG_WARNING = (
    "Avoid storing bitsight.api_key in "
    f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
)


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
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=True)

    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["api_key"] == "config-key"
    assert settings["warnings"] == [CONFIG_WARNING]


def test_local_only_api_key_does_not_emit_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    local = tmp_path / LOCAL_CONFIG_FILENAME
    write_config(base, include_api_key=False)
    write_local_config(local, api_key="local-key")

    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["api_key"] == "local-key"
    assert settings["warnings"] == []


def test_cli_arg_overrides_env_and_sets_debug(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
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
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=False)
    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)
    write_local_config(tmp_path / LOCAL_CONFIG_FILENAME, api_key="test")

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


def test_allow_insecure_tls_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=False)

    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)
    monkeypatch.delenv("BIRRE_ALLOW_INSECURE_TLS", raising=False)
    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.setenv("BIRRE_ALLOW_INSECURE_TLS", "true")

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["allow_insecure_tls"] is True
    assert settings["ca_bundle_path"] is None
    assert os.environ["BIRRE_ALLOW_INSECURE_TLS"] == "true"
    assert "BIRRE_CA_BUNDLE" not in os.environ


def test_ca_bundle_from_cli_overrides_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=False)

    monkeypatch.delenv("BITSIGHT_API_KEY", raising=False)
    monkeypatch.delenv("BIRRE_ALLOW_INSECURE_TLS", raising=False)
    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.setenv("BIRRE_CA_BUNDLE", " ")

    ca_path = tmp_path / "certs" / "proxy.pem"
    ca_path.parent.mkdir(parents=True, exist_ok=True)
    ca_path.write_text("dummy", encoding="utf-8")

    settings = resolve_birre_settings(
        config_path=str(base), ca_bundle_path_arg=str(ca_path)
    )

    assert settings["ca_bundle_path"] == str(ca_path)
    assert settings["allow_insecure_tls"] is False
    assert os.environ["BIRRE_CA_BUNDLE"] == str(ca_path)
    assert "BIRRE_ALLOW_INSECURE_TLS" not in os.environ


def test_invalid_context_falls_back_to_standard_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    base.write_text(
        "\n".join(
            [
                "[bitsight]",
                "subscription_folder = \"API\"",
                "subscription_type = \"continuous_monitoring\"",
                "",
                "[runtime]",
                "context = \"invalid\"",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.delenv("BIRRE_CONTEXT", raising=False)

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["context"] == "standard"
    assert settings["warnings"] == [
        "Unknown context 'invalid' requested; defaulting to 'standard'"
    ]
    assert os.environ["BIRRE_CONTEXT"] == "standard"


def test_empty_risk_filter_uses_default_and_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=False)

    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.delenv("BIRRE_RISK_VECTOR_FILTER", raising=False)

    settings = resolve_birre_settings(
        config_path=str(base), risk_vector_filter_arg="   "
    )

    assert settings["risk_vector_filter"] == DEFAULT_RISK_VECTOR_FILTER
    assert settings["warnings"] == [
        "Empty risk_vector_filter override; falling back to default configuration"
    ]
    assert os.environ["BIRRE_RISK_VECTOR_FILTER"] == DEFAULT_RISK_VECTOR_FILTER


def test_invalid_max_findings_reverts_to_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=False)

    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.setenv("BIRRE_MAX_FINDINGS", "0")
    monkeypatch.delenv("BIRRE_CONTEXT", raising=False)

    settings = resolve_birre_settings(config_path=str(base))

    assert settings["max_findings"] == DEFAULT_MAX_FINDINGS
    assert settings["warnings"] == [
        "Invalid max_findings override; using default configuration"
    ]
    assert os.environ["BIRRE_MAX_FINDINGS"] == str(DEFAULT_MAX_FINDINGS)


def test_allow_insecure_tls_overrides_ca_bundle_with_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base = tmp_path / DEFAULT_CONFIG_FILENAME
    write_config(base, include_api_key=False)

    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.delenv("BIRRE_ALLOW_INSECURE_TLS", raising=False)
    monkeypatch.delenv("BIRRE_CA_BUNDLE", raising=False)

    ca_path = tmp_path / "certs" / "bundle.pem"
    ca_path.parent.mkdir(parents=True, exist_ok=True)
    ca_path.write_text("dummy", encoding="utf-8")

    settings = resolve_birre_settings(
        config_path=str(base),
        allow_insecure_tls_arg=True,
        ca_bundle_path_arg=str(ca_path),
    )

    assert settings["allow_insecure_tls"] is True
    assert settings["ca_bundle_path"] is None
    assert settings["warnings"] == [
        "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
    ]
    assert os.environ["BIRRE_ALLOW_INSECURE_TLS"] == "true"
    assert "BIRRE_CA_BUNDLE" not in os.environ
