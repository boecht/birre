"""BiRRe FastMCP server entrypoint.

Usage:
    python server.py [--bitsight-api-key KEY]

If no key is supplied, the server falls back to the ``BITSIGHT_API_KEY``
environment variable.
"""

import argparse
import asyncio
import logging
import os
import sys

# FastMCP checks this flag during import time, so ensure it is enabled before
# importing any modules that depend on FastMCP.
os.environ["FASTMCP_EXPERIMENTAL_ENABLE_NEW_OPENAPI_PARSER"] = "true"

from src.birre import create_birre_server
from src.constants import DEFAULT_CONFIG_FILENAME
from src.config import (
    LoggingInputs,
    RuntimeInputs,
    SubscriptionInputs,
    TlsInputs,
    resolve_application_settings,
)
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
        default=DEFAULT_CONFIG_FILENAME,
        help=(
            "Path to BiRRe config TOML "
            f"(default: {DEFAULT_CONFIG_FILENAME})"
        ),
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
        default=None,
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
        default=None,
        help="Enable verbose debug logging and diagnostic payloads",
    )
    parser.add_argument(
        "--allow-insecure-tls",
        dest="allow_insecure_tls",
        action="store_true",
        default=None,
        help=(
            "Disable HTTPS certificate verification for BitSight API requests. "
            "Use only when behind a trusted intercepting proxy."
        ),
    )
    parser.add_argument(
        "--ca-bundle",
        dest="ca_bundle_path",
        help=(
            "Path to a custom CA bundle for BitSight API HTTPS verification "
            "(overrides system trust store)."
        ),
    )

    args = parser.parse_args()

    logging_inputs = LoggingInputs(
        level=args.log_level,
        format=args.log_format,
        file_path=args.log_file,
        max_bytes=args.log_max_bytes,
        backup_count=args.log_backup_count,
    )

    runtime_inputs = RuntimeInputs(
        context=args.context,
        debug=args.debug,
        risk_vector_filter=args.risk_vector_filter,
        max_findings=args.max_findings,
        skip_startup_checks=args.skip_startup_checks,
    )

    subscription_inputs = SubscriptionInputs(
        folder=args.subscription_folder,
        type=args.subscription_type,
    )

    tls_inputs = TlsInputs(
        allow_insecure=args.allow_insecure_tls,
        ca_bundle_path=args.ca_bundle_path,
    )

    runtime_settings, logging_settings = resolve_application_settings(
        api_key_input=args.api_key,
        config_path=args.config_path,
        subscription_inputs=subscription_inputs,
        runtime_inputs=runtime_inputs,
        logging_inputs=logging_inputs,
        tls_inputs=tls_inputs,
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
        "╰────────────────────────────────────────────────────────────────╯\n\033[0m",
        file=sys.stderr,
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
    try:
        server.run()
    except KeyboardInterrupt:
        print(
            "\n"
            "╭────────────────────────────────────────╮\n"
            "│\033[0;31m  Keyboard interrupt received — stopping  \033[0m│\n"
            "│\033[0;31m          BiRRe FastMCP server            \033[0m│\n"
            "╰────────────────────────────────────────╯\n\033[0m",
            file=sys.stderr,
        )
        logger.info("BiRRe FastMCP server stopped via KeyboardInterrupt")


if __name__ == "__main__":
    main()
