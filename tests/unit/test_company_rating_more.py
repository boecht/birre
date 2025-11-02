from __future__ import annotations

from types import SimpleNamespace

import pytest

import birre.domain.company_rating.service as s


def test_infection_narrative_preference() -> None:
    details = {"infection": {"family": "Zeus", "description": "C2 observed"}}
    out = s._apply_infection_narrative_preference("desc", "botnet_infections", details)
    assert "Infection:" in out

    # Without family, append description
    details2 = {"infection": {"description": "note"}}
    out2 = s._apply_infection_narrative_preference("Base", "botnet_infections", details2)
    assert out2.endswith("note")


def test_primary_port_and_asset() -> None:
    d = {"dest_port": 443}
    assert s._determine_primary_port(d) == 443
    d2 = {"port_list": [22]}
    assert s._determine_primary_port(d2) == 22
    item = {"evidence_key": "host"}
    assert s._determine_primary_asset(item, {}) == "host"
    details = {"assets": [{"asset": "example.com"}], "dest_port": 443}
    assert s._determine_primary_asset({}, details) == "example.com:443"
    details2 = {"observed_ips": ["1.2.3.4"]}
    assert s._determine_primary_asset({}, details2) == "1.2.3.4"


@pytest.mark.asyncio
async def test_extract_results_and_fetch_findings_paths() -> None:
    # results not a list -> []
    out = s._extract_results_from_payload(
        {"results": {}}, SimpleNamespace(info=lambda *a, **k: None), "L", debug_enabled=False
    )  # type: ignore[arg-type]
    assert out == []

    # _fetch_and_normalize_findings: non-dict raw -> ([], False)
    def _call(tool: str, ctx, params):  # noqa: ANN001
        return 123

    findings, ok = await s._fetch_and_normalize_findings(
        _call, SimpleNamespace(info=lambda *a, **k: None), {}, 5, "strict", debug_enabled=False
    )  # type: ignore[arg-type]
    assert findings == [] and ok is False
