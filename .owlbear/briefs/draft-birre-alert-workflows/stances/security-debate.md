# Security Debate Notes

## Initial Security Position

The initial stance treated BitSight alert/finding/company data as sensitive business/security data, recommended a read-only first module, favored a dedicated workflow tool surface, deferred Jira mutation, recommended a minimal future ledger, and warned against raw payload persistence, broad v2 exposure, Jira credential blast radius, and management-summary leakage.

## Critic Cycle 1

The critic found the direction sound but identified three load-bearing gaps.

Critical challenges:

- The stance contradicted itself by calling the first module read-only while also implying a local ledger with decision timestamps.
- The dedup/idempotency story depended on stable alert identity, but the available findings did not prove stable alert `guid` semantics.
- Prompt injection was absent even though alert detail fields and future finding remediation text are externally authored content that may flow into agents.

Moderate challenges:

- Deterministic classification was framed too strongly as a security requirement even though the real control is gated mutation and audit.
- Management-summary leakage was under-specified because MCP tool output naturally enters client transcripts/logs.
- Company enrichment was treated as safe despite being sensitive bulk posture data.
- BitSight credential blast radius was ignored while Jira credential risk was emphasized.

Revision after cycle 1:

- First module was explicitly scoped as read-only with no durable ledger writes.
- Stable alert identity was downgraded to an unverified assumption; only in-run deduplication remains acceptable for module one.
- Prompt injection and untrusted source text were added as explicit risks.
- Management summaries were treated as transcript/log-visible when emitted through MCP.
- BitSight credential blast radius was added.
- Determinism was reframed: the security invariant is gated mutation and traceability, not deterministic classification by itself.

## Critic Cycle 2

The critic judged the revised stance materially stronger, but found two coherence problems and several verification gaps.

Blocking challenges:

- The stance said every trust boundary needs audit while also forbidding module-one ledger writes. This made read-only module scope conflict with a durable-audit invariant.
- The stance warned about MCP summary leakage but did not apply the same reasoning to the first module's normalized alert/company batch, which is also sensitive MCP output.

Moderate challenges:

- BitSight least-privilege token scoping was conditional on a vendor capability not yet verified.
- Logging requirements were asserted without confirming current BiRRe logging/error behavior.
- Prompt-injection defense was assigned partly to module one even though prompt construction happens downstream.
- In-run dedup ambiguity reporting still leaves authority for ambiguity resolution to be designed.

Revision after cycle 2:

- The final stance distinguishes durable audit from non-durable read-only traceability. Module one remains non-mutating and does not write a ledger; durable audit is required before Jira/local-state mutation workflows begin.
- MCP output is now treated as a disclosure boundary for both normalized batches and summaries.
- Output minimization applies to the first module, not only management summaries.
- BitSight credential scoping is stated as a control only where supported; otherwise the residual risk must be documented and compensated locally.
- Logging and error redaction are listed as verification requirements rather than assumed current behavior.
- Prompt-injection control is assigned to downstream prompt construction and action gating, while module one must preserve untrusted text as data only.

## Final Debate Outcome

The final position keeps the first roadmap module deliberately narrow: fetch and normalize bounded BitSight alert data, enrich bounded distinct companies, return minimized sensitive output, and stop before durable local state or Jira mutation.

The security review rejects broad alert-tool exposure, raw payload dumping, implicit trust in MCP clients/agents, unverified cross-run idempotency, and Jira mutation before scoped credentials and audit exist.

Confidence after debate: 0.78.
