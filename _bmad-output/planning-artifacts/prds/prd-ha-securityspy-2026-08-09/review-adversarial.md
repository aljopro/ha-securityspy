# Adversarial Review — PRD: Home Assistant Integration for SecuritySpy

Reviewer stance: cynical, builder-protective. Only findings that should change decisions. Reviewed: `prd.md` + `addendum.md`, 2026-08-09.

**Verdict: The PRD is well-written enough to be dangerous — its prose polish hides that several load-bearing commitments (Silver-at-release, FR-35, self-healing reconciliation, restart-blocking startup) rest on unverified API behavior, an unresolved open question misclassified as non-blocking, and a solo-maintainer capacity it explicitly identifies as the primary risk and then ignores in scoping.**

---

## CRITICAL

### C-1. Open Question 3 is blocking, not open. It gates FR-3, FR-2, and the entire "self-healing" claim — the headline feature.
§13 Q3 ("Is classification written at capture close or later?") is framed as affecting only "whether FR-11 lags FR-9 by one poll." Wrong scope. If classification is written *later* than capture close — or written unreliably, or only when SecuritySpy's own AI pipeline completes — then:
- FR-3's reconciliation ("Observation Record reflects those detections on the next reconciliation") cannot be made testable, because you cannot bound *when* the Capture History becomes authoritative.
- FR-2's "values after restart match values before restart" can fail legitimately: the live Event Stream saw a detection whose Capture has no classification yet, so the pre-restart value (stream-derived) exceeds the post-restart value (history-derived). The PRD's own architecture (§11.3: "persistent state derives from the Capture History, never from Event Stream accumulation alone") makes this contradiction structural, not incidental.
This question must be answered by a spike **before Phase 2 commits**, same status as the FR-35 spike. The PRD gives Phase 2 no spike gate. Reclassify Q3 as blocking for FR-2/FR-3, or weaken FR-2/FR-3's consequences to what an eventually-consistent history can support.

### C-2. FR-39 (Silver at release, >95% coverage) is unsustainable rhetoric for a solo hobbyist, and the PRD knows it.
§10.2 names maintainer fatigue "the primary risk to this product," cites the predecessor's death by fatigue, and defines SM-C3 ("shipping a smaller surface that reaches Bronze beats a larger one that never releases"). Then §5.10 commits to **Silver in full at public release**: >95% test coverage across all modules (addendum §1), 100% config-flow coverage including every abort/error path, `parallel-updates` in every platform, reauth flow, plus a *separately released, CI-built, typed, strictly-checked PyPI library* — for an integration spanning ~10 entity platforms, an event stream reducer, a reconciliation engine, and dynamic entity creation. This is a core-team-sized quality bar assigned to one person with 11 cameras. The internal contradiction is exact: SM-C3 says Bronze-and-ship beats bigger-and-never; FR-39 makes Silver a release gate, i.e., bigger-and-maybe-never. Either demote FR-39 to "Silver within N months post-release" or cut scope elsewhere (Phase 4 control surface is the obvious donor). As written, the most likely outcome is the predecessor's: an unreleased, half-tested surface and a burned-out builder.

### C-3. FR-35 commits dynamic entity creation on a payload nobody has ever seen.
The PRD admits the Custom Model payload is "undocumented — the published specification omits the feature and the web client has no reference to it" and no HAR capture contains it. So FR-35's four "testable consequences" describe tests against a data shape with **zero empirical existence**. Worse, the assumption index admits the reference system may not even have a Custom Model camera to run the spike against. A spike-gated FR is fine; a spike-gated FR whose *precondition for running the spike* is itself unverified is a v2 feature wearing an MVP badge. And the failure mode is asymmetric: dynamic entity creation is one of the hardest patterns in HA (entity registry churn, unique-ID design for unknown class names, restore-on-restart for classes not yet re-emitted — FR-35's "not removed during a session" consequence is silent on *across* sessions, which is the actual hard case). Move FR-35 out of §7.1 In Scope entirely; keep FR-34.

---

## HIGH

### H-1. FR-2's first consequence would be rejected by an HA core reviewer as written.
"Observation Record values are populated **before the integration reports itself as set up**" mandates blocking `async_setup_entry` on N network queries (11 cameras × 3 classes, or a batched equivalent, per Q4 — unresolved). HA explicitly warns against slow setup; setup that blocks on full data hydration against a possibly-slow NVR fights `test-before-setup` timing expectations, delays HA startup, and turns a slow SecuritySpy into a failed config entry. The product need ("correct after restart, no waiting for a new detection") does not require blocking setup — it requires first-refresh-before-entities-report-state. Rewrite the consequence; as specified it's both an anti-pattern and in tension with FR-30/FR-31's graceful-degradation posture.

### H-2. FR-14 ("Home Assistant does not report an arm state that contradicts the server's") is not testable and not achievable.
This is an always-true invariant over a distributed system with a lossy push stream and polling. There is *always* a window where HA's state contradicts the server's — the PRD's own Event Stream definition ("lossy, no replay") guarantees it. A testable version bounds the window: "arm state changes in SecuritySpy are reflected within X seconds / one poll cycle." Also unstated: does the Event Stream even carry arm-mode-change events, or is this poll-only? If poll-only, "without a restart or reload" is trivially true but the latency could be minutes; the FR is silent on the number that matters.

### H-3. FR-7's motion-timeout consequence is a tautology dressed as a test.
"Motion presence clears on its own after a period of inactivity" — no period specified, no default, no configurability stated, and no entry in §13. The cited evidence (467 motion signals, zero end signals) proves the *problem*; the FR then hides the design decision (timeout length is user-visible behavior, exactly like Detection Debounce) inside "on its own." A test of "clears eventually" passes with any timeout from 1s to 1h. Same disease as FR-4's lookback window — but FR-4 at least got flagged; FR-7 didn't.

### H-4. The Silver rule `integration-owner` and Bronze `brands` are external dependencies the PRD treats as internal.
Addendum §1 notes `brands` "requires a PR to `home-assistant/brands` — external review latency; start early," yet FR-38 says Bronze rules are "verified by Home Assistant's own tooling running in the project's CI, on every change." Hassfest's `brands` check for a *custom* integration cannot pass a core-oriented check — custom integrations aren't in the brands repo until that PR merges, and the PRD elsewhere (§7.2) defers the brands PR to post-launch as part of default-store listing. So FR-38's "every Bronze rule satisfied" and §7.2's deferral contradict each other unless `brands` is pre-exempted — which the PRD never states. Similarly `docs-triggers`/`docs-actions`/`docs-conditions` assume documentation surfaces whose format hassfest checks against core's docs repo structure. The claim "Bronze in full, machine-verified" needs an explicit exemption list *in the PRD*, or it's unfalsifiable ("satisfied or explicitly exempted with a stated reason" lets the builder exempt anything — a gameable metric, see M-4).

### H-5. FR-28 (permission-aware entity creation) presumes a permission-introspection API that is never cited as verified.
Every other capability claim in this PRD leans on the HAR capture or the API reference. FR-28 requires the integration to *enumerate the configured user's permissions* (arming rights, file access) before entity creation. No research citation says SecuritySpy exposes a "what can this user do" endpoint; the addendum mentions "permission decoding" as library work but the PRD's evidentiary standard elsewhere would demand this be flagged as an assumption or open question. If permissions are only discoverable by *trying an operation and failing*, the whole FR (and UJ-3's repair-issue climax) needs redesign. Unverified load-bearing API capability, unflagged.

### H-6. FR-3/FR-31 reconciliation cannot recover what SecuritySpy never recorded — and the PRD's own §5.5 says per-class triggers are off by default.
"Self-healing" recovers only *Captures*. A detection during disconnection produces a Capture only if the relevant Detection Trigger is on and SecuritySpy actually recorded. §5.5 states per-class triggers are **off on a default install**. So for a default-configured user, FR-3's testable consequence ("Observation Record reflects those detections on the next reconciliation") is false by design, and UJ-4's "recovers anything missed" oversells. The FR needs the precondition stated ("detections that produced Captures"), and the docs/UX need to surface that the Observation Record is only as complete as the trigger configuration — otherwise the headline feature silently under-reports and users file bugs against correct behavior.

---

## MEDIUM

### M-1. FR-5 "discoverable as ordinary device triggers in the UI automation editor" smuggles in a second implementation.
Binary sensors are automatable via *state* triggers for free; "device triggers" in HA are a distinct `device_trigger.py` surface (and one modern core reviewers actively discourage in favor of entity-based triggers). Either the consequence means "state triggers on entities" (then say that) or it mandates building device-trigger machinery nothing else in the PRD needs (scope creep inside a consequence bullet). Ambiguous as written; a builder could satisfy or fail it depending on reading.

### M-2. FR-23 diagnostic sensor list is scope creep with an unverified item.
"Certificate expiry" as a Hub sensor: no research citation says SecuritySpy reports its certificate metadata via API; if the intent is that the *integration* inspects the TLS handshake, that's new mechanism invented inside a consequences list. CPU/memory/frame-rate/data-rate/last-error per camera is 5+ entities × 11 cameras of diagnostic surface for a solo MVP — directly counter to SM-C1 (entity count counter-metric) and SM-C3. Nothing in the user journeys needs any of it. Cut or defer half of FR-23/FR-24.

### M-3. SM-2 and SM-5 are unmeasurable-or-gameable as success metrics.
SM-2 ("runs continuously in production") has no duration, no reliability bar — one automation that fired once satisfies it. SM-5 ("someone installs it without asking a question") is unverifiable: you cannot observe the absence of a question, and with an audience of ~100–200 (§14.4), n=1 self-selected forum user proves nothing. SM-7 lists four disruptions but no observation window or repetition count — a single lucky reconnect passes. These read as metrics designed to be met.

### M-4. FR-38/FR-39's escape hatch ("satisfied **or explicitly exempted** with a stated reason") makes SM-6 self-certifying.
The builder writes the exemptions, the builder's CI verifies the builder's exemption file. Combined with H-4, "Bronze in full" can be trivially true. If the quality-scale claim is meant to be a real commitment, the PRD must enumerate *now* which rules are expected to be exempt (`appropriate-polling`, `brands`, likely the docs-* family in part) so the exemption list is a decision, not a pressure valve discovered at deadline.

### M-5. FR-20 "renamed in SecuritySpy is renamed in Home Assistant without breaking user customizations" contradicts HA's registry behavior.
Once a user renames a device/entity in HA, HA keeps the user's name; the integration cannot (and must not) push the SecuritySpy rename over it. And propagating device renames to entity IDs is explicitly not done by HA. The testable consequence as written ("a camera renamed in SecuritySpy is renamed in Home Assistant") fails whenever the user has customized — which the same bullet forbids breaking. Specify precedence: SecuritySpy name updates the *registry default* name only; user customizations always win.

### M-6. UJ-1's dashboard card and §5.1 never reconcile "outdoor cameras" scoping.
The journey's value depends on outdoor-only relevance ("an Observation Record dominated by kitchen movement is not useful"), but the product ships identical entities for all 11 cameras and holds "no privacy opinion." Fine — but then the *headline user journey's climax* depends on the user hand-building a filtered dashboard, which no FR, blueprint, or doc requirement supports. Either a third blueprint/dashboard example is in scope, or UJ-1's resolution overstates the out-of-box experience.

### M-7. Open Question 8 (minimum SecuritySpy version) is release-blocking, not open.
§11.5 requires enforcing a minimum version "at setup, failing with a clear message." You cannot ship that consequence with the minimum unverified — enforcing 6.0 when the endpoints need 6.15 is a broken promise; enforcing 6.20 (the only verified version) may exclude working installs. Only one server is available to test against, so the honest v1 answer is "tested against 6.20, enforced ≥ the earliest version *someone verifies*" — which is a doc/support posture decision the PRD should make, not defer.

## LOW

### L-1. FR-6's "~190 signals → exactly one event" consequence bakes a measurement artifact into a test.
The 95-second/191-signal trace is one camera, one scene. A person who leaves and returns within the episode-gap window legitimately produces two episodes. Fine as a regression fixture; brittle as a stated consequence ("exactly one") without defining episode-close semantics (gap length is another hidden tunable, cousin of H-3).

### L-2. FR-24 (update availability) assumes the API reports "version offered," uncited; and a solo NVR user gets this from SecuritySpy itself. Pure nice-to-have inflating Phase 1 surface.

### L-3. "Discipline violation" glossary framing (§4) and "emotionally load-bearing" scope notes (§7.2) are self-aware flourishes, but the latter is a genuine risk marker: two deferred features flagged as emotionally load-bearing plus Open Question 10 ("pulled forward?") is the PRD pre-authorizing its own scope creep. Delete Q10 or answer it "no" now.

### L-4. §13 Q9 (contact the fork maintainer) is the only open question with real strategic downside if deferred past public announcement — a hostile fork-vs-fork dynamic in a ~100-person community damages SM-5/SM-C4 permanently. Cheap to resolve; should be resolved before Phase 0, not "open."

---

## Counts
- Critical: 3 (C-1 reconciliation gated on misclassified open question; C-2 Silver-at-release vs. solo-maintainer contradiction; C-3 FR-35 on nonexistent payload evidence)
- High: 6
- Medium: 7
- Low: 4

## The three decisions this review forces
1. **Gate Phase 2 on a Capture-History timing spike** (Q3) exactly as Phase 3 is gated on the FR-35 spike — or rewrite FR-2/FR-3 to eventual-consistency language.
2. **Demote FR-39 to post-release** and pre-enumerate Bronze exemptions, or the quality commitment is either fatal or fake.
3. **Eject FR-35 from MVP scope** (keep FR-34) until the payload exists in a capture and the spike precondition (a Custom Model camera) is confirmed.
