---
id: 10
title: 'SA2-09: Map priority levels and filter returned candidates'
status: shape
priority: medium
created: 2026-07-10T11:49:00.687188+02:00
updated: 2026-07-10T11:49:00.687188+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:priority-gate
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 9
ac:
  - 'AC-1: Given candidates with priorities `3` and `4` and `max_returned_priority=3`,
    `filter_action_candidates` returns the priority `3` candidate and records the
    priority `4` candidate with reason `priority_filtered`.'
  - 'AC-2: Given a candidate with out-of-scope category `DNSSEC`, `filter_action_candidates`
    returns `eligible=False`, no action item, and reason `out_of_scope_category`.'
  - 'AC-3: Given category `web application security`, `filter_action_candidates` returns
    warning code `category_ambiguous` on the candidate metadata.'
  - 'AC-4: Given a priority-filtered candidate, `filter_action_candidates` records
    `company_guid`, `priority`, and `filter_reason` in `filtered_candidates`.'
  - 'AC-5: Given a candidate with priority equal to `max_returned_priority`, `filter_action_candidates`
    includes the candidate in returned action candidates.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Apply alert-driven action eligibility rules, preserve category ambiguity metadata, and filter returned new-ticket action candidates above the configured maximum priority.

## Local Architecture Anchors
- Scoring helpers from #9 supply component points and priority levels.
- New filtering helpers should live under `src/birre/domain/security_analyst/`.

## Dependencies
Depends on #9 for priority component scoring.

## Non-Goals
- Jira-action payload rendering.
- Existing-ticket update workflow.
- Direct Jira writes.
- Category clarification beyond the brief's stated ambiguity.

## Shape Notes
- Scope decision: filtering is separate from score calculation because it decides caller-visible inclusion and metadata for suppressed alert-driven candidates.
- Challenger result: proceed for keeping filtering separate from scoring.
- Verification focus: pure unit tests for priority threshold, out-of-scope suppression, ambiguity warning, and filtered metadata.
