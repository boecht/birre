# BiRRe Alert Workflow Discovery Decisions

## D1 - 2026-07-06 - Project Type

**Status quo:** BiRRe is an MCP server focused on curated interactive BitSight tools.

**Decision to make:** Should the expanded alert/ticket/summary workflows live inside BiRRe, in a new project, or be split?

**Options considered:**

- A: Implement everything in BiRRe.
- B: Create a new automation project and treat BiRRe as the BitSight integration layer.
- C: Extend BiRRe with deterministic BitSight workflow primitives and keep ticket storage/sync plus scheduling/orchestration outside or in an adjacent package.

**Chosen:** Existing-feature/refactor.

**Rejected:** Net-new wrapper/orchestrator for the first framing pass, because the deterministic BitSight retrieval/enrichment/classification work fits BiRRe's existing business-tool-over-API-orchestration architecture.

**Source inputs:**

- User's current need has shifted from interactive API use toward three automated workflows for alerts, ticket lifecycle review, and management summaries.
- Local repo evidence shows BiRRe already implements business tools that orchestrate hidden BitSight API calls.

## D2 - 2026-07-06 - Discovery Rigor

**Status quo:** The workflows are personal/team operational tooling, not a public product.

**Decision to make:** How rigorous should the ideation pass be?

**Options considered:**

- Tool: standard discovery for a single-user/internal utility.
- Shared: stronger discovery and challenge pass for a reusable operational workflow.
- Production: stricter review gates for a durable operational system.

**Chosen:** Shared.

**Rejected:** Tool, because the queue/ticket lifecycle and priority schema have enough state and consequence to justify stronger framing. Production, because this is not currently scoped as an external-facing or fully governed system.

**Source inputs:**

- User selected Shared rigor.

## D3 - 2026-07-06 - Ticket and Queue Boundary

**Status quo:** BiRRe has no internal durable alert queue, documentation ticket store, or Jira integration today.

**Decision to make:** Should BiRRe own alert queue state, ticket state, Jira interaction, or only deterministic BitSight enrichment/classification primitives?

**Options considered:**

- A: Internal alert queue in BiRRe; agent calls a `work on next item` style tool.
- B: No internal queue; return today's alerts as a batch and let an agent/runner split and process them.
- C: Use Jira directly as ticket source of truth, with no separate internal ticket store.
- D: Add a generic ticket-system interface.

**Chosen:** Pending.

**Rejected:** Generic ticket-system interface for now, because the concrete workflow is Jira and KISS/YAGNI favors implementing the real integration when needed instead of abstracting before a second ticket system exists.

**Working challenge:** Internal queue is not rejected, but it is not yet justified as the first foundation. It should be added only if the workflow needs durable retry, deduplication, locking/leases, resume-after-crash, or ordering semantics that a batch plus stable work-item IDs cannot provide.

**Source inputs:**

- User is unsure about internal queue storage, but sees value in a server-managed queue so the agent can call `work on next item in queue` rather than manually split a batch.
- User thinks direct Jira integration may avoid a separate internal ticket store, given Jira is the stable long-term target.
- Simplification check recommended delaying the queue and starting with batch-in, structured-work-items-out primitives.
- First-principles check separated Jira as ticket source of truth from the still-possible need for minimal local correlation/audit state.

## D4 - 2026-07-09 - First Roadmap Module Candidate

**Status quo:** The larger v5 workflow includes alert intake, Jira existence checks, new-ticket priority calculation, enrichment, ticket create/update, closure review, and due-ticket reporting.

**Decision to make:** What should be treated as the first module on the roadmap without silently collapsing the full workflow promise?

**Options considered:**

- A: Start with BitSight v2 alert intake since an input date.
- B: Start with Jira ticket lookup/correlation.
- C: Start with priority classification and company enrichment.
- D: Start by designing the full queue/ticket lifecycle foundation.

**Chosen:** Candidate first module is BitSight v2 alert intake plus loss-aware normalization since a defined input date: call `GET /alerts` with `alert_date_gte`, `expand=details`, and pagination, then return normalized alert records with stable identifiers, raw/source provenance, and metadata for later correlation.

**Rejected:** Jira lookup first, because there is no ticket to query without an alert/company identifier driving the workflow. Priority/enrichment first, because it depends on alert facts and company GUIDs. Full queue/ticket lifecycle first, because prior challenge output treats queue/state as capability to justify after the batch shape is proven.

**Source inputs:**

- User: first chronological workflow step is "get alerts"; v2 is likely the right API family, but v2 is complementary to v1 rather than a replacement.
- User-provided v2 sample shows `links.next`, `count`, `results`, `alert_date`, `company_guid`, `severity`, `trigger`, and type-specific `details`.
- Local code shows `create_v2_api_server` and `call_v2_openapi_tool` already exist, but current server wiring only exposes v2 tools for `risk_manager` and allowlists company-request operations.
- Local v2 API docs show `GET /alerts` supports `alert_date_gte`, `expand`, `limit`, `offset`, and filters for company/folder/type/severity.

**Open boundary:** This records roadmap sequencing, not the full implementation approach. Phase 2 still needs to decide whether alert intake lives behind a new context, an expanded risk-manager context, a CLI command, or a workflow-specific business tool.

**Challenge result:** Keep the module name and boundary narrow. It should prove that BiRRe can reliably retrieve, identify, deduplicate within a run, and normalize v2 alert facts. It should not calculate final priority, enrich from v1, or mutate Jira unless Phase 2 explicitly chooses to combine those steps.

## D5 - 2026-07-09 - First Module Boundary Refinement

**Status quo:** D4 framed the candidate first module as v2 alert intake plus loss-aware normalization, with v1 company enrichment delayed.

**Decision to make:** Should the first module stop at alert normalization, or include v1 company profile enrichment because the company-info tool already exists?

**Options considered:**

- A: Stop at v2 alert intake and normalization only.
- B: Include v1 company profile enrichment for each distinct company GUID.
- C: Leave the boundary unresolved for Phase 2.

**Chosen:** Include v1 company profile enrichment in the first module, while still stopping before Jira mutation and final priority classification.

**Rejected:** Alert-only output as the preferred boundary, because the existing v1 company-info capability makes the enrichment cheap and directly useful for the first ticket decision. Full classification/ticket creation remains out of the first module.

**Source inputs:**

- User selected `/v2/alerts` as the first endpoint to evaluate.
- User: company-info module already exists, so including it in the first module is likely trivial.
- User: for Jira tickets, company GUID should be the main identity because the alert is the trigger, not the primary thing being tracked.
- User: missing rating-drop/finding-result information appears in the web GUI but has not been found in tested v1/v2 alert endpoints; this should remain an explicit research gap rather than assumed solved.

**Open boundary:** Alert GUID remains important for trigger provenance, deduplication, and audit, but company GUID is the primary subject identity for Jira correlation.

## D6 - 2026-07-09 - First Module Source Evidence Default

**Status quo:** Phase 2 synthesis recommended selected source evidence by default with an optional raw/debug mode, balancing auditability against sensitive-data disclosure and response noise.

**Decision to make:** How should the first alert intake/enrichment module expose BitSight source payloads while the information flow is still being discovered?

**Options considered:**

- A: Include full raw alert/source payloads in every returned batch.
- B: Return selected source evidence by default, with an optional raw/debug mode.
- C: Return normalized fields only.

**Chosen:** Include full raw alert/source payloads in every returned batch for the first implementation.

**Rejected:** Selected-evidence-plus-debug mode for the first implementation, because it adds mode complexity before the required information flow is clear. Normalized-only output, because it risks losing fields that later classification, ticketing, or troubleshooting may need.

**Source inputs:**

- User: starting with full raw output feels easier to implement, and unnecessary fields can be stripped later once the information flow is clear.
- Panel synthesis: source provenance is important for auditability and avoiding silent underdelivery.
- Security review concern remains accepted as a future hardening pressure: later iterations should reduce routine disclosure once the needed fields are known.

## D7 - 2026-07-09 - Alert Date Window and Duplicate Tolerance

**Status quo:** Phase 2 synthesis identified uncertainty around `alert_date_gte` semantics and warned that duplicates or misses are possible without persistent cursor state.

**Decision to make:** Should module one optimize for local duplicate avoidance, or keep the date-window logic simple and let later workflow correlation handle repeated alerts?

**Options considered:**

- A: Caller-supplied lower-bound date/window with no persistent cursor.
- B: Conservative overlapping-window policy with explicit duplicate tolerance.
- C: Persistent cursor/deduplication state in module one.

**Chosen:** Use a simple caller-supplied date/window and accept duplicate/repeated alerts as normal process input. Later ticket correlation and duplicate checking are the correct place to prevent duplicate ticket work.

**Rejected:** Persistent cursor/deduplication in module one, because it over-optimizes the intake module around a problem the wider process can handle. Duplicate downloads/calculations are acceptable compared with the risk and complexity of premature state management.

**Source inputs:**

- User: duplicates are not very harmful because relevant alerts will hit a later duplicate-ticket check, while irrelevant duplicates mostly cost cheap compute time.
- User: the goal is structure followed by improvement toward fit, not perfect local module design on the first try.
- Research gap remains: `alert_date_gte` semantics still need validation, but the first implementation should expose evidence and tolerate repeated records instead of adding cursor state.

## D8 - 2026-07-09 - Security Analyst Context and CLI-Callable Core

**Status quo:** BiRRe currently exposes `standard` and `risk_manager` contexts. v2 OpenAPI server creation exists for `risk_manager`, but alert workflows are not currently exposed. Phase 2 synthesis left the context/tool exposure choice open.

**Decision to make:** Where should the alert workflow capability live, and should it be implemented as MCP-only tooling or as reusable workflow logic with multiple interfaces?

**Options considered:**

- A: Add the alert workflow tool to the existing `risk_manager` context first.
- B: Create a dedicated alert-workflow or monitoring context.
- C: Expose the capability in both an existing context and a new context.
- D: Create a new `security_analyst` context and keep the core workflow callable outside MCP, including from the command line.

**Chosen:** Create a new `security_analyst` context for the operational workflow surface, and design the core alert intake/enrichment logic as reusable application/domain code that can be called from both MCP and CLI interfaces.

**Rejected:** MCP-only implementation, because the first workflow is mostly deterministic and needs little LLM/agent interaction. Adding it only to `risk_manager` is also rejected as the primary direction because the new workflow is role-oriented security-analyst work, not just risk-manager company-request tooling.

**Source inputs:**

- User: new context should be `security_analyst`.
- User: this is not a simple MCP tool; it needs very little LLM/agent interaction and might almost be a script.
- User: there should be an interface before the tool is created that can be called from the command line too.
- Panel synthesis: BiRRe should own the first BitSight-only workflow primitive, while keeping the first module read-only and bounded.

## D9 - 2026-07-09 - Internal Batch vs Jira-Relevant Product Output

**Status quo:** Phase 2 synthesis framed the first useful step as returning a review-ready normalized alert/company batch to the caller, stopping before Jira lookup or mutation.

**Decision to make:** Is the alert/company batch the visible caller-facing product, or internal process data for a workflow whose visible product is Jira-relevant output?

**Options considered:**

- A: Return the normalized alert/company batch as the caller-facing first product.
- B: Keep the batch internal and return a dry-run ticket action plan.
- C: Keep the batch internal and produce structured Jira-relevant data for create/append workflow handling.

**Chosen:** Keep the alert/company batch internal. The visible workflow product should be structured Jira-relevant data: enough information to create or append the right Jira ticket and return ticket identifiers/links or equivalent action results once the Jira step is wired.

**Rejected:** Caller-facing batch output, because the intended user experience is not manual inspection of enriched alerts. The caller should trigger the process and receive Jira-relevant results, with alert intake/enrichment serving as internal stages.

**Source inputs:**

- User: the caller should not receive the internal batch; the process should get new alerts and additional information, inspect Jira, create or append a ticket, and return the Jira ticket ID/link at best with some additional status.
- User: Jira integration should be treated pragmatically as another API, not as a reason to keep the first product at batch-only output.
- Prior decisions: company GUID remains the primary Jira subject identity, alert GUID remains trigger/provenance, duplicates are acceptable because later ticket duplicate checks handle them.

## D10 - 2026-07-09 - Jira Adapter Boundary

**Status quo:** D9 established that the internal alert/company batch is process plumbing and that the visible workflow product is Jira-relevant output.

**Decision to make:** Should the first operational workflow call Jira directly, or first produce structured Jira-action data that a Jira adapter can consume?

**Options considered:**

- A: Direct Jira lookup/create/append in the first operational workflow.
- B: Produce structured Jira-action data first, then wire Jira lookup/create/append as the next adapter step.
- C: Support dry-run and apply modes from the start.

**Chosen:** Produce structured Jira-action data first.

**Rejected:** Direct Jira mutation in the first step, because the deterministic workflow core and action contract should be testable before external writes. Supporting both dry-run and apply modes from the start is deferred because it adds interface complexity before duplicate/correlation rules stabilize.

**Source inputs:**

- User selected structured Jira-action data first.
- Prior decision: core alert workflow logic should be CLI-callable and not trapped inside MCP wrapper code.
- Process goal: Jira ticket IDs/links remain the target visible result once the adapter is wired, but the first implementation should stabilize the structured action payload first.

## D11 - 2026-07-09 - Jira Correlation Key and Ticket Subject

**Status quo:** Prior decisions established company GUID as the primary subject identity and alert GUID as trigger/provenance, but the first Jira-action duplicate/correlation key was still open.

**Decision to make:** What should determine whether new alert-derived workflow data creates a new Jira action or appends to an existing company watch?

**Options considered:**

- A: Company GUID only.
- B: Company GUID plus alert type/risk vector.
- C: Company GUID plus individual alert GUID.
- D: Wait for final priority/finding identity before defining the action contract.

**Chosen:** Company GUID only for the first correlation key.

**Rejected:** Alert- or risk-vector-centered correlation, because the workflow is not primarily about resolving the specific alert or finding behind the alert. The alert is a trigger to review company performance and determine whether there is a one-time slip or a downward trend.

**Source inputs:**

- User: the goal is not to work on an alert; the alert triggers a look at company performance.
- User: watching stops when the rating goes back to normal.
- User: this is not just about resolving the finding behind the alert.
- Prior decisions: duplicate alerts are acceptable because ticket correlation handles repeated process input.

## D12 - 2026-07-09 - Rating-Aware Jira-Action Contract

**Status quo:** Critical review flagged that a company-watch workflow needs rating/baseline evidence, otherwise the structured Jira-action data risks being the internal alert batch renamed.

**Decision to make:** What rating evidence is required in the first structured Jira-action data?

**Options considered:**

- A: Minimal company-watch action with company GUID, current rating, raw alerts, and proposed Jira summary/body fields.
- B: Rating-aware company-watch action using alert-derived rating movement plus current company rating.
- C: Full watch action with separate trend analysis, finding enrichment, priority classification, and create/append/suppress recommendation.

**Chosen:** Rating-aware company-watch action using alert-derived rating/category movement and current company rating.

**Rejected:** Separate trend/baseline lookup as a required first-action dependency, because each relevant alert already implies a rating/category movement. Full watch logic is deferred until the first action contract is proven.

**Source inputs:**

- User: every alert has a rating change implied; a category drop from A to C can be translated into a points drop.
- User: company-info enrichment provides the current rating, so the action can combine alert-derived rating movement with current company state.
- User: the ticket should be able to include a table with event date, seen-at/date fields, rating drop amount, and rating after.
- Critical review: the company-watch product needs mechanism, not just watch language.

## D13 - 2026-07-09 - Runtime Caps Configuration

**Status quo:** The workflow accepts duplicate/repeated alert input and full raw/source payloads in the first implementation, so runtime caps are needed mainly to prevent unexpectedly large BitSight responses and long CLI/MCP runs.

**Decision to make:** What alert pagination and company-enrichment caps should module one use?

**Options considered:**

- A: Conservative defaults such as 100 alerts per page, 5 pages, and 100 distinct companies, with override flags.
- B: Larger defaults such as 500 alerts per page, 10 pages, and 500 distinct companies, with override flags.
- C: No default caps; require caller-supplied limits every time.
- D: Configurable caps with conservative defaults, likely 50 alerts per page, 10 pages, and 100 distinct companies.

**Chosen:** Make caps configurable, with conservative defaults. Initial target defaults are 50 alerts per page, 10 pages, and 100 distinct companies, unless implementation evidence supports the equivalent 100/5/100 shape.

**Rejected:** No default caps, because the workflow should remain ergonomic. Large defaults are deferred until real response sizes and runtime behavior are known.

**Source inputs:**

- User: make it configurable; start with the proposed 100/5/100 or maybe lower with 50/10/100.
- Prior decisions: duplicate input and full raw payloads are acceptable, but should not create surprise huge runs by default.

## D14 - 2026-07-09 - Priority Gate for Alert-Driven Jira Actions

**Status quo:** The structured Jira-action contract includes rating-aware company-watch evidence, but the Brief review identified that it still needs a priority gate so low-priority alert findings do not drive unnecessary Jira create/search work.

**Decision to make:** Should the first Jira-action payload calculate priority and filter low-priority alert-driven actions?

**Options considered:**

- A: Do not calculate priority in the first action payload.
- B: Calculate priority and use a configurable maximum returned priority threshold for alert-driven new-ticket actions.
- C: Calculate full priority and final ticket decisions immediately.

**Chosen:** Calculate priority for alert-driven action candidates and make the maximum returned priority configurable. Priority 4 findings should be filterable so they do not trigger new ticket creation/search work.

**Rejected:** No-priority action output, because ticket creation is tied to priority. Full final ticket decisions remain deferred until Jira adapter behavior is implemented and tested.

**Source inputs:**

- User: the action payload should probably calculate priority and filter priority 4 findings.
- User: a configurable maximum priority level returned may be better.
- User: filtering alert-driven creation/search should not prevent existing tickets from being updated, since existing-ticket updates do not use alerts.

## D15 - 2026-07-09 - Rating Movement Evidence Precedence

**Status quo:** D12 defined rating-aware Jira-action data using alert-derived rating/category movement plus current company rating.

**Decision to make:** Should company rating history from company-info enrichment also contribute to rating-drop evidence?

**Options considered:**

- A: Use only alert-derived rating/category movement.
- B: Use company rating history only as validation.
- C: Use both alert-derived movement and company history, with precedence rules.

**Chosen:** Use both alert-derived movement and company rating history. If company history shows a bigger relevant drop, use that. Otherwise use the alert-derived drop. If alert-derived drop is unavailable, use the history drop when present.

**Rejected:** Alert-only evidence, because company info includes rating history over multiple weeks or months and can validate or strengthen the rating movement. History-only evidence is also rejected because alerts are still the workflow trigger and source provenance.

**Source inputs:**

- User: company info returns a full history over multiple weeks or months.
- User: even if history includes non-alert updates such as improvements, it should at least validate alert-derived movement.
- User: if history has a bigger drop, use that one; otherwise use the derived alert drop; if alert-derived drop is unavailable, use history drop if any.

## D16 - 2026-07-09 - API-First Interface and MCP Debug Exposure

**Status quo:** D8 selected a `security_analyst` context and CLI-callable core, and the Brief draft implied MCP context exposure for the workflow.

**Decision to make:** Should the workflow be exposed as a normal MCP tool or primarily as deterministic API/CLI functionality?

**Options considered:**

- A: Expose the workflow as a normal MCP tool.
- B: Expose deterministic API/CLI functionality first, with MCP exposure only as a secondary/debug workflow surface if useful.
- C: Keep the workflow CLI-only.

**Chosen:** Expose deterministic API/CLI functionality first. MCP may expose the API, but if a tool exists it should be clearly marked as part of a larger workflow, likely debug/special-mode oriented rather than the main operational path.

**Rejected:** Normal MCP-tool-first framing, because this process needs little LLM/agent interaction and should not encourage treating the internal workflow as a chat-oriented tool.

**Source inputs:**

- User: context may expose this API, but not as a normal MCP tool.
- User: a tool may be acceptable if marked as just part of a bigger workflow, maybe in special debug mode.
- Prior decision: the workflow core should be callable from the command line.

## D17 - 2026-07-09 - Company GUID Requirement

**Status quo:** The Brief draft proposed warnings for alerts missing company GUIDs.

**Decision to make:** Should missing company GUID be treated as a normal expected warning condition?

**Options considered:**

- A: Treat missing company GUID as a normal non-enrichable alert warning.
- B: Treat company GUID as required for relevant alert workflow processing, and only handle missing GUIDs as unexpected schema/API anomalies if encountered.

**Chosen:** Treat company GUID as required for relevant alert workflow processing. Do not design around missing company GUID as a normal expected case unless docs or real responses prove it occurs.

**Rejected:** Normalizing missing company GUID into the standard expected workflow path, because a security alert about a vulnerability in a company without a company GUID is not currently grounded in the available evidence.

**Source inputs:**

- User: a missing company GUID for a company security alert does not make sense and felt like an ungrounded assumption.
- Local research: v2 alert schema includes `company_guid` among response fields.

## D18 - 2026-07-09 - Initial Priority Scoring Logic

**Status quo:** D14 established that alert-driven Jira-action candidates need priority calculation and a configurable maximum returned priority, but the scoring logic was not defined.

**Decision to make:** What priority logic should the first action payload use?

**Options considered:**

- A: Leave priority undefined until a later module.
- B: Use a point system combining supplier criticality, event category, rating change, and a human-factor placeholder.

**Chosen:** Use the point system as the initial priority calculation.

**Scoring inputs:**

- Supplier criticality from external list: criticality 1 = 0 points, 2 = 1 point, 3 = 3 points. If the list is missing or does not contain the supplier, default to 1 point.
- Event category: public disclosure or security incident = -1 point; botnet infection, malware, potentially exploited = 0 points; open ports, patching cadence, server software, insecure systems = 1 point; TLS certificates, TLS configuration, spam propagation, mobile app security, desktop software, mobile software, exposed credentials, web application headers, web application security = 3 points.
- Out-of-scope categories: DNSSEC, DMARC, DKIM, SPF, domain squatting, unsolicited communication, file sharing, and a duplicate/uncertain web application security entry pending clarification.
- Score change: more than 150 rating points = -1 point; more than 100 = 0 points; more than 40 = 1 point; 40 or fewer = 3 points.
- Human factor: many events = 0 points, normal = 1 point, low relevance = 3 points. The first implementation should likely default this to 1 point.

**Priority mapping:**

- Total up to 1 point = priority 0.
- Total 2 points = priority 1.
- Total 3 points = priority 2.
- Total 4 or 5 points = priority 3.
- Total 6 or more points = priority 4.

**Rejected:** Leaving priority undefined, because the alert-driven Jira-action output needs to know which candidates pass the configured maximum priority threshold.

**Source inputs:**

- User supplied the initial point-system rules and priority mapping during Brief review.
- User noted that the external supplier criticality list does not exist yet, so the default supplier criticality score should apply initially.
