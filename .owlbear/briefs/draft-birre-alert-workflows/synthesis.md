# BiRRe Alert Workflow Synthesis

## Summary

The late-domain panel initially converged on a narrow first module inside BiRRe: deterministic BitSight alert intake and enrichment that produces a normalized batch. The user corrected the product boundary during mediation: that batch is internal process data, not the visible caller-facing product.

The revised direction is a deterministic `security_analyst` workflow whose core logic can be called from CLI and API surfaces, with MCP exposure only as a secondary/debug-oriented workflow surface if useful. Internally, it fetches v2 alerts for a caller-supplied date window, requests expanded details, follows pagination, preserves full raw/source payloads for the first implementation, normalizes alert trigger facts, groups by company without collapsing distinct triggers, enriches distinct company GUIDs through existing v1 company-info, then produces rating-aware structured Jira-action data for company-watch ticket handling. Once the Jira adapter is wired, the caller should receive ticket identifiers/links and action status, not an alert batch.

This first process should still avoid durable internal queue/cursor state and management-summary generation. Jira should be treated pragmatically as another API integration, but the first implementation should stabilize the structured Jira-action payload before writing to Jira. Duplicate handling belongs at the company-watch correlation step rather than by over-optimizing local alert intake.

## Convergences

### BiRRe should own the first BitSight-only workflow primitive

Architecture, data, end-user, and security reviews all support implementing the first module inside BiRRe because the work is still BitSight retrieval, normalization, enrichment, and business-tool orchestration. This fits BiRRe's existing pattern better than starting with a separate automation project for module one.

The shared boundary is specific: expose a workflow-oriented business tool or context for alert intake and company enrichment, not a general-purpose automation platform.

### The first internal processing shape should be a batch, not a durable queue

Architecture and data reviews argue that queue semantics would prematurely force idempotency, retry, leases, ordering, replay, crash recovery, and audit design before the alert contract is proven. The end-user review accepts the batch boundary as long as the result is review-ready rather than a raw dump. The security review adds that the first module should avoid durable local state and external mutation because those introduce retention and access-control obligations.

The revised first shape is therefore batch-in internally, structured Jira-relevant ticket data or ticket action results out externally.

### Company GUID is the watch identity; alert GUID is trigger provenance

Architecture, data, and end-user reviews converge that company GUID should organize later Jira correlation because the operational ticket tracks company performance. The user refined this further: the goal is not to work on an alert or merely resolve the finding behind it. Alerts trigger a company watch to determine whether the event is a one-time slip or the start of a downward trend, and watching stops when the rating returns to normal. Alert GUID records why the company entered the workflow.

The internal shape should support one company watch with many alert triggers. It must never collapse multiple alerts into a single company event that loses alert type, date, severity, trigger, details, folder context, or source reference, but the first Jira correlation key is company GUID only.

### The first action contract is rating-aware, not a raw batch rename

Critical review flagged that a company-watch workflow needs mechanism: it must show why a company entered watch status and what rating movement is visible. The user resolved this by treating each relevant alert as carrying implied rating movement. When an alert includes before/after rating or category fields, the workflow should calculate the rating-drop amount and pair it with current company rating from v1 company-info.

The structured Jira-action data should therefore include company GUID, company name, current company rating, current rating date/source if available, per-alert event date/seen-at fields, rating-before/rating-after or category-before/category-after fields when present, calculated drop amount, alert trigger/provenance, and proposed Jira summary/body table content. Missing rating movement fields should be explicit warnings, not silently inferred.

### v1 company enrichment belongs in the first module

Architecture, data, and end-user reviews converge that v1 company profile enrichment is worth including because the existing company-info capability already provides fields needed for ticket decisions and makes the output materially useful. The data review limits this to company profile enrichment, not v1 findings or rating-change enrichment. Security accepts enrichment within a bounded, read-only fanout and recommends explicit caps.

### The module must be loss-aware and validation-heavy

Architecture and data reviews stress raw/source provenance, pagination metadata, and warning flags. End-user review translates that into trust: the process should know what was fetched, what was enriched, what failed, and what remains unknown. Security narrows raw preservation as a later hardening concern, but the user chose full raw/source payloads in the first implementation to simplify discovery and avoid premature field selection.

The internal contract should include run metadata, normalized alert trigger records, company enrichment records, validation statuses, warning flags, and full source payloads during the initial learning phase. Later iterations can reduce routine disclosure once the required information flow is proven.

### v2 alerts are trigger records, not proven remediation truth

Data, architecture, and end-user reviews all warn that v2 `expand=details` should not be assumed to contain full finding, remediation, due-date, or rating-event truth. Security adds that external detail text is untrusted and must not become instructions or authority for actions.

Richer finding/rating-drop context remains a later research and enrichment boundary, with v1 findings and rating-change endpoints named as likely leads but not settled dependencies.

### The first intake stage must be bounded; the visible workflow is Jira-relevant

Security strongly converges with architecture's concern about avoiding premature internal queue/cursor state. The user corrected the Jira boundary: Jira integration should not be treated as categorically out of scope merely because it is another API. Runtime bounds should include date/window inputs, page-size and page-count caps, optional filters where supported, bounded company enrichment fanout, and clear ticket-correlation behavior before mutation.

## Disagreements

### How much raw payload should be retained or exposed

Architecture and data reviews say raw alert payloads and raw details should be preserved so later stages can recover from incomplete normalization assumptions. Security agrees with provenance but warns that MCP output is a disclosure boundary and should not echo unrestricted sensitive payloads indefinitely.

The user resolved this for the first implementation: keep full raw payloads because the information flow is not yet clear, then strip unnecessary fields later once the process proves what is actually needed.

### Whether company-only correlation can overload a watch ticket

Data and security concerns originally pointed toward separating tickets by alert type, risk vector, or alert identity to avoid mixing unrelated issues. The user rejected that framing for the first workflow because the ticket subject is company performance watch, not alert remediation.

The accepted trade-off is that one company watch may contain heterogeneous alert evidence. That is appropriate if the ticket narrative and status fields frame the work as monitoring company performance until rating recovery, not as resolving each finding separately.

### Internal batch versus caller-facing product

End-user review pushed for a company-centered review packet with counts, coverage, enrichment status, and explicit gaps. The user clarified that this should not be the caller-facing product. The external product is structured Jira-relevant data and, after Jira integration, ticket identifiers/links and action status.

The internal batch can still be company-centered because company GUID is the Jira subject identity, but it should support the workflow rather than become the workflow's visible endpoint.

### Where future state should live

All reviews reject durable queue/state as the first foundation, but they leave room for later minimal state. Architecture and context suggest a minimal correlation/audit ledger may become necessary if Jira is the ticket source of truth but BiRRe must map BitSight identifiers to Jira issue keys and decisions. Security agrees only with explicit retention, deletion, access-control, and tamper-evidence expectations. Data warns that cross-run duplicate handling belongs outside module one unless a later owner is designed.

This remains a later decision, not a module-one choice.

## Recommendation

Proceed with a first roadmap workflow in BiRRe under a new `security_analyst` context, backed by CLI-callable core logic rather than MCP-only wrapper code. Its contract should be:

1. Accept an explicit alert retrieval window or lower-bound date plus bounded pagination/filter options.
2. Call v2 `GET /alerts` with `alert_date_gte`, `expand=details`, and pagination.
3. Validate the v2 page envelope before normalization.
4. Normalize alert trigger records while preserving alert GUID, company GUID when present, alert type, alert date/start date, severity, trigger, folder/alert-set context, expanded details, full raw/source payloads for the first implementation, endpoint/query parameters, and page metadata.
5. Treat company GUID as required for relevant company-watch processing; missing company GUID is an unexpected schema/API anomaly unless real responses prove otherwise.
6. Deduplicate enrichment calls by distinct company GUID.
7. Enrich each distinct company through the existing v1 company-info path.
8. Build an internal company-centered workflow data structure with nested per-alert triggers, run evidence, enrichment status, validation warnings, and unresolved data gaps.
9. Produce rating-aware structured Jira-action data for company-watch ticket handling, with company GUID as the first correlation key and alert GUIDs retained as trigger provenance.
10. Include proposed Jira summary/body table content with event date, seen-at/date fields, rating movement, rating after, current company rating, evidence, and missing-data warnings.
11. Stop before management-summary generation, durable queue/cursor state, closure automation, and direct Jira writes.
12. Calculate initial priority using the agreed point system for supplier criticality, event category, rating change, and defaulted human factor; filter returned alert-driven new-ticket candidates above the configured maximum priority.
13. Wire Jira lookup/create/append after the Jira-action payload is testable, rather than making the first implementation write to Jira immediately.

This recommendation is justified by convergence across architecture, data, end-user, and security reviews. It preserves the first useful operational value while avoiding decisions that the artifacts have not yet settled.

Confidence: 0.74 because the mediation decision changed the external product boundary after panel synthesis.

## Expectation Fit

The dominant approach preserves what the user is actually trying to get: a repeatable alert workflow that turns BitSight alerts and company context into Jira-relevant company-watch work. The user does not just need endpoint access or an enriched batch; they need deterministic process logic that can be triggered from CLI or MCP and, after the adapter is wired, return ticket outcomes.

What makes it worth using is the combination of completeness, process fit, and low manual handling. Internally grouping by company, keeping every alert trigger visible, including v1 company context, recording pagination and filter evidence, preserving raw payloads, and calculating alert-derived rating movement gives the workflow enough material to produce a useful Jira-action payload. The caller should see ticket-relevant results, not be asked to manually reconstruct the process from alert data.

After the First Useful Step, the remaining workflow still includes Jira adapter wiring, richer finding/rating-change enrichment, closure checks based on rating recovery, due-ticket review, management-summary generation, and any durable correlation/audit state. Priority rule tuning can evolve from the rating-aware action payload and observed workflow results.

## Open Questions

1. Should the duplicated/uncertain `web application security` category be treated as a priority-3-point category, out of scope, or split by a more specific BitSight risk-vector value?
2. What human or tool approval gate is required before any future module creates, updates, closes, or suppresses Jira tickets?
3. When Jira work begins, should Jira be the only durable ticket source of truth, or should BiRRe also maintain a minimal correlation/audit ledger?
4. What retention and redaction rules should apply to MCP outputs, logs, debug traces, and any future local correlation records that contain portfolio security data?
