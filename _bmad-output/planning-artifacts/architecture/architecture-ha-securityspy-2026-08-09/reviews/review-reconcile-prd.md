# Reconciliation Review — PRD vs ARCHITECTURE-SPINE

- Reviewed: 2026-08-09
- Inputs: prd.md, addendum.md (prd-ha-securityspy-2026-08-09), ARCHITECTURE-SPINE.md
- Method: every FR-1..FR-45, §10 constraint, §11 NFR, glossary discipline, and quiet requirement checked against the spine's ADs, conventions, stack, seed, capability map, and Deferred list. An item counts as "landed" if the spine decides it, defers it explicitly, or maps it to a home.

## Verdict

The spine is substantially complete — all 45 FRs are at least mapped, the two-plane invariant directly encodes the PRD's core reliability doctrine, and glossary discipline is captured. But roughly a half-dozen requirements did NOT land, the most consequential being the Silver-gates-announcement rule, camera-entities-disabled-by-default (FR-22 / SM-8), and the blueprints-as-design-test bar. No hard contradictions found.

## Gaps — HIGH (a PRD requirement the spine neither decides, defers, nor maps)

1. **Silver-gates-announcement (FR-39) is absent.** AD-14 wires "Bronze verified on every change" into CI but nothing in the spine records that public announcement is gated on the full Silver rule set (>95% coverage, entity-unavailable, log-when-unavailable, reauthentication-flow satisfied) — the reviewer-gate decision the addendum (§5) calls out as resolving a death-pattern finding, and one CI/release-process design must honor.

2. **FR-22 camera entities disabled by default is nowhere stated.** The seed includes `camera.py` and the capability map covers FR-19..24, but no AD or convention says the live-video entity ships `entity_registry_enabled_default = False` — the single mechanism protecting the ONVIF-coexistence constraint (§10.3, SM-8) and the "fresh install adds no enabled camera entities" consequence.

3. **Blueprints-as-the-design-test bar (§5.10, §12 Phase 5) did not land.** The spine places blueprints in the seed and maps FR-37, but omits the quiet requirement that an awkward blueprint falsifies the entity model and that an early blueprint draft against the Phase-3 entity surface is required — a sequencing/validation constraint the architecture is the natural home for.

4. **Entity categorization requirements (FR-12, FR-17, FR-23) are unmapped.** The PRD requires arming and Detection Trigger controls categorized as configuration and health values as diagnostic ("diagnostic entities do not appear among primary controls"); the spine's conventions table has no `entity_category` convention and no AD covers it.

## Gaps — MEDIUM (constraint or consequence with no spine home)

5. **§10.1 destructive/remote-execution endpoints "out of scope entirely" is not carried into the library contract.** AD-2 gives the library all protocol knowledge but nothing forbids `aiosecurityspy` (an independently usable package) from exposing capture deletion or shell/shortcut execution; the exclusion should bind the library surface, not just the integration.

6. **§10.1 least-privileged SecuritySpy user documentation** (also §11.2) has no home — no AD, convention, or docs note requires it, xand it is a Bronze/Silver docs deliverable.

7. **FR-13's transience disclosure did not land.** AD-7 correctly restricts writes to the Arm Override, but the PRD's testable consequence that the override's bounded lifetime (≤6 h or next scheduled event) must be reflected in control behavior and documentation — not implying an indefinite HA-set state — appears nowhere.

8. **FR-30 per-camera unavailability is undesigned.** AD-11 maps server/stream loss to entity availability, but the PRD's consequence that a single offline camera (server still reachable) makes only that Camera Device's entities unavailable has no mechanism (no per-camera health→availability path is named).

9. **Addendum §1: Gold `dynamic-devices` / `stale-devices` "worth honoring in the Phase-1 device model"** — the spine neither adopts nor defers dynamic camera addition/removal handling; AD-5's identity scheme permits it but nothing decides it, and the addendum flags it as expensive to retrofit.

## Gaps — LOW (small consequences, worth a line somewhere)

10. **FR-45 dismissibility/non-recurrence** — `repairs.py` covers the trap, but the "dismissible, does not recur once any trigger is enabled" behavior is unstated.
11. **FR-11 empty-set-vs-absent semantics** for an unclassified capture is not in the event/attribute conventions (which cover `capture_ref` nullable but not the image entity's class set).
12. **§10.3 "must not assume it is SecuritySpy's only client"** (HomeHelper/iOS/web concurrent) — no spine statement; mostly free given AD-8's partial POSTs, but the concurrency assumption is never recorded.
13. **FR-24 "does not install updates in v1"** — `update.py` exists in the seed; the read-only constraint on the update entity is unstated.
14. **FR-44 distinct failure modes** (no recording / destination unwritable / permission) map to AD-6 generically, but the destination-write path (HA-side filesystem, allowlist_external_dirs) is undesigned.

## Contradictions

None found. Two near-misses checked and cleared:
- AD-10's `[ASSUMPTION: lookback 7 days]` *decides* PRD Open Q2 rather than contradicting it — legitimately tagged as an assumption.
- AD-4's `update_interval=None` coexists with AD-10's "slow fallback interval" because the adapter schedules polls itself; internally consistent and consistent with `iot_class: local_push`.

## Verified-landed highlights (for confidence, not action)

- Glossary verbatim discipline: conventions table, "Docs vocabulary" row.
- FR-42/§11.2 credential containment: AD-13, including settings-payload-never-logged.
- §11.1 190:1 reduction and cameras×classes fan-out: AD-3, AD-10.
- FR-27's three-consecutive-failures assumption: adopted verbatim in AD-6.
- FR-34/35 open vocabulary + spike gating: AD-9 + Deferred.
- §11.5 min-version enforcement: `SecuritySpyUnsupportedVersionError` + Deferred floor verification.
