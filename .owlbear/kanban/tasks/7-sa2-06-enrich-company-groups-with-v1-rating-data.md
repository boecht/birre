---
id: 7
title: 'SA2-06: Enrich company groups with v1 rating data'
status: shape
priority: medium
created: 2026-07-10T11:48:29.949447+02:00
updated: 2026-07-10T11:48:29.949447+02:00
tags:
  - security-analyst
  - alert-workflow
  - scope:enrichment
  - type:build
  - reshaped-v2
parent: 1
depends_on:
  - 6
ac:
  - 'AC-1: Given company groups for `c-1` and `c-2`, `enrich_company_groups` calls
    the injected company fetcher for `c-1` and `c-2` and returns enrichment entries
    keyed by company GUID.'
  - 'AC-2: Given repeated input for company GUID `c-1`, `enrich_company_groups` calls
    the injected company fetcher once for `c-1`.'
  - 'AC-3: Given a company fetcher response with `name`, `primary_domain`, `current_rating`,
    and `ratings`, `enrich_company_groups` stores those four fields in the enrichment
    entry.'
  - 'AC-4: Given the company fetcher raises for `c-1`, `enrich_company_groups` returns
    warning code `company_enrichment_failed` and preserves trigger references for
    `c-1`.'
  - 'AC-5: Given a company group with three trigger references, `enrich_company_groups`
    returns those three trigger references unchanged in the enriched company record.'
proof_bundle: behavioral
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Fetch v1 company profile data once per distinct company GUID and attach current rating, company identity fields, rating history, enrichment status, and enrichment warnings to grouped trigger data.

## Local Architecture Anchors
- Existing company rating retrieval lives in `src/birre/domain/company_rating/service.py`.
- v1 OpenAPI bridge helpers live in `src/birre/integrations/bitsight/v1_bridge.py`.
- Existing domain call type aliases live in `src/birre/domain/common.py`.

## Dependencies
Depends on #6 for grouped company trigger records.

## Non-Goals
- Rating movement precedence logic.
- Priority scoring.
- Jira-action payload construction.
- Direct Jira writes.

## Shape Notes
- Scope decision: v1 enrichment owns async fanout, dedupe, and failure warning behavior; movement calculation comes after enrichment data exists.
- Challenger result: proceed for keeping enrichment separate from rating movement derivation.
- Verification focus: async unit tests with stubbed company fetcher responses and failures.
