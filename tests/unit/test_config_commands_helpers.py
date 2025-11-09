from __future__ import annotations

from pathlib import Path

from birre.cli.commands.config import (
    _build_cli_override_rows,
    _build_env_override_rows,
    _collect_config_file_entries,
    _determine_source_label,
    _determine_value_source,
    _format_config_section,
    _generate_local_config_content,
)
from birre.cli.models import (
    AuthOverrides,
    CliInvocation,
    LoggingOverrides,
    RuntimeOverrides,
    SubscriptionOverrides,
    TlsOverrides,
)
from birre.config.settings import (
    BITSIGHT_API_KEY_KEY,
    LOGGING_FILE_KEY,
    LOGGING_LEVEL_KEY,
    RUNTIME_DEBUG_KEY,
)


def test_format_section_skips_empty_entries() -> None:
    section = _format_config_section("test", {"alpha": "value", "empty": ""})
    assert 'alpha = "value"' in section
    assert all("empty" not in line for line in section)


def test_generate_local_config_content_includes_header() -> None:
    content = _generate_local_config_content({"a": {"one": 1}}, include_header=True)
    assert content.startswith("## Generated local configuration")


def test_determine_value_source_with_normalizer() -> None:
    def normalizer(value: str | None, _: None) -> str | None:
        if isinstance(value, str):
            return value.upper()
        return value

    assert _determine_value_source("value", "value", normalizer) == "Default"
    assert _determine_value_source("new", "value", normalizer) == "User Input"


def test_collect_config_file_entries(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "local.toml"
    config_file.write_text("[section]\nkey=value\n")

    def fake_parse(_file_path, param_hint=None):
        return {"section": {"key": "value"}}

    monkeypatch.setattr("birre.cli.commands.config.parse_toml_file", fake_parse)
    entries = _collect_config_file_entries([config_file])
    assert entries["section.key"][0] == "value"
    assert entries["section.key"][1] == "local.toml"


def test_build_cli_and_env_override_rows() -> None:
    invocation = CliInvocation(
        config_path=None,
        auth=AuthOverrides(api_key="secret"),
        subscription=SubscriptionOverrides(folder="ops", type=None),
        runtime=RuntimeOverrides(context=None, debug=True),
        tls=TlsOverrides(allow_insecure=None, ca_bundle_path=None),
        logging=LoggingOverrides(
            level="DEBUG",
            format=None,
            file_path="/tmp/log",
            max_bytes=None,
            backup_count=None,
        ),
    )
    rows = _build_cli_override_rows(invocation)
    assert any(BITSIGHT_API_KEY_KEY in row[0] for row in rows)
    env_rows = _build_env_override_rows({"BIRRE_DEBUG": "true"})
    assert any("runtime.debug" in row[0] for row in env_rows)


def test_determine_source_label_priority_overrides() -> None:
    cli_labels = {LOGGING_LEVEL_KEY: "CLI"}
    env_labels = {LOGGING_FILE_KEY: "ENV (BIRRE_LOG_FILE)"}
    config_entries = {"runtime.debug": (True, "local.toml")}
    assert (
        _determine_source_label(
            LOGGING_LEVEL_KEY, cli_labels, env_labels, config_entries
        )
        == "CLI"
    )
    assert (
        _determine_source_label(
            LOGGING_FILE_KEY, cli_labels, env_labels, config_entries
        )
        == "ENV (BIRRE_LOG_FILE)"
    )
    assert _determine_source_label(
        RUNTIME_DEBUG_KEY, cli_labels, env_labels, config_entries
    ).startswith("Config File")
