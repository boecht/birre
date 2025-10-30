"""Typer option declarations and normalization helpers.

This package provides all CLI option type annotations and normalization
functions organized by concern area.
"""

from __future__ import annotations

# Re-export from submodules for backward compatibility during transition
from birre.cli.options.auth_runtime import (
    AllowInsecureTlsOption,
    BitsightApiKeyOption,
    CaBundleOption,
    ContextOption,
    DebugOption,
    MaxFindingsOption,
    RiskVectorFilterOption,
    SkipStartupChecksOption,
    SubscriptionFolderOption,
    SubscriptionTypeOption,
)
from birre.cli.options.core import (
    LOG_FORMAT_CHOICES,
    LOG_LEVEL_CHOICES,
    LOG_LEVEL_MAP,
    ConfigPathOption,
    clean_string,
    normalize_context,
    normalize_log_format,
    normalize_log_level,
    validate_positive,
)
from birre.cli.options.logging import (
    LocalConfOutputOption,
    LogBackupCountOption,
    LogFileOption,
    LogFormatOption,
    LogLevelOption,
    LogMaxBytesOption,
    MinimizeOption,
    OfflineFlagOption,
    OverwriteOption,
    ProductionFlagOption,
    ProfilePathOption,
)

__all__ = [
    # From core
    "ConfigPathOption",
    "LOG_FORMAT_CHOICES",
    "LOG_LEVEL_CHOICES",
    "LOG_LEVEL_MAP",
    "clean_string",
    "normalize_context",
    "normalize_log_format",
    "normalize_log_level",
    "validate_positive",
    # From auth_runtime
    "AllowInsecureTlsOption",
    "BitsightApiKeyOption",
    "CaBundleOption",
    "ContextOption",
    "DebugOption",
    "MaxFindingsOption",
    "RiskVectorFilterOption",
    "SkipStartupChecksOption",
    "SubscriptionFolderOption",
    "SubscriptionTypeOption",
    # From logging
    "LocalConfOutputOption",
    "LogBackupCountOption",
    "LogFileOption",
    "LogFormatOption",
    "LogLevelOption",
    "LogMaxBytesOption",
    "MinimizeOption",
    "OfflineFlagOption",
    "OverwriteOption",
    "ProfilePathOption",
    "ProductionFlagOption",
]
