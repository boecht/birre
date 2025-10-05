from __future__ import annotations

import os
from functools import partial
from typing import Optional, Dict, Any
from pathlib import Path
import tomllib

from dotenv import load_dotenv
from fastmcp import FastMCP

from .apis import (
    call_v1_openapi_tool,
    create_v1_api_server,
    create_v2_api_server,
)
from .business import (
    register_company_rating_tool,
    register_company_search_tool,
)
from .logging import get_logger

logger = get_logger(__name__)


def _load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}


def _load_config_layers(base_path: str) -> Dict[str, Any]:
    """Load base config and optional `.local` overlay next to it.

    Example: base `config.toml` and overlay `config.local.toml`.
    """
    cfg = _load_config(base_path)
    p = Path(base_path)
    local_path = p.with_name(f"{p.stem}.local{p.suffix}")
    if local_path.exists():
        overlay = _load_config(str(local_path))
        if isinstance(cfg, dict) and isinstance(overlay, dict):
            # shallow merge for known sections (e.g., [bitsight])
            for section, values in overlay.items():
                if isinstance(values, dict):
                    base_section = (
                        cfg.get(section, {})
                        if isinstance(cfg.get(section), dict)
                        else {}
                    )
                    merged = {**base_section, **values}
                    cfg[section] = merged
                else:
                    cfg[section] = values
        else:
            cfg = overlay or cfg
    return cfg


def resolve_birre_settings(
    *,
    api_key_arg: Optional[str] = None,
    config_path: str = "config.toml",
    subscription_folder_arg: Optional[str] = None,
    subscription_type_arg: Optional[str] = None,
    debug_arg: Optional[bool] = None,
) -> Dict[str, Any]:
    """Resolve settings from config, env, and CLI.

    Precedence (lowest → highest): config file < environment < CLI args.
    """

    load_dotenv()

    cfg = _load_config_layers(config_path)
    cfg_bitsight = cfg.get("bitsight", {}) if isinstance(cfg, dict) else {}

    runtime_cfg = None
    if isinstance(cfg, dict):
        runtime_cfg = cfg.get("runtime")

    startup_skip_cfg = None
    debug_cfg = None
    if isinstance(runtime_cfg, dict):
        startup_skip_cfg = runtime_cfg.get("skip_startup_checks")
        debug_cfg = runtime_cfg.get("debug")

    # Config values
    api_key_cfg = None
    folder_cfg = None
    type_cfg = None
    if isinstance(cfg_bitsight, dict):
        api_key_cfg = cfg_bitsight.get("api_key")
        folder_cfg = cfg_bitsight.get("subscription_folder")
        type_cfg = cfg_bitsight.get("subscription_type")

    # Env values
    api_key_env = os.getenv("BITSIGHT_API_KEY")
    folder_env = os.getenv("BIRRE_SUBSCRIPTION_FOLDER")
    type_env = os.getenv("BIRRE_SUBSCRIPTION_TYPE")
    startup_skip_env = os.getenv("BIRRE_SKIP_STARTUP_CHECKS")
    debug_env = os.getenv("BIRRE_DEBUG")
    if debug_env is None:
        debug_env = os.getenv("DEBUG")

    # CLI values (highest priority if provided)
    api_key = api_key_arg or api_key_env or api_key_cfg
    subscription_folder = subscription_folder_arg or folder_env or folder_cfg
    subscription_type = subscription_type_arg or type_env or type_cfg

    skip_startup_checks = False
    if startup_skip_cfg is not None:
        skip_startup_checks = bool(startup_skip_cfg)
    if startup_skip_env is not None:
        skip_startup_checks = startup_skip_env.lower() in {"1", "true", "yes"}

    debug_enabled = False
    if debug_cfg is not None:
        debug_enabled = bool(debug_cfg)
    if debug_env is not None:
        debug_enabled = debug_env.lower() in {"1", "true", "yes"}
    if debug_arg is not None:
        debug_enabled = bool(debug_arg)

    if debug_enabled:
        os.environ["DEBUG"] = "true"
    else:
        os.environ.pop("DEBUG", None)

    if not api_key:
        raise ValueError("BITSIGHT_API_KEY is required (config/env/CLI)")

    return {
        "api_key": api_key,
        "subscription_folder": subscription_folder,
        "subscription_type": subscription_type,
        "skip_startup_checks": skip_startup_checks,
        "debug": debug_enabled,
    }


def create_birre_server(
    api_key: Optional[str] = None,
    *,
    config_path: str = "config.toml",
    subscription_folder: Optional[str] = None,
    subscription_type: Optional[str] = None,
) -> FastMCP:
    """Create and configure the BiRRe FastMCP business server."""

    settings = resolve_birre_settings(
        api_key_arg=api_key,
        config_path=config_path,
        subscription_folder_arg=subscription_folder,
        subscription_type_arg=subscription_type,
    )
    resolved_api_key = settings["api_key"]

    # Propagate resolved settings to environment for helpers.
    folder = settings.get("subscription_folder")
    if folder is not None:
        os.environ["BIRRE_SUBSCRIPTION_FOLDER"] = str(folder)
    t = settings.get("subscription_type")
    if t is not None:
        os.environ["BIRRE_SUBSCRIPTION_TYPE"] = str(t)

    v1_api_server = create_v1_api_server(resolved_api_key)

    if os.getenv("BIRRE_ENABLE_V2", "").lower() in {"1", "true", "yes"}:
        create_v2_api_server(resolved_api_key)

    business_server = FastMCP(
        name="BiRRe",
        instructions=(
            "Tools to retrieve BitSight security ratings for companies.\n"
            "Call `company_search(name?, domain?)` to find a company, then "
            "call `get_company_rating(guid)` with the returned GUID."
        ),
    )

    call_v1_tool = partial(call_v1_openapi_tool, v1_api_server, logger=logger)
    setattr(business_server, "call_v1_tool", call_v1_tool)

    async def _disable_unused_v1_tools() -> None:
        tools = await v1_api_server.get_tools()  # type: ignore[attr-defined]
        keep = {
            "companySearch",
            "manageSubscriptionsBulk",
            "getCompany",
            "getCompaniesFindings",
            "getFolders",
            "getCompanySubscriptions",
        }
        for name, tool in tools.items():
            if name not in keep:
                tool.disable()

    # Schedule disabling of unused v1 tools
    try:
        import asyncio

        asyncio.get_event_loop().run_until_complete(_disable_unused_v1_tools())
    except RuntimeError:
        pass

    register_company_search_tool(business_server, call_v1_tool, logger=logger)
    register_company_rating_tool(business_server, call_v1_tool, logger=logger)

    return business_server


__all__ = ["create_birre_server", "resolve_birre_settings"]
