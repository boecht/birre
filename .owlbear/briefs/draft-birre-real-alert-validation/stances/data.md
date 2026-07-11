# Data Quality Stance

The correction must introduce an explicit, envelope-aware normalization boundary between raw BitSight alerts and scoring or Jira timeline projection. The current fallback from missing alert movement to company history is data corruption by substitution: it produces a plausible rating change while discarding what the alert actually reported. Alert details must take design precedence for event-specific movement; company history may corroborate or contextualize that evidence, but it must never silently replace it.

Numeric rating movement and letter-grade movement are different schemas. They must remain different typed variants through normalization and projection. A shared ambiguous `before`/`after` pair invites invalid arithmetic and false equivalence.

## Schema and Validation Reasoning

Normalize each alert into a discriminated event record while retaining sanitized source provenance:

- Numeric rating events carry `start_rating`, `end_rating`, and, when present, `rating_threshold` as finite numeric values.
- Risk-category events carry `start_grade`, `end_grade`, `risk_vector`, and, when present, `threshold_grade` as strings governed by explicit grade rules.
- Envelope type, alert GUID, company identity, `alert_date`, `start_date`, `trigger`, and source-field presence remain separate metadata. Do not flatten them into an inferred movement record.
- Do not coerce grades into ratings, calculate numeric deltas from grades, or populate missing alert fields from company history.

The observed envelope names and field combinations support variants for `RISK_CATEGORY`, `RATING_CHANGE`, and `RATING_THRESHOLD`, but source/schema inspection was outside this panelist's permitted read scope. Implementation must confirm discriminator literals and required-versus-optional fields against the actual generated schema and representative payloads before fixing the contract.

Use `alert_date` as the timeline event date because that is the date shown for the alert event in the available API/UI evidence. Retain `start_date` separately as source context. The observed `alert_date=2026-07-09` and `start_date=2026-07-08` show that substitution is unsafe; one sample does not establish the complete semantics or exclude timezone effects. Missing or malformed `alert_date` must not fall back silently to `start_date`.

For risk-category events, `trigger` and `details.risk_vector` are two observed sources for the human label. The sampled response shows agreement, not a universal invariant. Normalize each independently using conservative comparison rules: trim surrounding whitespace and compare case-insensitively while preserving source spelling. Agreement increases confidence; disagreement must be surfaced with both values and excluded from category-dependent scoring until more real variants establish precedence. It must not cause an otherwise valid alert to disappear. `alert_type` remains envelope metadata and must never be scored as though `RISK_CATEGORY` were a human risk vector.

Scoring must accept only an explicit canonical category registry. Casing-only variants may compare equal while preserving canonical display text. Punctuation, spacing inside labels, abbreviations, and wording variants must remain unknown until observed equivalence is established. Unknown categories stay visible and unscored; guessed aliases are not acceptable.

Validate at the raw-to-normalized boundary and again before projection. Validation must make these states explicit:

- valid event evidence;
- valid alert with incomplete movement evidence;
- category conflict or unknown variant;
- malformed alert evidence;
- incomplete retrieval due to an explicit bound;
- complete empty result.

Reject non-finite numeric values, including NaN and infinities. Surface missing identities, invalid dates, impossible movement types, duplicate alert identities, and source conflicts. Quarantine malformed evidence from deterministic scoring or timeline claims, but retain a sanitized diagnostic record so legitimate variants are not silently dropped.

Pagination and date-window proof must follow the API's declared next offset/link until exhaustion or a declared bound. It must detect repeated pages or cursors, deduplicate by stable alert identity, and apply a deterministic ordering with an explicit tie-breaker before retaining a bounded subset. Every page must be checked against the requested lower bound; page one cannot prove later-page behavior. The run result must distinguish `complete`, `bounded/incomplete`, and `empty`, and report seen, accepted, rejected, duplicate, and retained counts. A cap proves bounded execution only, never completeness or representativeness. Repeated bounded runs are a prudent stability check, not evidence that instability already exists.

Company history is a separate evidence stream. When it can be aligned to an alert date under explicit temporal rules, record it as corroboration with its own provenance. A match does not replace alert movement; a conflict must display both sources and block a claim that the event has been deterministically reconciled. History-only movement may be useful company context, but it is not an alert-derived timeline event.

## Key Trade-offs

- Strict typed variants add projection work, but prevent grade/rating conflation and silent delta errors.
- Conservative category handling leaves some events unscored, but an explicit unknown is safer than confidently assigning the wrong priority.
- Continuing through bounded pagination yields useful evidence sooner, but only if incompleteness remains machine-visible and user-visible.
- Retaining sanitized conflict provenance increases diagnostic payload size, but is necessary to distinguish malformed data from legitimate schema evolution.
- Alert-first precedence may expose more missing movement than company-history fallback, but that is the honest state of the evidence.

## Warnings

- The available sample validates field presence, not field optionality, all envelope variants, or cross-page behavior.
- The exact inclusive semantics of `alert_date_gte`, timezone handling, ordering guarantees, and later-page compliance remain unproven.
- `trigger` and `details.risk_vector` agreement is observed only for the supplied risk-category response. Do not hard-code universal equality.
- Threshold fields are evidence, not decoration. Dropping `rating_threshold` or `threshold_grade` would make threshold events incomplete.
- A capped sample must not be described as representative without a documented sampling method.
- Source, tests, generated schema, and early stances were not reviewed because this panel mode permits reads only from `context.md`, `decisions.md`, and `research-notes.md`. Those surfaces require implementation-stage confirmation.

The explicit remainder is preserved unchanged: live Jira lookup/create/append with issue IDs and links; existing-ticket updates independent of new alerts; rating-recovery closure checks; due-ticket review and management summaries; broader real-category scoring validation; and best-effort finding correlation where useful. This correctness bundle is sequencing, not completion of the product promise.

## Confidence

**0.84.** Confidence is high in the required evidence separation, typed movement variants, conservative category semantics, and explicit pagination completeness states. It is limited by the small real-data sample and the unavailable source/schema review, especially for date semantics, discriminator contracts, category variants, and API ordering guarantees.
