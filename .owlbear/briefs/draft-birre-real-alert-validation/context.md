# BiRRe Real Alert Validation Context

## Current Problem Snapshot

BiRRe's approved alert-workflow plan has now been implemented as a read-only `security-analyst-alerts` CLI/API workflow, but it has not yet been validated against the user's current BitSight alerts. Unit fixtures cannot establish whether the real v2 alert feed matches the assumed schema, whether `alert_date_gte` behaves as needed, how older non-expiring alerts appear, or whether alert plus company data contains enough evidence to produce the intended company rating-change timeline.

The user can confirm that newly configured alerts appear in the BitSight web UI and can provide authenticated browser access or screenshots for API-to-UI comparison.

## Project Type

Existing-feature/refactor. This work validates and sharpens an implemented slice of the existing BiRRe security-analyst workflow.

## Working Outcome

Establish a bounded, sanitized real-data evidence set that shows:

- which configured and historical alerts the v2 API returns for a recent lower-bound date;
- whether dates, pagination, alert identity, company identity, details, and rating movement match the implemented assumptions;
- what the BitSight UI shows that the API payload omits;
- whether the existing workflow can derive the non-final Jira ticket's change-over-time table;
- which correctness gaps must be repaired together before the real Jira-action payload is trustworthy, and which later workflow capabilities remain after that repair.

## Expectation Signal

**What this should give the user:** A deterministic real-alert workflow whose Jira-action payload faithfully represents the BitSight event log: correct dates, human category/risk-vector labels, start/end rating or grade movement, derived change evidence, priority inputs, company history, and provenance.

**What makes it worth using:** The generated change-over-time evidence should match what an analyst sees in BitSight closely enough to support a company-watch ticket without manually reconstructing each event. Production execution must work without test-only operation-name or visibility bypasses.

**First Useful Step:** Repair and validate the inseparable real-alert correctness bundle: generated alert-operation exposure/name, real detail-field normalization, before/after propagation into timeline evidence, category/risk-vector mapping for scoring, and bounded pagination/date-window proof. This is sequencing, not completion of the full product.

**What remains afterward:** Live Jira lookup/create/append with issue IDs and links; existing-ticket updates independent of new alerts; rating-recovery closure checks; due-ticket review and management summaries; broader real-category scoring validation; and best-effort finding correlation where useful.

**Technically done but still wrong:** A command that emits Jira-shaped JSON but needs an in-memory wiring bypass, loses start/end evidence, scores `RISK_CATEGORY` instead of the human risk vector, relies only on company-history fallback, or treats one capped page as proof of complete behavior.

**Knowingly deferred:** Direct finding links are best effort and do not block the first useful step. Direct Jira mutation and later ticket lifecycle automation remain sequenced follow-ups, not rejected scope.

## UI Evidence

The BitSight Alerts page is a historical event table, not an alert work queue. It currently shows 2,081 rows and provides no alert detail view. Rows expose the event date, company, category/risk vector, numeric rating or letter-grade transition, and folder/subscription context. Findings are separate objects that can be opened.

This means the workflow should treat alerts as immutable trigger/provenance events. The Jira timeline can be derived from their displayed movement semantics, while any finding link requires a separate finding-correlation step rather than an alert-detail URL.

## Constraints

- BitSight and Jira credentials must not be copied into discovery artifacts or chat.
- Live calls use only locally configured credentials; authorization values from shared examples are never stored or reused.
- Live validation starts with bounded read-only calls.
- Company and alert evidence retained in the draft should be minimized or sanitized unless a raw field is necessary to explain a gap.
- The exported Jira ticket is working evidence, not an approved schema.
- This discovery does not choose the implementation approach for any gaps it finds.

## Active Unknowns

- The implemented production path is currently blocked by an operation-name and tool-visibility mismatch: the workflow calls `getAlerts`, while FastMCP generates `AlertsList`, and the security-analyst context hides alert tools behind a company-request-only allowlist.
- Exact semantics of `alert_date_gte` for current and older alerts.
- Whether old alerts are returned because of their event date, publication date, update behavior, or query/filter behavior.
- Real `expand=details` data contains start/end rating or grade movement, but implementation field names and category mapping do not match the real schema.
- Whether alert details contain enough finding identity to build the intended BitSight finding link remains unknown.
- Whether v1 company `ratings` data aligns with alert dates and explains the UI's rating-change presentation.
- Which finding API/UI identity should be correlated to an alert-derived company/risk-vector event.
