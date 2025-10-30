"""Logging and diagnostics option definitions.

Provides Typer option declarations for logging configuration,
diagnostics, and command-specific output options.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

LogLevelOption = Annotated[
    str | None,
    typer.Option(
        "--log-level",
        help="Logging level (e.g. INFO, DEBUG)",
        envvar="BIRRE_LOG_LEVEL",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogFormatOption = Annotated[
    str | None,
    typer.Option(
        "--log-format",
        help="Logging format (text or json)",
        envvar="BIRRE_LOG_FORMAT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogFileOption = Annotated[
    str | None,
    typer.Option(
        "--log-file",
        help="Path to a log file (use '-', none, stderr to disable)",
        envvar="BIRRE_LOG_FILE",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogMaxBytesOption = Annotated[
    int | None,
    typer.Option(
        "--log-max-bytes",
        min=1,
        help="Maximum size in bytes for rotating log files",
        envvar="BIRRE_LOG_MAX_BYTES",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

LogBackupCountOption = Annotated[
    int | None,
    typer.Option(
        "--log-backup-count",
        min=1,
        help="Number of rotating log file backups to retain",
        envvar="BIRRE_LOG_BACKUP_COUNT",
        show_envvar=True,
        rich_help_panel="Logging",
    ),
]

ProfilePathOption = Annotated[
    Path | None,
    typer.Option(
        "--profile",
        help="Write Python profiling data to the provided path",
        rich_help_panel="Diagnostics",
    ),
]

OfflineFlagOption = Annotated[
    bool,
    typer.Option(
        "--offline/--online",
        help="Skip network checks and run offline validation only",
        rich_help_panel="Diagnostics",
    ),
]

ProductionFlagOption = Annotated[
    bool,
    typer.Option(
        "--production/--testing",
        help="Use the BitSight production API for online validation",
        rich_help_panel="Diagnostics",
    ),
]

LocalConfOutputOption = Annotated[
    Path,
    typer.Option(
        "--output",
        help="Destination local config file",
    ),
]

OverwriteOption = Annotated[
    bool,
    typer.Option(
        "--overwrite/--no-overwrite",
        help="Allow overwriting an existing local configuration file",
    ),
]

MinimizeOption = Annotated[
    bool,
    typer.Option(
        "--minimize/--no-minimize",
        help="Rewrite the configuration file with a minimal canonical layout",
    ),
]

__all__ = [
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
