"""Utilities for resolving BiRRe configuration layers.

Values resolve with a simple precedence chain: command line inputs override
environment variables, which override the optional ``config.local.toml`` file,
which in turn overrides ``config.toml``. Blank strings are treated as "not
provided" so that lower-priority sources remain in effect.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

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

CONFIG_SECTION_KEYS: Dict[str, Set[str]] = {
    BITSIGHT_SECTION: {"api_key", "subscription_folder", "subscription_type"},
    RUNTIME_SECTION: {
        "skip_startup_checks",
        "debug",
        "allow_insecure_tls",
        "ca_bundle_path",
    },
    ROLES_SECTION: {"context", "risk_vector_filter", "max_findings"},
    LOGGING_SECTION: {"level", "format", "file", "max_bytes", "backup_count"},
}

KEY_TO_SECTION: Dict[str, str] = {
    key: section for section, keys in CONFIG_SECTION_KEYS.items() for key in keys
}

BOOL_KEYS = {"skip_startup_checks", "debug", "allow_insecure_tls"}
INT_KEYS = {"max_findings", "max_bytes", "backup_count"}

SOURCE_LABELS = {
    "cli": "command line arguments",
    "env": "the environment",
    "local": "the local configuration file",
    "config": "the configuration file",
}

_ENV_UNSET = object()
ENV_STRICT_CONFIG = "BIRRE_STRICT_CONFIG"

_AUDITED_CONFIG_PATHS: Set[str] = set()


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
        try:
            value, is_blank = _normalize_value(key, raw)
        except ValueError:
            raise
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
    postprocess: Optional[Callable[[Optional[object]], Optional[object]]] = None,
    record_override: bool = True,
) -> Tuple[Optional[object], Optional[str], Optional[str]]:
    """Resolve a setting from layered sources and optionally record overrides."""

    sources: List[Tuple[str, Optional[object]]] = [("cli", cli_value)]

    if env_value is not _ENV_UNSET:
        sources.append(("env", env_value))
    elif env_var:
        sources.append(("env", os.getenv(env_var)))
    else:
        sources.append(("env", None))

    if section_layers is not None:
        sources.append(("local", section_layers["local"].get(key)))
        sources.append(("config", section_layers["config"].get(key)))

    try:
        normalized, blanks = _normalize_sources_for_key(key, sources)
    except ValueError as exc:
        if invalid_warning:
            warnings.append(invalid_warning)
            return default, None, None
        raise exc

    try:
        value, layer = _apply_precedence(
            normalized,
            blanks,
            default=default,
            blank_warning=blank_warning,
            warnings=warnings,
        )
        if postprocess and value is not None:
            value = postprocess(value)
    except ValueError as exc:
        if invalid_warning:
            warnings.append(invalid_warning)
            return default, None, None
        raise exc

    message: Optional[str] = None
    if layer:
        message = _override_message(setting_name, normalized, layer)
        if message and record_override:
            overrides.append(message)

    return value, layer, message


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
    config_data: Dict[str, Any],
    local_data: Dict[str, Any],
    *,
    strict: bool,
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

    if strict and messages:
        raise ValueError("Invalid configuration keys: " + " ".join(messages))

    return messages


def _should_use_strict(strict_override: Optional[bool]) -> bool:
    """Return True when strict config auditing is enabled."""

    if strict_override is not None:
        return bool(strict_override)
    return coerce_bool(os.getenv(ENV_STRICT_CONFIG), default=False)


def _load_and_audit(
    config_path: str,
    *,
    strict: bool,
    warnings: Optional[List[str]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Load layered config data and perform section audits when necessary."""

    config_data, local_data = _load_layered_config(config_path)

    resolved_path = str(Path(config_path).resolve())
    messages: List[str] = []
    if strict:
        messages = _audit_config_sections(config_data, local_data, strict=True)
    elif resolved_path not in _AUDITED_CONFIG_PATHS:
        messages = _audit_config_sections(config_data, local_data, strict=False)
        _AUDITED_CONFIG_PATHS.add(resolved_path)

    if warnings is not None and messages:
        warnings.extend(messages)
    elif messages:
        logger = logging.getLogger(__name__)
        for message in messages:
            logger.warning(message)

    return config_data, local_data


def _coerce_positive_int(value: Optional[object]) -> int:
    if value is None:
        raise ValueError("Value must be provided")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError("Invalid integer value") from exc
    if integer <= 0:
        raise ValueError("Value must be positive")
    return integer


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
    strict_mode: Optional[bool] = None,
) -> Dict[str, Any]:
    """Resolve BiRRe runtime settings using config, env vars, and CLI overrides."""

    load_dotenv()

    overrides: List[str] = []
    warnings: List[str] = []

    strict = _should_use_strict(strict_mode)
    config_data, local_data = _load_and_audit(
        config_path, strict=strict, warnings=warnings
    )
    sections = _collect_sections(
        config_data, local_data, BITSIGHT_SECTION, RUNTIME_SECTION, ROLES_SECTION
    )
    bitsight_layers = sections[BITSIGHT_SECTION]
    runtime_layers = sections[RUNTIME_SECTION]
    roles_layers = sections[ROLES_SECTION]

    subscription_inputs = subscription_inputs or SubscriptionInputs()
    runtime_inputs = runtime_inputs or RuntimeInputs()
    tls_inputs = tls_inputs or TlsInputs()

    api_key, api_layer, _ = _resolve_setting(
        setting_name="BITSIGHT_API_KEY",
        key="api_key",
        overrides=overrides,
        warnings=warnings,
        cli_value=api_key_input,
        env_var="BITSIGHT_API_KEY",
        section_layers=bitsight_layers,
    )
    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")
    if api_layer == "config" and Path(config_path).name == DEFAULT_CONFIG_FILENAME:
        warnings.append(
            "Avoid storing bitsight.api_key in "
            f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
        )

    subscription_folder, _, _ = _resolve_setting(
        setting_name="SUBSCRIPTION_FOLDER",
        key="subscription_folder",
        overrides=overrides,
        warnings=warnings,
        cli_value=subscription_inputs.folder,
        env_var="BIRRE_SUBSCRIPTION_FOLDER",
        section_layers=bitsight_layers,
    )

    subscription_type, _, _ = _resolve_setting(
        setting_name="SUBSCRIPTION_TYPE",
        key="subscription_type",
        overrides=overrides,
        warnings=warnings,
        cli_value=subscription_inputs.type,
        env_var="BIRRE_SUBSCRIPTION_TYPE",
        section_layers=bitsight_layers,
    )

    context_value, _, context_message = _resolve_setting(
        setting_name="CONTEXT",
        key="context",
        overrides=overrides,
        warnings=warnings,
        cli_value=runtime_inputs.context,
        env_var="BIRRE_CONTEXT",
        section_layers=roles_layers,
        default="standard",
        record_override=False,
    )

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

    skip_startup_checks, _, _ = _resolve_setting(
        setting_name="SKIP_STARTUP_CHECKS",
        key="skip_startup_checks",
        overrides=overrides,
        warnings=warnings,
        cli_value=runtime_inputs.skip_startup_checks,
        env_var="BIRRE_SKIP_STARTUP_CHECKS",
        section_layers=runtime_layers,
        default=False,
    )

    debug_value, _, _ = _resolve_setting(
        setting_name="DEBUG",
        key="debug",
        overrides=overrides,
        warnings=warnings,
        cli_value=runtime_inputs.debug,
        env_value=os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG"),
        section_layers=runtime_layers,
        default=False,
    )

    risk_vector_filter, _, _ = _resolve_setting(
        setting_name="RISK_VECTOR_FILTER",
        key="risk_vector_filter",
        overrides=overrides,
        warnings=warnings,
        cli_value=runtime_inputs.risk_vector_filter,
        env_var=ENV_RISK_VECTOR_FILTER,
        section_layers=roles_layers,
        default=DEFAULT_RISK_VECTOR_FILTER,
        blank_warning="Empty risk_vector_filter override; falling back to default configuration",
    )

    allow_insecure_value, _, _ = _resolve_setting(
        setting_name="ALLOW_INSECURE_TLS",
        key="allow_insecure_tls",
        overrides=overrides,
        warnings=warnings,
        cli_value=tls_inputs.allow_insecure,
        env_var=ENV_ALLOW_INSECURE_TLS,
        section_layers=runtime_layers,
        default=False,
    )

    ca_bundle_path, ca_layer, ca_message = _resolve_setting(
        setting_name="CA_BUNDLE_PATH",
        key="ca_bundle_path",
        overrides=overrides,
        warnings=warnings,
        cli_value=tls_inputs.ca_bundle_path,
        env_var=ENV_CA_BUNDLE,
        section_layers=runtime_layers,
        blank_warning="Empty ca_bundle_path override; ignoring custom CA bundle configuration",
        record_override=False,
    )

    max_findings_value, _, _ = _resolve_setting(
        setting_name="MAX_FINDINGS",
        key="max_findings",
        overrides=overrides,
        warnings=warnings,
        cli_value=runtime_inputs.max_findings,
        env_var=ENV_MAX_FINDINGS,
        section_layers=roles_layers,
        default=DEFAULT_MAX_FINDINGS,
        postprocess=_coerce_positive_int,
        invalid_warning="Invalid max_findings override; using default configuration",
    )

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
    strict_mode: Optional[bool] = None,
) -> LoggingSettings:
    strict = _should_use_strict(strict_mode)

    logging_layers: Dict[str, Dict[str, Any]] = {"config": {}, "local": {}}
    if config_path:
        config_data, local_data = _load_and_audit(
            config_path, strict=strict, warnings=None
        )
        sections = _collect_sections(config_data, local_data, LOGGING_SECTION)
        logging_layers = sections[LOGGING_SECTION]

    dummy_overrides: List[str] = []
    dummy_warnings: List[str] = []

    level_value, _, _ = _resolve_setting(
        setting_name="LOG_LEVEL",
        key="level",
        overrides=dummy_overrides,
        warnings=dummy_warnings,
        cli_value=level_override,
        env_var=ENV_LOG_LEVEL,
        section_layers=logging_layers,
        default=DEFAULT_LOG_LEVEL,
        record_override=False,
    )

    format_value, _, _ = _resolve_setting(
        setting_name="LOG_FORMAT",
        key="format",
        overrides=dummy_overrides,
        warnings=dummy_warnings,
        cli_value=format_override,
        env_var=ENV_LOG_FORMAT,
        section_layers=logging_layers,
        default=DEFAULT_LOG_FORMAT,
        record_override=False,
    )

    file_path, _, _ = _resolve_setting(
        setting_name="LOG_FILE",
        key="file",
        overrides=dummy_overrides,
        warnings=dummy_warnings,
        cli_value=file_override,
        env_var=ENV_LOG_FILE,
        section_layers=logging_layers,
        record_override=False,
    )

    max_bytes_value, _, _ = _resolve_setting(
        setting_name="LOG_MAX_BYTES",
        key="max_bytes",
        overrides=dummy_overrides,
        warnings=dummy_warnings,
        cli_value=max_bytes_override,
        env_var=ENV_LOG_MAX_BYTES,
        section_layers=logging_layers,
        default=DEFAULT_MAX_BYTES,
        postprocess=_coerce_positive_int,
        record_override=False,
    )

    backup_count_value, _, _ = _resolve_setting(
        setting_name="LOG_BACKUP_COUNT",
        key="backup_count",
        overrides=dummy_overrides,
        warnings=dummy_warnings,
        cli_value=backup_count_override,
        env_var=ENV_LOG_BACKUP_COUNT,
        section_layers=logging_layers,
        default=DEFAULT_BACKUP_COUNT,
        postprocess=_coerce_positive_int,
        record_override=False,
    )

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
