# BiRRe Real Alert Validation Decisions

## D1 - 2026-07-11 - Project Type

**Status quo:** The alert-to-Jira-action workflow has an approved brief, decomposed implementation plan, and implemented CLI/API core, but only fixture-based validation is currently visible.

**Decision to make:** Is the next discovery net-new work, an existing-feature/refactor, or uncertain?

**Options considered:**

- Net-new: begin a separate Jira or data-processing capability.
- Existing-feature/refactor: validate the implemented alert workflow against real BitSight behavior and use evidence to choose the next plan.
- Uncertain: research several possible roadmap branches without an anchor.

**Chosen:** Existing-feature/refactor.

**Rejected:** Net-new Jira setup and broad uncertain exploration, because real alert behavior is the highest-impact unresolved dependency for all downstream ticket work.

**Source inputs:**

- User selected real BitSight alert validation as the probable next direction.
- User confirmed new configured alerts are visible in the BitSight UI and offered authenticated browser comparison.
- Local code contains the implemented read-only `security-analyst-alerts` workflow.

## D2 - 2026-07-11 - Discovery Rigor

**Status quo:** This is a narrow real-data validation pass for an internal workflow whose output will later influence Jira company-watch tickets and lifecycle decisions.

**Decision to make:** How much evidence and challenge should the validation require?

**Options considered:**

- Scratch: one-off smoke test.
- Tool: focused API/UI comparison with a concise validation record.
- Shared: several representative alert shapes, explicit API/UI comparison, challenge checks, and a reusable research bridge.
- Production: formal review at every boundary.

**Chosen:** Shared.

**Rejected:** Scratch and Tool, because one successful response may conceal date-window, historical-alert, or schema gaps. Production is disproportionate for the current internal pre-production workflow.

**Source inputs:**

- User selected Shared rigor.
- The parent alert workflow was also shaped at Shared rigor because ticket classification and lifecycle decisions have operational consequences.

## D3 - 2026-07-11 - Finding Link Expectation

**Status quo:** BitSight alerts are event-table rows with no alert detail page. Findings are separate objects that may be opened, but the v2 alert payload does not directly expose a finding identity in the sampled risk-category shape.

**Decision to make:** Must every Jira company-watch action contain a direct BitSight finding link?

**Options considered:**

- Required for every ticket.
- Required only for finding-backed actionable events.
- Best effort when a stable correlation can be derived.
- Not needed initially.

**Chosen:** Best effort.

**Rejected:** Making the link a ticket-creation blocker, because alert events and rating/grade movement already provide useful company-watch evidence while stable finding correlation remains unproven.

**Source inputs:**

- User selected best-effort finding links.
- User confirmed alerts cannot be opened, while findings can.

## D4 - 2026-07-11 - First Useful Step and Preserved Promise

**Status quo:** Live evidence exposed several connected correctness gaps, while the larger alert-to-Jira workflow still includes ticket creation, updates, closure, and reporting.

**Decision to make:** What should the next useful delivery prove without silently replacing the larger product promise?

**Options considered:**

- Fix only one defect class, such as operation wiring or detail-field mapping.
- Validate a complete real-alert correctness bundle, then continue to Jira and lifecycle capabilities.
- Expand immediately into Jira connectivity or finding correlation.

**Chosen:** Validate the complete real-alert correctness bundle: generated alert-operation exposure/name, real start/end field normalization, before/after propagation into timeline evidence, category/risk-vector mapping for scoring, and bounded pagination/date-window proof.

**Rejected:** A single-defect repair, because it could produce plausible but incorrect Jira-shaped output. Immediate Jira or finding expansion is sequenced later because the deterministic action payload must first be trustworthy.

**Preserved remainder:** Live Jira lookup/create/append and issue results; existing-ticket updates; rating-recovery closure checks; due-ticket management summaries; broader category validation; and best-effort finding correlation.

**Source inputs:**

- User confirmed the corrected First Useful Step and expectation framing.
- Simplification, first-principles, and expectation-fidelity checks all supported separating immutable alert evidence from company-watch and Jira lifecycle state.

## D5 - 2026-07-11 - Phase 2 Review Coverage

**Status quo:** The dominant correction path touches production wiring, real-schema normalization, and the analyst-facing timeline. Existing constraints already bound credential handling, raw evidence retention, and read-only validation.

**Decision to make:** Which domain reviews should evaluate the correction path before approach selection?

**Options considered:**

- Architecture, data, user experience, and security.
- Architecture, data, and user experience.
- A custom review roster.

**Chosen:** Architecture, data, and user experience.

**Rejected:** A separate security review for this step, because the work remains within an existing read-only BitSight trust boundary and the discovery already constrains credentials and retained evidence. Security review can return if the scope expands into Jira writes, durable raw payload storage, or broader access.

**Source inputs:**

- User selected review without security.
- Landscape signal: structural wiring, schema fidelity, and timeline clarity are the active decision risks.

## D6 - 2026-07-11 - Timeline Movement Display

**Status quo:** BitSight presents numeric rating transitions and letter-grade risk-vector transitions in the same event table. The working Jira draft also exposes a numeric score-change value.

**Decision to make:** How should both movement types coexist in the analyst-facing timeline without implying false numeric equivalence?

**Options considered:**

- A: Typed movement with an optional rating-only numeric delta.
- B: Typed endpoints only, with no delta.
- C: Separate movement and score-change columns, leaving grade deltas blank.

**Chosen:** Typed movement with an optional rating-only numeric delta, for example `Rating: 630 -> 620 (-10)` and `Risk-vector grade: B -> C`.

**Rejected:** Endpoints-only presentation because it discards a useful numeric signal from rating events. A separate score-change column because systematic blanks on grade rows could read as missing evidence and weaken the type distinction.

**Source inputs:**

- User selected option A.
- End-user review favored one chronological movement column; architecture and data reviews require rating and grade movement to remain distinct typed evidence.

## D7 - 2026-07-11 - Invalid Evidence Handling

**Status quo:** External alert records may be incomplete, contain conflicting human labels, use unsupported categories, or be structurally malformed. The reviews agree such records must not enter deterministic scoring as valid evidence.

**Decision to make:** Should non-valid records appear in the analyst-facing timeline?

**Options considered:**

- A: Keep identifiable incomplete or conflicting events as unscored review rows; send malformed records to diagnostics.
- B: Show every returned record with warning markers.
- C: Include valid events only.

**Chosen:** Include valid events only in the analyst-facing timeline. Incomplete, conflicting, unsupported, and malformed records do not become timeline rows and receive no priority score.

**Rejected:** Review rows and show-everything behavior because the user prefers a strict timeline containing only validated evidence.

**Required accounting:** Exclusion counts and sanitized reason codes remain machine-visible in run metadata so the absence of invalid rows cannot be mistaken for complete source validity. Raw identifying payloads are not required for that accounting.

**Source inputs:**

- User selected option C.
- Data and architecture reviews require malformed or conflicting evidence to stay outside deterministic scoring.

## D8 - 2026-07-11 - Provenance Placement

**Status quo:** Timeline rows need traceable source evidence, but full alert GUIDs, envelope details, start dates, and source fields would overwhelm the compact Jira-oriented table.

**Decision to make:** Where should provenance live in the first Jira-action payload?

**Options considered:**

- A: Compact source token in each timeline row plus a structured evidence register.
- B: Full provenance inline in every row.
- C: Provenance only in machine metadata, absent from proposed Jira content.

**Chosen:** Compact source token plus structured evidence register.

**Rejected:** Full inline provenance because it would make the timeline a debug surface. Metadata-only provenance because an analyst-facing row should remain traceable without separate tooling.

**Source inputs:**

- User selected option A.
- End-user review proposed readable source tokens with adjacent source details; architecture and data reviews require provenance to survive projection.

## D9 - 2026-07-11 - Category Validation

**Status quo:** Real alert envelopes use API types such as `RISK_CATEGORY`, while priority scoring requires human labels such as Open Ports or Web Application Security. Only a bounded subset has been observed.

**Decision to make:** How should category labels enter deterministic priority scoring?

**Options considered:**

- A: Explicit registry with case and surrounding-whitespace normalization only.
- B: Fuzzy aliases using synonyms, punctuation changes, or partial matches.
- C: Exact source strings only.

**Chosen:** Explicit registry with conservative case and whitespace normalization. Known labels map explicitly; unknown or conflicting labels are excluded from the valid-only timeline and scoring, with machine-visible reason counts.

**Rejected:** Fuzzy aliases because incorrect category mapping can silently change priority. Exact raw strings because harmless case or surrounding-whitespace differences should not invalidate an otherwise known label.

**Source inputs:**

- User selected explicit registry.
- Data review requires a conservative canonical registry and no guessed aliases.

## D10 - 2026-07-11 - Broken Baseline Correction

**Status quo:** The implemented production path cannot currently collect trustworthy validation data: the alert operation is hidden and called by the wrong name, normal CLI execution fails, CLI logs interfere with machine-readable JSON, and fixtures use field names and category semantics that do not match real responses.

**Decision to make:** Is the existing Jira-action implementation a usable baseline for incremental output refinement?

**Chosen:** No. Treat restoration of a bounded, machine-readable real alert collector through the production CLI/API path as the first dependency inside the approved correctness bundle. Use that collector to establish sanitized known-good fixtures before relying on downstream normalization, projection, or scoring behavior.

**Rejected:** Treating current fixture success or current Jira-shaped output as evidence that the workflow core is substantially correct.

**Preserved expectation:** The collector is sequencing and validation infrastructure, not the final caller-facing product. The First Useful Step still ends only when the complete real-alert correctness bundle produces trustworthy Jira-action timeline evidence.

**Source inputs:**

- User identified the current CLI and API call as unusable and emphasized that useful known-good data cannot yet be collected.
- Live discovery confirmed operation visibility/naming failure and stdout contamination before real-schema transformation gaps were evaluated.

## D11 - 2026-07-11 - Repair Strategy

**Status quo:** The current module boundaries express a useful read-only workflow intent, but its production wiring, CLI output, fixtures, normalization fields, and category semantics contain multiple disproven assumptions.

**Decision to make:** Patch the existing contracts, replace the flawed slice within existing boundaries, or stop after a standalone collector?

**Options considered:**

- A: Replace the flawed slice in place while retaining useful public intent and module ownership.
- B: Incrementally patch current contracts and fixtures.
- C: Build only a standalone collector and defer transformation/output work.

**Chosen:** Replace the flawed slice in place. Define contracts from the real schema outward: restore the production collector, establish sanitized known-good fixtures, then implement typed normalization, projection, and scoring. Remove obsolete assumptions instead of preserving compatibility with them.

**Rejected:** Incremental patching because it would preserve known-wrong fixture and payload contracts. Collector-only delivery because it would silently shrink the approved First Useful Step into validation plumbing.

**Source inputs:**

- User selected option A.
- Architecture, data, and end-user reviews converge on separate testable boundaries within one complete correctness bundle.

## D12 - 2026-07-11 - Support Contract Before Fixture Capture

**Status quo:** The selected sequence initially called for fixtures for each supported envelope shape before the supported shapes and validity rules were defined.

**Decision to make:** Should the support contract precede fixture capture or be inferred from captured examples?

**Options considered:**

- A: Define a provisional schema-derived support contract, then capture real examples that confirm or revise it.
- B: Capture broad examples first and infer support from them.
- C: Let support and fixture capture evolve without an initial boundary.

**Chosen:** Define the provisional support contract first. It names envelope discriminators, required and optional fields, validity states, and the initial explicit category registry justified by schema, docs, and observed evidence.

**Rejected:** Fixture-first inference because sampled examples would become the accidental contract. An unbounded iterative approach because it lacks a clear stopping rule.

**Source inputs:**

- User selected option A.
- The synthesis consistency critique identified circular sequencing as material; the finding is validated.

## D13 - 2026-07-11 - Real Sample Acquisition

**Status quo:** The production collector is broken, but direct authenticated read-only BitSight calls are available and have now returned bounded samples for `RISK_CATEGORY`, `RATING_THRESHOLD`, and `PERCENT_CHANGE`.

**Decision to make:** Does this work need a separate fixture certification lifecycle?

**Chosen:** No. Use bounded direct API responses as the source for sanitized, structurally faithful real samples. Record the query and observed envelope coverage, remove credentials and unnecessary identifying values, and do not claim coverage for unseen variants.

**Rejected:** Candidate-versus-certified fixture states as unnecessary process. Repairing the collector before obtaining any real samples is also rejected because direct calls already provide the evidence needed to rebuild it correctly.

**Source inputs:**

- User emphasized that direct API results can simply be provided and authorized use of the locally configured credential.
- Successful bounded calls confirmed three real envelope shapes and pagination counts without retaining identifying raw responses.

## D14 - 2026-07-11 - Polymorphic Envelope Authority

**Status quo:** The bundled OpenAPI enum documents `PERCENT_CHANGE` but omits `RATING_CHANGE`. Production supports both, and each alert envelope carries different detail semantics.

**Decision to make:** May one sampled or documented numeric envelope define movement handling for all alerts?

**Chosen:** No. Normalize and validate by the actual `alert_type` envelope. Initial observed variants are:

- `RISK_CATEGORY`: grade endpoints plus risk vector and threshold grade.
- `RATING_CHANGE`: rating endpoints.
- `RATING_THRESHOLD`: rating endpoints plus rating threshold.
- `PERCENT_CHANGE`: rating endpoints plus percentage change.

Production evidence takes precedence when it contradicts the bundled schema. Unsupported or newly observed envelopes require explicit contract extension rather than fallback to a superficially similar variant.

**Rejected:** Treating `PERCENT_CHANGE` as the only real numeric-change envelope or applying a uniform details contract across all alert types.

**Source inputs:**

- User corrected the uniform-envelope assumption.
- Direct production queries confirmed all four variants and their distinct detail-key shapes.

## D15 - 2026-07-11 - Rating-Triggered Provisional Priority

**Status quo:** The operative process treats score drops and threshold crossings as triggers for assessment, while Annex A exhaustively defines category scoring and the operator ultimately sets event priority through expert judgment.

**Decision to make:** How should rating-triggered actions represent priority before an Annex A category is known?

**Options considered:**

- A: Expose a provisional partial calculation using known components and mark category as pending.
- B: Omit all priority information until category classification is complete.

**Chosen:** Expose provisional priority evidence. Preserve the known tier, score-drop, and correction-factor components; mark the category component as pending; distinguish the result from a final priority. Annex A classification or operator judgment is required before priority becomes final.

**Rejected:** Omitting all priority evidence because the known score movement still carries operational urgency. Inventing an `Other` category or neutral category score is also rejected because Annex A is exhaustive.

**Source inputs:**

- User selected provisional priority.
- `prozess.htm` defines the matrix as decision support and operator expert judgment as the final priority authority.
- `operative_043905.html` defines score drops and threshold crossings as assessment triggers independent of category, and confirms that operational details remain expert-controlled.

## D16 - 2026-07-11 - Final Critic Triage

**Status quo:** The final critical review raised six findings against the selected direction.

**Classification:**

- Material: rating-only envelopes lacked a defined category and priority path. Resolved by D15 using provisional priority with category pending.
- Minor: production-volume grouping was described as undefined. The inherited company-watch contract already groups Jira actions by company GUID; this remains binding.
- Minor: security-review rationale was challenged by fixture and provenance retention. The selected design retains sanitized samples and selected normalized provenance, not full raw payloads or credentials; D5 remains valid for this read-only scope.
- Minor: D13 omitted the later sampled `RATING_CHANGE` envelope. D14 and current research supersede that stale sample list.
- Minor: same-day ordering remains an implementation detail. Deterministic ordering must avoid claiming source precision, but no product trade-off is required.
- Nonsense as framed: the critique treated every rating trigger as requiring an invented risk-vector category before entering the workflow. The operative process proves score movement independently triggers assessment and final priority remains expert-controlled.

**Source inputs:**

- User supplied the authoritative process and operative documents.
- User selected D15 after the process evidence was reviewed.

## D17 - 2026-07-11 - Brief Approval and Handoff Pause

**Status quo:** The product promise, collection contract, timeline and priority semantics, and validation bar were approved during the Brief walkthrough.

**Decision to make:** Should the approved Brief proceed immediately to Kanban task creation and shaping?

**Chosen:** Write `brief.md` as the binding product promise, then pause. Do not create a Kanban task and do not dispatch the shaper.

**Rejected:** Immediate pipeline handoff.

**Source inputs:**

- User: "approve and write brief, do not create a task or dispatch shaper".
