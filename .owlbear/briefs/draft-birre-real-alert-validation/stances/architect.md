# Architectural Stance

Approve the dominant correction path as one bounded correctness delivery with five explicit ownership boundaries. This is one acceptance bundle, not one merged component:

1. Generated-server and context composition expose `AlertsList` in the production `security_analyst` context.
2. The v2 retrieval adapter invokes that generated operation by its actual name and owns bounded pagination.
3. A normalization boundary converts external alert envelopes and details into a canonical alert event.
4. Timeline and action projection carry canonical event evidence into the read-only Jira-shaped payload.
5. Scoring consumes normalized human labels rather than transport-layer alert enums.

Shipping only one of these corrections would leave a path that can emit plausible but materially false action data. They therefore belong in one delivery, while remaining separately testable responsibilities.

## Structural Reasoning

### Production reachability is part of correctness

The current `getAlerts` call and alert-hiding allowlist are production defects, not test-environment inconveniences. The corrected path must expose and call generated `AlertsList` through the real context composition. An in-memory alias or visibility bypass may support investigation, but cannot count as delivery proof.

The operation inventory is a contract boundary. A focused production-context test should fail when the generated operation name and the workflow dependency diverge or when context filtering hides the required operation.

### Normalize once at the external-data boundary

Generated transport payloads must not flow directly into scoring or presentation. Introduce or sharpen one canonical event representation containing:

- alert GUID when supplied, retained as provenance rather than assumed to be a navigable link;
- `alert_date` as the event date;
- company identity;
- envelope `alert_type`;
- optional human `trigger`;
- movement kind: numeric rating, letter grade, or absent;
- typed before and after values;
- movement source and source-field provenance.

Map `start_rating` and `end_rating` to a numeric rating movement. Map `start_grade` and `end_grade` to a distinct grade movement. Do not coerce grades into numeric deltas or combine both variants behind an ambiguous pair of untyped values.

For risk-category events, the verified scoring input is the human `trigger`, cross-checked against `details.risk_vector` when both are present. Missing or conflicting values must produce an explicit unsupported or validation outcome. Falling back to the `RISK_CATEGORY` envelope enum would recreate the current semantic error. The sampled match supports this mapping for the bounded slice; broader category and casing calibration remains explicitly deferred.

### Event evidence must survive projection

Alert detail movement is authoritative for its event row. Company rating history may corroborate it or provide separately labeled fallback evidence when event movement is absent, but fallback availability must not be assumed and fallback must not conceal failed normalization.

Tests should assert that event date, movement kind, before and after values, source, human label, and supplied GUID survive from normalization through Jira-action timeline projection. The timeline records observed event semantics. It must not imply causality, ownership, remediation, or ticket lifecycle state.

### Pagination proof must report its boundary honestly

A capped first page is sample evidence, not completeness proof. Retrieval validation should:

- preserve the requested `alert_date_gte` on every page request;
- follow valid next offsets until exhaustion or an explicit page or record ceiling;
- reject repeated or non-advancing pagination tokens;
- assert that every returned `alert_date` satisfies the requested lower bound;
- mark ceiling termination as truncated or incomplete;
- compare repeated bounded runs while acknowledging that a live event feed can change between runs.

Because sampled `start_date` and `alert_date` differ, filtering and timeline ordering must deliberately use `alert_date`. Any `start_date` retention is provenance, not a substitute event date.

The proof claim must remain bounded: it can establish behavior for the tested window, pages, and runs, not universal BitSight API semantics. Live evidence complements deterministic fixture and contract tests; it does not replace them.

### The phase boundary remains read-only

This delivery ends at a deterministic Jira-action payload. It must not add Jira writes or finding correlation. The preserved remainder is explicit:

- live Jira lookup, create, and append operations with issue IDs and links;
- updates to existing tickets independent of new alerts;
- rating-recovery closure checks;
- due-ticket review and management summaries;
- broader real-category scoring validation;
- best-effort finding correlation.

## Key Trade-offs

- **One delivery versus independent fixes:** one acceptance bundle prevents partially corrected output from being mistaken for trustworthy output; separate ownership and tests prevent architectural collapse.
- **Canonical model versus direct payload reuse:** normalization adds a boundary but removes transport-schema coupling from scoring and presentation.
- **Alert evidence versus company history:** alert details preserve event fidelity; labeled company-history fallback improves resilience without inventing event-specific evidence.
- **Bounded proof versus exhaustive retrieval:** explicit ceilings keep live validation safe and repeatable enough for this phase, while truncation status prevents false completeness claims.
- **Strict trigger validation versus broad scoring coverage:** explicit unsupported outcomes are preferable to incorrect priorities; broader category calibration remains later work.

## Warnings

- Do not retain `getAlerts` through an alias merely to preserve existing fixtures.
- Do not broaden the context allowlist beyond the exact read-only alert capability required by this workflow.
- Do not let generated API dictionaries become the shared domain model.
- Do not silently substitute company history when alert movement normalization fails.
- Do not treat a missing GUID, trigger, movement field, or next offset as having semantics not established by evidence.
- Do not claim inclusive-date or pagination behavior beyond the bounded windows and pages actually exercised.
- Do not let Jira mutation, ticket lifecycle state, or finding correlation enter this correction bundle.

## Confidence

**0.87.** The architectural boundaries follow directly from the observed production wiring failure, real payload mismatch, evidence loss, scoring mismatch, and capped retrieval. Residual uncertainty is concentrated in unsampled alert variants, missing/conflicting trigger behavior, GUID reliability, and live pagination stability; the stance contains these as explicit validation outcomes rather than expanding scope.
