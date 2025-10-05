#!/usr/bin/env python3
"""BiRRe FastMCP server entrypoint.

Usage:
    python server.py [--bitsight-api-key KEY]

If no key is supplied, the server falls back to the ``BITSIGHT_API_KEY``
environment variable.
"""

import argparse
import asyncio
import json
import logging
from typing import Any, Dict

from src.birre import create_birre_server, resolve_birre_settings
from src.logging import (
    LoggingSettings,
    configure_logging,
    get_logger,
    resolve_logging_settings,
)
from src.startup_checks import run_offline_startup_checks, run_online_startup_checks


def _resolve_settings_helper(args: argparse.Namespace) -> Dict[str, Any]:
    return resolve_birre_settings(
        api_key_arg=args.api_key,
        config_path=args.config_path,
        subscription_folder_arg=args.subscription_folder,
        subscription_type_arg=args.subscription_type,
        debug_arg=args.debug,
    )


def main() -> None:
    """Main entry point for BiRRe MCP server."""

    parser = argparse.ArgumentParser(description="Run the BiRRe FastMCP server")
    parser.add_argument(
        "--bitsight-api-key",
        dest="api_key",
        help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
    )
    valid_levels = [
        name
        for name, value in logging.getLevelNamesMapping().items()
        if isinstance(name, str) and not name.isdigit()
    ]
    parser.add_argument(
        "--log-level",
        dest="log_level",
        choices=sorted(valid_levels),
        help="Logging level (defaults to INFO unless overridden)",
    )
    parser.add_argument(
        "--log-format",
        dest="log_format",
        choices=["text", "json"],
        help="Logging format (text or json)",
    )
    parser.add_argument(
        "--log-file",
        dest="log_file",
        help="Optional log file path (adds rotating file handler)",
    )
    parser.add_argument(
        "--log-max-bytes",
        dest="log_max_bytes",
        type=int,
        help="Maximum size in bytes for rotating log files",
    )
    parser.add_argument(
        "--log-backup-count",
        dest="log_backup_count",
        type=int,
        help="Number of rotating log file backups to keep",
    )
    parser.add_argument(
        "--skip-startup-checks",
        dest="skip_startup_checks",
        action="store_true",
        help="Skip BitSight startup checks (not recommended)",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default="config.toml",
        help="Path to BiRRe config TOML (default: config.toml)",
    )
    parser.add_argument(
        "--subscription-folder",
        dest="subscription_folder",
        help="Preferred BitSight subscription folder name (e.g. API), must exist",
    )
    parser.add_argument(
        "--subscription-type",
        dest="subscription_type",
        help="BitSight subscription type (e.g. continuous_monitoring)",
    )
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable verbose debug logging and diagnostic payloads",
    )

    args = parser.parse_args()

    server_settings = _resolve_settings_helper(args)
    debug_enabled = server_settings["debug"]

    logging_settings = resolve_logging_settings(
        config_path=args.config_path,
        level_override=args.log_level,
        format_override=args.log_format,
        file_override=args.log_file,
        max_bytes_override=args.log_max_bytes,
        backup_count_override=args.log_backup_count,
    )

    if debug_enabled and logging_settings.level > logging.DEBUG:
        logging_settings = LoggingSettings(
            level=logging.DEBUG,
            format=logging_settings.format,
            file_path=logging_settings.file_path,
            max_bytes=logging_settings.max_bytes,
            backup_count=logging_settings.backup_count,
        )

    configure_logging(logging_settings)
    logger = get_logger(__name__)

    offline_results = run_offline_startup_checks(
        api_key_present=bool(server_settings["api_key"]),
        subscription_folder=server_settings["subscription_folder"],
        subscription_type=server_settings["subscription_type"],
        logger=logger,
    )
    if offline_results["summary"]["error"] > 0:
        print(json.dumps({"offline": offline_results}, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    server = create_birre_server(
        api_key=args.api_key,
        config_path=args.config_path,
        subscription_folder=args.subscription_folder,
        subscription_type=args.subscription_type,
    )

    call_v1_tool = getattr(server, "call_v1_tool", None)
    online_results = asyncio.run(
        run_online_startup_checks(
            call_v1_tool=call_v1_tool,
            subscription_folder=server_settings["subscription_folder"],
            subscription_type=server_settings["subscription_type"],
            logger=logger,
            skip_startup_checks=(
                args.skip_startup_checks or server_settings["skip_startup_checks"]
            ),
        )
    )

    combined_results = {"offline": offline_results, "online": online_results}
    print(json.dumps(combined_results, indent=2, ensure_ascii=False))
    if (
        offline_results["summary"]["error"] > 0
        or online_results["summary"]["error"] > 0
    ):
        raise SystemExit(1)

    logger.info("Starting BiRRe FastMCP server")
    server.run()


if __name__ == "__main__":
    main()
