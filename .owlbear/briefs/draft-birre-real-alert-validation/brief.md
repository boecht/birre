# BiRRe Real Alert Correctness Brief

## Product Promise

Replace the flawed security-analyst alert slice with a deterministic read-only workflow that works through the real production CLI/API path and produces trustworthy, company-grouped Jira-action evidence from BitSight alerts.

The output must faithfully represent the BitSight event log: correct event and source dates, envelope-specific rating or grade movement, rating-only numeric deltas, category or event type, company context, selected provenance, retrieval completeness, and process-grounded priority evidence. An analyst should be able to use the resulting change-over-time evidence without manually reconstructing each event in BitSight.

## Scope Boundary

This implementation replaces the flawed slice in place. It may retain useful public intent and module ownership, but it must not preserve internal contracts, fixtures, or payload assumptions disproven by official documentation or verified production responses.

The implementation includes:

- production `AlertsList` exposure and invocation in the `security_analyst` context;
- one machine-readable JSON document on CLI stdout, with logs kept on the logging channel;
- bounded multi-page alert collection with explicit completeness metadata;
- polymorphic support contracts for the four verified production envelopes;
- envelope-specific validation and typed normalization;
- company grouping and a chronological valid-event timeline;
- typed movement presentation, selected provenance, and a structured evidence register;
- exhaustive Annex A category handling and provisional-versus-final priority semantics;
- deterministic tests and a bounded read-only production comparison.

This implementation does not include:

- Jira lookup, creation, append, update, closure, or reporting operations;
- finding correlation or guaranteed finding links;
- existing-ticket lifecycle automation;
- rating-recovery closure checks;
- due-ticket review or management-summary generation;
- claims of support for unobserved alert envelopes or universal BitSight behavior.

Those capabilities remain part of the larger product promise and are sequenced after this correctness bundle.

## Collection Contract

The normal production path must expose and call the generated `AlertsList` operation without aliases, monkeypatches, or test-only visibility bypasses.

The `security-analyst-alerts` command must emit exactly one parseable JSON document on stdout. Diagnostic and operational messages must use the configured logging channel and must not contaminate machine-readable output.

Collection must:

- preserve the requested lower-bound date and filters across pages;
- traverse pagination within configured page and item limits;
- detect non-advancing or looping pagination;
- deduplicate by stable alert identity;
- order retained events deterministically without claiming source precision that is not present;
- preserve company GUID as the company-watch grouping key;
- distinguish complete, empty, and bounded/incomplete runs.

Run metadata must include the requested date window and filters, configured limits, source count, retained count, duplicate count, exclusion counts by sanitized reason code, and termination/completeness status.

## Contract Authority

Official BitSight documentation is the initial source for query parameters and response expectations. Verified production behavior takes precedence where production contradicts bundled or published schema material. Such contradictions must be represented explicitly in tests and documentation rather than hidden by broad fallbacks.

Bounded direct API responses may be used as the source for sanitized, structurally faithful real samples. Credentials and unnecessary identifying values must not be retained. Samples establish only the variants and behavior they actually exercise.

## Supported Alert Envelopes

The initial supported production variants are:

- `RISK_CATEGORY`: grade movement using `start_grade` and `end_grade`, with `threshold_grade` and `risk_vector` retained as typed evidence;
- `RATING_CHANGE`: rating movement using `start_rating` and `end_rating`;
- `RATING_THRESHOLD`: rating movement using `start_rating` and `end_rating`, with `rating_threshold` retained as typed evidence;
- `PERCENT_CHANGE`: rating movement using `start_rating` and `end_rating`, with `rating_change_pct` retained as typed evidence.

Each envelope has its own required and optional fields. A new or changed envelope is unsupported until explicitly mapped and validated. It must never inherit another envelope's contract merely because its fields appear similar.

## Timeline Output

Each company action must contain a chronological timeline of valid supported events with the conceptual columns:

`Event date | Company | Category / type | Movement | Source`

Movement presentation must preserve type:

- rating variants show endpoints and a computed rating-only delta, for example `Rating: 630 -> 620 (-10)`;
- risk-category variants show grade endpoints, for example `Risk-vector grade: B -> C`;
- grade movement must never be converted into numeric arithmetic;
- threshold and percentage values remain typed evidence and must not be collapsed into a generic movement field.

`alert_date` is the timeline event date. `start_date` remains distinct source-period context.

Each row must contain a compact source token. Selected normalized provenance must be available in a structured evidence register, including enough information to trace the alert identity, envelope type, source period, and movement fields. Full raw payloads are not retained by default.

Only valid supported events enter the timeline. Incomplete, conflicting, unsupported, or malformed records receive no timeline row and no deterministic score. Their exclusion remains machine-visible through sanitized reason counts in run metadata.

Company rating history may corroborate alert evidence or provide separately labeled fallback context. It must never be presented as though it were alert-derived movement.

## Category and Priority Semantics

Annex A from the process handbook is exhaustive for event-category scoring. Category matching may normalize case and surrounding whitespace only. The workflow must not use fuzzy aliases, invent an `Other` category, or score transport envelope names such as `RISK_CATEGORY` as business categories.

Known risk-category alerts use their validated Annex A category. Unknown or conflicting category evidence is not scored as a valid classified event.

Score drops and threshold crossings independently trigger assessment according to the operative process. A rating-triggered action may therefore expose provisional priority evidence before an Annex A category is known.

Provisional priority evidence must:

- preserve known partner-tier, score-drop, and correction-factor components;
- mark the category component as pending;
- remain distinguishable from final priority in the schema and rendered output;
- allow later Annex A classification or operator judgment to complete or revise the calculation.

The workflow must not present a provisional calculation as final priority. Final priority remains operator-controlled expert judgment, consistent with the process handbook. Documented hard rules, including the minimum priority for a qualifying yellow-to-red total-rating deterioration, remain enforceable when their conditions are met.

## Validation Requirements

Deterministic validation must prove:

- `AlertsList` is visible and callable in the production `security_analyst` context;
- the CLI emits exactly one parseable JSON document on stdout while logs remain separate;
- each supported envelope uses its own contract and cross-envelope field assumptions are rejected;
- valid-only timeline inclusion and sanitized exclusion accounting;
- company-GUID grouping and evidence-register traceability;
- Annex A conservative matching with no fuzzy or invented categories;
- rating-triggered provisional priority and operator-controlled final-priority status;
- pagination filter preservation, multi-page traversal, stable-identity deduplication, non-advancement/loop detection, deterministic ordering, empty results, and cap termination;
- company history cannot silently replace alert-derived movement.

A bounded read-only production run must supplement deterministic tests. It must report its tested window, filters, limits, source/retained/excluded/duplicate counts, and completeness status. Representative output must be compared with the BitSight UI and the process semantics. This live proof establishes only the exercised behavior and must not be described as universal coverage.

## Completion Bar

The Brief is complete only when the normal CLI/API path works without monkeypatches or visibility bypasses and returns company-grouped, trustworthy Jira-action timeline evidence with explicit limits and exclusion accounting.

A collector that merely downloads alerts does not complete this Brief. Fixture-only success does not complete this Brief. Jira-shaped JSON that loses envelope-specific movement, invents category certainty, silently substitutes company history, contaminates stdout, or treats a capped page as complete is technically done but still wrong.

## Preserved Remainder

After this First Useful Step, the larger workflow still requires live Jira lookup/create/append with issue IDs and links, existing-ticket updates independent of new alerts, rating-recovery closure checks, due-ticket review and management summaries, broader production-envelope and category coverage, and best-effort finding correlation where useful.

This Brief sequences those capabilities; it does not reject or replace them.
