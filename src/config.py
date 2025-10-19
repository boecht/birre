"""Configuration helpers for the BiRRe server.

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

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection, Dict, Optional, Sequence, Tuple

import logging
import tomllib
from dotenv import load_dotenv

from .constants import (
    DEFAULT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    coerce_bool,
)

BITSIGHT_SECTION = "bitsight"

ROLE_CONFIG_KEYS = {"context", "risk_vector_filter", "max_findings"}
RUNTIME_CONFIG_KEYS = {
    "skip_startup_checks",
    "debug",
    "allow_insecure_tls",
    "ca_bundle_path",
}

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

ENV_RISK_VECTOR_FILTER = "BIRRE_RISK_VECTOR_FILTER"
DEFAULT_MAX_FINDINGS = 10
ENV_MAX_FINDINGS = "BIRRE_MAX_FINDINGS"

LOG_FORMAT_TEXT = "text"
LOG_FORMAT_JSON = "json"
DEFAULT_LOG_FORMAT = LOG_FORMAT_TEXT
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 10_000_000
DEFAULT_BACKUP_COUNT = 5

ENV_ALLOW_INSECURE_TLS = "BIRRE_ALLOW_INSECURE_TLS"
ENV_CA_BUNDLE = "BIRRE_CA_BUNDLE"

ENV_LOG_LEVEL = "BIRRE_LOG_LEVEL"
ENV_LOG_FORMAT = "BIRRE_LOG_FORMAT"
ENV_LOG_FILE = "BIRRE_LOG_FILE"
ENV_LOG_MAX_BYTES = "BIRRE_LOG_MAX_BYTES"
ENV_LOG_BACKUP_COUNT = "BIRRE_LOG_BACKUP_COUNT"


def _load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}


def _apply_overlay_section(
    base: Dict[str, Any],
    section: str,
    values: Any,
) -> None:
    """Apply a section from a local overlay configuration to the base config."""

    if not isinstance(values, dict):
        base[section] = values
        return

    base_section = base.get(section)
    if not isinstance(base_section, dict):
        base_section = {}
    base[section] = {**base_section, **values}


def load_config_layers(base_path: str) -> Dict[str, Any]:
    cfg = _load_config(base_path)
    path_obj = Path(base_path)
    local_path = path_obj.with_name(f"{path_obj.stem}.local{path_obj.suffix}")

    if not local_path.exists():
        return cfg

    overlay = _load_config(str(local_path))

    if not isinstance(cfg, dict) or not isinstance(overlay, dict):
        return overlay or cfg

    for section, values in overlay.items():
        _apply_overlay_section(cfg, section, values)

    return cfg


def _get_dict_section(cfg: Any, section: str) -> Dict[str, Any]:
    if isinstance(cfg, dict):
        candidate = cfg.get(section)
        if isinstance(candidate, dict):
            return candidate
    return {}


def _load_base_config(config_path: str) -> Dict[str, Any]:
    if config_path.endswith(DEFAULT_CONFIG_FILENAME):
        return _load_config(config_path)
    return {}


def _load_local_config(config_path: str) -> Dict[str, Any]:
    path_obj = Path(config_path)
    local_path = path_obj.with_name(f"{path_obj.stem}.local{path_obj.suffix}")
    if not local_path.exists():
        return {}
    return _load_config(str(local_path))


def _first_truthy(*values: Optional[Any]) -> Optional[Any]:
    for value in values:
        if value:
            return value
    return None


def _value_provided(value: Optional[Any]) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _normalize_optional_str(value: Optional[Any]) -> Optional[str]:
    """Normalize optional string-like inputs by trimming whitespace."""

    if value is None:
        return None
    candidate = str(value).strip()
    return candidate or None


def _string_was_blank(value: Optional[Any]) -> bool:
    if value is None:
        return False
    return str(value).strip() == ""


def _join_sources(names: Sequence[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


_SOURCE_LABELS = {
    "cli": "command line arguments",
    "env": "the environment",
    "local": "the local configuration file",
    "config": "the configuration file",
    "base": "the default configuration file",
}


_LAYER_LABELS = {
    "config": "configuration file",
    "local": "local configuration file",
}


def _describe_layer(layer: str, layer_paths: Dict[str, str]) -> str:
    base = _LAYER_LABELS.get(layer, f"{layer} layer")
    path = layer_paths.get(layer)
    if not path:
        return base
    return f"{base} '{path}'"


def _format_key_list(keys: Collection[str]) -> str:
    formatted = [f"`{key}`" for key in sorted(keys)]
    return _join_sources(formatted)


def _raise_misplaced_keys(
    *,
    keys: Collection[str],
    source_section: str,
    target_section: str,
    layer: str,
    layer_paths: Dict[str, str],
) -> None:
    key_list = _format_key_list(keys)
    layer_description = _describe_layer(layer, layer_paths)
    raise ValueError(
        f"{key_list} must be configured under [{target_section}]; "
        f"found in [{source_section}] within the {layer_description}."
    )


def _validate_runtime_roles_allocation(
    runtime_layers: Dict[str, Dict[str, Any]],
    roles_layers: Dict[str, Dict[str, Any]],
    layer_paths: Dict[str, str],
) -> None:
    for layer in ("config", "local"):
        runtime_section = runtime_layers.get(layer, {})
        roles_section = roles_layers.get(layer, {})

        misplaced_runtime = ROLE_CONFIG_KEYS.intersection(runtime_section)
        if misplaced_runtime:
            _raise_misplaced_keys(
                keys=misplaced_runtime,
                source_section="runtime",
                target_section="roles",
                layer=layer,
                layer_paths=layer_paths,
            )

        misplaced_roles = RUNTIME_CONFIG_KEYS.intersection(roles_section)
        if misplaced_roles:
            _raise_misplaced_keys(
                keys=misplaced_roles,
                source_section="roles",
                target_section="runtime",
                layer=layer,
                layer_paths=layer_paths,
            )


def _record_override_summary(
    messages: list[str],
    setting: str,
    sources: Sequence[Tuple[str, Optional[Any]]],
    blank_keys: Collection[str],
    chosen_value: Optional[Any],
) -> None:
    if chosen_value is None:
        return

    blank_lookup = set(blank_keys)
    chosen_index: Optional[int] = None
    for index, (key, value) in enumerate(sources):
        if key in blank_lookup:
            continue
        if value == chosen_value and _value_provided(value):
            chosen_index = index
            break

    if chosen_index is None:
        return

    overridden_keys = [
        source_key
        for source_key, candidate in sources[chosen_index + 1 :]
        if source_key not in blank_lookup and _value_provided(candidate)
    ]

    if not overridden_keys:
        return

    chosen_key = sources[chosen_index][0]

    # Skip logs when the chosen source is config but nothing lower priority
    # supplied a value; this matches the previous behaviour of ignoring
    # "config over base" messages to avoid noisy defaults.
    if chosen_key == "config" and not any(
        _value_provided(candidate)
        for source_key, candidate in sources[:chosen_index]
        if source_key not in blank_lookup
    ):
        return

    chosen_label = _SOURCE_LABELS.get(chosen_key, chosen_key)
    overridden_labels = [_SOURCE_LABELS.get(k, k) for k in overridden_keys]
    overridden_phrase = _join_sources(overridden_labels)
    messages.append(
        f"Using {setting} from {chosen_label}, overriding values from {overridden_phrase}."
    )


def _normalize_sources(
    *sources: Tuple[str, Optional[Any]]
) -> Tuple[
    list[Tuple[str, Optional[str]]],
    Dict[str, Optional[str]],
    set[str],
]:
    normalized_list: list[Tuple[str, Optional[str]]] = []
    normalized_map: Dict[str, Optional[str]] = {}
    blank_keys: set[str] = set()

    for key, raw in sources:
        normalized = _normalize_optional_str(raw)
        normalized_list.append((key, normalized))
        normalized_map[key] = normalized
        if _string_was_blank(raw):
            blank_keys.add(key)

    return normalized_list, normalized_map, blank_keys


def _build_normalized_chain(
    *sources: Tuple[str, Optional[Any]]
) -> Tuple[
    list[Tuple[str, Optional[str]]],
    Dict[str, Optional[str]],
    set[str],
    Optional[str],
]:
    chain, mapping, blank_keys = _normalize_sources(*sources)
    chosen = _first_truthy(*(value for _, value in chain))
    return chain, mapping, blank_keys, chosen


def _select_configured_value(
    mapping: Dict[str, Optional[str]],
    blank_keys: Collection[str],
    *,
    order: Sequence[str] = ("local", "config", "base"),
) -> Tuple[Optional[str], bool]:
    blank_lookup = set(blank_keys)
    for key in order:
        if key in blank_lookup:
            return None, True
        candidate = mapping.get(key)
        if candidate is not None:
            return candidate, False
    return None, False


def _resolve_bool_chain(*values: Optional[Any], default: bool = False) -> bool:
    result = default
    for value in values:
        result = coerce_bool(value, default=result)
    return result


def _resolve_bool_setting(
    setting: str,
    *,
    cli_value: Optional[Any],
    env_value: Optional[Any],
    runtime_layers: Dict[str, Dict[str, Any]],
    config_key: str,
    override_logs: list[str],
) -> bool:
    resolved = _resolve_bool_chain(
        runtime_layers["base"].get(config_key),
        runtime_layers["config"].get(config_key),
        runtime_layers["local"].get(config_key),
        env_value,
        cli_value,
    )
    sources = [
        ("cli", cli_value),
        ("env", env_value),
        ("local", runtime_layers["local"].get(config_key)),
        ("config", runtime_layers["config"].get(config_key)),
        ("base", runtime_layers["base"].get(config_key)),
    ]
    _record_override_summary(override_logs, setting, sources, (), resolved)
    return resolved


def _resolve_api_key(
    api_key_input: Optional[str],
    bitsight_layers: Dict[str, Dict[str, Any]],
    override_logs: list[str],
) -> Tuple[Optional[str], Optional[str]]:
    chain, mapping, blank_keys, value = _build_normalized_chain(
        ("cli", api_key_input),
        ("env", os.getenv("BITSIGHT_API_KEY")),
        ("local", bitsight_layers["local"].get("api_key")),
        ("config", bitsight_layers["config"].get("api_key")),
        ("base", bitsight_layers["base"].get("api_key")),
    )
    _record_override_summary(
        override_logs,
        "BITSIGHT_API_KEY",
        chain,
        blank_keys,
        value,
    )
    warning = None
    if mapping["base"] is not None:
        warning = (
            "Avoid storing bitsight.api_key in "
            f"{DEFAULT_CONFIG_FILENAME}; prefer {LOCAL_CONFIG_FILENAME}, environment variables, or CLI overrides."
        )
    return value, warning


def _resolve_subscription_setting(
    setting: str,
    *,
    cli_value: Optional[str],
    env_key: str,
    config_key: str,
    bitsight_layers: Dict[str, Dict[str, Any]],
    override_logs: list[str],
) -> Optional[str]:
    chain, _, blank_keys, value = _build_normalized_chain(
        ("cli", cli_value),
        ("env", os.getenv(env_key)),
        ("local", bitsight_layers["local"].get(config_key)),
        ("config", bitsight_layers["config"].get(config_key)),
        ("base", bitsight_layers["base"].get(config_key)),
    )
    _record_override_summary(override_logs, setting, chain, blank_keys, value)
    return value


def _resolve_context_setting(
    runtime_inputs: RuntimeInputs,
    roles_layers: Dict[str, Dict[str, Any]],
    override_logs: list[str],
) -> Tuple[str, Optional[str]]:
    chain, mapping, blank_keys, _ = _build_normalized_chain(
        ("cli", runtime_inputs.context),
        ("env", os.getenv("BIRRE_CONTEXT")),
        ("local", roles_layers["local"].get("context")),
        ("config", roles_layers["config"].get("context")),
        ("base", roles_layers["base"].get("context")),
    )
    config_value = (
        mapping["config"] if mapping["config"] is not None else mapping["base"]
    )
    normalized_context, warning = _resolve_context_value(
        mapping["cli"],
        mapping["env"],
        config_value,
    )
    if not warning:
        _record_override_summary(
            override_logs,
            "CONTEXT",
            chain,
            blank_keys,
            normalized_context,
        )
    return normalized_context, warning


def _resolve_risk_setting(
    runtime_inputs: RuntimeInputs,
    roles_layers: Dict[str, Dict[str, Any]],
    override_logs: list[str],
) -> Tuple[str, Optional[str]]:
    chain, mapping, blank_keys, _ = _build_normalized_chain(
        ("cli", runtime_inputs.risk_vector_filter),
        ("env", os.getenv(ENV_RISK_VECTOR_FILTER)),
        ("local", roles_layers["local"].get("risk_vector_filter")),
        ("config", roles_layers["config"].get("risk_vector_filter")),
        ("base", roles_layers["base"].get("risk_vector_filter")),
    )
    config_value, config_blank = _select_configured_value(mapping, blank_keys)
    risk_vector_filter, warning = _resolve_risk_vector_filter(
        mapping["cli"],
        "cli" in blank_keys,
        mapping["env"],
        "env" in blank_keys,
        config_value,
        config_blank,
    )
    if not warning:
        _record_override_summary(
            override_logs,
            "RISK_VECTOR_FILTER",
            chain,
            blank_keys,
            risk_vector_filter,
        )
    return risk_vector_filter, warning


def _resolve_tls_settings(
    tls_inputs: TlsInputs,
    runtime_layers: Dict[str, Dict[str, Any]],
    override_logs: list[str],
) -> Tuple[bool, Optional[str], Optional[str]]:
    allow_insecure_env = os.getenv(ENV_ALLOW_INSECURE_TLS)
    allow_insecure_tls = _resolve_bool_setting(
        "ALLOW_INSECURE_TLS",
        cli_value=tls_inputs.allow_insecure,
        env_value=allow_insecure_env,
        runtime_layers=runtime_layers,
        config_key="allow_insecure_tls",
        override_logs=override_logs,
    )

    chain, mapping, blank_keys, _ = _build_normalized_chain(
        ("cli", tls_inputs.ca_bundle_path),
        ("env", os.getenv(ENV_CA_BUNDLE)),
        ("local", runtime_layers["local"].get("ca_bundle_path")),
        ("config", runtime_layers["config"].get("ca_bundle_path")),
        ("base", runtime_layers["base"].get("ca_bundle_path")),
    )
    config_value, config_blank = _select_configured_value(mapping, blank_keys)
    ca_bundle_path, warning = _resolve_ca_bundle_path(
        mapping["cli"],
        "cli" in blank_keys,
        mapping["env"],
        "env" in blank_keys,
        config_value,
        config_blank,
    )
    if not warning:
        _record_override_summary(
            override_logs,
            "CA_BUNDLE_PATH",
            chain,
            blank_keys,
            ca_bundle_path,
        )
    return allow_insecure_tls, ca_bundle_path, warning


def _resolve_max_findings_setting(
    runtime_inputs: RuntimeInputs,
    roles_layers: Dict[str, Dict[str, Any]],
    override_logs: list[str],
) -> Tuple[int, Optional[str]]:
    max_findings_env = os.getenv(ENV_MAX_FINDINGS)
    config_value = None
    for source in ("local", "config", "base"):
        candidate = roles_layers[source].get("max_findings")
        if candidate is not None:
            config_value = candidate
            break

    max_value, warning = _resolve_max_findings(
        runtime_inputs.max_findings,
        max_findings_env,
        config_value,
    )
    if not warning:
        sources = [
            ("cli", runtime_inputs.max_findings),
            ("env", max_findings_env),
            ("local", roles_layers["local"].get("max_findings")),
            ("config", roles_layers["config"].get("max_findings")),
            ("base", roles_layers["base"].get("max_findings")),
        ]
        _record_override_summary(
            override_logs,
            "MAX_FINDINGS",
            sources,
            (),
            max_value,
        )
    return max_value, warning


def _resolve_context_value(
    context_arg: Optional[str],
    context_env: Optional[str],
    context_cfg: Optional[Any],
) -> Tuple[str, Optional[str]]:
    requested = _first_truthy(context_arg, context_env, context_cfg)
    normalized, invalid, candidate = _normalize_context(requested)
    if invalid:
        return normalized, (
            f"Unknown context '{candidate}' requested; defaulting to 'standard'"
        )
    return normalized, None


def _resolve_risk_vector_filter(
    arg_value: Optional[str],
    arg_blank: bool,
    env_value: Optional[str],
    env_blank: bool,
    cfg_value: Optional[str],
    cfg_blank: bool,
) -> Tuple[str, Optional[str]]:
    for value, was_blank in (
        (arg_value, arg_blank),
        (env_value, env_blank),
        (cfg_value, cfg_blank),
    ):
        if was_blank:
            return DEFAULT_RISK_VECTOR_FILTER, (
                "Empty risk_vector_filter override; falling back to default configuration"
            )
        if value is not None:
            return value, None

    return DEFAULT_RISK_VECTOR_FILTER, None


def _resolve_ca_bundle_path(
    arg_value: Optional[str],
    arg_blank: bool,
    env_value: Optional[str],
    env_blank: bool,
    cfg_value: Optional[str],
    cfg_blank: bool,
) -> Tuple[Optional[str], Optional[str]]:
    for value, was_blank in (
        (arg_value, arg_blank),
        (env_value, env_blank),
        (cfg_value, cfg_blank),
    ):
        if was_blank:
            return None, (
                "Empty ca_bundle_path override; ignoring custom CA bundle configuration"
            )
        if value is not None:
            return value, None

    return None, None


def _resolve_max_findings(
    arg_value: Optional[int],
    env_value: Optional[str],
    cfg_value: Optional[Any],
) -> Tuple[int, Optional[str]]:
    for candidate in (arg_value, env_value, cfg_value):
        if candidate is not None:
            raw = candidate
            break
    else:
        raw = None

    try:
        return _coerce_positive_int(raw, DEFAULT_MAX_FINDINGS), None
    except ValueError:
        return DEFAULT_MAX_FINDINGS, (
            "Invalid max_findings override; using default configuration"
        )


def _normalize_context(value: Optional[object]) -> tuple[str, bool, object]:
    raw = value if value not in (None, "") else None
    candidate: object = raw if raw is not None else "standard"
    normalized = str(candidate).strip().lower()
    if normalized in {"standard", "risk_manager"}:
        return normalized, False, candidate
    return "standard", raw is not None, candidate


def _resolve_level(level_value: Optional[str]) -> int:
    mapping = logging.getLevelNamesMapping()
    if level_value is None:
        return mapping.get(DEFAULT_LOG_LEVEL, logging.INFO)
    if isinstance(level_value, int):
        return level_value
    upper = str(level_value).upper()
    if upper.isdigit():
        return int(upper)
    if upper not in mapping:
        raise ValueError(f"Unknown log level: {level_value}")
    return mapping[upper]


def _coerce_positive_int(candidate: Optional[Any], default: int) -> int:
    if candidate is None:
        return default
    try:
        value = int(candidate)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid integer value: {candidate}") from exc
    if value <= 0:
        raise ValueError(f"Value must be positive: {candidate}")
    return value


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
        """Map provided values to ``resolve_logging_settings`` keyword arguments."""

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

    config_path_obj = Path(config_path)
    local_path = config_path_obj.with_name(
        f"{config_path_obj.stem}.local{config_path_obj.suffix}"
    )

    config_data = _load_config(config_path)
    local_data = _load_local_config(config_path)
    base_data = _load_base_config(config_path)

    bitsight_layers = {
        "local": _get_dict_section(local_data, BITSIGHT_SECTION),
        "config": _get_dict_section(config_data, BITSIGHT_SECTION),
        "base": _get_dict_section(base_data, BITSIGHT_SECTION),
    }
    runtime_layers = {
        "local": _get_dict_section(local_data, "runtime"),
        "config": _get_dict_section(config_data, "runtime"),
        "base": _get_dict_section(base_data, "runtime"),
    }
    roles_layers = {
        "local": _get_dict_section(local_data, "roles"),
        "config": _get_dict_section(config_data, "roles"),
        "base": _get_dict_section(base_data, "roles"),
    }

    layer_paths = {
        "config": str(config_path_obj),
        "local": str(local_path),
    }

    _validate_runtime_roles_allocation(runtime_layers, roles_layers, layer_paths)

    subscription_inputs = subscription_inputs or SubscriptionInputs()
    runtime_inputs = runtime_inputs or RuntimeInputs()
    tls_inputs = tls_inputs or TlsInputs()

    override_logs: list[str] = []
    warnings: list[str] = []

    api_key, base_warning = _resolve_api_key(api_key_input, bitsight_layers, override_logs)
    if base_warning:
        warnings.append(base_warning)

    subscription_folder = _resolve_subscription_setting(
        "SUBSCRIPTION_FOLDER",
        cli_value=subscription_inputs.folder,
        env_key="BIRRE_SUBSCRIPTION_FOLDER",
        config_key="subscription_folder",
        bitsight_layers=bitsight_layers,
        override_logs=override_logs,
    )

    subscription_type = _resolve_subscription_setting(
        "SUBSCRIPTION_TYPE",
        cli_value=subscription_inputs.type,
        env_key="BIRRE_SUBSCRIPTION_TYPE",
        config_key="subscription_type",
        bitsight_layers=bitsight_layers,
        override_logs=override_logs,
    )

    normalized_context, context_warning = _resolve_context_setting(
        runtime_inputs,
        roles_layers,
        override_logs,
    )
    if context_warning:
        warnings.append(context_warning)

    skip_startup_checks = _resolve_bool_setting(
        "SKIP_STARTUP_CHECKS",
        cli_value=runtime_inputs.skip_startup_checks,
        env_value=os.getenv("BIRRE_SKIP_STARTUP_CHECKS"),
        runtime_layers=runtime_layers,
        config_key="skip_startup_checks",
        override_logs=override_logs,
    )

    debug_env = os.getenv("BIRRE_DEBUG") or os.getenv("DEBUG")
    debug_enabled = _resolve_bool_setting(
        "DEBUG",
        cli_value=runtime_inputs.debug,
        env_value=debug_env,
        runtime_layers=runtime_layers,
        config_key="debug",
        override_logs=override_logs,
    )

    risk_vector_filter, risk_warning = _resolve_risk_setting(
        runtime_inputs,
        roles_layers,
        override_logs,
    )
    if risk_warning:
        warnings.append(risk_warning)

    allow_insecure_tls, ca_bundle_path, ca_warning = _resolve_tls_settings(
        tls_inputs,
        runtime_layers,
        override_logs,
    )
    if ca_warning:
        warnings.append(ca_warning)

    if allow_insecure_tls and ca_bundle_path:
        warnings.append(
            "allow_insecure_tls takes precedence over ca_bundle_path; HTTPS verification will be disabled"
        )
        ca_bundle_path = None

    max_value, max_warning = _resolve_max_findings_setting(
        runtime_inputs,
        roles_layers,
        override_logs,
    )
    if max_warning:
        warnings.append(max_warning)

    # Environment variables are not mutated; downstream consumers rely on returned settings.

    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "context": normalized_context,
        "risk_vector_filter": risk_vector_filter,
        "max_findings": max_value,
        "skip_startup_checks": skip_startup_checks,
        "debug": debug_enabled,
        "allow_insecure_tls": allow_insecure_tls,
        "ca_bundle_path": ca_bundle_path,
        "warnings": warnings,
        "overrides": override_logs,
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
    config_section = {}
    if config_path:
        data = load_config_layers(config_path)
        if isinstance(data, dict):
            candidate = data.get("logging", {})
            if isinstance(candidate, dict):
                config_section = candidate

    level_value = (
        level_override
        or os.getenv(ENV_LOG_LEVEL)
        or config_section.get("level")
        or DEFAULT_LOG_LEVEL
    )
    format_value = (
        _normalize_optional_str(format_override)
        or _normalize_optional_str(os.getenv(ENV_LOG_FORMAT))
        or _normalize_optional_str(config_section.get("format"))
        or DEFAULT_LOG_FORMAT
    )

    file_path = (
        _normalize_optional_str(file_override)
        or _normalize_optional_str(os.getenv(ENV_LOG_FILE))
        or _normalize_optional_str(config_section.get("file"))
    )

    max_bytes_value = (
        max_bytes_override
        or os.getenv(ENV_LOG_MAX_BYTES)
        or config_section.get("max_bytes")
    )
    backup_count_value = (
        backup_count_override
        or os.getenv(ENV_LOG_BACKUP_COUNT)
        or config_section.get("backup_count")
    )

    resolved_level = _resolve_level(level_value)
    resolved_format = format_value.lower()
    if resolved_format not in {LOG_FORMAT_TEXT, LOG_FORMAT_JSON}:
        raise ValueError(f"Unsupported log format: {format_value}")

    resolved_max_bytes = _coerce_positive_int(max_bytes_value, DEFAULT_MAX_BYTES)
    resolved_backup_count = _coerce_positive_int(
        backup_count_value, DEFAULT_BACKUP_COUNT
    )

    return LoggingSettings(
        level=resolved_level,
        format=resolved_format,
        file_path=file_path,
        max_bytes=resolved_max_bytes,
        backup_count=resolved_backup_count,
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
    logging_kwargs = (
        logging_inputs.as_kwargs() if logging_inputs is not None else {}
    )
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
