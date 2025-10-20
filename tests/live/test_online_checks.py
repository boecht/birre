import os

import pytest

import fastmcp

if getattr(fastmcp, "__FASTMCP_STUB__", False):
    pytest.skip(
        "fastmcp dependency not installed; skipping live tests", allow_module_level=True
    )

from src.birre import create_birre_server
from src.settings import RuntimeSettings, resolve_birre_settings
from src.logging import get_logger
from src.startup_checks import run_online_startup_checks


pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_runtime_settings() -> RuntimeSettings:
    api_key = os.getenv("BITSIGHT_API_KEY")
    if not api_key:
        pytest.skip("BITSIGHT_API_KEY not configured; skipping live tests")
    return resolve_birre_settings()


@pytest.fixture(scope="module")
def live_server(live_runtime_settings: RuntimeSettings):
    logger = get_logger("birre.live.test")
    return create_birre_server(live_runtime_settings, logger=logger)


@pytest.mark.asyncio
async def test_run_online_startup_checks_live(
    live_runtime_settings: RuntimeSettings, live_server
) -> None:
    logger = get_logger("birre.live.startup")
    call_v1_tool = getattr(live_server, "call_v1_tool", None)
    assert call_v1_tool is not None, "BiRRe server does not expose call_v1_tool"

    result = await run_online_startup_checks(
        call_v1_tool=call_v1_tool,
        subscription_folder=live_runtime_settings.subscription_folder,
        subscription_type=live_runtime_settings.subscription_type,
        logger=logger,
        skip_startup_checks=False,
    )

    assert result is True
