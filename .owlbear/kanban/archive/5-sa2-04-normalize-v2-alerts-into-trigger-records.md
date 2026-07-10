---
id: 5
title: 'SA2-04: Normalize v2 alerts into trigger records'
status: shape
priority: high
created: 2026-07-10T11:48:16.215002+02:00
updated: 2026-07-10T11:48:16.215002+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:normalization
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 4
ac:
  - 'AC-1: Given a v2 alert item with `guid`, `company_guid`, `alert_date`, `severity`,
    `trigger`, and `details`, `normalize_alert_trigger` returns those values plus
    `raw_alert`.'
  - 'AC-2: Given a v2 alert item without `company_guid`, `normalize_alert_trigger`
    returns warning code `company_guid_missing_anomaly` and `enrichable=False`.'
  - 'AC-3: Given a v2 alert item with `folder_guid` and `alert_set_guid`, `normalize_alert_trigger`
    returns those values in `folder_context`.'
  - 'AC-4: Given page metadata containing endpoint, query, page index, and offset,
    `normalize_alert_trigger` includes those values in `source_metadata`.'
  - 'AC-5: Given a v2 alert item with nested `details`, `normalize_alert_trigger`
    preserves the nested details object without field loss.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Convert raw v2 alert result items into loss-aware trigger records while preserving alert identity, company identity, dates, severity, trigger text, folder context, details, endpoint/query metadata, page metadata, and raw payloads.

## Local Architecture Anchors
- New workflow normalization should live under `src/birre/domain/security_analyst/`.
- Existing Pydantic model patterns are visible in `src/birre/domain/company_rating/service.py` and `src/birre/domain/risk_manager/service.py`.

## Dependencies
Depends on #4 for fetched page envelopes.

## Non-Goals
- Company grouping.
- Company enrichment.
- Priority scoring.
- Jira-action payload construction.

## Shape Notes
- Scope decision: normalization preserves evidence and records company GUID anomalies without deciding grouping or enrichment behavior.
- Challenger result: proceed for keeping normalization separate from grouping.
- Verification focus: pure unit tests using fixture v2 alert dictionaries.
