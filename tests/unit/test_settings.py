from __future__ import annotations

from pathlib import Path
import logging
import pytest

from src.constants import DEFAULT_CONFIG_FILENAME
from src.settings import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_MAX_FINDINGS,
    DEFAULT_RISK_VECTOR_FILTER,
    LoggingInputs,
    LoggingSettings,
    RuntimeInputs,
    RuntimeSettings,
    SubscriptionInputs,
    TlsInputs,
    apply_cli_overrides,
    load_settings,
    logging_from_settings,
    resolve_application_settings,
    runtime_from_settings,
)


def _write_base_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "[bitsight]",
                'api_key = "file-key"',
                'subscription_folder = "FileFolder"',
                'subscription_type = "continuous_monitoring"',
                "",
                "[runtime]",
                "skip_startup_checks = false",
                "debug = false",
                "allow_insecure_tls = false",
                'ca_bundle_path = ""',
                "",
                "[roles]",
                'context = "standard"',
                f'risk_vector_filter = "{DEFAULT_RISK_VECTOR_FILTER}"',
                f"max_findings = {DEFAULT_MAX_FINDINGS}",
                "",
                "[logging]",
                'level = "INFO"',
                'format = "text"',
                'file = ""',
                "max_bytes = 10000000",
                "backup_count = 5",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_runtime_defaults_from_config(tmp_path: Path) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    settings_obj = load_settings(str(config_path))
    runtime = runtime_from_settings(settings_obj)

    assert isinstance(runtime, RuntimeSettings)
    assert runtime.api_key == "file-key"
    assert runtime.subscription_folder == "FileFolder"
    assert runtime.subscription_type == "continuous_monitoring"
    assert runtime.context == "standard"
    assert runtime.risk_vector_filter == DEFAULT_RISK_VECTOR_FILTER
    assert runtime.max_findings == DEFAULT_MAX_FINDINGS
    assert runtime.debug is False
    assert runtime.allow_insecure_tls is False
    assert runtime.warnings == ()
    assert runtime.overrides == ()


def test_environment_overrides_take_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    monkeypatch.setenv("BITSIGHT_API_KEY", "env-key")
    monkeypatch.setenv("BIRRE_SUBSCRIPTION_FOLDER", "EnvFolder")
    monkeypatch.setenv("BIRRE_SUBSCRIPTION_TYPE", "env-type")
    monkeypatch.setenv("BIRRE_CONTEXT", "risk_manager")
    monkeypatch.setenv("BIRRE_RISK_VECTOR_FILTER", "env1,env2")
    monkeypatch.setenv("BIRRE_MAX_FINDINGS", "25")
    monkeypatch.setenv("BIRRE_SKIP_STARTUP_CHECKS", "true")
    monkeypatch.setenv("BIRRE_ALLOW_INSECURE_TLS", "true")
    monkeypatch.setenv("BIRRE_CA_BUNDLE", " /tmp/custom.pem ")

    settings_obj = load_settings(str(config_path))
    runtime = runtime_from_settings(settings_obj)

    assert runtime.api_key == "env-key"
    assert runtime.subscription_folder == "EnvFolder"
    assert runtime.subscription_type == "env-type"
    assert runtime.context == "risk_manager"
    assert runtime.risk_vector_filter == "env1,env2"
    assert runtime.max_findings == 25
    assert runtime.skip_startup_checks is True
    assert runtime.allow_insecure_tls is True
    assert runtime.ca_bundle_path is None
    assert runtime.warnings == (
        "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled",
    )


def test_cli_overrides_supersede_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    monkeypatch.setenv("BIRRE_CONTEXT", "standard")
    monkeypatch.setenv("BIRRE_DEBUG", "false")

    settings_obj = load_settings(str(config_path))
    apply_cli_overrides(
        settings_obj,
        api_key_input="cli-key",
        subscription_inputs=SubscriptionInputs(folder="CliFolder", type="cli-type"),
        runtime_inputs=RuntimeInputs(
            context="risk_manager",
            debug=True,
            risk_vector_filter="cliA,cliB",
            max_findings=5,
            skip_startup_checks=True,
        ),
        tls_inputs=TlsInputs(allow_insecure=False, ca_bundle_path=" /etc/ssl/custom.pem "),
    )

    runtime = runtime_from_settings(settings_obj)
    assert runtime.api_key == "cli-key"
    assert runtime.subscription_folder == "CliFolder"
    assert runtime.subscription_type == "cli-type"
    assert runtime.context == "risk_manager"
    assert runtime.risk_vector_filter == "cliA,cliB"
    assert runtime.max_findings == 5
    assert runtime.skip_startup_checks is True
    assert runtime.debug is True
    assert runtime.ca_bundle_path == "/etc/ssl/custom.pem"


def test_blank_environment_values_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    monkeypatch.setenv("BIRRE_RISK_VECTOR_FILTER", "   ")
    monkeypatch.setenv("BIRRE_MAX_FINDINGS", "")

    settings_obj = load_settings(str(config_path))
    runtime = runtime_from_settings(settings_obj)

    assert runtime.risk_vector_filter == DEFAULT_RISK_VECTOR_FILTER
    assert runtime.max_findings == DEFAULT_MAX_FINDINGS
    assert runtime.warnings == ()


def test_allow_insecure_tls_warning(tmp_path: Path) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    settings_obj = load_settings(str(config_path))
    apply_cli_overrides(
        settings_obj,
        runtime_inputs=RuntimeInputs(),
        tls_inputs=TlsInputs(allow_insecure=True, ca_bundle_path="/tmp/ca.pem"),
    )

    runtime = runtime_from_settings(settings_obj)
    assert runtime.allow_insecure_tls is True
    assert runtime.ca_bundle_path is None
    assert runtime.warnings == (
        "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled",
    )


def test_logging_overrides_follow_cli(tmp_path: Path) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    settings_obj = load_settings(str(config_path))
    apply_cli_overrides(
        settings_obj,
        logging_inputs=LoggingInputs(
            level="DEBUG",
            format="json",
            file_path=str(tmp_path / "birre.log"),
            max_bytes=2048,
            backup_count=2,
        ),
    )

    logging_settings = logging_from_settings(settings_obj)
    assert isinstance(logging_settings, LoggingSettings)
    assert logging_settings.level == logging.DEBUG
    assert logging_settings.format == "json"
    assert logging_settings.file_path and logging_settings.file_path.endswith("birre.log")
    assert logging_settings.max_bytes == 2048
    assert logging_settings.backup_count == 2


def test_resolve_application_settings_combines_sections(tmp_path: Path) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    _write_base_config(config_path)

    runtime, logging_settings = resolve_application_settings(
        api_key_input="cli-key",
        config_path=str(config_path),
        subscription_inputs=SubscriptionInputs(folder="CliFolder"),
        runtime_inputs=RuntimeInputs(debug=True),
        logging_inputs=LoggingInputs(level="WARNING"),
    )

    assert isinstance(runtime, RuntimeSettings)
    assert runtime.api_key == "cli-key"
    assert runtime.debug is True
    assert logging_settings.level == logging.DEBUG
    assert logging_settings.format == DEFAULT_LOG_FORMAT
    assert logging_settings.max_bytes == 10_000_000
    assert logging_settings.backup_count == 5


def test_invalid_values_fall_back_with_warnings(tmp_path: Path) -> None:
    config_path = tmp_path / DEFAULT_CONFIG_FILENAME
    config_path.write_text(
        "\n".join(
            [
                "[bitsight]",
                'api_key = "file-key"',
                "",
                "[roles]",
                'context = "invalid"',
                'risk_vector_filter = ""',
                "max_findings = 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings_obj = load_settings(str(config_path))
    runtime = runtime_from_settings(settings_obj)

    assert runtime.context == "standard"
    assert runtime.risk_vector_filter == DEFAULT_RISK_VECTOR_FILTER
    assert runtime.max_findings == DEFAULT_MAX_FINDINGS
    assert runtime.warnings == (
        "Unknown context 'invalid' requested; defaulting to 'standard'",
        "Empty risk_vector_filter override; falling back to default configuration",
        "Invalid max_findings override; using default configuration",
    )
