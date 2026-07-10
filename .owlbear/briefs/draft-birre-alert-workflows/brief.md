# BiRRe Security Analyst Alert Workflow Brief

## Product Promise

Build a deterministic BiRRe security-analyst workflow for alert-driven company performance watch preparation. The workflow uses BitSight alerts as triggers to identify companies that need attention, enriches those companies, derives rating-movement evidence from alert details plus company rating history/current rating, calculates initial priority, and produces structured Jira-action data for company watch tickets.

The caller should not receive the internal alert/company batch as the product. The visible product of the first useful step is a structured, testable Jira-action payload. After the Jira adapter is wired, the caller-facing result should become Jira ticket identifiers/links and action status.

## Scope Boundary

The first implementation creates reusable deterministic workflow logic callable from CLI/API surfaces. MCP exposure is secondary/debug-oriented if useful; this is not primarily a normal chat-oriented MCP tool.

The first implementation does not write to Jira. It produces a testable Jira-action payload that a later Jira adapter can consume. It does not add durable internal queue/cursor state, management-summary generation, closure automation, or direct ticket mutation.

The ticket subject is company performance watch. Alert GUIDs and finding details are evidence/provenance, not the primary unit of work. Company GUID is the first correlation key.

## Inputs and Configuration

The caller supplies an alert date/window and may override configured caps. Defaults are configuration-backed and initially target:

- 50 alerts per page
- 10 pages
- 100 distinct companies

Caller/config may also set the maximum returned priority for alert-driven new-ticket action candidates.

## Internal Processing

The workflow should:

1. Call v2 `GET /alerts` with the date/window, `expand=details`, pagination, and relevant filters when available.
2. Preserve full raw/source payloads for the first implementation.
3. Normalize alert trigger records while preserving alert identity, company identity, dates, severity, trigger, folder context, details, endpoint/query metadata, page metadata, and raw payloads.
4. Treat company GUID as required for relevant company-watch processing; missing company GUID is an unexpected schema/API anomaly unless real responses prove otherwise.
5. Group enrichable alerts by company GUID.
6. Call existing v1 company-info enrichment once per distinct company GUID, including current rating and rating history when available.
7. Derive per-alert rating movement from alert before/after rating or category fields when present.
8. Validate and augment rating movement with company rating history: use the history drop if it is larger, otherwise use alert-derived drop; if alert-derived drop is unavailable, use history drop when present.
9. Calculate alert-driven priority/action eligibility with the initial point system.
10. Filter returned new-ticket action candidates above the configured maximum priority, such as priority 4.

The priority gate applies to alert-driven new-ticket action candidates. It does not block future existing-ticket update workflows, which may operate without new alerts.

## Jira-Action Output

For each company watch candidate, the structured Jira-action payload should include:

- company GUID and company identity fields
- current company rating and relevant company rating-history evidence
- company GUID correlation key
- trigger alerts and alert GUID provenance
- event/seen dates
- rating before/after or category before/after when available
- calculated rating drop amount and evidence source
- priority score, priority level, and action eligibility
- proposed Jira summary fields
- proposed Jira body/table fields, including event date, seen-at/date fields, rating movement, rating after, current rating, and evidence
- raw evidence references/payloads for the first implementation
- warnings and missing-data flags

## Initial Priority Logic

Use the initial point system below.

Supplier criticality:

- criticality 1: 0 points
- criticality 2: 1 point
- criticality 3: 3 points
- missing list or missing supplier: 1 point

Event category:

- public disclosure or security incident: -1 point
- botnet infection, malware, potentially exploited: 0 points
- open ports, patching cadence, server software, insecure systems: 1 point
- TLS certificates, TLS configuration, spam propagation, mobile app security, desktop software, mobile software, exposed credentials, web application headers, web application security: 3 points

Out of scope:

- DNSSEC
- DMARC
- DKIM
- SPF
- domain squatting
- unsolicited communication
- file sharing

The duplicated or uncertain `web application security` category remains a clarification item: it appears both as a 3-point category and as an out-of-scope candidate in discussion, so implementation should keep this visible rather than silently resolving it.

Score change:

- more than 150 rating points: -1 point
- more than 100 rating points: 0 points
- more than 40 rating points: 1 point
- 40 or fewer rating points: 3 points

Human factor:

- many events: 0 points
- normal: 1 point
- low relevance: 3 points

The first implementation should default human factor to 1.

Priority mapping:

- total up to 1 point: priority 0
- total 2 points: priority 1
- total 3 points: priority 2
- total 4 or 5 points: priority 3
- total 6 or more points: priority 4

## Non-Goals

The first implementation does not include:

- direct Jira writes
- durable internal alert queue or cursor state
- management-summary generation
- closure automation
- alert GUID or finding identity as the ticket subject
- raw-batch-as-product caller surface
- normal MCP-tool-first workflow exposure

## Validation Expectations

Validation should cover:

- pagination and configurable caps
- grouping by company GUID
- required company GUID behavior
- company enrichment fanout deduplication
- rating movement precedence between alert-derived movement and company history
- priority scoring and filtering
- Jira-action payload shape
- CLI/API execution of the deterministic workflow core without MCP
- warnings for missing rating movement, cap truncation, enrichment failures, category ambiguity, and priority-filtered items

## What Remains After the First Useful Step

After this first useful step, remaining workflow work includes:

- Jira adapter lookup/create/append that consumes the structured action payload and returns ticket IDs/links/status
- later existing-ticket update workflow independent of new alerts
- rating-recovery closure checks
- due-ticket review and management summaries
- possible minimal Jira correlation/audit ledger if Jira alone is insufficient as source of truth
- later redaction/slimming of raw payloads once the required information flow is proven
