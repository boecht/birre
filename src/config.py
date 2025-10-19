"""Utilities for resolving BiRRe configuration layers.

Settings resolve according to the following precedence:

1. Command line inputs
2. Environment variables
3. Local configuration overlays (``config.local.toml``)
4. Primary configuration file (``config.toml``)

Blank or whitespace-only values are treated as "not provided" so they do not
override lower-priority sources. Normalization happens before any setting is
evaluated so downstream helpers never see untrimmed values.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, Optional, Sequence, Tuple

import tomllib
from dotenv import load_dotenv

from .constants import DEFAULT_CONFIG_FILENAME, LOCAL_CONFIG_FILENAME, coerce_bool

BITSIGHT_SECTION = "bitsight"
RUNTIME_SECTION = "runtime"
ROLES_SECTION = "roles"
LOGGING_SECTION = "logging"

DEFAULT_RISK_VECTOR_FILTER = ",".join(
    [
        "botnet_infections",
        "spam_propagation",
        "malware_servers",
        "unsolicited_comm",
        "potentially_exploited",
        "open_ports",
        "patching_cadence",
        "insecure_systems",
        "server_software",
    ]
)
DEFAULT_MAX_FINDINGS = 10

ENV_RISK_VECTOR_FILTER = "BIRRE_RISK_VECTOR_FILTER"
ENV_MAX_FINDINGS = "BIRRE_MAX_FINDINGS"

ENV_ALLOW_INSECURE_TLS = "BIRRE_ALLOW_INSECURE_TLS"
ENV_CA_BUNDLE = "BIRRE_CA_BUNDLE"

ENV_LOG_LEVEL = "BIRRE_LOG_LEVEL"
ENV_LOG_FORMAT = "BIRRE_LOG_FORMAT"
ENV_LOG_FILE = "BIRRE_LOG_FILE"
ENV_LOG_MAX_BYTES = "BIRRE_LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "BIRRE_LOG_BACKUP_COUNT"

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
DEFAULT_LOG_FORMAT = LOG_FORMAT_TEXT
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_BACKUP_COUNT = 5

BOOL_KEYS = {"skip_startup_checks", "debug", "allow_insecure_tls"}
INT_KEYS = {"max_findings", "max_bytes", "backup_count"}

CONFIG_SECTION_KEYS: Mapping[str, frozenset[str]] = {
    BITSIGHT_SECTION: frozenset({"api_key", "subscription_folder", "subscription_type"}),
    RUNTIME_SECTION: frozenset({"skip_startup_checks", "debug", "allow_insecure_tls", "ca_bundle_path"}),
    ROLES_SECTION: frozenset({"context", "risk_vector_filter", "max_findings"}),
    LOGGING_SECTION: frozenset({"level", "format", "file", "max_bytes", "backup_count"}),
}

KEY_TO_SECTION = {
    key: section
    for section, keys in CONFIG_SECTION_KEYS.items()
    for key in keys
}

SOURCE_LABELS = {
    "cli": "command line arguments",
    "env": "the environment",
    "local": "the local configuration file",
    "config": "the configuration file",
}

_MISSING = object()


def _read_toml(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError:
        return {}


def _merge_overlay(config_data: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    if not overlay:
        return dict(config_data)

    merged = dict(config_data)
    for section, values in overlay.items():
        if isinstance(values, dict) and isinstance(merged.get(section), dict):
            merged_section = dict(merged[section])
            merged_section.update(values)
            merged[section] = merged_section
        else:
            merged[section] = values
    return merged


def load_config_layers(base_path: str) -> Dict[str, Any]:
    """Return the primary configuration with any local overlay applied."""

    config_path = Path(base_path)
    config_data = _read_toml(config_path)
    local_path = config_path.with_name(f"{config_path.stem}.local{config_path.suffix}")
    local_data = _read_toml(local_path)
    return _merge_overlay(config_data, local_data)


def _load_layered_config(config_path: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    config_file = Path(config_path)
    config_data = _read_toml(config_file)
    local_file = config_file.with_name(f"{config_file.stem}.local{config_file.suffix}")
    local_data = _read_toml(local_file)
    return config_data, local_data


def _get_section(data: Mapping[str, Any], name: str) -> Dict[str, Any]:
    section = data.get(name)
    return dict(section) if isinstance(section, dict) else {}


def _normalize_value(key: str, raw: Optional[object]) -> Tuple[Optional[object], bool]:
    if raw is None:
        return None, False

    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return None, True
        raw = stripped

    if key in BOOL_KEYS:
        return coerce_bool(raw), False

    if key in INT_KEYS:
        try:
            return int(raw), False
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid integer value for {key}") from exc

    return str(raw), False


def _join_labels(names: Iterable[str]) -> str:
    labels = [SOURCE_LABELS.get(name, name) for name in names]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _override_message(setting: str, normalized: Sequence[Tuple[str, Optional[object]]], chosen_layer: Optional[str]) -> Optional[str]:
    if chosen_layer is None:
        return None

    chosen_index = next(
        (index for index, (layer, _) in enumerate(normalized) if layer == chosen_layer),
        None,
    )
    if chosen_index is None:
        return None

    overridden = [layer for layer, value in normalized[chosen_index + 1 :] if value is not None]
    if not overridden:
        return None

    return (
        f"Using {setting} from {SOURCE_LABELS.get(chosen_layer, chosen_layer)}, "
        f"overriding values from {_join_labels(overridden)}."
    )


def _audit_config_sections(config_data: Dict[str, Any], local_data: Dict[str, Any]) -> List[str]:
    messages: List[str] = []
    for layer_name, layer_data in (("config", config_data), ("local", local_data)):
        if not isinstance(layer_data, dict):
            continue
        label = SOURCE_LABELS.get(layer_name, layer_name).capitalize()
        for section, allowed_keys in CONFIG_SECTION_KEYS.items():
            values = layer_data.get(section)
            if not isinstance(values, dict):
                continue
            for key in values:
                if key in allowed_keys:
                    continue
                target_section = KEY_TO_SECTION.get(key)
                if target_section:
                    messages.append(
                        f"{label} [{section}] defines '{key}', but this key belongs under [{target_section}]."
                    )
                else:
                    messages.append(f"{label} [{section}] defines unused key '{key}'.")
    return messages


def _section_layers(config_data: Dict[str, Any], local_data: Dict[str, Any], names: Iterable[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    layers: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for name in names:
        layers[name] = {
            "config": _get_section(config_data, name),
            "local": _get_section(local_data, name),
        }
    return layers


def _resolve_value(
    *,
    key: str,
    setting_name: str,
    overrides: MutableSequence[str],
    warnings: MutableSequence[str],
    section_layers: Optional[Mapping[str, Dict[str, Any]]] = None,
    cli_value: Optional[object] = None,
    env_var: Optional[str] = None,
    env_value: Optional[object] = _MISSING,
    default: Optional[object] = None,
    blank_warning: Optional[str] = None,
    invalid_warning: Optional[str] = None,
    record_override: bool = True,
) -> Tuple[Optional[object], Optional[str], Optional[str]]:
    sources: List[Tuple[str, Optional[object]]] = [("cli", cli_value)]

    if env_var or env_value is not _MISSING:
        env_raw = env_value if env_value is not _MISSING else os.getenv(env_var) if env_var else None
        sources.append(("env", env_raw))

    if section_layers is not None:
        sources.append(("local", section_layers["local"].get(key)))
        sources.append(("config", section_layers["config"].get(key)))

    normalized: List[Tuple[str, Optional[object]]] = []
    chosen_layer: Optional[str] = None
    chosen_value: Optional[object] = None

    for layer, raw in sources:
        try:
            value, is_blank = _normalize_value(key, raw)
        except ValueError:
            if invalid_warning:
                warnings.append(invalid_warning)
                return default, None, None
            raise

        if is_blank:
            normalized.append((layer, None))
            if blank_warning and chosen_layer is None:
                warnings.append(blank_warning)
                return default, None, None
            continue

        normalized.append((layer, value))
        if chosen_layer is None and value is not None:
            chosen_layer = layer
            chosen_value = value

    if chosen_layer is None:
        return default, None, None

    message: Optional[str] = None
    if record_override:
        message = _override_message(setting_name, normalized, chosen_layer)
        if message:
            overrides.append(message)

    return chosen_value, chosen_layer, message


@dataclass(frozen=True)
class SubscriptionInputs:
    folder: Optional[str] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class RuntimeInputs:
    context: Optional[str] = None
    debug: Optional[bool] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    skip_startup_checks: Optional[bool] = None


@dataclass(frozen=True)
class TlsInputs:
    allow_insecure: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


@dataclass(frozen=True)
class LoggingInputs:
    level: Optional[str] = None
    format: Optional[str] = None
    file_path: Optional[str] = None
    max_bytes: Optional[int] = None
    backup_count: Optional[int] = None

    def as_kwargs(self) -> Dict[str, Optional[Any]]:
        return {
            "level_override": self.level,
            "format_override": self.format,
            "file_override": self.file_path,
            "max_bytes_override": self.max_bytes,
            "backup_count_override": self.backup_count,
        }


@dataclass(frozen=True)
class LoggingSettings:
    level: int
    format: str
    file_path: Optional[str]
    max_bytes: int
    backup_count: int

    @property
    def level_name(self) -> str:
        return logging.getLevelName(self.level)


def _normalize_context(value: Optional[object], message: Optional[str], overrides: MutableSequence[str], warnings: MutableSequence[str]) -> str:
    if value is None:
        return "standard"

    candidate = str(value).strip().lower()
    if candidate in {"standard", "risk_manager"}:
        if message:
            overrides.append(message)
        return candidate

    warnings.append(f"Unknown context '{value}' requested; defaulting to 'standard'")
    return "standard"


def _resolve_subscription(
    *,
    sections: Mapping[str, Dict[str, Dict[str, Any]]],
    overrides: MutableSequence[str],
    warnings: MutableSequence[str],
    api_key_input: Optional[str],
    subscription_inputs: SubscriptionInputs,
    config_path: str,
) -> Tuple[str, Optional[str], Optional[str]]:
    bitsight_layers = sections[BITSIGHT_SECTION]

    api_value, api_layer, _ = _resolve_value(
        key="api_key",
        setting_name="BITSIGHT_API_KEY",
        overrides=overrides,
        warnings=warnings,
        section_layers=bitsight_layers,
        cli_value=api_key_input,
        env_var="BITSIGHT_API_KEY",
    )
    if not api_value:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")
    if api_layer == "config" and Path(config_path).name == DEFAULT_CONFIG_FILENAME:
        warnings.append(
            "Avoid storing bitsight.api_key in "
            f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
        )

    folder_value, _, _ = _resolve_value(
        key="subscription_folder",
        setting_name="SUBSCRIPTION_FOLDER",
        overrides=overrides,
        warnings=warnings,
        section_layers=bitsight_layers,
        cli_value=subscription_inputs.folder,
        env_var="BIRRE_SUBSCRIPTION_FOLDER",
    )

    type_value, _, _ = _resolve_value(
        key="subscription_type",
        setting_name="SUBSCRIPTION_TYPE",
        overrides=overrides,
        warnings=warnings,
        section_layers=bitsight_layers,
        cli_value=subscription_inputs.type,
        env_var="BIRRE_SUBSCRIPTION_TYPE",
    )

    return str(api_value), folder_value, type_value


def _resolve_roles(
    *,
    sections: Mapping[str, Dict[str, Dict[str, Any]]],
    overrides: MutableSequence[str],
    warnings: MutableSequence[str],
    runtime_inputs: RuntimeInputs,
) -> Tuple[str, str, int]:
    role_layers = sections[ROLES_SECTION]

    context_value, _, context_message = _resolve_value(
        key="context",
        setting_name="CONTEXT",
        overrides=overrides,
        warnings=warnings,
        section_layers=role_layers,
        cli_value=runtime_inputs.context,
        env_var="BIRRE_CONTEXT",
        default="standard",
        record_override=False,
    )
    context = _normalize_context(context_value, context_message, overrides, warnings)

    risk_value, _, _ = _resolve_value(
        key="risk_vector_filter",
        setting_name="RISK_VECTOR_FILTER",
        overrides=overrides,
        warnings=warnings,
        section_layers=role_layers,
        cli_value=runtime_inputs.risk_vector_filter,
        env_var=ENV_RISK_VECTOR_FILTER,
        default=DEFAULT_RISK_VECTOR_FILTER,
        blank_warning="Empty risk_vector_filter override; falling back to default configuration",
    )
    if not isinstance(risk_value, str) or not risk_value:
        risk = DEFAULT_RISK_VECTOR_FILTER
    else:
        risk = risk_value

    max_findings_value, _, _ = _resolve_value(
        key="max_findings",
        setting_name="MAX_FINDINGS",
        overrides=overrides,
        warnings=warnings,
        section_layers=role_layers,
        cli_value=runtime_inputs.max_findings,
        env_var=ENV_MAX_FINDINGS,
        default=DEFAULT_MAX_FINDINGS,
        invalid_warning="Invalid max_findings override; using default configuration",
    )
    max_findings = int(max_findings_value) if max_findings_value is not None else DEFAULT_MAX_FINDINGS

    return context, risk, max_findings


def _resolve_runtime(
    *,
    sections: Mapping[str, Dict[str, Dict[str, Any]]],
    overrides: MutableSequence[str],
    warnings: MutableSequence[str],
    runtime_inputs: RuntimeInputs,
) -> Tuple[bool, bool]:
    runtime_layers = sections[RUNTIME_SECTION]

    skip_value, _, _ = _resolve_value(
        key="skip_startup_checks",
        setting_name="SKIP_STARTUP_CHECKS",
        overrides=overrides,
        warnings=warnings,
        section_layers=runtime_layers,
        cli_value=runtime_inputs.skip_startup_checks,
        env_var="BIRRE_SKIP_STARTUP_CHECKS",
        default=False,
    )

    debug_value, _, _ = _resolve_value(
        key="debug",
        setting_name="DEBUG",
        overrides=overrides,
        warnings=warnings,
        section_layers=runtime_layers,
        cli_value=runtime_inputs.debug,
        env_value=os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG"),
        default=False,
    )

    return bool(skip_value), bool(debug_value)


def _resolve_tls(
    *,
    sections: Mapping[str, Dict[str, Dict[str, Any]]],
    overrides: MutableSequence[str],
    warnings: MutableSequence[str],
    tls_inputs: TlsInputs,
) -> Tuple[bool, Optional[str]]:
    runtime_layers = sections[RUNTIME_SECTION]

    allow_value, _, _ = _resolve_value(
        key="allow_insecure_tls",
        setting_name="ALLOW_INSECURE_TLS",
        overrides=overrides,
        warnings=warnings,
        section_layers=runtime_layers,
        cli_value=tls_inputs.allow_insecure,
        env_var=ENV_ALLOW_INSECURE_TLS,
        default=False,
    )

    ca_value, _, _ = _resolve_value(
        key="ca_bundle_path",
        setting_name="CA_BUNDLE_PATH",
        overrides=overrides,
        warnings=warnings,
        section_layers=runtime_layers,
        cli_value=tls_inputs.ca_bundle_path,
        env_var=ENV_CA_BUNDLE,
        blank_warning="Empty ca_bundle_path override; ignoring custom CA bundle configuration",
        record_override=False,
    )

    allow_insecure = bool(allow_value)
    if allow_insecure:
        if ca_value:
            warnings.append(
                "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
            )
        return True, None

    return False, ca_value if isinstance(ca_value, str) else ca_value


def resolve_birre_settings(
    *,
    config_path: str = DEFAULT_CONFIG_FILENAME,
    api_key_input: Optional[str] = None,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
) -> Dict[str, Any]:
    subscription_inputs = subscription_inputs or SubscriptionInputs()
    runtime_inputs = runtime_inputs or RuntimeInputs()
    tls_inputs = tls_inputs or TlsInputs()

    load_dotenv()

    config_data, local_data = _load_layered_config(config_path)
    sections = _section_layers(config_data, local_data, (BITSIGHT_SECTION, RUNTIME_SECTION, ROLES_SECTION))

    overrides: List[str] = []
    warnings: List[str] = _audit_config_sections(config_data, local_data)

    api_key, subscription_folder, subscription_type = _resolve_subscription(
        sections=sections,
        overrides=overrides,
        warnings=warnings,
        api_key_input=api_key_input,
        subscription_inputs=subscription_inputs,
        config_path=config_path,
    )

    context, risk_vector_filter, max_findings = _resolve_roles(
        sections=sections,
        overrides=overrides,
        warnings=warnings,
        runtime_inputs=runtime_inputs,
    )

    skip_startup_checks, debug_value = _resolve_runtime(
        sections=sections,
        overrides=overrides,
        warnings=warnings,
        runtime_inputs=runtime_inputs,
    )

    allow_insecure_tls, ca_bundle_path = _resolve_tls(
        sections=sections,
        overrides=overrides,
        warnings=warnings,
        tls_inputs=tls_inputs,
    )

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "context": context,
        "risk_vector_filter": risk_vector_filter,
        "max_findings": max_findings,
        "skip_startup_checks": skip_startup_checks,
        "debug": debug_value,
        "allow_insecure_tls": allow_insecure_tls,
        "ca_bundle_path": ca_bundle_path,
        "warnings": warnings,
        "overrides": overrides,
    }


def _resolve_level(level_value: Optional[object]) -> int:
    mapping = logging.getLevelNamesMapping()
    if level_value is None:
        return mapping.get(DEFAULT_LOG_LEVEL, logging.INFO)
    if isinstance(level_value, int):
        return level_value
    text = str(level_value).strip()
    if not text:
        return mapping.get(DEFAULT_LOG_LEVEL, logging.INFO)
    upper = text.upper()
    if upper.isdigit():
        return int(upper)
    if upper not in mapping:
        raise ValueError(f"Unknown log level: {level_value}")
    return mapping[upper]


def resolve_logging_settings(
    *,
    config_path: Optional[str] = None,
    level_override: Optional[str] = None,
    format_override: Optional[str] = None,
    file_override: Optional[str] = None,
    max_bytes_override: Optional[int] = None,
    backup_count_override: Optional[int] = None,
) -> LoggingSettings:
    overrides: List[str] = []
    warnings: List[str] = []

    sections: Dict[str, Dict[str, Dict[str, Any]]] = {
        LOGGING_SECTION: {"config": {}, "local": {}}
    }

    if config_path:
        config_data, local_data = _load_layered_config(config_path)
        audit_messages = _audit_config_sections(config_data, local_data)
        if audit_messages:
            logger = logging.getLogger(__name__)
            for message in audit_messages:
                logger.warning(message)
        sections = _section_layers(config_data, local_data, (LOGGING_SECTION,))

    logging_layers = sections[LOGGING_SECTION]

    level_value, _, _ = _resolve_value(
        key="level",
        setting_name="LOG_LEVEL",
        overrides=overrides,
        warnings=warnings,
        section_layers=logging_layers,
        cli_value=level_override,
        env_var=ENV_LOG_LEVEL,
        default=DEFAULT_LOG_LEVEL,
        record_override=False,
    )
    format_value, _, _ = _resolve_value(
        key="format",
        setting_name="LOG_FORMAT",
        overrides=overrides,
        warnings=warnings,
        section_layers=logging_layers,
        cli_value=format_override,
        env_var=ENV_LOG_FORMAT,
        default=DEFAULT_LOG_FORMAT,
        record_override=False,
    )
    file_value, _, _ = _resolve_value(
        key="file",
        setting_name="LOG_FILE",
        overrides=overrides,
        warnings=warnings,
        section_layers=logging_layers,
        cli_value=file_override,
        env_var=ENV_LOG_FILE,
        record_override=False,
    )
    max_bytes_value, _, _ = _resolve_value(
        key="max_bytes",
        setting_name="LOG_MAX_BYTES",
        overrides=overrides,
        warnings=warnings,
        section_layers=logging_layers,
        cli_value=max_bytes_override,
        env_var=ENV_LOG_MAX_BYTES,
        default=DEFAULT_MAX_BYTES,
        invalid_warning="Invalid max_bytes override; using default configuration",
        record_override=False,
    )
    backup_count_value, _, _ = _resolve_value(
        key="backup_count",
        setting_name="LOG_BACKUP_COUNT",
        overrides=overrides,
        warnings=warnings,
        section_layers=logging_layers,
        cli_value=backup_count_override,
        env_var=ENV_LOG_BACKUP_COUNT,
        default=DEFAULT_BACKUP_COUNT,
        invalid_warning="Invalid backup_count override; using default configuration",
        record_override=False,
    )

    level_number = _resolve_level(level_value)
    if not isinstance(format_value, str):
        raise ValueError("Log format must resolve to a string")
    resolved_format = format_value.lower()
    if resolved_format not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    max_bytes = int(max_bytes_value) if max_bytes_value is not None else DEFAULT_MAX_BYTES
    backup_count = int(backup_count_value) if backup_count_value is not None else DEFAULT_BACKUP_COUNT

    return LoggingSettings(
        level=level_number,
        format=resolved_format,
        file_path=file_value,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


def resolve_application_settings(
    *,
    api_key_input: Optional[str] = None,
    config_path: str = DEFAULT_CONFIG_FILENAME,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    logging_inputs: Optional[LoggingInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
) -> Tuple[Dict[str, Any], LoggingSettings]:
    runtime_settings = resolve_birre_settings(
        api_key_input=api_key_input,
        config_path=config_path,
        subscription_inputs=subscription_inputs,
        runtime_inputs=runtime_inputs,
        tls_inputs=tls_inputs,
    )

    logging_kwargs = logging_inputs.as_kwargs() if logging_inputs else {}
    logging_settings = resolve_logging_settings(config_path=config_path, **logging_kwargs)

    if runtime_settings["debug"] and logging_settings.level > logging.DEBUG:
        logging_settings = LoggingSettings(
            level=logging.DEBUG,
            format=logging_settings.format,
            file_path=logging_settings.file_path,
            max_bytes=logging_settings.max_bytes,
            backup_count=logging_settings.backup_count,
        )

    return runtime_settings, logging_settings
