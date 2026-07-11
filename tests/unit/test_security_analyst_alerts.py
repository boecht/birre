import pytest

from birre.domain.security_analyst.alerts import (
    enrich_company_groups,
    fetch_v2_alert_pages,
    group_alert_triggers_by_company,
    normalize_alert_trigger,
)
from birre.domain.security_analyst.movement import derive_rating_movement
from birre.domain.security_analyst.priority import filter_action_candidates
from birre.domain.security_analyst.request import build_alert_workflow_request
from birre.domain.security_analyst.workflow import run_alert_workflow_action_payload


def test_derive_rating_movement_prefers_larger_alert_rating_drop() -> None:
    assert derive_rating_movement(
        {"rating_before": 800, "rating_after": 700},
        [{"rating": 800}, {"rating": 680}],
    ) == {"drop": 120.0, "source": "company_history"}


def test_derive_rating_movement_uses_alert_rating_when_larger() -> None:
    assert derive_rating_movement(
        {"rating_before": 800, "rating_after": 700},
        [{"rating": 800}, {"rating": 750}],
    ) == {"drop": 100.0, "source": "alert_rating"}


def test_derive_rating_movement_uses_category_rating_map() -> None:
    assert derive_rating_movement(
        {"category_before": "A", "category_after": "C"},
        category_rating_map={"A": 900, "C": 600},
    ) == {"drop": 50.0, "source": "alert_category"}


def test_derive_rating_movement_warns_when_no_drop_exists() -> None:
    assert derive_rating_movement({}) == {"warning": "rating_movement_missing"}


@pytest.mark.asyncio
async def test_run_alert_workflow_returns_action_payload_and_all_warning_metadata() -> None:
    async def call_v2_tool(_name: str, _ctx: object, _params: dict[str, object]) -> object:
        return {
            "results": [
                {
                    "guid": "alert-1",
                    "company_guid": "company-1",
                    "alert_type": "web application security",
                },
                {"guid": "alert-missing-company"},
            ],
            "next": "next-page",
        }

    async def fetch_company(_guid: str) -> object:
        raise RuntimeError("unavailable")

    result = await run_alert_workflow_action_payload(
        call_v2_tool,
        fetch_company,
        max_pages=1,
    )

    assert result["action_items"][0]["company_guid"] == "company-1"
    assert set(result["metadata"]["warnings"]) == {
        "alert_page_cap_reached",
        "company_guid_missing_anomaly",
        "company_enrichment_failed",
        "rating_movement_missing",
        "category_ambiguous",
    }


@pytest.mark.asyncio
async def test_fetch_v2_alert_pages_paginates_with_filters_and_details() -> None:
    calls: list[dict[str, object]] = []

    async def call_v2_tool(_name: str, _ctx: object, params: dict[str, object]) -> object:
        calls.append(params)
        return {
            "results": [{"guid": str(len(calls))}],
            "links": {"next": "next"} if len(calls) == 1 else {},
        }

    result = await fetch_v2_alert_pages(
        call_v2_tool,
        None,
        build_alert_workflow_request(alert_date_gte="2026-07-01", page_size=50, max_pages=2),
        severity="high",
        alert_type="rating",
        folder_guid="folder-1",
    )

    assert len(result["pages"]) == 2
    assert calls[0] == {
        "limit": 50,
        "offset": 0,
        "expand": "details",
        "alert_date_gte": "2026-07-01",
        "severity": "high",
        "alert_type": "rating",
        "folder_guid": "folder-1",
    }
    assert calls[1]["offset"] == 50


@pytest.mark.asyncio
async def test_fetch_v2_alert_pages_reports_cap_and_rejects_invalid_results() -> None:
    async def capped_call(_name: str, _ctx: object, _params: dict[str, object]) -> object:
        return {"results": [], "next": "next"}

    result = await fetch_v2_alert_pages(
        capped_call,
        None,
        build_alert_workflow_request(max_pages=1),
    )
    assert result["metadata"]["warnings"] == ["alert_page_cap_reached"]

    async def invalid_call(_name: str, _ctx: object, _params: dict[str, object]) -> object:
        return {"results": {}}

    with pytest.raises(ValueError, match="results"):
        await fetch_v2_alert_pages(
            invalid_call,
            None,
            build_alert_workflow_request(max_pages=1),
        )


def test_normalize_alert_trigger_preserves_alert_and_source_fields() -> None:
    details = {"finding": {"name": "Rating change", "values": [1, 2]}}
    alert = {
        "guid": "alert-1",
        "company_guid": "company-1",
        "company_name": "Acme",
        "alert_type": "rating",
        "alert_date": "2026-07-01",
        "start_date": "2026-06-30",
        "severity": "high",
        "trigger": "Rating changed",
        "folder_guid": "folder-1",
        "alert_set_guid": "set-1",
        "details": details,
    }
    page_metadata = {
        "endpoint": "getAlerts",
        "query": {"offset": 50},
        "page_index": 1,
        "offset": 50,
    }

    result = normalize_alert_trigger(alert, page_metadata)

    assert result["alert_guid"] == "alert-1"
    assert result["company_guid"] == "company-1"
    assert result["alert_date"] == "2026-07-01"
    assert result["severity"] == "high"
    assert result["trigger"] == "Rating changed"
    assert result["folder_context"] == {
        "folder_guid": "folder-1",
        "alert_set_guid": "set-1",
    }
    assert result["details"] == details
    assert result["raw_alert"] == alert
    assert result["source_metadata"] == page_metadata
    assert result["enrichable"] is True
    assert result["warnings"] == []


def test_normalize_alert_trigger_marks_missing_company_as_non_enrichable() -> None:
    result = normalize_alert_trigger({"guid": "alert-2"}, {})

    assert result["enrichable"] is False
    assert result["warnings"] == ["company_guid_missing_anomaly"]


def test_group_alert_triggers_by_company_preserves_alert_provenance() -> None:
    triggers = [
        {"company_guid": "c-1", "alert_guid": "a-1", "enrichable": True},
        {"company_guid": "c-1", "alert_guid": "a-2", "enrichable": True},
        {"company_guid": "c-2", "alert_guid": "a-3", "enrichable": True},
    ]

    result = group_alert_triggers_by_company(triggers, max_companies=2)

    assert set(result["groups"]) == {"c-1", "c-2"}
    assert [trigger["alert_guid"] for trigger in result["groups"]["c-1"]["triggers"]] == [
        "a-1",
        "a-2",
    ]
    assert result["metadata"]["warnings"] == []


def test_group_alert_triggers_by_company_applies_cap_and_preserves_warnings() -> None:
    triggers = [
        {"company_guid": "c-1", "alert_guid": "a-1", "enrichable": True},
        {"company_guid": "c-2", "alert_guid": "a-2", "enrichable": True},
        {
            "company_guid": None,
            "alert_guid": "a-3",
            "enrichable": False,
            "warnings": ["company_guid_missing_anomaly"],
        },
    ]

    result = group_alert_triggers_by_company(triggers, max_companies=1)

    assert set(result["groups"]) == {"c-1"}
    assert result["metadata"]["warnings"] == [
        "company_cap_reached",
        "company_guid_missing_anomaly",
    ]


def test_group_alert_triggers_by_company_returns_empty_result() -> None:
    assert group_alert_triggers_by_company([], max_companies=1) == {
        "groups": {},
        "metadata": {"warnings": []},
    }


def test_filter_action_candidates_applies_scope_priority_and_ambiguity_rules() -> None:
    result = filter_action_candidates(
        [
            {"company_guid": "c-3", "priority": 3, "category": "TLS certificates"},
            {"company_guid": "c-4", "priority": 4, "category": "TLS certificates"},
            {"company_guid": "c-dns", "priority": 3, "category": "DNSSEC"},
            {
                "company_guid": "c-web",
                "priority": 3,
                "category": "web application security",
            },
        ],
        max_returned_priority=3,
    )

    assert [candidate["company_guid"] for candidate in result["action_candidates"]] == [
        "c-3",
        "c-web",
    ]
    assert result["action_candidates"][1]["metadata"] == {"warning": "category_ambiguous"}
    assert result["filtered_candidates"] == [
        {
            "company_guid": "c-4",
            "priority": 4,
            "eligible": False,
            "action_item": None,
            "filter_reason": "priority_filtered",
        },
        {
            "company_guid": "c-dns",
            "priority": 3,
            "eligible": False,
            "action_item": None,
            "filter_reason": "out_of_scope_category",
        },
    ]


def test_filter_action_candidates_includes_priority_threshold() -> None:
    result = filter_action_candidates(
        [{"company_guid": "c-3", "priority": 3}], max_returned_priority=3
    )

    assert result["action_candidates"] == [{"company_guid": "c-3", "priority": 3, "eligible": True}]


@pytest.mark.asyncio
async def test_enrich_company_groups_fetches_distinct_companies_and_fields() -> None:
    calls: list[str] = []

    async def fetch_company(guid: str) -> dict[str, object]:
        calls.append(guid)
        return {
            "name": f"Company {guid}",
            "primary_domain": f"{guid}.example.com",
            "current_rating": 740,
            "ratings": [{"rating": 740}],
        }

    grouped = group_alert_triggers_by_company(
        [
            {"company_guid": "c-1", "alert_guid": "a-1", "enrichable": True},
            {"company_guid": "c-1", "alert_guid": "a-2", "enrichable": True},
            {"company_guid": "c-2", "alert_guid": "a-3", "enrichable": True},
        ],
        max_companies=2,
    )

    result = await enrich_company_groups(grouped, fetch_company)

    assert calls == ["c-1", "c-2"]
    assert result["groups"]["c-1"]["name"] == "Company c-1"
    assert result["groups"]["c-1"]["primary_domain"] == "c-1.example.com"
    assert result["groups"]["c-1"]["current_rating"] == 740
    assert result["groups"]["c-1"]["ratings"] == [{"rating": 740}]


@pytest.mark.asyncio
async def test_enrich_company_groups_preserves_triggers_and_reports_failure() -> None:
    async def fetch_company(guid: str) -> object:
        if guid == "c-1":
            raise RuntimeError("unavailable")
        return {"name": "Company 2"}

    grouped = group_alert_triggers_by_company(
        [
            {"company_guid": "c-1", "alert_guid": "a-1", "enrichable": True},
            {"company_guid": "c-1", "alert_guid": "a-2", "enrichable": True},
            {"company_guid": "c-1", "alert_guid": "a-3", "enrichable": True},
        ],
        max_companies=1,
    )

    result = await enrich_company_groups(grouped, fetch_company)
    failed = result["groups"]["c-1"]

    assert failed["enrichment_status"] == "failed"
    assert failed["enrichment_warnings"] == ["company_enrichment_failed"]
    assert result["metadata"]["warnings"] == ["company_enrichment_failed"]
    assert [trigger["alert_guid"] for trigger in failed["triggers"]] == [
        "a-1",
        "a-2",
        "a-3",
    ]
