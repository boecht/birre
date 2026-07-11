# BiRRe Real Alert Validation Synthesis

## Summary

The three active stances support one dominant approach: deliver the real-alert corrections as a single bounded correctness bundle with separately testable boundaries. The production `security_analyst` context must expose the generated `AlertsList` operation; retrieval must use that operation and prove bounded pagination; an envelope-aware normalization boundary must preserve typed alert evidence; timeline projection must carry that evidence without silent company-history substitution; and scoring must consume validated human labels rather than transport enums.

This approach fits the user's expectation because it makes the read-only Jira-action payload a faithful, inspectable representation of the BitSight event log before any ticket mutation is attempted. It is worth using when an analyst can trust the event date, company, human category or risk vector, rating or grade endpoints, source provenance, and evidence-coverage status without manually reconstructing the event in BitSight.

The First Useful Step is the complete correctness bundle, not one isolated repair: production operation exposure and naming, real detail-field normalization, before/after propagation, category and risk-vector mapping for scoring, and bounded pagination/date-window proof. This is sequencing, not completion of the larger product promise.

The technically-done-but-wrong version is a command that emits plausible Jira-shaped JSON while depending on an in-memory operation alias or visibility bypass, dropping alert-specific start/end evidence, scoring `RISK_CATEGORY` as a human label, silently replacing missing alert movement with company history, or treating a capped first page as complete evidence.

Per the user's decision, this phase has architecture, data, and end-user review only. A separate security review is omitted because validation remains inside the existing read-only BitSight trust boundary with bounded live calls, local credentials, and minimized or sanitized retained evidence. That decision should be revisited only if scope expands into writes, durable raw-payload storage, or broader access.

## Convergences

### One acceptance bundle with separate ownership boundaries

- **Architect** treats production reachability, retrieval, normalization, projection, and scoring as one acceptance bundle whose responsibilities remain independently testable.
- **Data** agrees that normalization must sit between raw envelopes and scoring or projection, and that retrieval completeness must be machine-visible.
- **End user** agrees that the projected output must preserve typed movement, human labels, source provenance, and coverage limits.

Together these positions reject partial fixes that can produce believable but materially false output.

### Alert evidence is authoritative for an alert event

- **Architect** says alert detail movement is authoritative for its event row and company history may only corroborate or provide separately labeled fallback evidence.
- **Data** calls silent history substitution data corruption and requires the two evidence streams to retain separate provenance.
- **End user** requires history to be labeled as corroboration or fallback and never displayed as though it came from the alert.

The shared rule is that absent, malformed, or conflicting alert evidence must stay visible as an evidence state rather than being repaired through inference.

### Numeric ratings and letter grades remain distinct

- **Architect** requires distinct typed movement variants.
- **Data** requires discriminated schemas and forbids grade-to-rating coercion or grade arithmetic.
- **End user** presents both in one compact movement column while naming the type, for example `Rating: 630 -> 620` and `Risk-vector grade: C -> D`.

The domain representation stays typed even if the analyst-facing projection uses one scan-friendly column.

### Event date and human label semantics are conservative

- **Architect**, **Data**, and **End user** all use `alert_date` as the timeline event date and retain `start_date` only as distinct source context.
- All three use the human `trigger` for the analyst-facing category or risk vector and cross-check it against `details.risk_vector` for risk-category events.
- All three reject the envelope value `RISK_CATEGORY` as a scoring label and require conflicts or unknowns to remain explicit rather than guessed.

### Pagination proof is bounded and honest

- **Architect** requires preserving the date filter across pages, advancing through valid offsets, detecting non-advancing pagination, and reporting ceiling termination as incomplete.
- **Data** adds stable-identity deduplication, deterministic ordering, per-page lower-bound checks, and explicit complete, bounded/incomplete, and empty outcomes with counts.
- **End user** requires the requested window, returned count, and truncation status to appear beside the timeline.

A bounded run can prove behavior only for the exercised window, pages, and limits. It cannot prove universal API semantics or representativeness.

## Resolved Review Tensions

- Rating and grade movement share one typed movement column. Rating variants include a computed numeric delta; grade variants never use arithmetic.
- Timeline rows use compact source tokens with selected normalized provenance in a structured evidence register.
- Only valid events enter the timeline. Excluded incomplete, conflicting, unsupported, and malformed records are counted by sanitized reason code.
- Annex A is the exhaustive category registry. Matching is conservative; no fuzzy aliases or invented `Other` category are allowed.
- Rating-only envelopes remain valid assessment triggers. They expose a provisional partial priority with category pending; final priority requires Annex A classification or operator judgment.

## Recommendation

Proceed with the dominant five-boundary correctness bundle:

1. Expose generated `AlertsList` through the real `security_analyst` production context and call it by its generated name.
2. Make retrieval own bounded multi-page traversal, date-filter preservation, loop detection, stable-identity deduplication, deterministic ordering, and explicit completeness status.
3. Normalize external alert envelopes into envelope-specific typed rating or grade evidence plus explicit excluded states, retaining selected normalized provenance.
4. Project valid evidence into a chronological analyst-facing timeline that uses `alert_date`, typed movement text, readable sources, and explicit run-level truncation status.
5. Apply Annex A category scoring only when classification is known. Rating-triggered actions may expose provisional partial priority with category pending; only operator/evidence-completed calculations are final.

Acceptance should require production-context proof, deterministic fixture or contract tests for each boundary, and a bounded read-only live comparison against the BitSight UI. Live evidence supplements deterministic tests and must report its tested window, bounds, counts, rejected or duplicate records, and completeness status.

The initial presentation follows the compact table shape `Event date | Company | Category / type | Movement | Source`, with rating-only numeric deltas and a structured source register.

Do not add Jira lookup, creation, append, update, closure, or reporting behavior to this bundle. Do not add finding correlation. Those capabilities are outside this brief's First Useful Step and no integration design for them is implied here.

**Recommendation confidence: 0.86.** All three stances converge on the correction boundaries and trust model. Confidence is limited by unsampled alert variants, uncertain date and pagination semantics, category-label variation, and unobserved missing/conflict rendering cases.

## Selected Direction

The user selected an in-place replacement of the flawed security-analyst slice, not incremental compatibility with its known-wrong contracts and not a collector-only prototype.

Sequence the selected direction inside one complete delivery:

1. Restore a bounded production collector through the real CLI/API path: expose and call `AlertsList`, preserve machine-readable stdout, and make logs use the logging channel.
2. Define a provisional polymorphic support contract from production observations, bundled schema, and documentation. Production evidence wins where those sources conflict.
3. Obtain bounded, sanitized, structurally faithful samples for each observed supported envelope. Initial variants are `RISK_CATEGORY`, `RATING_CHANGE`, `RATING_THRESHOLD`, and `PERCENT_CHANGE`; each retains its own required and optional detail fields.
4. Replace fixture-derived movement and category assumptions with envelope-discriminated normalization. New envelopes are unsupported until explicitly added; they never inherit a superficially similar contract.
5. Project valid evidence into one chronological timeline. Rating variants show rating endpoints and a computed rating delta; grade variants show grade endpoints without arithmetic. Variant-specific threshold or percentage evidence remains typed and inspectable.
6. Put a compact source token in each row and retain selected normalized provenance in a structured evidence register; do not retain full raw payloads by default.
7. Use exhaustive Annex A category scoring with case and surrounding-whitespace normalization only. Rating-only events carry category-pending provisional priority evidence rather than an invented category score.
8. Include valid events only in the timeline. Count excluded incomplete, conflicting, unsupported, and malformed records by sanitized reason code in run metadata.
9. Validate stable identity, deduplication, deterministic ordering, loop detection, bounded pagination, and date behavior with deterministic tests plus a read-only live comparison whose window, limits, counts, and completeness status are explicit.

This sequencing does not redefine the collector as the product. The First Useful Step remains incomplete until the entire correctness bundle produces trustworthy Jira-action timeline evidence.

## Open Questions

1. Beyond the four observed initial variants, which additional production envelopes are relevant to the configured operational alerts and what distinct contracts do they require?
2. Are `alert_date_gte` semantics inclusive across page boundaries, and how do timezone, ordering, publication, or update behavior affect older alerts in the tested window?
3. Which stable alert identity and pagination token or offset rules are reliable enough for deduplication and loop detection?
4. What exact minimum fields make each envelope valid for timeline inclusion, and which sanitized exclusion reason codes are required?
5. How should the Jira-action schema represent known priority components, category-pending state, and final operator-confirmed priority without conflating them?
6. Does the compact source-token and evidence-register payload remain readable when rendered into a representative Jira description?
8. How should same-day events be ordered without implying source precision that the API does not provide?

## Explicit Remainder

After the First Useful Step, the previously preserved product remainder is still outstanding: live Jira lookup/create/append with issue IDs and links; existing-ticket updates independent of new alerts; rating-recovery closure checks; due-ticket review and management summaries; broader real-category scoring validation; and best-effort finding correlation where useful. These are named only to preserve the larger expectation. They are not designed, added, or treated as acceptance criteria for this brief.
