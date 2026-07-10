---
id: 9
title: 'SA2-08: Compute alert workflow priority score components'
status: shape
priority: medium
created: 2026-07-10T11:48:53.927750+02:00
updated: 2026-07-10T11:48:53.927750+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:priority-scoring
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 8
ac:
  - 'AC-1: Given supplier criticality values `1`, `2`, `3`, and missing, `score_supplier_criticality`
    returns points `0`, `1`, `3`, and `1`.'
  - 'AC-2: Given event categories `public disclosure` and `security incident`, `score_event_category`
    returns `-1` for each category.'
  - 'AC-3: Given event categories `botnet infection`, `malware`, and `potentially
    exploited`, `score_event_category` returns `0` for each category.'
  - 'AC-4: Given event categories `open ports`, `patching cadence`, `server software`,
    and `insecure systems`, `score_event_category` returns `1` for each category.'
  - 'AC-5: Given event categories `TLS certificates`, `TLS configuration`, `spam propagation`,
    `mobile app security`, `desktop software`, `mobile software`, `exposed credentials`,
    `web application headers`, and `web application security`, `score_event_category`
    returns `3` for each category.'
  - 'AC-6: Given event categories `DNSSEC`, `DMARC`, `DKIM`, `SPF`, `domain squatting`,
    `unsolicited communication`, and `file sharing`, `score_event_category` returns
    `out_of_scope=True` for each category.'
  - 'AC-7: Given rating drops `151`, `101`, `41`, and `40`, `score_rating_change`
    returns points `-1`, `0`, `1`, and `3`.'
  - 'AC-8: Given total point values `1`, `2`, `3`, `4`, `5`, and `6`, `compute_priority_level`
    returns priorities `0`, `1`, `2`, `3`, `3`, and `4`.'
  - 'AC-9: Given omitted human factor, `score_human_factor` returns `1`; given `many_events`,
    `normal`, and `low_relevance`, it returns `0`, `1`, and `3`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Implement the initial priority point system for supplier criticality, event category, rating change, human factor, and total-to-priority mapping.

## Local Architecture Anchors
- New pure scoring helpers should live under `src/birre/domain/security_analyst/`.
- Request-level supplier criticality input is defined by #2.
- Rating movement evidence is produced by #8.

## Dependencies
Depends on #8 for rating movement evidence.

## Non-Goals
- Returned-candidate filtering.
- Jira-action payload construction.
- Direct Jira writes.
- Supplier criticality list ingestion from an external system.

## Shape Notes
- Scope decision: keep point calculations pure and exhaustive before filtering consumes the result.
- Challenger result: proceed for keeping scoring separate from filtering.
- Verification focus: pure unit tests for each point function and priority mapping.
