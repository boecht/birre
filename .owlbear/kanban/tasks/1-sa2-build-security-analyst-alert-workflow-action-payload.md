---
id: 1
title: 'SA2: Build security analyst alert workflow action payload'
status: shape
priority: high
created: 2026-07-10T11:47:47.085533+02:00
updated: 2026-07-10T11:49:32.825003+02:00
tags:
  - ideation-handoff
  - security-analyst
  - alert-workflow
  - reshaped-v2
parent:
depends_on:
  - 13
ac:
  - 'AC-1: Shaper verifies by board inspection that parent #1 has child tasks #2,
    #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, and #13.'
  - 'AC-2: Shaper verifies by artifact inspection that child task bodies #2 through
    #13 cite `.owlbear/briefs/draft-birre-alert-workflows/brief.md` and contain `##
    Shape Notes`.'
  - 'AC-3: Shaper verifies by board inspection that consolidation task #13 depends
    on tasks #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, and #12.'
  - 'AC-4: Collector verifies parent completion by stage-transition audit after task
    #13 reaches `collect` or `archived` with proof for fixture-based API and CLI output.'
  - 'AC-5: Verifier verifies parent scope by artifact inspection that direct Jira
    writes, durable queue/cursor state, management summaries, closure automation,
    and normal MCP-tool-first exposure are absent from child task scopes.'
proof_bundle: critical
blocked: false
block_reason:
claimed_at:
archival_reason:
archival_refs: []
---
Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`

## Scope
Build the first deterministic BiRRe security-analyst workflow for alert-driven company performance watch preparation. The first caller-facing product is structured Jira-action data for company watch tickets, while v2 alert and v1 enrichment batches remain internal workflow data.

## Non-Goals
- Direct Jira writes.
- Durable internal alert queue or cursor state.
- Management-summary generation.
- Closure automation.
- Alert GUID or finding identity as the ticket subject.
- Normal MCP-tool-first exposure.

## Shape Notes
- Scope decision: restart shaping from the approved brief and supersede tasks #13 through #25 after the replacement set is created.
- Local anchors: `src/birre/application/server.py`, `src/birre/config/settings.py`, `src/birre/domain/company_rating/service.py`, `src/birre/integrations/bitsight/v1_bridge.py`, `src/birre/cli/app.py`, and `tests/cli/test_cli_app_commands.py`.
- Challenger result: reconsidered a compressed seven-child proposal. Accepted. The replacement keeps separate build slices for shared server context, v2 intake, normalization, grouping, enrichment, movement, scoring, filtering, payload construction, API/CLI exposure, and consolidation proof.
- Dependency note: each child owns one implementation risk boundary from the brief.



## Child Tasks
- #2 SA2-01 request and cap contract
- #3 SA2-02 security_analyst context and v2 alert bridge
- #4 SA2-03 v2 alert pagination
- #5 SA2-04 alert trigger normalization
- #6 SA2-05 company grouping
- #7 SA2-06 v1 company enrichment
- #8 SA2-07 rating movement precedence
- #9 SA2-08 priority scoring
- #10 SA2-09 priority gate and filtering
- #11 SA2-10 Jira-action payload
- #12 SA2-11 API runner and CLI output
- #13 SA2-12 consolidation proof

## Supersedes
Tasks #13 through #25 are superseded by this replacement shape and will be archived with archival reason `dropped`.
