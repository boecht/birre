---
id: 11
title: 'SA2-10: Build structured Jira-action payload'
status: shape
priority: medium
created: 2026-07-10T11:49:08.691829+02:00
updated: 2026-07-10T11:49:08.691829+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:jira-action-payload
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 10
ac:
  - 'AC-1: Given a scored company candidate, `build_jira_action_payload` returns an
    action item with `company_guid`, `correlation_key` equal to company GUID, company
    identity fields, and current company rating.'
  - 'AC-2: Given trigger alert records, `build_jira_action_payload` includes alert
    GUID provenance, event date, seen-at date, severity, trigger, and raw evidence
    reference fields in the action item.'
  - 'AC-3: Given rating movement evidence, `build_jira_action_payload` includes rating
    before, rating after, calculated drop amount, movement source, and current rating
    in proposed Jira body fields.'
  - 'AC-4: Given priority and eligibility data, `build_jira_action_payload` includes
    priority score, priority level, eligibility, and filtered-candidate metadata.'
  - 'AC-5: Given warning and missing-data inputs, `build_jira_action_payload` includes
    warning codes and missing-data flags in the action item and run metadata.'
  - 'AC-6: Given internal grouped alert/company data, `build_jira_action_payload`
    returns top-level keys `action_items` and `metadata` and no top-level key named
    `internal_batch`.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Build the caller-facing structured Jira-action payload for company performance watch tickets, with company GUID as the correlation key and alert GUIDs/details retained as trigger provenance.

## Local Architecture Anchors
- New payload models/builders should live under `src/birre/domain/security_analyst/`.
- The brief defines the first visible product as structured Jira-action data, not the internal alert/company batch.

## Dependencies
Depends on #10 for filtered action candidates.

## Non-Goals
- Direct Jira lookup, create, append, transition, or closure.
- Durable correlation ledger.
- Management summary generation.
- Raw-batch-as-product caller output.

## Shape Notes
- Scope decision: payload construction is the first product boundary and must hide internal batch plumbing while preserving evidence needed by a later Jira adapter.
- Challenger result: proceed for keeping payload construction separate from runner/CLI exposure.
- Verification focus: pure unit tests for payload shape, evidence fields, warnings, and absence of internal-batch top-level data.
