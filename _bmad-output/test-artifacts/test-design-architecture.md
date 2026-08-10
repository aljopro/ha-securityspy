---
title: 'Test Design for Architecture — SecuritySpy Home Assistant Integration'
date: 2026-08-09
author: Murat (Master Test Architect) for Jensen
status: Architecture Review Pending
project: ha-securityspy
prd: ../planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md
adr: ../planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md
---

# Test Design for Architecture — SecuritySpy Home Assistant Integration

**Purpose:** Architectural concerns, testability gaps, and NFR requirements for review by the architect/builder. This is the contract on what the architecture must provide before test development can proceed. Test scenarios, tooling, and execution live in the companion [test-design-qa.md](test-design-qa.md).

---

## Executive Summary

**Scope:** Full greenfield system — the `aiosecurityspy` protocol library (PyPI) and the `ha-securityspy` Home Assistant custom integration. FR-1…FR-45 across 7 epics.

**Business context (from PRD):** The predecessor integration was archived after accumulating state from a lossy event stream that blanked on every restart. The headline deliverable — the Observation Record — is explicitly the correction of that defect. Maintainer fatigue is named as the primary product risk, and the engaged user population is small (~100–200), so durability matters more than reach.

**Architecture (from the spine, AD-1…AD-18):** Three layers (protocol library → adapter → entity platforms) with a two-plane data flow: a lossy push plane for latency and an authoritative poll plane that is the only source of persistent truth. One coordinator, one merge function, one availability computation, one exception seam, one auth counter.

**Expected scale:** 11 cameras on the reference system, 3 built-in object classes, ~190 classification signals per person-crossing per camera, 10-second heartbeat cadence. No declared upper bound on camera count.

**Risk summary:** 20 risks — **1 critical (score 9)**, 11 high (6–8), 5 medium, 3 low. The critical risk is an unresolved empirical unknown, already spike-gated. The high-risk cluster divides into correctness-of-the-headline, resilience-under-absence, and sustainability-of-the-test-suite.

---

## Quick Guide

### 🚨 BLOCKERS — Must Be Decided Before Test Development Proceeds

| # | Item | Why it blocks | Owner |
| --- | --- | --- | --- |
| B-1 | **Run the classification-write-timing spike (Story 4.1 / PRD Open Q3).** | R-001, the only score-9 risk. Until it returns, no honest freshness assertion for FR-2/FR-3/FR-11 can be written, and any test encoding a guess bakes the guess in as truth. Epic 4's gate is FAIL until resolved. | Builder |
| B-2 | **Commit to a `FakeSecuritySpyServer` test double with independent fault switches** (`server_down`, `camera_offline(n)`, `stall_stream`, `drop_stream`, `fail_auth`), shipped from the library repo as a pytest plugin. | Nothing above `client.py`/`stream.py` is testable without it. The spine mandates a fixture corpus, which is not the same thing. Unblocks the mitigations for R-005, R-007, R-010, R-014, R-015 simultaneously. | Library (Epic 1) |
| B-3 | **Make time injectable** in the stream client (heartbeat watch, backoff) and the reducer (debounce, motion inactivity timeout). | AD-11 declares a ~30 s loss window and indefinite backoff; FR-7 a 30 s motion timeout. Without injection these become real-time waits — a slow suite that feeds R-009 and R-010, the two risks most likely to end the project. | Library (Epic 1) |
| B-4 | **Add an explicit `async_reconcile(reason)` seam** on the coordinator that all four AD-10 triggers call. | AD-4's `update_interval=None` plus self-scheduled polling leaves no deterministic way to drive a reconciliation cycle from a test, which is what most of Epic 4's coverage depends on. | Adapter (Epic 4) |
| B-5 | **Decide the coverage tooling and threshold enforcement point now** (`pytest-cov`, `fail_under`, explicit module list, per repo). | FR-39's Silver bar is > 95 % across integration modules. A coverage bar retrofitted at the end is the classic reason a Silver gate stalls — and the announcement is gated on it. | CI (Epic 7) |
| B-6 | **Verify the earliest sufficient SecuritySpy 6.x release** (PRD Open Q8). | The min-version enforcement test (§11.5, FR-38) has no boundary value to assert against. Interim: make the floor a named constant and assert behavior at the constant. | Builder |

### ⚠️ HIGH PRIORITY — Recommendations Requiring Approval

| # | Recommendation | Rationale |
| --- | --- | --- |
| H-1 | **A `pytest -m live` suite is a real deliverable, excluded from CI, blocking release.** It carries: the two spikes, the settings snapshot-diff, lookback cost measurement, and the blueprint import checklist. | R-002, R-012, and R-001 share one property — unit tests cannot see them. The protocol is reverse-engineered from a single HAR of one server version; fixture-based CI is structurally blind to server drift. |
| H-2 | **Anonymize fixtures at capture time and add a secret scan over the fixture corpus in CI.** | R-017. Fixtures come from the builder's own server, and per FR-42 the settings endpoint returns plaintext camera credentials. Fixtures are a distribution surface. |
| H-3 | **Route the four connection-lifecycle log messages through named constants.** | FR-32's log-once discipline is otherwise asserted against literal strings, which makes a correct implementation fail on a wording change. |
| H-4 | **Adopt a test-suite runtime budget as a stated constraint** — library < 30 s, integration < 3 min — and treat a regression as a defect. | R-009. The PRD names maintainer fatigue as the primary product risk; a slow or flaky suite is the most direct way a test strategy causes the failure it exists to prevent. |
| H-5 | **Land the identity tests in Epic 2, before any entity platform work.** | R-006. AD-5 is explicitly permanent; a unique-ID mistake found after release orphans every user customization and cannot be fixed without breaking existing installs. |
| H-6 | **Parameterize the fake server by camera count and probe at 50 cameras nightly.** | Scale is unbounded in the requirements and measured only at 11. Better to learn where AD-10's batching shape breaks now than from a user with 40 cameras. |

### 📋 INFO ONLY — Solutions Provided, No Decision Needed

- **Pact / contract testing does not apply.** There is no consumer/provider pair under our control; the external contract is an undocumented third-party API. Recorded-fixture parity plus the live suite is the equivalent discipline.
- **Browser automation does not apply.** The UI surface is Home Assistant's own; config-flow steps are covered by `pytest-homeassistant-custom-component`.
- **AD-2's layer boundary is enforceable as a test** — "no HA imports in the library", "no protocol knowledge in the integration", "no destructive endpoint on the public surface" all become cheap permanent guards.
- **ADR checklist categories 3 (Scalability/Availability) and 4 (Disaster Recovery) largely do not apply** — there is no service of ours to scale or fail over. The equivalent concern is resilience to the *server's* absence, covered under reliability.

---

## For Architects and Devs — Open Topics

### Risk Assessment

**Total risks identified:** 20 — 1 critical (score 9), 11 high (6–8), 5 medium (4), 3 low (≤ 3).

**Critical (score 9) — blocks the gate**

| ID | Cat | Risk | P | I | Score | Mitigation | Owner | Timeline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | DATA | Classification write timing unknown (Open Q3). If SecuritySpy writes the object class materially later than capture close, FR-2/FR-3 freshness and FR-11 are wrong, and the headline ships with a false promise. | 3 | 3 | **9** | Story 4.1 spike against the live reference server before Phase 2 commits; the measured result becomes both the documented latency bound and the test's expected assertion. | Builder | Before Epic 4 |

**High priority (score 6–8)**

| ID | Cat | Risk | P | I | Score | Mitigation | Owner | Timeline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-002 | TECH | Undocumented API drift — the protocol layer is reverse-engineered from a HAR of one server version; a point release breaks it and fixture-based CI will not notice. | 2 | 3 | 6 | Live smoke suite before each release; fixture-vs-live parity diff; enforced min-version floor. | Builder | Epic 1 → each release |
| R-003 | SEC | Credential leakage — the settings endpoint returns per-camera credentials in plaintext; research already observed a password echoed into logs. | 2 | 3 | 6 | AD-13 structurally, verified by negative guard tests over diagnostics, logs at all levels, and exception messages. | Library | Epic 1 |
| R-004 | PERF | Signal→episode reduction fails under real load, putting ~190 writes/person/camera onto the HA state machine — the defect §11.1 names explicitly. | 2 | 3 | 6 | Reference-corpus replay asserting episode count *and* HA state-write count; multi-camera concurrent replay. | Library + Adapter | Epics 1, 5 |
| R-005 | TECH | Push/poll merge regressions — timestamps flickering or moving backwards, the exact failure AD-16 exists to prevent. Subtle, intermittent, directly visible in the headline. | 2 | 3 | 6 | Table/property tests over the merge function incl. the deletion-driven regression; out-of-order interleaving test. | Adapter | Epic 4 |
| R-006 | OPS | Identity scheme is permanent and wrong-once-only; a unique-ID mistake found after release orphans user customizations irrecoverably. | 2 | 3 | 6 | Identity tests land before entity platform work; rename/IP/port/reconfigure churn assertions; unique-ID format frozen as an asserted constant. | Adapter | Epic 2 |
| R-007 | OPS | Silent stream death — heartbeat detection or backoff fails and the integration looks alive while receiving nothing. Users never report it because nothing appears broken. | 2 | 3 | 6 | Injected-clock tests for the 3-missed-beat rule and backoff schedule; a **stall** scenario distinct from a **drop**; assert `reconnected` triggers exactly one reconciliation. | Library + Adapter | Epic 3 |
| R-008 | TECH | HA breaking changes — a custom integration against a monthly-release platform, with the test kit pinned to HA versions. | 3 | 2 | 6 | CI matrix at declared-min and latest; a weekly scheduled run so breakage surfaces without a commit; hassfest + pylint plugin on every change. | CI | Epic 7, ongoing |
| R-009 | BUS | Maintainer fatigue — named in the PRD as the primary product risk. A heavy, slow, or flaky suite is a direct accelerant. | 2 | 3 | 6 | Suite runtime budget as a constraint; no hard waits; no scenario without a named risk or FR (SM-C3 applied to tests). | Builder | Ongoing |
| R-010 | TECH | Test-suite flakiness from async/stream timing — the highest-probability risk in the register; stream, debounce, timeout, and reconnect tests are all timing-shaped. | 3 | 2 | 6 | Injected clock mandatory; hard waits banned; nightly burn-in on the stream/reducer/coordinator modules; quarantine-and-fix, never retry-to-green. | QA | Epic 1 onward |
| R-011 | DATA | The default-install trap (FR-45) — per-class triggers are off by default, so a *correct* integration shows an empty Observation Record and reads as broken on first run. | 3 | 2 | 6 | Tests for detection, the repair issue, dismissal, and non-recurrence; first-run scenario in the manual release checklist. | Adapter | Epic 6 |
| R-012 | TECH | Settings partial-POST collateral damage — a wrong key silently overwrites unrelated camera configuration. No unit test can detect it. | 2 | 3 | 6 | Live before/after full-settings snapshot diff per writable setting, pre-release; write surface kept to one key per POST. | Builder | Epic 6 |
| R-017 | OPS | Fixture corpus leaks the builder's environment (camera names, LAN topology, credentials) into a public repository. | 2 | 3 | 6 | Anonymize at capture time; CI secret scan over fixtures; review gate on new fixtures. | Library | Epic 1 |

**Medium (score 4)**

| ID | Cat | Risk | Score | Mitigation |
| --- | --- | --- | --- | --- |
| R-013 | PERF | Lookback-window startup cost vs. empty values on quiet cameras; the window is unset (Open Q2). | 4 | Measure at 7 d and 30 d against the reference server; never block setup on hydration; keep it options-adjustable. |
| R-014 | TECH | Auth-counter double-ownership — reauth fires on one transient 401, or never fires. | 4 | Table test across both planes incl. reset-on-success and mixed sequences. |
| R-015 | OPS | Unclean teardown — a surviving task, timer, or connection breaks reload. | 4 | Zero-residue unload assertion; unload→reload→unload cycle. |
| R-016 | DATA | Object Class slug collisions or unknown-class handling breaking built-ins. | 4 | `class_slug()` unit tests incl. collision-skip-with-one-warning; unknown-class carry-through. |
| R-020 | OPS | Blueprints drift from the entity model and SM-3 fails at announcement, in front of the users the project is trying to earn. | 4 | Blueprints drafted early against the Phase-3 entity surface; automated selector-resolution test; manual import checklist at the release gate. |

**Low (score ≤ 3)**

| ID | Cat | Risk | Score | Note |
| --- | --- | --- | --- | --- |
| R-018 | BUS | The Custom Model spike cannot run — no reference camera has a custom model. | 3 | Already handled by design: FR-35 auto-defers to v2, AD-9 keeps the schema safe. |
| R-019 | SEC | Certificate verification disabled becomes the default path, normalizing MITM exposure. | 2 | Verification on by default; consequence stated in the UI string; asserted in the config-flow test. |

**Category legend:** TECH architecture/integration · SEC security · PERF performance/scalability · DATA data integrity · BUS business/product · OPS operational/deployment.

### NFR Testability Requirements

What the architecture must provide so NFR validation can be automated. Planning guidance only — final PASS/CONCERNS/FAIL belongs to `nfr-assess` once implementation evidence exists.

| Category | Threshold | What architecture must provide | Status |
| --- | --- | --- | --- |
| PERF — signal reduction | ~190:1; per-signal state writes are a defect | A replayable recorded-signal corpus, and a reducer callable without I/O (AD-3 already delivers this) | ✅ Covered |
| PERF — poll fan-out | ≤ 1 `caplist` request per class per cycle, batched across cameras | Request-observable client, i.e. the fake server (B-2) | ⚠️ Gap → B-2 |
| PERF — startup/lookback | Unset (Open Q2) | Measured values, and setup that never blocks on hydration | ⚠️ **UNKNOWN** → R-013 |
| PERF — detection latency | "within a few seconds", no numeric bound | Injectable clock (B-3) so latency is asserted as debounce + transport, not wall time | ⚠️ Partial → B-3 |
| SEC — credential containment | Absolute, all levels | Anonymizer as the sole diagnostics exit (AD-13 delivers), plus fixture anonymization at capture (H-2) | ⚠️ Gap → H-2 |
| SEC — destructive surface | Absolute absence | Public API and endpoint table both assertable (AD-2 delivers) | ✅ Covered |
| REL — availability layers | Three distinct behaviors | Independent fault injection per layer (B-2) | ⚠️ Gap → B-2 |
| REL — stream loss detection | 3 missed heartbeats ≈ 30 s (assumption) | Injectable clock; a stall must be distinguishable from a drop | ⚠️ Gap → B-3 |
| REL — reconnect backoff | Indefinite exponential; schedule unspecified | A stated schedule (monotonic, capped) to assert against | ⚠️ Partial |
| REL — poll plane is truth | Absolute (AD-1) | Ability to run with the stream permanently dead — the ASR-1 invariant | ✅ Covered by B-2 |
| OPS — log discipline | Once at loss, DEBUG retries, once at recovery | Stable message identity via constants (H-3) | ⚠️ Gap → H-3 |
| MAINT — coverage | Bronze: full config-flow incl. every error/abort path. Silver: > 95 % | Coverage tooling and enforcement point (B-5) | ⚠️ Gap → B-5 |
| MAINT — typing / layer purity | `mypy --strict`; no cross-layer imports | Already structural (AD-2, AD-14) | ✅ Covered |
| COMPAT — min SecuritySpy version | Assumed 6.x, earliest sufficient release unverified | A verified floor, or a named constant to assert behavior at (B-6) | ⚠️ **UNKNOWN** → B-6 |
| COMPAT — ONVIF coexistence | Zero enabled camera entities on fresh install | Already structural (AD-12) | ✅ Covered |

**Unknown thresholds (do not guess):** lookback window (Open Q2), fallback interval and FILE debounce (spine assumptions), detection threshold/debounce defaults (Open Q5), minimum SecuritySpy version (Open Q8), classification write timing (Open Q3, blocking), upper bound on camera count, test-suite runtime budget (proposed in H-4, not yet stated anywhere).

### Testability Concerns and Architectural Gaps

**🚨 ACTIONABLE — the architecture must provide these**

| ID | Gap | Required affordance | Impact if unmet | Owner | Timeline |
| --- | --- | --- | --- | --- | --- |
| TC-1 | No test double for the SecuritySpy server. The spine mandates a fixture corpus, which is not a server. | `FakeSecuritySpyServer` serving both planes, exported as a pytest plugin from the library repo | Everything above the transport is untestable; the integration repo re-invents a worse one | Library | Epic 1 |
| TC-2 | Heartbeat watch, backoff, and inactivity timeouts are wall-clock bound. | Injected time source and sleep/backoff strategy on the stream client and reducer | Real-time waits → slow, flaky suite → R-009 + R-010 | Library | Epic 1 |
| TC-3 | The coordinator self-schedules reconciliation with no public seam. | One `async_reconcile(reason)` entry point that all four AD-10 triggers call; HA-clock-driven timers | Epic 4 coverage cannot be driven deterministically | Adapter | Epic 4 |
| TC-4 | Fault injection per failure class is undesigned, but AD-17 requires three independently provable availability layers. | Independent fault switches on the fake server | Cannot prove the three layers do not collapse into one | Library | Epic 1 |
| TC-5 | Log-once discipline is assertable only against literal strings. | Fixed logger names; the four lifecycle messages routed through named constants | Correct implementations fail on wording changes | Adapter | Epic 3 |
| TC-6 | Live-server-only facts (post-roll ≈ 96 s, Open Q3, Q6, Q1) are not reproducible in CI. | A marked, CI-excluded live suite treated as a pre-release gate | Either the facts go unverified, or a guess gets encoded as truth | Builder | Epic 1 onward |
| TC-7 | Permission-gated entity creation has a combinatorial setup matrix with no fixture strategy. | A parameterized permissions fixture over the decoded bitmask + an entity-set snapshot helper | FR-28 gets spot-checked instead of covered | Adapter | Epic 2 |
| TC-8 | Fixture provenance is a privacy hazard — real captures, real topology, plaintext credentials. | Anonymization at capture time + CI secret scan over fixtures | R-017 becomes a public repository leak | Library | Epic 1 |
| TC-9 | Blueprints have no automated verification path; HA offers no blueprint execution harness. | Automate what is automatable — selector resolution against the real entity set — and treat the rest as an explicit manual gate | SM-3 is claimed but never verified | Builder | Epic 5 → 7 |
| TC-10 | The Silver coverage bar has no tooling decision. | `pytest-cov` + `fail_under` + explicit module list, per repo | The Silver gate stalls at the point announcement depends on it | CI | Epic 7 |
| TC-11 | The minimum SecuritySpy version boundary is unverified. | A verified floor, or a named constant with behavior asserted at it | The version-rejection test has no boundary value | Builder | Epic 2 |
| TC-12 | AD-8's "verified non-destructive" claim for partial POSTs holds only against the live server. | A live snapshot-diff of the full settings payload before/after each single-key write | R-012 ships undetected and destroys user configuration | Builder | Epic 6 |

**Accepted trade-offs (no action required):** live-server-dependent facts stay manual by nature (TC-6); the blueprint import check stays manual (TC-9b) rather than being faked as automated; scale beyond 11 cameras is probed, not guaranteed.

### Testability Assessment Summary

**FYI — what the architecture already gets right**

- **AD-3's pure reducer** makes the highest-risk logic in the system unit-testable with zero I/O. The single best testability decision here.
- **AD-15's frozen typed `SecuritySpyData`** gives every entity test one constructible input; platforms become pure projections.
- **AD-16's single merge function** and **AD-17's single availability computation** each collapse an otherwise emergent, system-wide behavior into one unit under test.
- **AD-18's single auth counter with one owner** turns a notoriously flaky behavior into a table-driven test.
- **AD-13's anonymizer as sole diagnostics exit** allows one negative guard instead of auditing every call site.
- **AD-2's boundaries** are assertable by import guards — permanent, cheap, and self-enforcing.
- **AD-14's two-repo split** gives the library an HA-free suite that runs in seconds; most protocol logic never pays the HA harness cost.
- **`mypy --strict` + frozen dataclasses + `from_api()`** remove a whole class of shape-drift tests a dict-passing design would need.

The pattern is worth naming: this architecture is unusually testable *in the small* and under-specified *in the seams*. Every gap above is a missing affordance, not a design flaw.

### Risk Mitigation Plans (Score ≥ 6)

Only production-code and architecture mitigations appear here. QA-owned mitigations are in the QA document.

**R-001 — Classification write timing (score 9)**
1. Instrument a live probe: trigger a recording, poll `caplist` at short intervals, record when `o` becomes non-empty relative to capture close.
2. Repeat across ≥ 3 cameras and ≥ 5 events to distinguish a fixed delay from a variable one.
3. Write the measured bound into the docs, into AD-10's cycle triggers if it changes them, and into the FR-2/FR-3/FR-11 assertions.
**Owner:** Builder · **Timeline:** before Epic 4 commits · **Status:** Planned · **Verification:** Story 4.1 spike report exists and Epic 4's gate flips from FAIL.

**R-002 — Undocumented API drift**
1. Record fixtures with a documented capture procedure and the server version stamped in.
2. Add a parity test that replays each fixture request against the live server and diffs the response *shape* (not values).
3. Enforce the min-version floor with a clear, distinct failure.
**Owner:** Builder · **Timeline:** Epic 1, re-run each release · **Verification:** parity test in the live suite, green at the release tag.

**R-003 / R-017 — Credential containment and fixture leakage**
1. `anonymize.py` is the only diagnostics exit (AD-13, already adopted).
2. Fixtures pass through the anonymizer at capture time, before they are ever written to disk.
3. CI secret scan over the fixture corpus, and a review gate on new fixtures.
**Owner:** Library · **Timeline:** Epic 1 · **Verification:** negative guard tests plus a clean secret scan on every PR.

**R-004 — Signal reduction under load**
1. Keep the reducer pure and per-camera/per-class isolated (AD-3, adopted).
2. Guarantee raw signals never cross the adapter boundary — assertable as a source guard.
3. Instrument the coordinator so state-machine writes per episode are countable in tests.
**Owner:** Library + Adapter · **Timeline:** Epics 1, 5 · **Verification:** corpus replay asserts both episode count and state-write count.

**R-005 — Push/poll merge regressions**
1. All Observation Record and Latest Capture writes funnel through the one merge function (AD-16, adopted) — enforce with a source guard.
2. Make the merge function pure and directly callable so interleavings can be tested exhaustively.
**Owner:** Adapter · **Timeline:** Epic 4 · **Verification:** property test over interleavings incl. server-side deletion.

**R-006 — Permanent identity**
1. Freeze the unique-ID format in documented constants.
2. Land identity tests in Epic 2 before any platform work.
**Owner:** Adapter · **Timeline:** Epic 2 · **Verification:** rename/IP/port/reconfigure suite asserts zero churn.

**R-007 — Silent stream death**
1. Injectable clock (B-3).
2. Explicit `connected`/`disconnected`/`reconnected`/`auth_failed` callbacks (AD-11, adopted) with once-per-transition semantics.
3. The fake server must be able to *stall* as well as *drop*.
**Owner:** Library + Adapter · **Timeline:** Epic 3 · **Verification:** stall and drop scenarios both produce loss and exactly one reconciliation on recovery.

**R-008 — HA breaking changes**
1. CI matrix at declared-min and latest HA.
2. Weekly scheduled run against the current HA release.
**Owner:** CI · **Timeline:** Epic 7, ongoing · **Verification:** scheduled workflow exists and alerts.

**R-009 / R-010 — Suite sustainability and flakiness**
1. Adopt the runtime budget as a stated constraint (H-4).
2. Ban wall-clock waits in tests; injected clock only.
3. Nightly burn-in on the timing-shaped modules; quarantine-and-fix policy.
**Owner:** Builder + QA · **Timeline:** ongoing · **Verification:** three consecutive green burn-in nights at each release tag.

**R-011 — Default-install trap**
1. Detection is a first-class code path in `repairs.py`, not a documentation note.
2. Dismissal and non-recurrence semantics defined before implementation (currently listed as deferred detail in the spine).
**Owner:** Adapter · **Timeline:** Epic 6 · **Verification:** four-scenario repair-issue test.

**R-012 — Settings collateral damage**
1. Keep one key per POST (AD-8, adopted).
2. Build the live snapshot-diff harness alongside the first writable control, not at the end.
**Owner:** Builder · **Timeline:** Epic 6 · **Verification:** zero-diff outside the written key, for every writable setting, at the release tag.

### Assumptions and Dependencies

**Architectural assumptions carried into this test design**

1. Lookback window 7 d, fallback interval 10 min, FILE debounce 5 s (spine AD-10) — provisional, unmeasured (R-013).
2. Detection Threshold 70 %, Debounce 3 signals, motion timeout 30 s — provisional, to be tuned against real footage (PRD Open Q5).
3. Stream loss after 3 missed heartbeats at a measured 10 s cadence (AD-11).
4. Reauth after 3 consecutive auth failures across both planes (AD-18).
5. Minimum SecuritySpy 6.x, minimum HA 2026.3 — neither boundary verified (Open Q8).
6. Two repositories, not a monorepo (AD-14) — shapes where the test double lives and how it is shared.
7. Eleven cameras is the reference scale; no upper bound is specified anywhere.

**Dependencies**

| Dependency | Needed by | Blocking |
| --- | --- | --- |
| Live reference server access with a least-privileged test user | Epic 1 (fixture capture), Epic 4 (spike) | B-1, H-1 |
| A camera running a Custom Model | Epic 5 spike | FR-35 only (auto-defers) |
| PyPI project + trusted publisher configured | Epic 1 release | SM-9 verification |
| HACS custom-repository validation | Epic 7 | FR-36 |

**Risks to the plan**

| Risk | Impact | Contingency |
| --- | --- | --- |
| The 4.1 spike returns "classification is written much later" | FR-2/FR-3 freshness claims weaken; AD-10 cycle triggers may need revisiting | Document the honest bound; the Observation Record remains restart-correct regardless — only the *freshness* claim changes |
| No Custom Model camera becomes available | FR-35 unverifiable | Already designed for: auto-defer to v2, FR-34 ships alone |
| Builder capacity is hobby-cadence | The ~150–225 h test effort stretches over months | Front-load the test infrastructure (B-2, B-3); it is the one investment that pays back across every later epic |

---

**Next steps for the architect/builder:**

1. Decide B-1 through B-6.
2. Approve or amend H-1 through H-6.
3. Add the missing affordances (TC-1…TC-5, TC-7) to Epic 1 and Epic 2 story scope.

**Next steps for QA:** see [test-design-qa.md](test-design-qa.md) for the 141-scenario coverage plan, execution strategy, and effort estimate.
