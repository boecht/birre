# Planning Summary

## Parent Task

- Parent task: #1 — Build security analyst alert workflow action payload
- Approved Brief: `.owlbear/briefs/draft-birre-alert-workflows/brief.md`
- Status after handoff: parent task created in backlog and depends on consolidation task #12.

## Child Tasks Created

| ID | Title | Coverage |
|---:|---|---|
| #2 | P1-01: Define alert workflow request and cap configuration contract | alert window, configurable caps, default target caps, maximum returned priority |
| #3 | P1-02: Fetch v2 alert pages with deterministic cap truncation | v2 alerts, `expand=details`, pagination, cap truncation, source/page metadata |
| #4 | P1-03: Normalize v2 alerts into company-correlated trigger records | alert GUID provenance, company GUID correlation, raw/details preservation, company GUID anomaly behavior |
| #5 | P1-04: Group alert triggers by company GUID with distinct-company cap | company grouping, trigger preservation, distinct-company cap warning |
| #6 | P1-05: Enrich company groups with v1 company info and rating history | v1 company-info enrichment, current rating, rating history, fanout dedupe, enrichment warning |
| #7 | P1-06: Derive rating movement with alert-history precedence | alert-derived movement, history-derived movement, larger-drop precedence, missing movement warning |
| #8 | P1-07: Score alert-driven company watch candidates | point-based priority scoring, out-of-scope categories, category ambiguity, max-priority filtering |
| #9 | P1-08: Build structured Jira-action payload for company watch tickets | caller-facing action payload, company-watch subject, company GUID correlation, evidence and warning fields |
| #10 | P1-09: Expose deterministic alert workflow core as API-callable function | reusable deterministic orchestration core, warning propagation, non-MCP-first implementation |
| #11 | P1-10: Add CLI command for alert workflow Jira-action payload output | CLI/API-first surface, JSON action payload output, no raw-batch-as-product surface |
| #12 | consolidation test: security analyst alert workflow action payload | integrated proof across request config, v2 alert fixtures, v1 enrichment fixtures, scoring, action payload, API core, and CLI output |

## Dependency Shape

The implementation chain is linear from #2 through #11. Consolidation task #12 depends on #2 through #11. Parent #1 depends on #12 as the completion gate.

## Brief Coverage

Covered:

- deterministic security-analyst workflow core
- CLI/API-first implementation surface
- MCP not treated as the primary tool surface
- v2 alert intake with pagination and configurable caps
- full raw/source payload preservation for first implementation
- company GUID as watch correlation key
- company GUID required/anomaly behavior
- v1 company-info enrichment with rating history
- rating movement precedence between alert-derived and history-derived drops
- structured Jira-action payload as first useful caller-facing product
- initial point-based priority scoring and max-priority filtering
- warning/missing-data surfaces
- no direct Jira writes in the first implementation
- no durable queue/cursor state, closure automation, or management summary generation

## Expected-Experience Coverage

The decomposition preserves the approved expectation that the caller should not receive an internal enriched alert batch as the product. The implementation path leads to deterministic Jira-action output for company performance watch tickets, with company GUID as the watch identity and alert GUIDs/details retained as evidence.

The child tasks also preserve the process correction that this is not alert remediation. Rating movement, company rating history, and company-watch action payloads are represented before CLI/API exposure.

## Omissions and Accepted Follow-Ups

Not included in this first implementation by design:

- Jira lookup/create/append adapter that returns live ticket IDs/links/status
- existing-ticket update workflow independent of new alerts
- rating-recovery closure checks
- due-ticket review and management summaries
- durable correlation/audit ledger
- final redaction/slimming of raw payloads after information flow is proven

Open clarification retained for implementation:

- `web application security` appears both as a 3-point category and as an out-of-scope candidate in discussion. The child scoring task should keep this visible as an ambiguity rather than silently resolving it.

## Repair Actions

Shared-tier post-planner expectation-fidelity check found one material gap: supplier criticality was used by priority scoring but not assigned to a request/config input or enrichment source.

Additive repair was applied by amending existing child-task AC rather than creating a new task:

- #2 now defines optional supplier-criticality input/provenance and fallback behavior when the criticality list is absent or a supplier is missing.
- #2 now requires supplier-criticality input to be keyed by BitSight company GUID, with missing entries defaulting rather than name-based guessing.
- #7 now explicitly covers the branch where alert-derived movement is unavailable but company rating history provides a usable drop.
- #8 now consumes supplier criticality from the request/config contract, records supplier-score provenance, covers 1/2/3/default behavioral branches, and emits explicit metadata for priority-filtered candidates.

No new child task was required after these AC repairs.
