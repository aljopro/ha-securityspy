# PRD Quality Review — Home Assistant Integration for SecuritySpy

## Overall verdict

This is a strong, decision-dense PRD that knows exactly what it is: a launch-grade capability spec with a clear thesis (the Observation Record as restart-correct state derived from Capture History, not event accumulation) and an honest ledger of what it doesn't know (ten Open Questions, three indexed assumptions, gated FR-35). What's at risk is narrow but real: a handful of FR consequences use unbounded language ("repeated failures," "bounded time," "period of inactivity") that story creation will have to invent numbers for, and two of those are in the Resilience section — the feature the PRD itself calls the one "that separates an integration people keep from one they uninstall."

## Decision-readiness — strong

Decisions are stated as decisions, with the rejected alternative named. §5.4 ("Home Assistant writes only the Arm Override, never the Arm Schedule... writing a schedule would destroy configuration") is a decision with its cost stated; the addendum §5 records the rejected options explicitly ("Rejected: full three-dimensional control... defer-to-architecture"). §7.2 de-scopes honestly rather than silently, including admitting deferrals are "emotionally load-bearing." Open Questions are genuinely open — Q2 (lookback window) and Q3 (classification timing) have no smuggled answers, and Q9 (contact the fork maintainer) surfaces a socially awkward decision most PRDs would omit. `[NOTE FOR PM]` callouts sit at real tensions (FR-4 lookback, FR-35 spike gate), not safe checkpoints.

No findings.

## Substance over theater — strong

No persona theater: §3 uses Jobs To Be Done plus four UJs, all of which drive requirements (UJ-4 alone generates FR-30…FR-33). NFRs are product-specific to the point of citing measurements: "191 signals on one camera in 95 seconds" (§5.2), "794 bytes versus 27 KB" (§11.1), "467 motion signals and zero end signals" (FR-7). The competitive section (§9) earns its place by conceding "there is no technical moat" and naming the active fork's real contributions rather than strawmanning it. The Vision (§1) could not swap into another PRD — "eleven cameras... contributing zero non-camera entities" is this product's problem statement and no other's.

No findings.

## Strategic coherence — strong

The thesis is explicit and repeated with discipline: "state that outlives the process observing it" (§5.1), "the stream is... a latency optimization, not a source of truth" (§11.3). Release Shape (§12) prioritizes by dependency and permanence ("identity decisions made here are permanent"), not by ease. Success Metrics validate the thesis directly — SM-1 is literally the Vision's driveway question — and four counter-metrics (SM-C1…C4) exist with named counterbalances, including the unusual and correct SM-C4 ("do not optimize for install count") tied to the maintainer-fatigue risk in §10.2.

No findings.

## Done-ness clarity — adequate

Most FRs are exemplary: consequences are concrete, falsifiable, and occasionally carry their own test fixture ("A 95-second single-person episode producing ~190 Classification Signals produces exactly one Classification Event," FR-6). But a cluster of consequences use bounded-sounding language with no bound, and these will force story authors to invent thresholds:

### Findings
- **medium** Unquantified reauthentication trigger (§5.7 FR-27) — "reauthentication triggers only after repeated failures" gives no count or window; an engineer cannot distinguish two failures from twenty, and the difference is user-visible (spurious reauth prompts vs. silent stall). *Fix:* state a threshold or explicitly delegate the number to architecture with a named Open Question.
- **medium** Unbounded "bounded time" for loss detection (§5.8 FR-31) — "detected within a bounded time via the absence of the server's periodic heartbeat" never states the bound, though the heartbeat interval is presumably known from research. Downstream tests cannot assert detection latency. *Fix:* express the bound as a multiple of the heartbeat interval (e.g., "within N missed heartbeats") even if N is provisional.
- **medium** Motion clear timeout unspecified (§5.2 FR-7) — "clears on its own after a period of inactivity" names no default, no configurability, and unlike FR-8's threshold/debounce it is not covered by the tuning FR or the Assumptions Index. *Fix:* either fold the motion timeout into FR-8's configurable tuning or state a shipped default and tag it `[ASSUMPTION]`.
- **low** Soft latency bound (§11.1) — "within a few seconds, dominated by Detection Debounce" is honest about the dominating term but "a few" is untestable as written. Low because the debounce dependency makes a hard number genuinely conditional. *Fix:* restate as a formula: transport latency ≤ X, total = debounce window + X.

## Scope honesty — strong

This is the PRD's best dimension. §6 Non-Goals does real work (each entry names what a reader might otherwise assume: "Not a competitor to HomeHelper... users may run both"). §7.2 de-scopes with reasons and hazards attached ("disk-fill hazard, since generated clips persist on the server until deleted"). FR-35 is the model of an honestly gated requirement: "conditional on a discovery spike... If the payload proves unusable... FR-35 defers to v2 and FR-34 alone ships." Open-items density (10 Open Questions + 3 assumptions + several PM notes) is appropriate for a green-light PRD because only one item (Q1) blocks anything, and the PRD says so: "*Blocking for FR-35 only.*"

No findings.

## Downstream usability — strong

Chain-top PRD feeding architecture and epics, and built for it: the Glossary (§4) is declared binding ("Introducing a synonym anywhere is a discipline violation") and is actually honored — "Detection Episode," "Capture History," "Arm Override" are used verbatim throughout, and §5.5's note explicitly polices the nearest ambiguity ("These are SecuritySpy's own sensitivities, distinct from the integration's Detection Threshold"). FR-1…FR-42 are contiguous with no gaps or duplicates; every "Realizes UJ-n" and "Validates FR-n" reference resolves. Release Shape maps phases to FR ranges, giving epic creation a ready skeleton. The addendum cleanly separates implementation depth (exact Bronze/Silver rule names, blueprint import URL mechanics) so the PRD stays extractable.

### Findings
- **low** Phase/FR mapping small overlap ambiguity (§12) — Phase 1 claims "FR-19…FR-31" which includes FR-30/FR-31 (Resilience) but Phase 1's prose lists only "availability"; full recovery (reconciliation against Capture History) depends on Phase 2's Observation Record. Epic creation may sequence FR-31's reconciliation consequence before its dependency exists. *Fix:* split FR-31's reconciliation consequence to Phase 2/3 or note the dependency in Phase 1.

## Shape fit — strong

Correct shape for the product: a solo-built, public-distribution integration rendered as a capability spec with exactly four UJs, each with a named protagonist (Jensen ×2, Priya, and the deliberately unattended UJ-4) and each load-bearing. The PRD resists both over-formalization (no persona gallery, no revenue metrics) and under-formalization (launch-grade rigor on identity permanence, quality scale, and credential safety is exactly right for public HACS distribution where "identity decisions are effectively permanent"). The addendum is the right pressure valve — mechanism detail exists but is kept out of the product document by explicit policy (§0, addendum §6).

No findings.

## Mechanical notes

- **Assumptions Index roundtrip:** entries 1–3 round-trip to inline `[ASSUMPTION]` tags (FR-8, FR-35, §11.5). Entries 4 and 5 are labeled "inferences worth naming" with no inline tag at §8 SM-C4 or §5.10 FR-37 — deliberate and disclosed, but a strict roundtrip check will flag them. Harmless.
- **ID continuity:** FR-1…FR-42, UJ-1…UJ-4, SM-1…SM-9 + SM-C1…C4 — contiguous, unique, all cross-references resolve.
- **Glossary drift:** none found; capitalized glossary terms are used consistently, including in consequences.
- **UJ protagonists:** all four named/characterized; UJ-4's "Unattended" framing is intentional and works.
- **Cross-document refs:** relative links to brief, API reference, and architecture-implications are consistent between prd.md and addendum.md; not verified on disk.
