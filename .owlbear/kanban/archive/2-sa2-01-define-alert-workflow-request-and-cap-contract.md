---
id: 2
title: 'SA2-01: Define alert workflow request and cap contract'
status: shape
priority: high
created: 2026-07-10T11:47:55.031140+02:00
updated: 2026-07-10T11:47:55.031140+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:config
  - type:build
  - reshaped-v2
parent: 1
depends_on: []
ac:
  - 'AC-1: Given omitted cap inputs, `build_alert_workflow_request` returns `page_size=50`,
    `max_pages=10`, `max_companies=100`, `max_returned_priority=4`, and `human_factor=1`.'
  - 'AC-2: Given caller overrides `page_size=25`, `max_pages=2`, `max_companies=5`,
    `max_returned_priority=3`, and `human_factor=0`, `build_alert_workflow_request`
    returns those five values in the request object.'
  - 'AC-3: Given `page_size=0`, `build_alert_workflow_request` raises `ValueError`
    with message text containing `page_size`.'
  - "AC-4: Given supplier criticality input `{'c-1': 2, 'c-2': 3}`, `build_alert_workflow_request`
    stores criticality entries keyed by BitSight company GUID and does not derive
    entries from company names."
  - 'AC-5: Given no supplier criticality entry for company GUID `c-3`, `resolve_supplier_criticality`
    returns `1`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Define the deterministic request and configuration contract for alert window, pagination caps, distinct-company cap, maximum returned priority, default human factor, and supplier criticality input.

## Local Architecture Anchors
- New workflow code should live under `src/birre/domain/security_analyst/`.
- Configuration precedent lives in `src/birre/config/settings.py` and CLI option helpers under `src/birre/cli/options/`.

## Dependencies
None.

## Non-Goals
- BitSight network calls.
- Server context registration.
- Jira adapter calls.
- Durable cursor state.

## Shape Notes
- Scope decision: keep pure request/config modeling separate from server context wiring.
- Challenger result: proceed after accepting the challenger request to preserve the split from context wiring.
- Verification focus: direct unit tests for request construction and supplier criticality fallback behavior.
