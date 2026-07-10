# Security Stance

## Security Judgment: this workflow crosses real trust boundaries

BitSight alert, company posture, finding, rating-change, Jira issue, local correlation, and management-summary data are sensitive operational-security and business data. The design must treat them as privileged data from the first module, not as ordinary API output.

The workflow crosses at least three trust boundaries:

- BitSight API to BiRRe: external portfolio/security-posture data enters the local workflow.
- BiRRe to MCP clients and agents: sensitive normalized batches become tool output and may enter transcripts or client logs.
- BiRRe to Jira or local state: future writes can create durable operational records and trigger business workflow effects.

The first module should cross only the first two boundaries. It should not cross the Jira/local-state mutation boundary.

## Risk Assessment

The first alert-intake module should be read-only with respect to durable local state and external systems. It may fetch BitSight alerts, normalize records, enrich distinct companies through the existing v1 company-info path, and return a bounded batch to the caller. It must not write a durable ledger, create internal queue items, mutate Jira, finalize priority, close tickets, or persist full raw payloads.

That read-only boundary does not make the module low risk. MCP output is itself a disclosure boundary. A normalized alert/company batch returned to the caller may persist in client transcripts, debug logs, or agent context. Therefore the module output must be minimized for the workflow purpose, clearly marked sensitive, and separated from raw payload dumps. Raw/source provenance should mean enough source identity and selected source fields to verify normalization, not unrestricted echoing of every alert, finding, or company field.

The design must not rely on a stable alert identity until real v2 results prove its semantics. If v2 results include an alert `guid`, treat it as candidate provenance, not as a proven cross-run idempotency key. For the first module, deduplication should be in-run only and should report ambiguity instead of silently merging. Cross-run deduplication, Jira idempotency, and closure decisions must wait until source identity semantics are verified.

The absence of a documented `updated_at` field is a hard constraint. A stateless `alert_date_gte` pull can duplicate alerts and may miss mutation semantics if alerts change after first appearance. The first module should surface fetch-window metadata and uncertainty rather than pretending it has authoritative lifecycle state.

## Compliance Implications

The workflow can expose monitored-portfolio security posture, company profile attributes, rating-change details, finding/remediation text, and future Jira issue state. Even as an internal workflow, this creates confidentiality, retention, and access-control obligations.

Management summaries are especially sensitive because they aggregate and rank security issues. If they are emitted through MCP, assume they enter the client transcript/log path. Do not claim summaries or batches are kept out of transcripts when MCP is the channel. Minimize and redact outputs where feasible, and require explicit user action before generating broad portfolio summaries.

Future local correlation or audit data must have a retention and deletion posture. A ledger that links BitSight company/finding/alert identifiers to Jira issue keys is itself sensitive even if it avoids storing full payloads.

## Least-Privilege Recommendations

Expose alert workflows through a dedicated workflow context or narrowly scoped business tool surface. Do not broaden the existing `risk_manager` v2 allowlist indiscriminately. The alert surface should allowlist only the v2 alert-list operation and the existing company enrichment needed for this workflow.

Require explicit runtime bounds:

- caller-supplied date range or lower bound;
- page-size and page-count caps;
- optional company, folder, severity, or alert-type filters where supported;
- bounded distinct-company enrichment fanout;
- clear failure when limits are exceeded rather than automatic unbounded fetches.

Treat all external text as untrusted content: v2 alert detail messages, v1 finding remediation text, company descriptions, Jira issue text, and future summary inputs. These fields may be data, but they must never become tool instructions, system policy, or authorization decisions. Downstream prompt construction must quote or isolate source text and keep action permissions outside model-authored content.

Credentials need least privilege on both sides. The BitSight token is the immediate high-blast-radius credential because it can read sensitive portfolio data. Use scoped/read-only credentials where BitSight supports them; where the vendor cannot scope sufficiently, document that residual risk explicitly and compensate with local access controls, secret hygiene, and output minimization. Jira credentials later must be project-scoped and field-scoped before mutation is allowed.

Before Jira mutation exists, require:

- project-scoped Jira credentials;
- explicit issue-field allowlists;
- dry-run/action-preview output;
- idempotency semantics based on verified source identities;
- audit records for actor, tool version, source window, proposed action, result, and timestamp.

A future local ledger should be minimal: verified source identifiers, normalized work-item id, Jira issue key, timestamps, actor/tool version, source fetch window, decision/action result, and payload hash or pointer. It should not store full finding or alert payloads by default. It also needs access control, retention, deletion, and tamper-evidence expectations.

## Warnings

Do not let agent-authored text make irreversible state transitions. Agents can draft explanations, summaries, and action candidates, but ticket creation, update, closure, and suppression require explicit tool or human gates with audit.

Do not treat deterministic classification as a security control by itself. The security invariant is gated mutation, traceability, and reviewable source evidence. Deterministic rules can still misclassify if their inputs are stale, incomplete, or attacker-influenced.

Do not use local state as an authoritative finding database unless the workflow deliberately accepts the storage, retention, and access-control burden. Jira may become the ticket source of truth, but BiRRe may still need a small correlation/audit ledger once cross-run idempotency and closure workflows begin.

Do not ignore error paths. Exceptions, request URLs, query parameters, company GUIDs, partial payloads, and API response bodies can leak through logs or MCP error responses. Existing logging behavior should be verified before exposing bulk alert intake.

Do not assume every MCP client or attached agent is authorized to see portfolio alert data. Operation allowlisting limits what tools can do; it does not by itself authenticate who may invoke them.

## Confidence

Confidence: 0.78.

The core stance is strong: keep the first module bounded, read-only, non-mutating, and explicit about MCP output disclosure; defer durable ledger/Jira mutation until identity, idempotency, retention, and credential scope are designed. Remaining uncertainty is vendor-specific: BitSight token scoping, real alert `guid` semantics, alert mutation behavior without `updated_at`, and current BiRRe logging/error redaction need verification before implementation decisions are locked.
