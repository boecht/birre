# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "fastmcp==2.12.4",
#     "python-dotenv",
#     "httpx",
# ]
# ///

"""BiRRe FastMCP server entrypoint.

Usage:
    python server.py [--bitsight-api-key KEY]

If no key is supplied, the server falls back to the ``BITSIGHT_API_KEY``
environment variable.
"""

import argparse
import asyncio
import logging

from src.birre import create_birre_server
from src.config import resolve_application_settings
from src.logging import configure_logging
from src.startup_checks import run_offline_startup_checks, run_online_startup_checks


def main() -> None:
    """Main entry point for BiRRe MCP server."""

    parser = argparse.ArgumentParser(description="Run the BiRRe FastMCP server")
    parser.add_argument(
        "--bitsight-api-key",
        dest="api_key",
        help="BitSight API key (overrides BITSIGHT_API_KEY env var)",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default="config.toml",
        help="Path to BiRRe config TOML (default: config.toml)",
    )
    parser.add_argument(
        "--context",
        dest="context",
        help="Tool persona to expose (standard or risk_manager)",
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
        help="Log file path (adds rotating file handler)",
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
        "--risk-vector-filter",
        dest="risk_vector_filter",
        help="Override the default risk vectors used for top findings (comma-separated).",
    )
    parser.add_argument(
        "--max-findings",
        dest="max_findings",
        type=int,
        help="Maximum number of findings/details to surface per company (default: 10).",
    )
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable verbose debug logging and diagnostic payloads",
    )

    args = parser.parse_args()

    runtime_settings, logging_settings = resolve_application_settings(
        api_key_arg=args.api_key,
        config_path=args.config_path,
        context_arg=args.context,
        risk_vector_filter_arg=args.risk_vector_filter,
        max_findings_arg=args.max_findings,
        log_level_override=args.log_level,
        log_format_override=args.log_format,
        log_file_override=args.log_file,
        log_max_bytes_override=args.log_max_bytes,
        log_backup_count_override=args.log_backup_count,
        subscription_folder_arg=args.subscription_folder,
        subscription_type_arg=args.subscription_type,
        debug_arg=args.debug,
    )

    print(
        "\n"
        "╭────────────────────────────────────────────────────────────────╮\n"
        "│\033[0;33m                                                                \033[0m│\n"
        "│\033[0;33m     ███████████   ███  ███████████   ███████████               \033[0m│\n"
        "│\033[0;33m    ░░███░░░░░███ ░░░  ░░███░░░░░███ ░░███░░░░░███              \033[0m│\n"
        "│\033[0;33m     ░███    ░███ ████  ░███    ░███  ░███    ░███   ██████     \033[0m│\n"
        "│\033[0;33m     ░██████████ ░░███  ░██████████   ░██████████   ███░░███    \033[0m│\n"
        "│\033[0;33m     ░███░░░░░███ ░███  ░███░░░░░███  ░███░░░░░███ ░███████     \033[0m│\n"
        "│\033[0;33m     ░███    ░███ ░███  ░███    ░███  ░███    ░███ ░███░░░      \033[0m│\n"
        "│\033[0;33m     ███████████  █████ █████   █████ █████   █████░░██████     \033[0m│\n"
        "│\033[0;33m    ░░░░░░░░░░░  ░░░░░ ░░░░░   ░░░░░ ░░░░░   ░░░░░  ░░░░░░      \033[0m│\n"
        "│\033[0;33m                                                                \033[0m│\n"
        "│\033[2m                   Bitsight Rating Retriever                    \033[0m│\n"
        "│\033[0;33m                 Model Context Protocol Server                  \033[0m│\n"
        "│\033[0;33m                https://github.com/boecht/birre                 \033[0m│\n"
        "╰────────────────────────────────────────────────────────────────╯\n\033[0m"
    )

    configure_logging(logging_settings)
    logger = logging.getLogger("birre")

    for message in runtime_settings.get("warnings", []):
        logger.warning(message)

    logger.info("Running offline startup checks")
    offline_ok = run_offline_startup_checks(
        has_api_key=bool(runtime_settings["api_key"]),  # CodeQL false positive
        subscription_folder=runtime_settings["subscription_folder"],
        subscription_type=runtime_settings["subscription_type"],
        logger=logger,
    )
    if not offline_ok:
        logger.critical("Offline startup checks failed; aborting startup")
        raise SystemExit(1)

    logger.info("Preparing BiRRe FastMCP server")
    server = create_birre_server(settings=runtime_settings, logger=logger)

    logger.info("Running online startup checks")
    call_v1_tool = getattr(server, "call_v1_tool", None)
    online_ok = asyncio.run(
        run_online_startup_checks(
            call_v1_tool=call_v1_tool,
            subscription_folder=runtime_settings["subscription_folder"],
            subscription_type=runtime_settings["subscription_type"],
            logger=logger,
            skip_startup_checks=(
                args.skip_startup_checks or runtime_settings["skip_startup_checks"]
            ),
        )
    )
    if not online_ok:
        logger.critical("Online startup checks failed; aborting startup")
        raise SystemExit(1)

    logger.info("Starting BiRRe FastMCP server")
    server.run()


if __name__ == "__main__":
    main()
