"""Company rating tools and helpers for BiRRe."""

from __future__ import annotations

import asyncio
import heapq
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import FunctionTool
from pydantic import BaseModel, Field, model_validator

from birre.config.settings import DEFAULT_MAX_FINDINGS, DEFAULT_RISK_VECTOR_FILTER
from birre.domain.common import CallV1Tool
from birre.domain.company_rating.constants import (
    DEFAULT_SEVERITY_FLOOR,
    SEVERITY_LOW,
    SEVERITY_MATERIAL,
    SEVERITY_MODERATE,
    SEVERITY_RANK_LOW,
    SEVERITY_RANK_MATERIAL,
    SEVERITY_RANK_MODERATE,
    SEVERITY_RANK_SEVERE,
    SEVERITY_RANK_UNKNOWN,
    SEVERITY_SCORE_UNKNOWN,
    SEVERITY_SEVERE,
    TIMESTAMP_INVALID,
)
from birre.domain.subscription import (
    SubscriptionAttempt,
    cleanup_ephemeral_subscription,
    create_ephemeral_subscription,
)
from birre.infrastructure.logging import BoundLogger, log_rating_event


class TrendSummary(BaseModel):
    direction: str
    change: float


class CurrentRating(BaseModel):
    value: float | None = None
    color: str | None = None


class FindingSummary(BaseModel):
    top: int
    finding: str | None = None
    details: str | None = None
    asset: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None


class TopFindingsPolicy(BaseModel):
    severity_floor: str
    supplements: list[str]
    max_items: int
    profile: str


class TopFindings(BaseModel):
    policy: TopFindingsPolicy
    findings: list[FindingSummary] = Field(default_factory=list)
    count: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _default_count(cls, values: Any) -> dict[str, Any]:
        if not isinstance(values, dict):
            return {"policy": values, "findings": [], "count": 0}
        findings = values.get("findings") or []
        values_dict: dict[str, Any] = dict(values)
        values_dict.setdefault("findings", findings)
        values_dict.setdefault("count", len(findings))
        return values_dict


class RatingLegendEntry(BaseModel):
    color: str
    min: int
    max: int


class RatingLegend(BaseModel):
    rating: list[RatingLegendEntry]


class CompanyRatingResponse(BaseModel):
    error: str | None = None
    warning: str | None = None
    name: str | None = None
    domain: str | None = None
    current_rating: CurrentRating | None = None
    trend_8_weeks: TrendSummary | None = None
    trend_1_year: TrendSummary | None = None
    top_findings: TopFindings | None = None
    legend: RatingLegend | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.error:
            return {"error": self.error}
        data = self.model_dump(exclude_unset=True)
        data.pop("error", None)
        return data


COMPANY_RATING_OUTPUT_SCHEMA: dict[str, Any] = CompanyRatingResponse.model_json_schema()


def _rating_color(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 740:
        return "green"
    if value >= 630:
        return "yellow"
    return "red"


def _aggregate_ratings(
    raw_ratings: list[dict[str, Any]],
    *,
    horizon_days: int,
    mode: str,
) -> list[tuple[datetime, float]]:
    cutoff = datetime.now(UTC).date() - timedelta(days=horizon_days)
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    anchors: dict[tuple[int, int], datetime] = {}

    for entry in raw_ratings:
        if not isinstance(entry, dict):
            continue
        date_str = entry.get("rating_date")
        rating_value = entry.get("rating")
        if not date_str or rating_value is None:
            continue
        try:
            rating_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()
        except ValueError:
            continue
        if rating_date < cutoff:
            continue

        if mode == "weekly":
            iso = rating_date.isocalendar()
            key = (iso.year, iso.week)
            anchor = datetime.fromisocalendar(iso.year, iso.week, 1)
        elif mode == "monthly":
            key = (rating_date.year, rating_date.month)
            anchor = datetime(rating_date.year, rating_date.month, 1)
        else:
            key = (rating_date.year, rating_date.timetuple().tm_yday)
            anchor = datetime.combine(rating_date, datetime.min.time())

        buckets[key].append(float(rating_value))
        anchors[key] = anchor

    series: list[tuple[datetime, float]] = []
    for key, values in buckets.items():
        anchor = anchors[key]
        avg_rating = sum(values) / len(values)
        series.append((anchor, avg_rating))

    series.sort(key=lambda item: item[0])
    return series


def _compute_trend(series: list[tuple[datetime, float]]) -> dict[str, object]:
    if len(series) < 2:
        return {
            "direction": "insufficient data",
            "change": 0.0,
        }

    xs = [point[0].toordinal() for point in series]
    ys = [point[1] for point in series]
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        slope = 0.0
    else:
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom

    smoothed_delta = slope * (xs[-1] - xs[0])

    def classify(delta: float) -> str:
        if delta >= 40:
            return "up"
        if delta >= 20:
            return "slightly up"
        if delta <= -40:
            return "down"
        if delta <= -20:
            return "slightly down"
        return "stable"

    label = classify(smoothed_delta)
    return {
        "direction": label,
        "change": round(smoothed_delta, 1),
    }


def _rank_severity_category_value(val: Any) -> int:
    if isinstance(val, str):
        v = val.lower()
        if v == SEVERITY_SEVERE:
            return SEVERITY_RANK_SEVERE
        if v == SEVERITY_MATERIAL:
            return SEVERITY_RANK_MATERIAL
        if v == SEVERITY_MODERATE:
            return SEVERITY_RANK_MODERATE
        if v == SEVERITY_LOW:
            return SEVERITY_RANK_LOW
    return SEVERITY_RANK_UNKNOWN


def _derive_numeric_severity_score(item: Any) -> float:
    def _extract_numeric(value: Any) -> float | None:
        return float(value) if isinstance(value, int | float) else None

    if not isinstance(item, dict):
        return SEVERITY_SCORE_UNKNOWN

    direct = _extract_numeric(item.get("severity"))
    if direct is not None:
        return direct

    details = item.get("details")
    if not isinstance(details, dict):
        return SEVERITY_SCORE_UNKNOWN

    for key in ("severity", "grade"):
        candidate = _extract_numeric(details.get(key))
        if candidate is not None:
            return candidate

    cvss = details.get("cvss")
    if isinstance(cvss, dict):
        base_score = _extract_numeric(cvss.get("base"))
        if base_score is not None:
            return base_score

    return SEVERITY_SCORE_UNKNOWN


def _parse_timestamp_seconds(val: Any) -> int:
    if isinstance(val, str) and val:
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return int(datetime.strptime(val, fmt).timestamp())
            except Exception:
                continue
    return TIMESTAMP_INVALID


def _derive_asset_importance_score(obj: Any) -> float:
    if isinstance(obj, dict):
        assets = obj.get("assets") if isinstance(obj.get("assets"), dict) else {}
        if isinstance(assets, dict):
            for key in ("combined_importance", "importance"):
                val = assets.get(key)
                if isinstance(val, int | float):
                    return float(val)
    return 0.0


def _build_finding_sort_key(item: Any) -> tuple[float, int, float, float, str]:
    sev_num = _derive_numeric_severity_score(item)
    sev_cat = _rank_severity_category_value(
        item.get("severity") if isinstance(item, dict) else None
    )
    imp = _derive_asset_importance_score(item)
    last = _parse_timestamp_seconds(
        item.get("last_seen") if isinstance(item, dict) else None
    )
    rv = (item.get("risk_vector") or "") if isinstance(item, dict) else ""
    # Desc numeric severity, then desc categorical rank, desc importance,
    # desc last_seen; asc risk_vector
    return (-sev_num, -sev_cat, -imp, -last, rv)


def _build_finding_score_tuple(item: Any) -> tuple[float, int, float, float]:
    # Positive score tuple for heapq.nlargest (descending desired)
    sev_num = _derive_numeric_severity_score(item)
    sev_cat = _rank_severity_category_value(
        item.get("severity") if isinstance(item, dict) else None
    )
    imp = _derive_asset_importance_score(item)
    last = _parse_timestamp_seconds(
        item.get("last_seen") if isinstance(item, dict) else None
    )
    return (sev_num, sev_cat, imp, last)


def _select_top_finding_candidates(
    results: list[dict[str, Any]], k: int
) -> list[dict[str, Any]]:
    if not results:
        return []
    # Keep only the top-k by primary numeric keys; finalize ordering with full _sort_key
    candidates = heapq.nlargest(k, results, key=_build_finding_score_tuple)
    candidates.sort(key=_build_finding_sort_key)
    return candidates


# ---- Finding normalization helpers ----

# Infection vectors whose narrative should take precedence when available
INFECTION_RISK_VECTORS = {
    "botnet_infections",
    "spam_propagation",
    "malware_servers",
    "unsolicited_comm",
    "potentially_exploited",
}


def _determine_finding_label(
    item: dict[str, Any], details: dict[str, Any]
) -> str | None:
    """Choose a finding label from details.name/display_name or risk_vector_label."""
    if isinstance(details.get("name"), str):
        return details.get("name")
    if isinstance(details.get("display_name"), str):
        return details.get("display_name")
    rv_label = item.get("risk_vector_label")
    return rv_label if isinstance(rv_label, str) else None


def _compose_base_details_text(details: dict[str, Any]) -> str | None:
    """
    Build the base details text from display_name/description/
    searchable_details/infection.family.
    """
    display_name: str | None = (
        details.get("display_name")
        if isinstance(details.get("display_name"), str)
        else None
    )
    long_desc: str | None = (
        details.get("description")
        if isinstance(details.get("description"), str)
        else None
    )
    if display_name and long_desc:
        return f"{display_name} — {long_desc}"
    if long_desc:
        return long_desc
    if display_name:
        return display_name
    searchable_details = details.get("searchable_details")
    if isinstance(searchable_details, str):
        return searchable_details
    inf = details.get("infection")
    if isinstance(inf, dict) and isinstance(inf.get("family"), str):
        return f"Infection: {inf['family']}"
    return None


def _find_first_remediation_text(details: dict[str, Any]) -> str | None:
    """Return the first available remediation hint text if present."""
    rem_list = (
        details.get("remediations")
        if isinstance(details.get("remediations"), list)
        else []
    )
    for rem in rem_list or []:
        if isinstance(rem, dict):
            text = (
                rem.get("help_text") or rem.get("remediation_tip") or rem.get("message")
            )
            if isinstance(text, str) and text:
                return text
    return None


def _normalize_detected_service_summary(text: str, remediation_hint: str | None) -> str:
    """Rewrite 'Detected service: ...' text to include a concise remediation hint when available."""
    if not remediation_hint:
        return text
    try:
        after = text.split(":", 1)[1].strip()
        service = after.split(",", 1)[0].strip()
        return f"Detected service: {service} — {remediation_hint}"
    except Exception:
        return f"{text} — {remediation_hint}" if remediation_hint not in text else text


def _append_remediation_hint(
    text: str | None, remediation_hint: str | None
) -> str | None:
    """Append remediation hint to text, preserving punctuation and avoiding duplication."""
    if not remediation_hint:
        return text
    if isinstance(text, str):
        if remediation_hint in text:
            return text
        if text.endswith((".", "!", "?")):
            return f"{text} {remediation_hint}"
        return f"{text}. {remediation_hint}"
    return remediation_hint


def _apply_infection_narrative_preference(
    text: str | None, risk_vector: Any, details: dict[str, Any]
) -> str | None:
    """Prefer infection narrative for infection vectors when description/family are present."""
    if not isinstance(risk_vector, str) or risk_vector not in INFECTION_RISK_VECTORS:
        return text
    inf = details.get("infection")
    if not isinstance(inf, dict):
        return text
    family = inf.get("family") if isinstance(inf.get("family"), str) else None
    desc_val = inf.get("description")
    inf_desc = desc_val.strip() if isinstance(desc_val, str) else None
    if family and inf_desc:
        return f"Infection: {family} — {inf_desc}"
    if inf_desc:
        if text and inf_desc not in (text or ""):
            return f"{text} — {inf_desc}"
        return inf_desc or text
    return text


def _determine_primary_port(details: dict[str, Any]) -> int | None:
    """Return a port from details.dest_port or the first of details.port_list."""
    dest_port = details.get("dest_port")
    if isinstance(dest_port, int):
        return dest_port
    ports = details.get("port_list")
    if isinstance(ports, list) and ports:
        p0 = ports[0]
        if isinstance(p0, int):
            return p0
    return None


def _determine_primary_asset(
    item: dict[str, Any], details: dict[str, Any]
) -> str | None:
    """Choose an asset from evidence_key, then details.assets[0] (+port), then observed_ips[0]."""
    asset: str | None = (
        item.get("evidence_key") if isinstance(item.get("evidence_key"), str) else None
    )
    if asset:
        return asset
    assets = details.get("assets")
    if isinstance(assets, list) and assets:
        first = assets[0]
        if isinstance(first, dict) and isinstance(first.get("asset"), str):
            port = _determine_primary_port(details)
            return f"{first['asset']}:{port}" if port else first["asset"]
    observed = details.get("observed_ips")
    if isinstance(observed, list) and observed:
        ip0 = observed[0]
        if isinstance(ip0, str):
            return ip0
    return None


def _normalize_finding_entry(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one API finding item into the compact summary shape used in outputs."""
    raw_details = item.get("details")
    details_obj: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    finding_label = _determine_finding_label(item, details_obj)
    text = _compose_base_details_text(details_obj)
    remediation = _find_first_remediation_text(details_obj)
    if isinstance(text, str) and text.startswith("Detected service:") and remediation:
        text = _normalize_detected_service_summary(text, remediation)
    else:
        text = _append_remediation_hint(text, remediation)
    text = _apply_infection_narrative_preference(
        text, item.get("risk_vector"), details_obj
    )
    asset = _determine_primary_asset(item, details_obj)
    first_seen_raw = item.get("first_seen")
    # BitSight's Finding schema (apis/v1/components/schemas.json) does not require
    # first_seen/last_seen, so the fields may be absent entirely in the payload.
    # When the source omits them we surface ``null`` in our normalized output to
    # preserve the key without claiming a timestamp we do not have.
    first_seen = first_seen_raw if isinstance(first_seen_raw, str) else None
    last_seen_raw = item.get("last_seen")
    last_seen = last_seen_raw if isinstance(last_seen_raw, str) else None
    return {
        "finding": finding_label,
        "details": text,
        "asset": asset,
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def _normalize_top_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        items.append(_normalize_finding_entry(item))
    return items


def _default_top_findings_payload(limit: int) -> dict[str, Any]:
    return {
        "policy": {
            "severity_floor": "material",
            "supplements": [],
            "max_items": limit,
            "profile": "strict",
        },
        "count": 0,
        "findings": [],
    }


def _emit_sorted_preview(
    ctx: Context, items: list[Any], label: str, *, debug_enabled: bool
) -> None:
    try:
        preview_items = heapq.nlargest(15, items, key=_build_finding_score_tuple)
        preview_items.sort(key=_build_finding_sort_key)
        preview = []
        for i, it in enumerate(preview_items[:15], start=1):
            preview.append(
                {
                    "idx": i,
                    "sev_num": _derive_numeric_severity_score(it),
                    "sev_cat": it.get("severity") if isinstance(it, dict) else None,
                    "importance": _derive_asset_importance_score(it),
                    "last_seen": it.get("last_seen") if isinstance(it, dict) else None,
                    "risk_vector": it.get("risk_vector")
                    if isinstance(it, dict)
                    else None,
                }
            )
        _debug(
            ctx,
            f"Sort preview ({label})",
            preview,
            debug_enabled=debug_enabled,
        )
    except Exception:
        pass


def _extract_results_from_payload(
    payload: dict[str, Any],
    ctx: Context,
    label: str,
    *,
    debug_enabled: bool,
) -> list[Any]:
    results = payload.get("results") or []
    if not isinstance(results, list):
        return []
    _emit_sorted_preview(ctx, results, label, debug_enabled=debug_enabled)
    return results


async def _fetch_and_normalize_findings(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    params: dict[str, Any],
    limit: int,
    label: str,
    *,
    debug_enabled: bool,
) -> tuple[list[dict[str, Any]], bool]:
    result = call_v1_tool("getCompaniesFindings", ctx, params)
    raw = await result if hasattr(result, "__await") else result
    if not isinstance(raw, dict):
        return [], False
    _debug(
        ctx,
        f"getCompaniesFindings raw response ({label})",
        raw,
        debug_enabled=debug_enabled,
    )
    results = _extract_results_from_payload(
        raw, ctx, label, debug_enabled=debug_enabled
    )
    top_raw = _select_top_finding_candidates(results, limit)
    findings = _normalize_top_findings(top_raw)
    return findings, True


@dataclass
class _TopFindingsSelection:
    findings: list[dict[str, Any]]
    severity_floor: str = "material"
    profile: str = "strict"
    supplements: list[str] = field(default_factory=list)
    max_items: int = 0

    def policy(self) -> dict[str, Any]:
        return {
            "severity_floor": self.severity_floor,
            "supplements": self.supplements,
            "max_items": self.max_items,
            "profile": self.profile,
        }


def _normalize_top_finding_limit(max_findings: int) -> int:
    if isinstance(max_findings, int) and max_findings > 0:
        return max_findings
    return DEFAULT_MAX_FINDINGS


async def _request_top_findings(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    params: dict[str, Any],
    limit: int,
    label: str,
    *,
    debug_enabled: bool,
) -> list[dict[str, Any]] | None:
    findings, ok = await _fetch_and_normalize_findings(
        call_v1_tool,
        ctx,
        params,
        limit,
        label,
        debug_enabled=debug_enabled,
    )
    if not ok:
        return None
    return findings[:limit]


async def _build_top_findings_selection(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    base_params: dict[str, Any],
    limit: int,
    *,
    debug_enabled: bool,
) -> _TopFindingsSelection | None:
    strict_findings = await _request_top_findings(
        call_v1_tool,
        ctx,
        base_params,
        limit,
        "strict",
        debug_enabled=debug_enabled,
    )
    if strict_findings is None:
        return None

    selection = _TopFindingsSelection(
        findings=list(strict_findings),
        max_items=limit,
    )
    if len(selection.findings) >= 3:
        return selection

    selection.profile = "relaxed"
    selection.severity_floor = DEFAULT_SEVERITY_FLOOR
    relaxed_params = dict(base_params)
    relaxed_params["severity_category"] = "severe,material,moderate"
    relaxed_findings = await _request_top_findings(
        call_v1_tool,
        ctx,
        relaxed_params,
        limit,
        "relaxed",
        debug_enabled=debug_enabled,
    )
    if relaxed_findings:
        selection.findings = list(relaxed_findings)
    if len(selection.findings) >= 3:
        return selection

    web_params = dict(relaxed_params)
    web_params["risk_vector"] = "web_appsec"
    web_findings = await _request_top_findings(
        call_v1_tool,
        ctx,
        web_params,
        limit,
        "web_appsec",
        debug_enabled=debug_enabled,
    )
    if web_findings:
        needed = max(0, limit - len(selection.findings))
        if needed > 0:
            selection.findings.extend(web_findings[:needed])

    selection.profile = "relaxed+web_appsec"
    selection.supplements = ["web_appsec"]

    return selection


async def _assemble_top_findings_section(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guid: str,
    risk_vector_filter: str,
    max_findings: int,
    *,
    debug_enabled: bool,
) -> dict[str, Any]:
    limit = _normalize_top_finding_limit(max_findings)
    params = {
        "guid": guid,
        "affects_rating": True,
        "risk_vector": risk_vector_filter,
        "severity_category": "severe,material",
        # Intentionally omit server-side sort/limit; sort & cap locally
        # Request only used fields to reduce payload size while preserving help_text
        "fields": (
            "severity,details,evidence_key,assets,risk_vector,"
            "risk_vector_label,first_seen,last_seen"
        ),
    }

    selection = await _build_top_findings_selection(
        call_v1_tool,
        ctx,
        params,
        limit,
        debug_enabled=debug_enabled,
    )
    if selection is None:
        return _default_top_findings_payload(limit)

    for idx, entry in enumerate(selection.findings, start=1):
        if isinstance(entry, dict):
            entry["top"] = idx

    _debug(
        ctx,
        "Normalized top findings",
        selection.findings,
        debug_enabled=debug_enabled,
    )

    return {
        "policy": selection.policy(),
        "count": len(selection.findings),
        "findings": selection.findings,
    }


def _debug(ctx: Context, message: str, obj: Any, *, debug_enabled: bool) -> None:
    """Emit a structured debug log if DEBUG env var is enabled."""
    try:
        if not debug_enabled:
            return None

        try:
            pretty = json.dumps(obj, indent=2, ensure_ascii=False)
        except Exception:
            pretty = str(obj)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None

        loop.create_task(ctx.info(f"{message}: {pretty}"))
    except Exception:
        return None

    return None


def _top_findings_unavailable_payload() -> TopFindings:
    return TopFindings.model_validate(
        {
            "policy": {
                "severity_floor": "material",
                "supplements": [],
                "max_items": 0,
                "profile": "unavailable",
            },
            "count": 0,
            "findings": [],
        }
    )


async def _retrieve_top_findings_payload(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guid: str,
    effective_filter: str,
    effective_findings: int,
    *,
    debug_enabled: bool,
) -> TopFindings:
    try:
        payload = await _assemble_top_findings_section(
            call_v1_tool,
            ctx,
            guid,
            effective_filter,
            effective_findings,
            debug_enabled=debug_enabled,
        )
        return TopFindings.model_validate(payload)
    except Exception as exc:  # pragma: no cover - defensive log
        await ctx.warning(f"Failed to fetch top findings: {exc}")
        return _top_findings_unavailable_payload()


async def _fetch_company_profile_dict(
    call_v1_tool: CallV1Tool, ctx: Context, guid: str
) -> dict[str, Any]:
    """Fetch and validate the company profile object from BitSight v1."""
    company = await call_v1_tool("getCompany", ctx, {"guid": guid})
    if not isinstance(company, dict):
        raise ValueError("Unexpected response format from BitSight company endpoint")
    return company


def _summarize_current_rating(company: dict[str, Any]) -> tuple[Any, Any]:
    """Return (value, color) tuple for the company's current rating."""
    value = company.get("current_rating")
    return value, _rating_color(value)


def _calculate_rating_trend_summaries(
    company: dict[str, Any],
) -> tuple[TrendSummary, TrendSummary]:
    """Calculate 8-week and 1-year rating trends from the ratings series."""
    raw_ratings = company.get("ratings", [])
    weekly_series = _aggregate_ratings(raw_ratings, horizon_days=56, mode="weekly")
    yearly_series = _aggregate_ratings(raw_ratings, horizon_days=365, mode="monthly")
    weekly = TrendSummary.model_validate(_compute_trend(weekly_series))
    yearly = TrendSummary.model_validate(_compute_trend(yearly_series))
    return weekly, yearly


def _build_rating_legend_entries() -> list[RatingLegendEntry]:
    return [
        RatingLegendEntry(color="red", min=250, max=629),
        RatingLegendEntry(color="yellow", min=630, max=739),
        RatingLegendEntry(color="green", min=740, max=900),
    ]


def _extract_policy_profile(top_findings_payload: Any) -> str | None:
    if isinstance(top_findings_payload, TopFindings):
        return top_findings_payload.policy.profile
    if isinstance(top_findings_payload, dict):
        policy = top_findings_payload.get("policy")
        if isinstance(policy, dict):
            profile = policy.get("profile")
            if isinstance(profile, str):
                return profile
    return None


async def _build_rating_payload(
    call_v1_tool: CallV1Tool,
    ctx: Context,
    guid: str,
    effective_filter: str,
    effective_findings: int,
    logger: BoundLogger,
    *,
    debug_enabled: bool,
) -> CompanyRatingResponse:
    log_rating_event(logger, "fetch_start", ctx=ctx, company_guid=guid)

    company = await _fetch_company_profile_dict(call_v1_tool, ctx, guid)
    current_value, color = _summarize_current_rating(company)
    weekly_trend, yearly_trend = _calculate_rating_trend_summaries(company)
    top_findings = await _retrieve_top_findings_payload(
        call_v1_tool,
        ctx,
        guid,
        effective_filter,
        effective_findings,
        debug_enabled=debug_enabled,
    )

    primary_domain = company.get("primary_domain") or company.get("display_url") or ""
    response = CompanyRatingResponse(
        name=company.get("name", ""),
        domain=primary_domain,
        current_rating=CurrentRating(value=current_value, color=color),
        trend_8_weeks=weekly_trend,
        trend_1_year=yearly_trend,
        top_findings=top_findings,
        legend=RatingLegend(rating=_build_rating_legend_entries()),
    )

    log_rating_event(
        logger,
        "fetch_success",
        ctx=ctx,
        company_guid=guid,
        findings_count=top_findings.count,
        policy=_extract_policy_profile(top_findings),
    )
    return response


def register_company_rating_tool(
    business_server: FastMCP,
    call_v1_tool: CallV1Tool,
    *,
    logger: BoundLogger,
    risk_vector_filter: str | None = None,
    max_findings: int | None = None,
    default_folder: str | None = None,
    default_type: str | None = None,
    debug_enabled: bool = False,
) -> FunctionTool:
    effective_filter = (
        risk_vector_filter.strip()
        if isinstance(risk_vector_filter, str) and risk_vector_filter.strip()
        else DEFAULT_RISK_VECTOR_FILTER
    )
    effective_findings = (
        max_findings
        if isinstance(max_findings, int) and max_findings > 0
        else DEFAULT_MAX_FINDINGS
    )

    @business_server.tool(output_schema=COMPANY_RATING_OUTPUT_SCHEMA)
    async def get_company_rating(ctx: Context, guid: str) -> dict[str, Any]:
        """Fetch normalized BitSight rating analytics for a company.

        Parameters
        - guid: BitSight company GUID from `company_search`.

        Behavior
        - Ensures subscription: creates an ephemeral subscription if needed; if already subscribed,
        it does not unsubscribe. Ephemeral subs are cleaned up after data retrieval.

        Returns
        - {
            "name": str,
            "domain": str,
            "current_rating": {"value": float|int, "color": "red|yellow|green"},
            "trend_8_weeks": {"direction": str, "change": float},
            "trend_1_year": {"direction": str, "change": float},
            "top_findings": {
            "policy": {
                "severity_floor": "material" | "moderate",
                # minimum severity included (always includes 'severe')
                "supplements": ["web_appsec"] | [],
                # vectors appended after fallback (kept at the end)
                "max_items": 5 | 10,                          # cap used for this response
                "profile": "strict" | "relaxed" | "relaxed+web_appsec"  # human-readable summary
            },
            "count": int,
            "findings": [
                {
                    "top": int, "finding": str, "details": str,
                    "asset": str, "first_seen": str, "last_seen": str
                }
            ]
            },
            "legend": {"rating": [{"color": str, "min": int, "max": int}, ...]}
        }

        Output semantics
        - current_rating.value: Numeric BitSight rating on a 250–900 scale
        (higher is better). May be null if unavailable.
        - current_rating.color: Traffic-light bucket derived from value:
        red (250–629), yellow (630–739), green (740–900).
        - trend_8_weeks / trend_1_year: {direction, change}
        - direction ∈ {up, slightly up, stable, slightly down, down} or "insufficient data"
        - change is the approximate rating delta over the window (float)
        - if insufficient data points (<2), direction is "insufficient data" and change is 0.0
        - top_findings: The top findings impacting the rating (compact summary per finding).
        - policy:
            - severity_floor: "material" (includes severe+material) or
            "moderate" (includes severe+material+moderate).
            - supplements: ["web_appsec"] when fallback was needed;
            otherwise []. Appended items come last.
            - max_items: Configured `max_findings` (default 10). When
            web-appsec padding is applied, the list remains capped at
            this value.
            - profile: quick summary: "strict" | "relaxed" | "relaxed+web_appsec".
        - Behavior: Start strict (severe,material). If <3 items, relax to
            include 'moderate'. If still <3,
            append from Web Application Security until the configured limit
            is reached (appended findings remain last).
        - legend.rating: Explicit color thresholds used to compute current_rating.color.

        Error contract
        - On failure returns {"error": str} (e.g., subscription could not be ensured or API error).

        Example (GitHub, Inc.)
        >>> get_company_rating(guid="e90b389b-0b7e-4722-9411-97d81c8e2bc6")
        {
        "name": "GitHub, Inc.",
        "domain": "github.com",
        "current_rating": {"value": 740, "color": "green"},
        "trend_8_weeks": {"direction": "up", "change": 52.0},
        "trend_1_year": {"direction": "stable", "change": 14.3},
        "top_findings": {"count": 3, "findings": [
            {
                "top": 1, "finding": "Open Ports",
                "details": "Detected service: …", "asset": "…",
                "first_seen": "…", "last_seen": "…"
            },
            {
                "top": 2, "finding": "Patching Cadence",
                "details": "CVE-… — …", "asset": "…",
                "first_seen": "…", "last_seen": "…"
            }
        ]},
        "legend": {"rating": [
            {"color": "red", "min": 250, "max": 629},
            {"color": "yellow", "min": 630, "max": 739},
            {"color": "green", "min": 740, "max": 900}
        ]}
        }
        """
        await ctx.info(f"Getting rating analytics for company: {guid}")

        # 1) Ensure access via subscription
        attempt: SubscriptionAttempt = await create_ephemeral_subscription(
            call_v1_tool,
            ctx,
            guid,
            logger=logger,
            default_folder=default_folder,
            subscription_type=default_type,
            debug_enabled=debug_enabled,
        )
        if not attempt.success:
            msg = attempt.message or (
                "Unable to access company rating; subscription required and could not be created"
            )
            await ctx.error(msg)
            return {"error": msg}
        auto_subscribed = attempt.created

        result_model: CompanyRatingResponse
        try:
            result_model = await _build_rating_payload(
                call_v1_tool,
                ctx,
                guid,
                effective_filter,
                effective_findings,
                logger,
                debug_enabled=debug_enabled,
            )
        except Exception as exc:  # pragma: no cover - defensive log
            error_message = f"Failed to build rating payload: {exc}"
            await ctx.error(error_message)
            log_rating_event(
                logger,
                "fetch_failure",
                ctx=ctx,
                company_guid=guid,
                error=str(exc),
            )
            result_model = CompanyRatingResponse(error=error_message)
        finally:
            if auto_subscribed:
                await cleanup_ephemeral_subscription(
                    call_v1_tool,
                    ctx,
                    guid,
                    debug_enabled=debug_enabled,
                )

        return result_model.to_payload()

    return get_company_rating


__all__ = ["register_company_rating_tool"]
