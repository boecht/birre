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
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

import tomllib
from dotenv import load_dotenv

from .constants import (
    DEFAULT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    coerce_bool,
)

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

def _build_key_index(section_map: Mapping[str, Iterable[str]]) -> Dict[str, str]:
    return {key: section for section, keys in section_map.items() for key in keys}


CONFIG_SECTION_KEYS: Mapping[str, frozenset[str]] = {
    BITSIGHT_SECTION: frozenset({"api_key", "subscription_folder", "subscription_type"}),
    RUNTIME_SECTION: frozenset(
        {"skip_startup_checks", "debug", "allow_insecure_tls", "ca_bundle_path"}
    ),
    ROLES_SECTION: frozenset({"context", "risk_vector_filter", "max_findings"}),
    LOGGING_SECTION: frozenset({"level", "format", "file", "max_bytes", "backup_count"}),
}

KEY_TO_SECTION: Dict[str, str] = _build_key_index(CONFIG_SECTION_KEYS)

BOOL_KEYS = {"skip_startup_checks", "debug", "allow_insecure_tls"}
INT_KEYS = {"max_findings", "max_bytes", "backup_count"}

SOURCE_LABELS = {
    "cli": "command line arguments",
    "env": "the environment",
    "local": "the local configuration file",
    "config": "the configuration file",
}

_ENV_UNSET = object()


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


def _collect_sections(
    config_data: Dict[str, Any], local_data: Dict[str, Any], *names: str
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {
        name: {
            "config": _get_section(config_data, name),
            "local": _get_section(local_data, name),
        }
        for name in names
    }


def _get_section(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    section = data.get(name)
    if isinstance(section, dict):
        return section
    return {}


def _normalize_value(key: str, raw: Optional[object]) -> Tuple[Optional[object], bool]:
    """Normalize a raw value for ``key`` and report whether it was blank."""

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


def _normalize_sources_for_key(
    key: str, sources: Sequence[Tuple[str, Optional[object]]]
) -> Tuple[List[Tuple[str, Optional[object]]], List[str]]:
    """Normalize layered sources for ``key`` and capture blank layers."""

    normalized: List[Tuple[str, Optional[object]]] = []
    blanks: List[str] = []
    for layer, raw in sources:
        value, is_blank = _normalize_value(key, raw)
        if is_blank:
            blanks.append(layer)
            normalized.append((layer, None))
        else:
            normalized.append((layer, value))
    return normalized, blanks


def _apply_precedence(
    normalized: Sequence[Tuple[str, Optional[object]]],
    blanks: Sequence[str],
    *,
    default: Optional[object],
    blank_warning: Optional[str],
    warnings: List[str],
) -> Tuple[Optional[object], Optional[str]]:
    """Return the highest-precedence non-null value while respecting blanks."""

    blank_layers = set(blanks)
    for layer, value in normalized:
        if layer in blank_layers:
            if blank_warning:
                warnings.append(blank_warning)
                return default, None
            continue
        if value is not None:
            return value, layer
    return default, None


def _gather_sources(
    key: str,
    *,
    cli_value: Optional[object],
    env_var: Optional[str],
    env_value: Optional[object],
    section_layers: Optional[Dict[str, Dict[str, Any]]],
) -> List[Tuple[str, Optional[object]]]:
    """Assemble ordered configuration sources for ``key``."""

    sources: List[Tuple[str, Optional[object]]] = [("cli", cli_value)]

    if env_value is not _ENV_UNSET:
        sources.append(("env", env_value))
    else:
        env_data = os.getenv(env_var) if env_var else None
        sources.append(("env", env_data))

    if section_layers is not None:
        sources.append(("local", section_layers["local"].get(key)))
        sources.append(("config", section_layers["config"].get(key)))

    return sources


def _resolve_setting(
    *,
    setting_name: str,
    key: str,
    overrides: List[str],
    warnings: List[str],
    cli_value: Optional[object] = None,
    env_var: Optional[str] = None,
    env_value: Optional[object] = _ENV_UNSET,
    section_layers: Optional[Dict[str, Dict[str, Any]]] = None,
    default: Optional[object] = None,
    blank_warning: Optional[str] = None,
    invalid_warning: Optional[str] = None,
    record_override: bool = True,
) -> Tuple[Optional[object], Optional[str], Optional[str]]:
    """Resolve a setting from layered sources and optionally record overrides."""

    sources = _gather_sources(
        key,
        cli_value=cli_value,
        env_var=env_var,
        env_value=env_value,
        section_layers=section_layers,
    )

    try:
        normalized, blanks = _normalize_sources_for_key(key, sources)
        value, layer = _apply_precedence(
            normalized,
            blanks,
            default=default,
            blank_warning=blank_warning,
            warnings=warnings,
        )
    except ValueError:
        if invalid_warning:
            warnings.append(invalid_warning)
            return default, None, None
        raise

    message: Optional[str] = None
    if layer:
        message = _override_message(setting_name, normalized, layer)
        if message and record_override:
            overrides.append(message)

    return value, layer, message


@dataclass(frozen=True)
class SettingSpec:
    setting_name: str
    key: str
    section: Optional[str]
    env_var: Optional[str] = None
    default: Optional[object] = None
    blank_warning: Optional[str] = None
    invalid_warning: Optional[str] = None
    record_override: bool = True


def _resolve_group(
    specs: Sequence[SettingSpec],
    *,
    cli_values: Mapping[str, Optional[object]],
    sections: Mapping[str, Dict[str, Dict[str, Any]]],
    overrides: List[str],
    warnings: List[str],
    env_overrides: Optional[Mapping[str, Optional[object]]] = None,
) -> Dict[str, Tuple[Optional[object], Optional[str], Optional[str]]]:
    """Resolve a batch of settings defined by ``specs``."""

    results: Dict[str, Tuple[Optional[object], Optional[str], Optional[str]]] = {}
    env_overrides = env_overrides or {}

    for spec in specs:
        section_layers = sections.get(spec.section) if spec.section else None
        env_value = env_overrides.get(spec.key, _ENV_UNSET)
        value, layer, message = _resolve_setting(
            setting_name=spec.setting_name,
            key=spec.key,
            overrides=overrides,
            warnings=warnings,
            cli_value=cli_values.get(spec.key),
            env_var=spec.env_var,
            env_value=env_value,
            section_layers=section_layers,
            default=spec.default,
            blank_warning=spec.blank_warning,
            invalid_warning=spec.invalid_warning,
            record_override=spec.record_override,
        )
        results[spec.key] = (value, layer, message)

    return results


SUBSCRIPTION_SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec("BITSIGHT_API_KEY", "api_key", BITSIGHT_SECTION, "BITSIGHT_API_KEY"),
    SettingSpec(
        "SUBSCRIPTION_FOLDER",
        "subscription_folder",
        BITSIGHT_SECTION,
        "BIRRE_SUBSCRIPTION_FOLDER",
    ),
    SettingSpec(
        "SUBSCRIPTION_TYPE",
        "subscription_type",
        BITSIGHT_SECTION,
        "BIRRE_SUBSCRIPTION_TYPE",
    ),
)

ROLE_SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec(
        "CONTEXT",
        "context",
        ROLES_SECTION,
        "BIRRE_CONTEXT",
        default="standard",
        record_override=False,
    ),
    SettingSpec(
        "RISK_VECTOR_FILTER",
        "risk_vector_filter",
        ROLES_SECTION,
        ENV_RISK_VECTOR_FILTER,
        default=DEFAULT_RISK_VECTOR_FILTER,
        blank_warning="Empty risk_vector_filter override; falling back to default configuration",
    ),
    SettingSpec(
        "MAX_FINDINGS",
        "max_findings",
        ROLES_SECTION,
        ENV_MAX_FINDINGS,
        default=DEFAULT_MAX_FINDINGS,
        invalid_warning="Invalid max_findings override; using default configuration",
    ),
)

RUNTIME_SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec(
        "SKIP_STARTUP_CHECKS",
        "skip_startup_checks",
        RUNTIME_SECTION,
        "BIRRE_SKIP_STARTUP_CHECKS",
        default=False,
    ),
    SettingSpec("DEBUG", "debug", RUNTIME_SECTION, default=False),
)

TLS_SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec(
        "ALLOW_INSECURE_TLS",
        "allow_insecure_tls",
        RUNTIME_SECTION,
        ENV_ALLOW_INSECURE_TLS,
        default=False,
    ),
    SettingSpec(
        "CA_BUNDLE_PATH",
        "ca_bundle_path",
        RUNTIME_SECTION,
        ENV_CA_BUNDLE,
        blank_warning="Empty ca_bundle_path override; ignoring custom CA bundle configuration",
        record_override=False,
    ),
)

LOGGING_SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec(
        "LOG_LEVEL",
        "level",
        LOGGING_SECTION,
        ENV_LOG_LEVEL,
        default=DEFAULT_LOG_LEVEL,
        record_override=False,
    ),
    SettingSpec(
        "LOG_FORMAT",
        "format",
        LOGGING_SECTION,
        ENV_LOG_FORMAT,
        default=DEFAULT_LOG_FORMAT,
        record_override=False,
    ),
    SettingSpec("LOG_FILE", "file", LOGGING_SECTION, ENV_LOG_FILE, record_override=False),
    SettingSpec(
        "LOG_MAX_BYTES",
        "max_bytes",
        LOGGING_SECTION,
        ENV_LOG_MAX_BYTES,
        default=DEFAULT_MAX_BYTES,
        record_override=False,
    ),
    SettingSpec(
        "LOG_BACKUP_COUNT",
        "backup_count",
        LOGGING_SECTION,
        ENV_LOG_BACKUP_COUNT,
        default=DEFAULT_BACKUP_COUNT,
        record_override=False,
    ),
)


def _join_labels(names: Iterable[str]) -> str:
    labels = [SOURCE_LABELS.get(name, name) for name in names]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _override_message(
    setting: str,
    normalized: Sequence[Tuple[str, Optional[object]]],
    chosen_layer: Optional[str],
) -> Optional[str]:
    if chosen_layer is None:
        return None

    chosen_index = next(
        (index for index, (layer, _) in enumerate(normalized) if layer == chosen_layer),
        None,
    )
    if chosen_index is None:
        return None

    overridden = [
        layer
        for layer, value in normalized[chosen_index + 1 :]
        if value is not None
    ]
    if not overridden:
        return None

    return (
        f"Using {setting} from {SOURCE_LABELS.get(chosen_layer, chosen_layer)}, "
        f"overriding values from {_join_labels(overridden)}."
    )


def _audit_config_sections(
    config_data: Dict[str, Any], local_data: Dict[str, Any]
) -> List[str]:
    """Validate section/key placement and report misplaced or unused entries."""

    messages: List[str] = []
    for layer_name, layer_data in (("config", config_data), ("local", local_data)):
        if not isinstance(layer_data, dict):
            continue
        for section, allowed_keys in CONFIG_SECTION_KEYS.items():
            values = layer_data.get(section)
            if not isinstance(values, dict):
                continue
            for key in values:
                if key in allowed_keys:
                    continue
                label = SOURCE_LABELS.get(layer_name, layer_name).capitalize()
                target_section = KEY_TO_SECTION.get(key)
                if target_section:
                    messages.append(
                        f"{label} [{section}] defines '{key}', but this key belongs under [{target_section}]."
                    )
                else:
                    messages.append(
                        f"{label} [{section}] defines unused key '{key}'."
                    )

    return messages


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


@dataclass(frozen=True)
class SubscriptionInputs:
    """Inputs that influence subscription resolution."""

    folder: Optional[str] = None
    type: Optional[str] = None


@dataclass(frozen=True)
class RuntimeInputs:
    """Inputs that influence runtime behaviour of the server."""

    context: Optional[str] = None
    debug: Optional[bool] = None
    risk_vector_filter: Optional[str] = None
    max_findings: Optional[int] = None
    skip_startup_checks: Optional[bool] = None


@dataclass(frozen=True)
class TlsInputs:
    """Inputs that control TLS verification behaviour."""

    allow_insecure: Optional[bool] = None
    ca_bundle_path: Optional[str] = None


@dataclass(frozen=True)
class LoggingInputs:
    """Inputs that influence logging configuration resolution."""

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


def resolve_birre_settings(
    *,
    api_key_input: Optional[str] = None,
    config_path: str = DEFAULT_CONFIG_FILENAME,
    subscription_inputs: Optional[SubscriptionInputs] = None,
    runtime_inputs: Optional[RuntimeInputs] = None,
    tls_inputs: Optional[TlsInputs] = None,
) -> Dict[str, Any]:
    """Resolve BiRRe runtime settings using config, env vars, and CLI overrides."""

    load_dotenv()

    overrides: List[str] = []
    warnings: List[str] = []

    config_data, local_data = _load_layered_config(config_path)
    warnings.extend(_audit_config_sections(config_data, local_data))
    sections = _collect_sections(
        config_data, local_data, BITSIGHT_SECTION, RUNTIME_SECTION, ROLES_SECTION
    )

    subscription_inputs = subscription_inputs or SubscriptionInputs()
    runtime_inputs = runtime_inputs or RuntimeInputs()
    tls_inputs = tls_inputs or TlsInputs()

    subscription_values = _resolve_group(
        SUBSCRIPTION_SPECS,
        cli_values={
            "api_key": api_key_input,
            "subscription_folder": subscription_inputs.folder,
            "subscription_type": subscription_inputs.type,
        },
        sections=sections,
        overrides=overrides,
        warnings=warnings,
    )

    api_key, api_layer, _ = subscription_values["api_key"]
    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")
    if api_layer == "config" and Path(config_path).name == DEFAULT_CONFIG_FILENAME:
        warnings.append(
            "Avoid storing bitsight.api_key in "
            f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
        )

    subscription_folder = subscription_values["subscription_folder"][0]
    subscription_type = subscription_values["subscription_type"][0]

    role_values = _resolve_group(
        ROLE_SPECS,
        cli_values={
            "context": runtime_inputs.context,
            "risk_vector_filter": runtime_inputs.risk_vector_filter,
            "max_findings": runtime_inputs.max_findings,
        },
        sections=sections,
        overrides=overrides,
        warnings=warnings,
    )

    context_value, _, context_message = role_values["context"]
    if context_value is None:
        normalized_context_value = "standard"
    else:
        candidate = str(context_value).strip().lower()
        if candidate in {"standard", "risk_manager"}:
            normalized_context_value = candidate
            if context_message:
                overrides.append(context_message)
        else:
            normalized_context_value = "standard"
            warnings.append(
                f"Unknown context '{context_value}' requested; defaulting to 'standard'"
            )
            context_message = None

    runtime_values = _resolve_group(
        RUNTIME_SPECS,
        cli_values={
            "skip_startup_checks": runtime_inputs.skip_startup_checks,
            "debug": runtime_inputs.debug,
        },
        sections=sections,
        overrides=overrides,
        warnings=warnings,
        env_overrides={
            "debug": os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG"),
        },
    )

    tls_values = _resolve_group(
        TLS_SPECS,
        cli_values={
            "allow_insecure_tls": tls_inputs.allow_insecure,
            "ca_bundle_path": tls_inputs.ca_bundle_path,
        },
        sections=sections,
        overrides=overrides,
        warnings=warnings,
    )

    risk_vector_filter = role_values["risk_vector_filter"][0]
    max_findings_value = role_values["max_findings"][0]
    skip_startup_checks = runtime_values["skip_startup_checks"][0]
    debug_value = runtime_values["debug"][0]
    allow_insecure_value = tls_values["allow_insecure_tls"][0]
    ca_bundle_path, _, ca_message = tls_values["ca_bundle_path"]

    if allow_insecure_value and ca_bundle_path:
        warnings.append(
            "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
        )
        ca_bundle_path = None
        ca_message = None
    elif ca_message:
        overrides.append(ca_message)

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "context": normalized_context_value,
        "risk_vector_filter": risk_vector_filter,
        "max_findings": int(max_findings_value)
        if max_findings_value is not None
        else DEFAULT_MAX_FINDINGS,
        "skip_startup_checks": bool(skip_startup_checks),
        "debug": bool(debug_value),
        "allow_insecure_tls": bool(allow_insecure_value),
        "ca_bundle_path": ca_bundle_path,
        "warnings": warnings,
        "overrides": overrides,
    }


def resolve_logging_settings(
    *,
    config_path: Optional[str] = None,
    level_override: Optional[str] = None,
    format_override: Optional[str] = None,
    file_override: Optional[str] = None,
    max_bytes_override: Optional[int] = None,
    backup_count_override: Optional[int] = None,
) -> LoggingSettings:
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
        sections = _collect_sections(config_data, local_data, LOGGING_SECTION)

    resolved = _resolve_group(
        LOGGING_SPECS,
        cli_values={
            "level": level_override,
            "format": format_override,
            "file": file_override,
            "max_bytes": max_bytes_override,
            "backup_count": backup_count_override,
        },
        sections=sections,
        overrides=[],
        warnings=[],
    )

    level_value = resolved["level"][0]
    format_value = resolved["format"][0]
    file_path = resolved["file"][0]
    max_bytes_value = resolved["max_bytes"][0]
    backup_count_value = resolved["backup_count"][0]

    level_number = _resolve_level(level_value)

    if not isinstance(format_value, str):
        raise ValueError("Log format must resolve to a string")
    resolved_format = format_value.lower()
    if resolved_format not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    return LoggingSettings(
        level=level_number,
        format=resolved_format,
        file_path=file_path,
        max_bytes=int(max_bytes_value)
        if max_bytes_value is not None
        else DEFAULT_MAX_BYTES,
        backup_count=int(backup_count_value)
        if backup_count_value is not None
        else DEFAULT_BACKUP_COUNT,
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
    logging_settings = resolve_logging_settings(
        config_path=config_path,
        **logging_kwargs,
    )
    if runtime_settings["debug"] and logging_settings.level > logging.DEBUG:
        logging_settings = LoggingSettings(
            level=logging.DEBUG,
            format=logging_settings.format,
            file_path=logging_settings.file_path,
            max_bytes=logging_settings.max_bytes,
            backup_count=logging_settings.backup_count,
        )
    return runtime_settings, logging_settings


__all__ = [
    "resolve_birre_settings",
    "resolve_logging_settings",
    "resolve_application_settings",
    "load_config_layers",
    "SubscriptionInputs",
    "RuntimeInputs",
    "TlsInputs",
    "LoggingInputs",
    "LoggingSettings",
    "LOG_FORMAT_TEXT",
    "LOG_FORMAT_JSON",
    "DEFAULT_RISK_VECTOR_FILTER",
    "DEFAULT_MAX_FINDINGS",
    "ENV_ALLOW_INSECURE_TLS",
    "ENV_CA_BUNDLE",
]
