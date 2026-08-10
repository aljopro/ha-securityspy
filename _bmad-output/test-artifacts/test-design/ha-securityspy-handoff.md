---
title: 'TEA Test Design → BMAD Handoff Document'
version: '1.0'
workflowType: 'testarch-test-design-handoff'
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/SOLUTION-DESIGN.md
  - _bmad-output/planning-artifacts/epics.md
sourceWorkflow: 'testarch-test-design'
generatedBy: 'TEA Master Test Architect'
generatedAt: '2026-08-09'
projectName: 'ha-securityspy'
---

# TEA → BMAD Integration Handoff — ha-securityspy

## Purpose

Bridges this system-level test design into BMAD's epic/story work. Epics and stories already exist (`_bmad-output/planning-artifacts/epics.md`), so this document is primarily an **enrichment** input: it says which quality requirements, risks, and test scenarios should be folded into existing stories, and which stories need scope added.

## TEA Artifacts Inventory

| Artifact | Path | BMAD integration point |
| --- | --- | --- |
| Architecture test design | `_bmad-output/test-artifacts/test-design-architecture.md` | Blockers B-1…B-6 become story scope in Epics 1, 2, 4, 7; risk mitigation plans become epic quality gates |
| QA test design | `_bmad-output/test-artifacts/test-design-qa.md` | P0/P1 scenarios become story acceptance criteria; entry/exit criteria become epic gates |
| Full coverage matrix (141 scenarios, by epic) | `_bmad-output/test-artifacts/test-design-progress.md` §4.1 | Per-story scenario assignment |
| Risk register (20 risks) | Both documents, §Risk Assessment | Epic risk classification and story prioritization |

## Epic-Level Integration Guidance

### Risk references per epic

| Epic | Risks owned | Epic-level quality gate |
| --- | --- | --- |
| **1. API Library** | R-002, R-003, R-004, R-010, R-016, R-017 | Fake server + injected clock exist and are exported; credential guards and fixture secret scan green; reference-corpus replay proves the ~190:1 reduction |
| **2. Connect and Model** | R-006, R-014, R-019 | Identity format frozen and asserted as exact strings **before** any entity platform work; complete config-flow error/abort coverage (Bronze) |
| **3. Resilience** | R-007, R-015 | Three availability layers independently proven; four-disruption suite green; zero-residue unload |
| **4. Observation Record** | **R-001 (score 9)**, R-005, R-013 | **Gate is FAIL until the 4.1 spike returns.** Then: watermark-merge property tests green; ASR-1 invariant (stream dead, values still correct) green |
| **5. Live Detection** | R-004, R-018, R-020 | One event per episode on the reference corpus; state writes O(episodes); blueprint selectors resolve against the real entity set |
| **6. Control SecuritySpy** | R-011, R-012 | Live settings snapshot-diff shows zero collateral change; no schedule-mutating request exists on any path; default-install trap fully covered |
| **7. Ship It** | R-008, R-009, R-020 | Full Bronze rule set green in CI before the HACS release; full Silver + > 95 % coverage before announcement; suite runtime within budget |

### Cross-cutting quality gates

- **P0 pass rate 100 %**, P1 ≥ 95 %, zero open P0/P1 defects at any release tag.
- **No score-≥6 risk ships without its mitigation scenarios implemented and passing.**
- **Suite runtime budget:** library < 30 s, integration < 3 min. A regression is a defect, not a nuisance (R-009).
- **No wall-clock waits in any test.** Injected clock only (R-010).

## Story-Level Integration Guidance

### New scope to add to existing stories

| Story | Scope to add | Source |
| --- | --- | --- |
| 1.1 (library skeleton) | `FakeSecuritySpyServer` with independent fault switches, exported as a pytest plugin; injected time source on stream client and reducer; fixture capture + anonymization procedure; coverage tooling wired from day one | B-2, B-3, B-5, TC-1…TC-4, TC-8 |
| 1.3 (stream client) | Explicit stall-vs-drop distinction in the fault model; connection callbacks with once-per-transition semantics | TC-4, R-007 |
| 2.3 (device hierarchy) | Unique-ID format frozen in documented constants, asserted as exact strings; identity tests land before platform work | B-5/H-5, R-006 |
| 2.7 (permission gating) | Parameterized permission-matrix fixture + entity-set snapshot helper | TC-7 |
| 3.3 (logging) | The four lifecycle log messages routed through named constants | H-3, TC-5 |
| 4.1 (spike) | Written spike report with a measured bound, feeding the docs *and* the test assertions | B-1, R-001 |
| 4.2 (last-seen sensors) | `async_reconcile(reason)` seam on the coordinator | B-4, TC-3 |
| 5.6 (blueprint draft) | Automated selector-resolution test against the real entity set | TC-9a, R-020 |
| 6.5/6.6 (triggers, sensitivity) | Live settings snapshot-diff harness, built with the first writable control rather than at the end | TC-12, R-012 |
| 7.3 (Bronze CI) | Verified minimum SecuritySpy version, or a named constant with behavior asserted at it | B-6, TC-11 |

### P0 scenarios that must become story acceptance criteria

These are the scenarios where a passing implementation and a *correct* implementation can otherwise diverge silently:

- **4.3-SYS-090** — with the stream permanently dead, every persistent value is still correct (AD-1; the predecessor's defect, inverted).
- **4.2-UNIT-080/081** — push may only advance a timestamp; poll overwrites authoritatively, including regressions.
- **4.3-SYS-086/087** — populated on the first refresh after restart, and setup never blocks on hydration.
- **2.3-SYS-047/048/049** — identity survives rename, IP change, port change, and reconfigure with zero unique-ID churn.
- **1.5-UNIT-023 / 5.2-SYS-103/105** — the 191-signal corpus yields O(1) episodes and O(episodes) state writes.
- **1.3-INT-010** — a stalled stream is detected as loss, not treated as healthy.
- **3.1-SYS-065/066/067** — the three availability layers behave independently.
- **1.7-UNIT-036 / 1.7-INT-037** — no credential and no settings payload escapes into diagnostics or logs at any level.
- **1.6-INT-034 / 6.1-SYS-117** — no code path mutates a SecuritySpy schedule.
- **6.7-SYS-128/129/130** — the default-install trap is detected, explained, dismissible, and never silently "fixed".
- **2.6-SYS-056** — a fresh install adds zero enabled camera entities (ONVIF untouched).

### Testability attributes (equivalent of data-testid)

There is no DOM here; the equivalent stable handles are:

- **Entity keys and unique IDs** — snake_case, frozen at release, never derived from user-editable data (AD-5, AD-9). These are the selectors every SYS test and both blueprints bind to.
- **`translation_key` on every entity description** — the stable identity for UI-facing strings.
- **Named log-message constants** — the stable handles for FR-32 assertions.
- **`ReconcileReason` enum** — the stable handle for asserting *why* a cycle ran.
- **Typed exception hierarchy** — the stable handle for the AD-6 mapping table.

## Risk-to-Story Mapping

| Risk | Cat | P×I | Story / epic | Test level |
| --- | --- | --- | --- | --- |
| R-001 | DATA | 3×3=**9** | 4.1 (spike), gates 4.2–4.6 | LIVE |
| R-002 | TECH | 2×3=6 | 1.2, 1.3, 1.4, 7.3 | UNIT + LIVE |
| R-003 | SEC | 2×3=6 | 1.7 | UNIT + INT |
| R-004 | PERF | 2×3=6 | 1.5, 5.1, 5.2 | UNIT + SYS |
| R-005 | TECH | 2×3=6 | 4.2, 4.3, 6.2 | UNIT + SYS |
| R-006 | OPS | 2×3=6 | 2.3, 2.9 | SYS |
| R-007 | OPS | 2×3=6 | 1.3, 3.1, 3.2, 4.4 | INT + SYS |
| R-008 | TECH | 3×2=6 | 7.1, 7.3 | CI |
| R-009 | BUS | 2×3=6 | Cross-cutting (all epics) | Process |
| R-010 | TECH | 3×2=6 | 1.1 infra, all timing stories | Process + CI |
| R-011 | DATA | 3×2=6 | 6.7 | SYS |
| R-012 | TECH | 2×3=6 | 6.5, 6.6 | INT + LIVE |
| R-017 | OPS | 2×3=6 | 1.1, 1.7 | CI |
| R-013 | PERF | 2×2=4 | 4.2, 4.3 | INT + LIVE |
| R-014 | TECH | 2×2=4 | 2.8 | INT |
| R-015 | OPS | 2×2=4 | 3.4 | SYS |
| R-016 | DATA | 2×2=4 | 1.4, 1.5 | UNIT |
| R-020 | OPS | 2×2=4 | 5.6, 7.2 | SYS + LIVE |
| R-018 | BUS | 3×1=3 | 5.7, 5.8 | LIVE (gated) |
| R-019 | SEC | 1×2=2 | 2.2 | INT |

## Recommended BMAD → TEA Workflow Sequence

1. **TEA Test Design** (done) → this handoff.
2. **BMAD epic/story enrichment** — fold the "new scope" table and the P0 acceptance criteria into `epics.md`. Epics already exist, so this is an update, not a regeneration.
3. **TEA ATDD** — generate red-phase acceptance tests for the P0 scenarios, starting with Epic 1's infrastructure and Epic 2's identity tests.
4. **BMAD implementation** (`dev-story`) — test-first, epic order per the PRD's phases.
5. **TEA Automate** — expand to the P1/P2 coverage as each epic lands.
6. **TEA Trace** — traceability matrix and gate decisions before the Bronze release.
7. **TEA NFR Assess** — after implementation evidence exists, converting this plan's evidence sources into PASS/CONCERNS/FAIL.

## Phase Transition Quality Gates

| From | To | Gate criteria |
| --- | --- | --- |
| Test Design | Epic/story enrichment | Every score-≥6 risk has a mitigation strategy and an owner ✅ (complete) |
| Epic/story enrichment | ATDD | B-2 and B-3 in Epic 1's scope; P0 scenarios present as acceptance criteria; B-1 scheduled ahead of Epic 4 |
| ATDD | Implementation | Failing acceptance tests exist for all P0 scenarios of the epic in flight |
| Implementation | Test automation | All acceptance tests pass; suite within the runtime budget; zero quarantined tests |
| Test automation | **HACS release** | Trace matrix ≥ 80 % of P0/P1 requirements; full Bronze rule set green in CI; LIVE suite executed; R-001 resolved |
| HACS release | **Public announcement** | Full Silver rule set green; > 95 % coverage across integration modules; SM-2 soak running; SM-3 blueprints verified by manual import |
