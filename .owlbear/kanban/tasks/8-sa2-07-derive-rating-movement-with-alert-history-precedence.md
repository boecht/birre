---
id: 8
title: 'SA2-07: Derive rating movement with alert/history precedence'
status: shape
priority: medium
created: 2026-07-10T11:48:36.135600+02:00
updated: 2026-07-10T11:48:36.135600+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:rating-movement
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 7
ac:
  - "AC-1: Given an alert trigger with `rating_before=800` and `rating_after=700`,
    `derive_rating_movement` returns `drop=100` and `source='alert_rating'`."
  - "AC-2: Given alert-derived drop `50` and company-history drop `120`, `derive_rating_movement`
    returns `drop=120` and `source='company_history'`."
  - "AC-3: Given no alert-derived drop and company-history drop `80`, `derive_rating_movement`
    returns `drop=80` and `source='company_history'`."
  - 'AC-4: Given no alert-derived drop and no company-history drop, `derive_rating_movement`
    returns warning code `rating_movement_missing`.'
  - "AC-5: Given category movement `A` to `C` and category rating map `{'A': 900,
    'C': 600}`, `derive_rating_movement` returns `drop=50` and `source='alert_category'`."
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Derive per-alert rating movement from alert before/after rating or category fields, compare it with company rating-history movement, and select the movement evidence required by the brief.

## Local Architecture Anchors
- Rating history summarization patterns live in `src/birre/domain/company_rating/service.py`.
- New pure movement helpers should live under `src/birre/domain/security_analyst/`.

## Dependencies
Depends on #7 for enriched company records and rating history.

## Non-Goals
- v1 enrichment calls.
- Priority scoring.
- Jira-action payload construction.
- Direct Jira writes.

## Shape Notes
- Scope decision: rating movement is pure deterministic evidence selection and should not be coupled to API fanout.
- Challenger result: proceed for keeping movement separate from enrichment.
- Verification focus: pure unit tests covering alert-derived, history-derived, larger-history, and missing-data branches.
