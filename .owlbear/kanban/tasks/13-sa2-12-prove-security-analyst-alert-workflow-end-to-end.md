---
id: 13
title: 'SA2-12: Prove security analyst alert workflow end to end'
status: shape
priority: medium
created: 2026-07-10T11:49:21.574175+02:00
updated: 2026-07-10T11:49:21.574175+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:consolidation
  - type:test
  - reshaped-v2
parent: 1
depends_on:
  - 2
  - 3
  - 4
  - 5
  - 6
  - 7
  - 8
  - 9
  - 10
  - 11
  - 12
ac:
  - 'AC-1: Given fixture v2 alerts for two companies and fixture v1 company enrichment
    responses, the consolidation test observes `run_alert_workflow_action_payload`
    returning action items keyed by company GUID.'
  - 'AC-2: Given fixture pages that exceed the page cap and company cap, the consolidation
    test observes warning codes `alert_page_cap_reached` and `company_cap_reached`.'
  - 'AC-3: Given fixtures covering alert-derived movement, larger history movement,
    history fallback, missing movement, out-of-scope category, web-application-security
    ambiguity, and priority filtering, the consolidation test observes the expected
    movement source, eligibility, priority, and warning codes.'
  - 'AC-4: Given the CLI command with stubbed workflow dependencies, the consolidation
    test observes stdout JSON containing structured Jira-action fields and no top-level
    internal alert/company batch field.'
  - 'AC-5: Given the consolidation test executes, no Jira client is called and no
    durable queue/cursor artifact is written.'
proof_bundle: critical
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Add an integrated fixture proof that the shaped workflow produces deterministic structured Jira-action output from stubbed v2 alert pages and v1 company enrichment/rating-history responses through the API runner and CLI surface.

## Local Architecture Anchors
- Unit and CLI test precedent lives under `tests/unit/` and `tests/cli/`.
- The API runner from #12 and payload builder from #11 are the integration targets.

## Dependencies
Depends on #2 through #12.

## Non-Goals
- Live BitSight online test requirement.
- Direct Jira write tests.
- Durable queue/cursor tests.
- Management summary tests.

## Shape Notes
- Scope decision: keep a consolidation proof because the brief crosses multiple deterministic stages and the first useful output is an aggregate payload.
- Challenger result: accepted with caveat; consolidation is useful here because it proves the parent product promise, but it must stay fixture-based and avoid creating a second implementation path.
- Verification focus: one focused end-to-end fixture path plus CLI output assertion.
