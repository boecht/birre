---
id: 6
title: 'SA2-05: Group alert triggers by company GUID with company cap'
status: shape
priority: medium
created: 2026-07-10T11:48:22.313317+02:00
updated: 2026-07-10T11:48:22.313317+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:grouping
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 5
ac:
  - 'AC-1: Given enrichable triggers for company GUIDs `c-1`, `c-1`, and `c-2`, `group_alert_triggers_by_company`
    returns groups keyed by `c-1` and `c-2`.'
  - 'AC-2: Given two triggers for company GUID `c-1` with alert GUIDs `a-1` and `a-2`,
    the `c-1` group contains trigger references for `a-1` and `a-2`.'
  - 'AC-3: Given `max_companies=1` and enrichable triggers for `c-1` and `c-2`, `group_alert_triggers_by_company`
    returns one company group and warning code `company_cap_reached`.'
  - 'AC-4: Given a trigger with `enrichable=False`, `group_alert_triggers_by_company`
    excludes it from company groups and returns its warning code in group metadata.'
  - 'AC-5: Given an empty trigger list, `group_alert_triggers_by_company` returns
    an empty group mapping and an empty warning list.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Group enrichable trigger records by company GUID, preserve distinct alert triggers inside each company group, and apply the distinct-company cap with warning metadata.

## Local Architecture Anchors
- New workflow grouping should live under `src/birre/domain/security_analyst/`.
- The brief requires company GUID as the company-watch correlation key and alert GUID as provenance.

## Dependencies
Depends on #5 for normalized trigger records.

## Non-Goals
- v1 company enrichment.
- Rating movement derivation.
- Priority scoring.
- Jira-action payload construction.

## Shape Notes
- Scope decision: group by company GUID after normalization so missing-GUID anomaly behavior remains visible.
- Challenger result: proceed for keeping grouping separate from normalization.
- Verification focus: pure unit tests for grouping, cap truncation, and trigger preservation.
