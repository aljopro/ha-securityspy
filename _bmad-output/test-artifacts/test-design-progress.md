---
workflowStatus: 'completed'
totalSteps: 5
stepsCompleted:
  [
    'step-01-detect-mode',
    'step-02-load-context',
    'step-03-risk-and-testability',
    'step-04-coverage-plan',
    'step-05-generate-output',
  ]
lastStep: 'step-05-generate-output'
nextStep: ''
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md
  - _bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md
  - _bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/SOLUTION-DESIGN.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/planning-artifacts/research/securityspy-api-reference.md
  - _bmad-output/planning-artifacts/research/architecture-implications.md
  - _bmad/tea/config.yaml
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/adr-quality-readiness-checklist.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/nfr-criteria.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-levels-framework.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/risk-governance.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-quality.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/probability-impact.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-priorities-matrix.md
lastSaved: '2026-08-09'
---

# Test Design Progress — ha-securityspy

## Step 1: Mode Detection

**Mode selected:** System-Level

**Rationale:**

- User intent: "Create" run, no epic/story scope specified.
- Artifacts present:
  - PRD: `_bmad-output/planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md` (+ addendum, reviews)
  - Architecture: `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md`, `SOLUTION-DESIGN.md`
  - Epics: `_bmad-output/planning-artifacts/epics.md`
  - Research: `securityspy-api-reference.md`, `architecture-implications.md`
- No `sprint-status.yaml` found → not in epic execution mode.
- Rule: PRD/ADR + Epics both present → prefer System-Level Mode first.

**Prerequisites:** SATISFIED (PRD ✅, architecture/solution design ✅, tech context ✅).

**Persistent facts:** no `project-context.md` present in repo.

## Step 2: Context & Knowledge Loaded

**Config resolved:** `tea_use_playwright_utils: true`, `tea_use_pactjs_utils: false`, `tea_pact_mcp: none`,
`tea_browser_automation: auto`, `test_stack_type: auto`, `risk_threshold: p1`,
`test_artifacts: _bmad-output/test-artifacts`.

**Detected stack:** `backend` (Python). Greenfield — no source tree yet. Planned stack from the spine:
Python ≥ 3.14, hatchling/`src` layout, uv, ruff, mypy `--strict`; pytest + `pytest-homeassistant-custom-component`
(0.13.x); GitHub Actions (hassfest, HA pylint plugin, HACS Action, coverage). No `package.json`,
no `playwright.config.*`, no `playwright-cli` binary.

**Deviations from default loading (justified):**

- **Browser exploration skipped** — no running app, no web UI surface; the integration's UI is Home Assistant's own
  (config flow steps are tested via `pytest-homeassistant-custom-component`, not a browser).
- **Playwright Utils fragments not loaded** — JS/TS-only utilities; stack is Python.
- **Pact / contract-testing fragments not loaded** — no consumer/provider pair under our control. The external
  contract is SecuritySpy's undocumented HTTP API, which no Pact broker can verify; the equivalent discipline is
  recorded-fixture parity (HAR/recorded CR-framed stream frames) plus a live smoke run against the reference server.

**Existing test coverage:** none — greenfield, no `tests/` directory in either planned repo.

**Knowledge fragments loaded (System-Level required set):**

- `adr-quality-readiness-checklist.md` (8 categories / 29 criteria)
- `nfr-criteria.md`
- `test-levels-framework.md`
- `risk-governance.md`
- `test-quality.md`
- plus `probability-impact.md`, `test-priorities-matrix.md` for scoring and P0–P3 assignment

**Extracted for downstream steps:**

- **Integration points:** SecuritySpy REST/poll plane (`caplist`, status light/heavy, settings partial POST,
  `getfile`, schedule-list), SecuritySpy CR-framed event stream (push plane), Home Assistant core
  (config entries, device/entity registry, coordinator, repairs, services, blueprints), PyPI + HACS distribution.
- **NFRs with thresholds:** ~190:1 signal→episode reduction; detection latency "within a few seconds";
  poll fan-out must not be cameras × classes; heartbeat loss ≈ 3 missed beats (~30 s); light status ~794 B vs
  heavy ~27 KB; Silver coverage bar > 95 %; capture post-roll ≈ 96 s.
- **Missing thresholds (open questions to raise in Step 3/4):** lookback window length (assumed 7 d),
  fallback poll interval (assumed 10 min), FILE-event debounce (assumed 5 s), Detection Threshold/Debounce
  defaults (assumed 70 % / 3 signals, motion timeout 30 s), minimum SecuritySpy version (assumed 6.x),
  classification write timing (Open Q3 — blocking Phase 2).


## Step 3: Testability Review, ASRs, Risk Register, NFR Plan

### 3.1 🚨 Testability Concerns (ACTIONABLE)

| ID | Concern | Evidence | Required architectural affordance | Owner |
| --- | --- | --- | --- | --- |
| TC-1 | **No test double for the SecuritySpy server exists or is mandated.** Every layer above `client.py`/`stream.py` needs one, and it must serve both planes (REST + CR-framed stream) plus fault injection (401, 403, 500, connection reset, silent stall). | Spine §Tests convention says only "protocol fixtures from HAR/recorded frames" — a fixture corpus, not a server. | Ship a `FakeSecuritySpyServer` (aiohttp test server) in the library repo's test support, exported as a pytest plugin/fixture so the integration repo reuses it rather than re-inventing. Fixture corpus feeds it. | Library (Epic 1) |
| TC-2 | **Stream backoff, heartbeat watch, and motion inactivity timeout are wall-clock bound.** AD-11 declares loss after 3 missed heartbeats (~30 s) and indefinite exponential backoff; FR-7's motion timeout defaults to 30 s. Testing these against real time makes the suite slow and flaky. | AD-11, AD-3, FR-7, FR-31. | The library's stream client and reducer must accept an injected time source and sleep/backoff strategy (constructor params, defaulted). Integration side uses HA's `async_fire_time_changed`. Without this, TC-2 becomes flakiness risk R-010. | Library (Epic 1) |
| TC-3 | **The coordinator has no `update_interval` and schedules its own reconciliation** (startup, reconnect, debounced `FILE`, slow fallback). Tests cannot deterministically drive a cycle through the public HA API alone. | AD-4, AD-10. | Expose one explicit `async_reconcile(reason: ReconcileReason)` seam on the coordinator that all four triggers call, and make the debounce/fallback timers HA-clock driven. Tests assert on reason + call count. | Adapter (Epic 4) |
| TC-4 | **Fault injection per failure class is not designed.** AD-17 requires three distinct availability layers (server unreachable / single camera offline / stream-only loss). Only a double that can produce each independently can prove they do not collapse into one. | AD-17, FR-30. | `FakeSecuritySpyServer` must expose `set_server_down()`, `set_camera_offline(n)`, `stall_stream()`, `drop_stream()`, `fail_auth()` as independent switches. | Library (Epic 1) |
| TC-5 | **Log-once discipline (FR-32) is asserted on log text**, which is inherently brittle unless message identity is stable. | FR-32, AD-11. | Fix logger names per module and route the four lifecycle messages (loss ERROR, retry DEBUG, recovery WARNING) through named constants so tests assert on the constant, not a literal. | Adapter (Epic 3) |
| TC-6 | **Live-server-only facts cannot be reproduced in CI**: post-roll ≈ 96 s, classification write timing (Open Q3), whether enabling per-class triggers actually produces trigger signals (Open Q6), Custom Model payload shape (Open Q1). | PRD §13, §5.3 NFR. | A separate, explicitly-marked live smoke suite (`pytest -m live`, credentials from env, excluded from CI, documented as a pre-release manual gate). Do not attempt to fake these in unit tests — faking them would encode the guess as truth. | QA + builder |
| TC-7 | **Permission-gated entity creation (FR-28) has a combinatorial setup matrix** — arming permission × file access × settings-write permission, each altering the created entity set. No fixture strategy is defined. | FR-28, AD-12. | A parameterized `permissions` fixture over the decoded permission bitmask, plus a single assertion helper that snapshots the created entity set per permission combination. | Adapter (Epic 2) |
| TC-8 | **Fixture provenance is a privacy hazard.** Fixtures come from anonymized real captures and a HAR of the builder's own server, containing camera names, LAN topology, and (per FR-42) plaintext camera credentials. | Spine §Tests convention, FR-42, §11.2. | The anonymizer (`anonymize.py`) must run over fixtures at capture time, and CI must carry a secret-scan step over the fixture corpus. Fixtures are a distribution surface — treat them as one. | Library (Epic 1) |
| TC-9 | **Blueprints (FR-37, SM-3) have no automated verification path.** HA offers no blueprint execution harness; "works unmodified" is a manual claim. | FR-37, SM-3, spine blueprint convention. | Two-part substitute: (a) automated — YAML schema validation + assert every `entity_id`/selector in the blueprint resolves against the entity set the integration actually creates in a test HA instance; (b) manual — a documented import-and-fire checklist in the release gate. Automate (a); do not pretend (b) is automated. | Ship (Epic 7) |
| TC-10 | **The Silver coverage bar (> 95 % across integration modules) has no tooling decision.** Nothing in the spine names a coverage tool, threshold enforcement point, or which modules count. | FR-39, AD-14. | Decide now: `pytest-cov` with `fail_under` per repo in CI, and an explicit module include/exclude list. Retrofitting a coverage bar late is exactly the kind of debt that stalls the Silver gate. | CI (Epic 7) |
| TC-11 | **The minimum SecuritySpy version boundary is unverified** (Open Q8), so the rejection test (FR-38 / §11.5) has no boundary value to assert. | PRD §11.5, §13 Q8. | Either verify the earliest sufficient 6.x release, or make the floor a named constant with a test that asserts *behavior at the constant* rather than a hardcoded "6.0". | Builder |
| TC-12 | **Settings partial POSTs are asserted "verified non-destructive" (AD-8) against the live server only.** A regression in SecuritySpy, or a wrong key, silently destroys user configuration and no unit test can see it. | AD-8, FR-17, FR-18. | A live-suite test that snapshots the full settings payload before and after a single-key write and diffs it, run against the reference server before each release. | QA + builder |

### 3.2 ✅ Testability Assessment Summary (already strong)

- **AD-3's reducer is a pure function** with injected threshold/debounce — the highest-risk logic in the system (~190:1 reduction, FR-5…FR-8) is unit-testable at the lowest level with zero I/O. This is the single best testability decision in the architecture.
- **AD-2's layer boundary is enforceable by test**: "the integration contains zero SecuritySpy protocol knowledge" is assertable by an import/grep guard test, and "the library has no HA imports" likewise. Both are cheap, permanent guards.
- **AD-15's frozen, fully-typed `SecuritySpyData` container** gives every entity test one constructible input — entity platforms become pure projections testable without a server at all.
- **AD-16's single watermark merge function** means push/poll conflict semantics live in one testable function rather than being an emergent property of the whole system.
- **AD-17's availability computed once in `entity.py`** collapses what would otherwise be N per-platform availability behaviors into one unit under test.
- **AD-18's single auth-failure counter with one owner** makes the "3 consecutive failures, reset on any success, fed by both planes" rule a table-driven unit test.
- **AD-13's anonymizer as the sole diagnostics exit** allows one negative guard test — "no credential substring appears in diagnostics output for any fixture" — instead of auditing every call site.
- **`mypy --strict` + frozen dataclasses + `from_api()` constructors** remove a whole class of shape-drift tests that a dict-passing design would require.
- **Two-repo split (AD-14)** gives the library a fast, HA-free test suite that runs in seconds — the majority of protocol logic never pays the HA test-harness cost.

### 3.3 Architecturally Significant Requirements (ASRs)

| ASR | Source | Why significant for test | Verdict |
| --- | --- | --- | --- |
| ASR-1 | AD-1 / FR-1…FR-4 — poll plane is the only source of persistent truth | Restart-correctness and self-healing are the product; a stream-derived persistent value is a defect class of its own | **ACTIONABLE** — needs a dedicated invariant test: kill the stream entirely, restart HA, assert every persistent value is still correct |
| ASR-2 | AD-16 — one watermark merge (push advances only; poll authoritative incl. regression) | Two writers on one value; the only conflict rule in the system | **ACTIONABLE** — property/table test incl. the regression case (capture deleted server-side) |
| ASR-3 | AD-5 — identity = server UUID + camera number, permanent | Irreversible after release; SM-4 and every user customization depend on it | **ACTIONABLE** — rename/IP-change/port-change/reconfigure tests asserting zero unique-ID churn and no duplicate devices |
| ASR-4 | AD-3 / §11.1 — ~190:1 signal→episode reduction | A performance requirement stated as a defect threshold, not an optimization | **ACTIONABLE** — replay the recorded 191-signal/95-second frame corpus, assert episode count and HA state-write count |
| ASR-5 | AD-13 / FR-42 — credential containment | Live hazard: settings payloads carry plaintext camera credentials | **ACTIONABLE** — negative guard tests over diagnostics, logs (all levels), and exception messages |
| ASR-6 | AD-2 — destructive/remote-execution endpoints absent from the library surface | Structural safety; "you cannot call what doesn't exist" is testable | **ACTIONABLE** — surface test asserting no delete/exec endpoint appears in the public API or in `const.py` endpoint tables |
| ASR-7 | AD-17 — three-layer availability | Distinguishes "unavailable" from "error" from "stale"; FR-30 and SM-7 rest on it | **ACTIONABLE** — three independent fault-injection scenarios |
| ASR-8 | AD-18 — one auth-failure counter, both planes, threshold 3 | Reauth flapping or never firing are both user-visible failures | **ACTIONABLE** — table test across both planes |
| ASR-9 | AD-10 — batched caplist, ≤ 1 request per class per cycle | §10.2 scaling constraint; naive impl is 33 req/cycle on the reference system | **ACTIONABLE** — request-count assertion against the fake server at 11 cameras |
| ASR-10 | AD-9 — Object Class open string, single `class_slug()` | Event schema permanence; unknown classes must not break built-ins | **ACTIONABLE** — unknown-class and slug-collision tests |
| ASR-11 | AD-11 — library owns stream lifecycle, emits explicit connection callbacks | Reconnect + reconciliation coupling (FR-3, FR-31) | **ACTIONABLE** — asserts `reconnected` triggers exactly one reconciliation |
| ASR-12 | AD-14 — Bronze gates release, Silver gates announcement, verified in CI | The release criterion itself; SM-6 | **ACTIONABLE** — CI must run hassfest + HA pylint plugin + HACS Action + coverage on every change (Epic 7) |
| ASR-13 | AD-4 — one coordinator, `update_interval=None` | Shapes every entity test's setup | **FYI** — covered transitively; no dedicated test needed beyond TC-3's seam |
| ASR-14 | AD-7 — arming writes override only, never schedule | Destroys user configuration if violated | **ACTIONABLE** — assert no schedule-mutating request is ever issued, across the full arming test matrix |
| ASR-15 | AD-8 — settings writes are single-key partial POSTs | Lost-update and collateral-damage hazard | **ACTIONABLE** in unit (payload shape) + **live-suite** for the non-destructive claim (TC-12) |
| ASR-16 | AD-12 — HA runtime conventions (`runtime_data`, `PARALLEL_UPDATES`, entity categories, disabled-by-default camera) | Mostly machine-verified by hassfest/pylint plugin | **FYI** — delegate to CI tooling; add targeted tests only for entity-category and disabled-by-default assertions (FR-22, SM-8) |
| ASR-17 | AD-6 — single exception-mapping seam | Two platforms classifying one failure differently is a real failure mode | **ACTIONABLE** — table test mapping each library exception to its HA outcome |
| ASR-18 | PRD §11.5 — min SecuritySpy/HA version declared and enforced | Fails clearly rather than misbehaving | **ACTIONABLE**, blocked on TC-11 |

### 3.4 Risk Register

Scoring per `probability-impact.md`: Probability 1–3 × Impact 1–3 = 1–9. ≥ 6 requires documented mitigation; = 9 blocks the gate.

| ID | Cat | Risk | P | I | Score | Level | Mitigation | Owner | Timeline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | DATA | **Classification write timing is unknown (Open Q3).** If SecuritySpy writes the object class to a capture materially later than capture close, the Observation Record's freshness claim (FR-2/FR-3) and FR-11's class-alongside-image are both wrong — and the headline deliverable ships with a false promise. | 3 | 3 | **9** | 🚨 CRITICAL | Story 4.1 spike against the live reference server **before Phase 2 commits** (already gated in PRD §12). Outcome must be written into the docs as an honest latency bound, and into the test suite as the expected freshness assertion. Gate stays FAIL until the spike returns. | Builder | Before Epic 4 |
| R-002 | TECH | **Undocumented API drift.** The entire protocol layer is reverse-engineered from a HAR of SecuritySpy 6.20. A point release changing `caplist` fields, the CR framing, or bitmask meanings breaks everything, and CI (fixture-based) will not notice. | 2 | 3 | 6 | ⚠️ HIGH | Live smoke suite (TC-6) run against the reference server before every release; fixture-vs-live parity test that diffs recorded fixture shape against a live response; min-version floor enforced with a clear failure (ASR-18). | Builder | Epic 1, gate at each release |
| R-003 | SEC | **Credential leakage.** SecuritySpy's settings endpoint returns per-camera credentials in plaintext; stream URLs carry credentials; research already observed a password echoed into logs by an external tool. | 2 | 3 | 6 | ⚠️ HIGH | AD-13 structurally; verified by negative guard tests over diagnostics/logs/exceptions (ASR-5) + a secret scan over the fixture corpus (TC-8) + CI secret scanning. | Library | Epic 1 (Story 1.7) |
| R-004 | PERF | **Signal→episode reduction fails under real load**, putting ~190 writes/person/camera onto the HA state machine and recorder — the defect §11.1 names explicitly. Eleven cameras multiply it. | 2 | 3 | 6 | ⚠️ HIGH | Replay-corpus test asserting episode count *and* HA state-write count (ASR-4); a multi-camera concurrent-replay test at 11 cameras. | Library + Adapter | Epic 1 (1.5), Epic 5 |
| R-005 | TECH | **Push/poll merge regressions** — timestamps flickering or moving backwards between planes, the exact failure AD-16 exists to prevent. Subtle, intermittent, and directly visible in the headline feature. | 2 | 3 | 6 | ⚠️ HIGH | Table/property test over the merge function incl. deletion-driven regression; an interleaving test that fires `FILE` events and polls out of order. | Adapter | Epic 4 |
| R-006 | OPS | **Identity scheme is permanent and wrong-once-only.** A unique-ID mistake discovered after release orphans every user customization, and cannot be fixed without breaking existing installs. | 2 | 3 | 6 | ⚠️ HIGH | Identity tests land in Epic 2 *before* any entity platform work; explicit rename/IP/port/reconfigure churn assertions (ASR-3); freeze unique-ID format in a documented constant with a test asserting its exact string shape. | Adapter | Epic 2 (Story 2.3) |
| R-007 | OPS | **Silent stream death.** Heartbeat-loss detection or backoff fails and the integration looks alive while receiving nothing — the failure mode users never report because nothing appears broken. | 2 | 3 | 6 | ⚠️ HIGH | Injected-clock tests for the 3-missed-heartbeat rule and backoff schedule (TC-2, TC-4); a stall (not disconnect) scenario distinct from a drop; assert `reconnected` → exactly one reconciliation. | Library + Adapter | Epic 3 |
| R-008 | TECH | **HA breaking changes.** A custom integration against a fast-moving HA (2026.3 floor, 2026.8 current) can break on any monthly release; `pytest-homeassistant-custom-component` pins to HA versions. | 3 | 2 | 6 | ⚠️ HIGH | CI matrix across the declared min HA version and latest; scheduled weekly CI run so breakage surfaces without a commit; hassfest + HA pylint plugin on every change. | CI | Epic 7, ongoing |
| R-009 | BUS | **Maintainer fatigue** — the PRD names it as the primary product risk, and the predecessor died of it. An over-heavy, slow, or flaky test suite is a direct accelerant. | 2 | 3 | 6 | ⚠️ HIGH | Test-suite budget as a first-class constraint: library suite < 30 s, integration suite < 3 min, zero `sleep`-based waits (`test-quality.md` DoD enforced in review); SM-C3 scope discipline applies to tests too — no scenario without a named risk or FR. | Builder | Ongoing |
| R-010 | TECH | **Test-suite flakiness from async/stream timing.** Highest-probability risk in the register: stream tests, debounce tests, timeout tests, and reconnect tests are all timing-shaped. | 3 | 2 | 6 | ⚠️ HIGH | Injected clock mandatory (TC-2); ban `asyncio.sleep`/`waitForTimeout`-style waits in tests; CI burn-in (run changed tests N× ) on the stream/reducer modules; quarantine + fix policy, never retry-to-green. | QA | Epic 1 onward |
| R-011 | DATA | **The default-install trap (FR-45)** — per-class triggers are off by default, so a correct integration presents an empty Observation Record and reads as broken. Damages first-run trust, which is where adoption is won or lost. | 3 | 2 | 6 | ⚠️ HIGH | Explicit test for the detection condition, the repair issue, its dismissal, and its non-recurrence once any trigger is enabled; first-run scenario in the manual release checklist. | Adapter | Epic 6 (Story 6.7) |
| R-012 | TECH | **Settings partial POST collateral damage** — a wrong key or a server-side quirk silently overwrites unrelated camera configuration. Unit tests cannot detect it; only a live before/after diff can. | 2 | 3 | 6 | ⚠️ HIGH | TC-12 live snapshot-diff test per writable setting, run pre-release; keep the write surface minimal (single key per POST, per AD-8). | Builder | Epic 6 |
| R-013 | PERF | **Startup cost of the lookback window.** An over-long window × 11 cameras × 3 classes makes the first reconciliation expensive; an over-short one makes quiet cameras read empty. The value is unset (Open Q2). | 2 | 2 | 4 | MEDIUM | Measure the batched `caplist` cost against the reference server at 7 d and 30 d; assert setup is never blocked on hydration (FR-2); make the window options-adjustable. | Builder | Epic 4 |
| R-014 | TECH | **Auth-counter double-ownership.** Both planes feed one counter; a mistake means reauth fires on one transient 401 or never fires at all. | 2 | 2 | 4 | MEDIUM | Table test across both planes incl. reset-on-success and mixed-plane sequences (ASR-8). | Adapter | Epic 2 (Story 2.8) |
| R-015 | OPS | **Unclean teardown** — a surviving task, timer, or connection after unload breaks reload and leaks across HA restarts. | 2 | 2 | 4 | MEDIUM | Unload test asserting zero remaining tasks/timers/connections; unload→reload→unload cycle test. | Adapter | Epic 3 (Story 3.4) |
| R-016 | DATA | **Object Class slug collisions / unknown-class handling** breaking built-in classes or silently merging two custom classes. | 2 | 2 | 4 | MEDIUM | Unit tests for `class_slug()` incl. collision-skip-with-one-warning path; unknown-class carry-through test asserting built-ins unaffected. | Library | Epic 1 (Story 1.4/1.5) |
| R-017 | OPS | **Fixture corpus leaks the builder's own environment** (camera names, LAN topology, credentials) into a public repository. | 2 | 3 | 6 | ⚠️ HIGH | Anonymize at capture time via `anonymize.py`; CI secret scan over fixtures; a review gate on any new fixture (TC-8). | Library | Epic 1 |
| R-018 | BUS | **The Custom Model spike cannot run** — the reference system has no camera with a custom model, so FR-35 has no verifiable payload. | 3 | 1 | 3 | LOW | Already handled by design: FR-35 auto-defers to v2, AD-9 keeps the schema safe. Test plan covers FR-34 unconditionally and marks FR-35 scenarios as spike-gated. | Builder | Epic 5 (Story 5.7) |
| R-019 | SEC | **Certificate verification disabled becomes the default path** because LAN-IP connections need it, normalizing MITM exposure. | 1 | 2 | 2 | LOW | Verification on by default; the toggle's consequence stated in the UI string; a test asserting the default is `True` and that the warning string is present. | Adapter | Epic 2 (Story 2.2) |
| R-020 | OPS | **Blueprints drift from the entity model** and SM-3 fails at the worst moment — at announcement, in front of the users the project is trying to earn. | 2 | 2 | 4 | MEDIUM | Blueprints drafted early against the Phase-3 entity surface (Story 5.6); automated selector-resolution test (TC-9a); manual import checklist in the release gate (TC-9b). | Builder | Epic 5 → Epic 7 |

**Distribution:** 1 CRITICAL (score 9), 11 HIGH (6–8), 5 MEDIUM (4), 3 LOW (≤ 3).

### 3.5 NFR Planning Assessment

Categories in scope, thresholds extracted, and planned evidence. Per this workflow's boundary, this **plans** NFR validation — it does not judge PASS/CONCERNS/FAIL. Run `nfr-assess` once implementation evidence exists.

| Category | Requirement | Threshold | Status | Planned evidence |
| --- | --- | --- | --- | --- |
| **PERF** | Signal→episode reduction | ~190:1 on the reference corpus; per-signal state writes are a defect | **KNOWN** | Replay test asserting episode count + HA state-write count (ASR-4) |
| **PERF** | Detection latency, classify → HA event | "within a few seconds", dominated by debounce | **PARTIAL** — no numeric bound | Injected-clock test asserting latency = debounce window + transport, not a wall-clock number; live-suite observation for the honest doc claim |
| **PERF** | Observation Record poll fan-out | ≤ 1 `caplist` request per class per cycle, batched across cameras; never cameras × classes | **KNOWN** | Request-count assertion against the fake server at 11 cameras (ASR-9) |
| **PERF** | Health polling endpoint choice | light ~794 B preferred over heavy ~27 KB | **KNOWN** | Assert the light endpoint is used unless a value demands the heavy one |
| **PERF** | Lookback window / fallback interval / FILE debounce | 7 d / 10 min / 5 s — all `[ASSUMPTION]` | **UNKNOWN** → R-013 | Measure against the reference server; convert assumption into a measured default before release |
| **PERF** | Test-suite runtime | Not stated anywhere | **UNKNOWN** → R-009 | Proposed budget: library < 30 s, integration < 3 min, enforced in CI |
| **SEC** | Credential redaction in diagnostics/logs/errors | Absolute — zero occurrences, all levels | **KNOWN** | Negative guard tests over every fixture; CI secret scan (ASR-5, R-003, R-017) |
| **SEC** | Settings payloads never logged | Absolute, including DEBUG | **KNOWN** | `caplog`-based test at DEBUG asserting no settings body appears |
| **SEC** | Destructive endpoints absent from library surface | Absolute | **KNOWN** | Public-surface + endpoint-table assertion (ASR-6) |
| **SEC** | Certificate verification default | On by default; disabling is explicit with stated consequence | **KNOWN** | Config-flow default + UI-string test (R-019) |
| **SEC** | Least-privileged SecuritySpy user | Documented, not enforced | **KNOWN (docs)** | README review item in the release checklist |
| **REL** | No user-visible failure requires an HA restart | Absolute | **KNOWN** | The four-disruption suite (SM-7): SecuritySpy restart, Mac reboot, network drop, HA upgrade |
| **REL** | Stream-loss detection | 3 missed heartbeats ≈ 30 s `[ASSUMPTION]` | **PARTIAL** — cadence measured (10 s), count assumed | Injected-clock test against the constant; verify cadence in the live suite |
| **REL** | Reconnect backoff | Indefinite exponential | **PARTIAL** — no schedule specified | Assert monotonic non-decreasing delay with a cap, and that retries never stop |
| **REL** | Persistent state derives from the poll plane only | Absolute (AD-1) | **KNOWN** | ASR-1 invariant test: stream permanently dead → all persistent values still correct |
| **REL** | Motion clears without `MOTION_END` | Absolute; verified against a camera emitting 467 motion / 0 end signals | **KNOWN** | Replay that corpus, assert motion clears on the inactivity timeout |
| **REL** | Reauth threshold | 3 consecutive failures `[ASSUMPTION]`, bounded and documented | **KNOWN (as constant)** | Table test at 2 / 3 / reset-on-success (ASR-8) |
| **SCALE** | Camera count | 11 on the reference system; no declared upper bound | **UNKNOWN** | Parameterize the fake server; run the fan-out and reduction tests at 11 and at 50 to find where the shape breaks |
| **MAINT** | Coverage | Bronze: complete config-flow coverage incl. every error/abort path. Silver: > 95 % across integration modules | **KNOWN** | `pytest-cov` with `fail_under` in CI + explicit module list (TC-10) |
| **MAINT** | Typing | `mypy --strict` passes on both repos | **KNOWN** | CI gate |
| **MAINT** | Quality-scale rules | Full Bronze at release, full Silver at announcement, verified by HA's own tooling in CI | **KNOWN** | hassfest + HA pylint plugin + HACS Action in CI (ASR-12) |
| **MAINT** | Layer purity | Library has no HA imports; integration has no protocol knowledge | **KNOWN** | Import-guard tests in both repos (ASR-6 companion) |
| **OPS** | Log discipline | Loss once (ERROR), retries DEBUG, recovery once (WARNING); a multi-hour outage produces no proportional log volume | **KNOWN** | `caplog` test over a simulated multi-hour outage with an injected clock (TC-5) |
| **OPS** | Diagnostics downloadable and redacted | Absolute | **KNOWN** | Diagnostics snapshot test through the anonymizer |
| **OPS** | Error classification | Transient vs auth vs permanent incompatibility distinguished | **KNOWN** | Exception-mapping table test (ASR-17) |
| **COMPAT** | Min SecuritySpy version | Assumed 6.x; earliest sufficient release unverified | **UNKNOWN** → TC-11, ASR-18 | Verify, then behavior-at-constant test |
| **COMPAT** | Min HA version | 2026.3 `[ASSUMPTION]`, Python-3.14 boundary | **KNOWN (as constant)** | CI matrix min + latest (R-008) |
| **COMPAT** | ONVIF coexistence | Existing ONVIF setup unchanged; no enabled camera entities on fresh install | **KNOWN** | `entity_registry_enabled_default = False` assertion + fresh-install entity snapshot (SM-8) |

**ADR Quality Readiness Checklist mapping (8 categories / 29 criteria)** — the categories that translate to this project: **1. Testability & Automation** (TC-1…TC-4, TC-7 — the main gap cluster), **2. Test Data Strategy** (TC-8 fixture provenance/anonymization; no multi-tenancy dimension — single local server), **5. Security** (strong: AD-2/AD-13 are structural), **6. Monitorability** (log discipline + diagnostics: strong), **7. QoS/QoE** (latency and degradation covered; no rate-limiting dimension — the integration is the only load source and must throttle *itself*, per AD-10), **8. Deployability** (HACS + PyPI semver, rollback = reinstall a prior version). Categories **3. Scalability & Availability** and **4. Disaster Recovery** largely do not apply: there is no service to scale or fail over — the equivalent concern is resilience to the *server's* absence, already covered under REL. Scored coverage of the 29 criteria is deferred to `nfr-assess` after implementation evidence exists.

### 3.6 Risk Summary

**One critical blocker:** R-001 (classification write timing). It is already gated by the PRD's Phase-2 spike and by Story 4.1 — but until that spike returns, the gate decision for Epic 4 is **FAIL**, and no Observation Record freshness claim should reach documentation or a test assertion.

**The high-risk cluster splits three ways:**

1. **Truth and correctness of the headline** — R-005 (merge regressions), R-006 (permanent identity), R-011 (default-install trap). These are where the product is either right or quietly wrong, and two of the three are unfixable after release.
2. **Resilience under absence** — R-007 (silent stream death), R-002 (API drift), R-012 (settings collateral damage). All three share one property: unit tests cannot see them. They are the reason the live smoke suite (TC-6) is a real deliverable and not a nicety.
3. **Sustainability of the test suite itself** — R-009 (maintainer fatigue), R-010 (async flakiness), R-008 (HA churn). The PRD names maintainer fatigue as the primary product risk; a slow or flaky suite is the most direct way a test strategy can cause the failure it exists to prevent. The suite budget and the no-hard-waits rule are therefore requirements, not style preferences.

**Highest-leverage testability investment:** `FakeSecuritySpyServer` with independent fault switches and an injected clock (TC-1, TC-2, TC-4). It unblocks the mitigations for R-005, R-007, R-010, R-014, and R-015 simultaneously — build it in Epic 1 alongside the library, not later.

## Step 4: Coverage Plan & Execution Strategy

### 4.0 Level Taxonomy (this project)

The generic E2E/API/Component/Unit ladder maps onto a Python + Home Assistant custom integration as follows. Every scenario below carries exactly one level; the Duplicate Coverage Guard was applied — a behavior provable at UNIT does not reappear at SYS.

| Level | Meaning here | Runs where | Speed |
| --- | --- | --- | --- |
| **UNIT** | Pure Python, zero I/O — library models, `episodes.py` reducer, `class_slug()`, bitmask/field decoders, `anonymize.py`, the watermark merge function | Library repo (mostly), adapter repo (merge fn) | ms |
| **INT** | One component against a double — `client.py`/`stream.py` against `FakeSecuritySpyServer`; or an HA-side unit (coordinator, config flow, one platform) against a mocked library | Both repos | ms–s |
| **SYS** | Full in-process stack: real `aiosecurityspy` + `FakeSecuritySpyServer` + real HA via `pytest-homeassistant-custom-component`. This is the CI-runnable "E2E" | Integration repo | s |
| **LIVE** | Against the real SecuritySpy reference server. `pytest -m live`, credentials from env, **excluded from CI**, run as a pre-release manual gate | Manual | min |

### 4.1 Coverage Matrix

Scenario ID format: `{EPIC}.{STORY}-{LEVEL}-{SEQ}`.

#### Epic 1 — The API Library (`aiosecurityspy`)

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 1.1-INT-001 | Package builds from `src/` layout; `mypy --strict` and ruff pass; no HA import appears anywhere in the package (import-guard) | INT | P0 | FR-40, FR-41 | ASR-6 |
| 1.1-INT-002 | Public surface contains no capture-deletion, shell-, or shortcut-execution endpoint; `const.py` endpoint table likewise | INT | P0 | AD-2, §7.2 | ASR-6 |
| 1.2-INT-003 | Client uses the caller-injected `aiohttp` session and never constructs its own | INT | P0 | FR-41 | — |
| 1.2-INT-004 | Auth success against the fake server; typed models returned, no raw dicts cross the boundary | INT | P0 | FR-40, AD-15 | — |
| 1.2-INT-005 | 401 → `SecuritySpyAuthError`; 403 → `SecuritySpyPermissionError`; connection reset → `SecuritySpyConnectError`; unsupported version → `SecuritySpyUnsupportedVersionError`; no raw `aiohttp` error escapes | INT | P0 | AD-6, FR-25 | ASR-17 |
| 1.2-INT-006 | HTTPS with verification on succeeds against a matching cert; fails with a distinct error against a mismatched one; succeeds with verification off | INT | P0 | FR-26 | R-019 |
| 1.3-UNIT-007 | CR-framed stream parser: multi-frame buffer, split frame across reads, trailing partial frame, empty frame, oversized frame | UNIT | P0 | FR-31, AD-2 | R-002 |
| 1.3-UNIT-008 | Unknown/malformed frame is skipped without terminating the stream or corrupting the following frame | UNIT | P0 | FR-34, R-002 | R-002 |
| 1.3-INT-009 | Heartbeat watch with injected clock: loss declared after exactly 3 missed beats; not at 2 | INT | P0 | FR-31, AD-11 | R-007, TC-2 |
| 1.3-INT-010 | **Silent stall** (socket open, no bytes) is detected as loss — distinct from a clean disconnect | INT | P0 | FR-31 | R-007 |
| 1.3-INT-011 | Backoff schedule with injected clock: monotonic non-decreasing, capped, retries indefinitely — never gives up | INT | P0 | FR-31 | R-007 |
| 1.3-INT-012 | Callback contract: `connected` / `disconnected` / `reconnected` / `auth_failed` each fire exactly once per transition, in order | INT | P0 | AD-11 | R-007 |
| 1.3-INT-013 | On `auth_failed` the stream pauses reconnection and defers to the caller — it never self-retries auth | INT | P0 | AD-11, AD-18 | R-014 |
| 1.3-INT-014 | `disconnect()` is idempotent and cancels every task and timer | INT | P0 | FR-33 | R-015 |
| 1.4-UNIT-015 | `caplist` decoding: `f`+`s` → absolute timezone-aware UTC datetime; `o` bitmask → class set | UNIT | P0 | FR-1, FR-11 | R-002 |
| 1.4-UNIT-016 | Capture with no classification decodes to an **empty** class set, never absent or error | UNIT | P0 | FR-11 | — |
| 1.4-UNIT-017 | Server-side class filter and multi-camera `cams=` batching produce one request shape per class | UNIT | P1 | FR-4, AD-10 | R-013 |
| 1.4-UNIT-018 | Absent value is `None` — never epoch, never zero — across every timestamp field | UNIT | P0 | FR-1 | — |
| 1.5-UNIT-019 | Reducer: signals below threshold, however frequent, open no episode | UNIT | P0 | FR-5 | R-004 |
| 1.5-UNIT-020 | Reducer: isolated qualifying signals below debounce open no episode (no flicker) | UNIT | P0 | FR-5 | R-004 |
| 1.5-UNIT-021 | Reducer: peak confidence is the episode maximum, not the value at threshold crossing | UNIT | P0 | FR-6 | — |
| 1.5-UNIT-022 | Reducer: exactly one episode per contiguous qualifying run per class per camera | UNIT | P0 | FR-6 | R-004 |
| 1.5-UNIT-023 | **Reference corpus replay** — the recorded 191-signal / 95-second capture yields O(1) episodes, not O(191) | UNIT | P0 | FR-6, §11.1 | R-004, ASR-4 |
| 1.5-UNIT-024 | Concurrent classes on one camera, and the same class on 11 cameras, reduce independently without cross-talk | UNIT | P0 | FR-5 | R-004 |
| 1.5-UNIT-025 | Per-camera/per-class threshold and debounce injection; changing them mid-stream takes effect without restart | UNIT | P1 | FR-8 | — |
| 1.5-UNIT-026 | Motion reducer clears on inactivity timeout with an injected clock, on a corpus containing **zero** `MOTION_END` signals (467-signal reference camera) | UNIT | P0 | FR-7, §11.3 | R-007 |
| 1.5-UNIT-027 | `class_slug()`: normalization, idempotence, and collision → skip with exactly one warning, never a silent merge | UNIT | P1 | FR-34, AD-9 | R-016 |
| 1.5-UNIT-028 | An unknown Object Class parses and carries end-to-end without disturbing built-in class handling | UNIT | P0 | FR-34 | R-016 |
| 1.6-UNIT-029 | Permission bitmask decoding across the full matrix (arming / file access / settings write) | UNIT | P0 | FR-28 | TC-7 |
| 1.6-UNIT-030 | Trigger-reason bitmask decodes to named reasons — motion, audio, per-class movement, arrival/departure, manual — never a raw bitmask in output | UNIT | P0 | FR-43 | — |
| 1.6-UNIT-031 | Bool read/write asymmetry: JSON `true/false` on read, `1/0` on write | UNIT | P0 | AD-2 | R-012 |
| 1.6-INT-032 | Settings write is a single-key partial POST — payload contains exactly the changed key | INT | P0 | FR-17, AD-8 | R-012 |
| 1.6-UNIT-033 | Schedule model parses user-defined schedules; no hardcoded schedule list exists in the code | UNIT | P1 | FR-15 | — |
| 1.6-INT-034 | No code path issues a schedule-mutating request, asserted across the whole arming API surface | INT | P0 | FR-13, AD-7 | ASR-14 |
| 1.7-UNIT-035 | Anonymizer redacts usernames, passwords, tokens, and per-camera device credentials from every fixture | UNIT | P0 | FR-42 | R-003 |
| 1.7-UNIT-036 | **Negative guard:** no credential substring from any fixture appears in anonymized diagnostics output | UNIT | P0 | FR-42 | R-003 |
| 1.7-INT-037 | Settings payloads never appear in logs at any level, DEBUG included | INT | P0 | FR-42, §11.2 | R-003 |
| 1.7-UNIT-038 | Exception messages and stack traces carry no credentials, incl. credential-bearing URLs | UNIT | P0 | FR-42 | R-003 |
| 1.x-INT-039 | **Fixture corpus secret scan** — CI step asserting no live credential or real hostname survives in committed fixtures | INT | P0 | §11.2 | R-017, TC-8 |
| 1.x-INT-040 | `FakeSecuritySpyServer` self-test: every fault switch (`server_down`, `camera_offline`, `stall_stream`, `drop_stream`, `fail_auth`) behaves as declared | INT | P0 | TC-1, TC-4 | R-005, R-007 |

#### Epic 2 — Connect and Model

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 2.1-INT-041 | Config flow happy path: host/port/user/password → validated → entry created, no YAML | INT | P0 | FR-25 | — |
| 2.1-INT-042 | Distinct abort/error strings for unreachable host, bad credentials, insufficient permissions, unsupported version — **every error and abort path** (Bronze requirement) | INT | P0 | FR-25, FR-38 | R-002 |
| 2.1-INT-043 | Duplicate server (same UUID) aborts as already-configured, regardless of the address used | INT | P0 | FR-25, AD-5 | R-006 |
| 2.2-INT-044 | Verification toggle defaults to **on**; the UI string stating the consequence of disabling it is present | INT | P0 | FR-26 | R-019 |
| 2.2-INT-045 | LAN-IP + dyndns-issued cert: fails with a clear message when verification is on, succeeds when off | INT | P1 | FR-26 | R-019 |
| 2.3-SYS-046 | One hub device per entry, `entry_type=SERVICE`; one camera device per camera, `via_device` → hub | SYS | P0 | FR-19 | — |
| 2.3-SYS-047 | **Identity format is frozen**: hub `{uuid}`, camera `{uuid}_{n}`, entity `{uuid}_{n}_{key}` — asserted as exact strings | SYS | P0 | FR-21, AD-5 | R-006, ASR-3 |
| 2.3-SYS-048 | Camera renamed in SecuritySpy → HA device renamed, **zero** unique-ID churn, customizations preserved | SYS | P0 | FR-20, FR-21 | R-006 |
| 2.3-SYS-049 | Host/IP/port change → no duplicate devices, no orphaned entities | SYS | P0 | FR-21, FR-29 | R-006 |
| 2.3-SYS-050 | Eleven-camera fixture: all named from SecuritySpy, none named after an IP, none with manufacturer "Generic" (**SM-4**) | SYS | P0 | FR-20 | — |
| 2.3-SYS-051 | Camera key type is `int` throughout `SecuritySpyData` — no stringly-typed camera number leaks in | SYS | P1 | AD-15 | — |
| 2.3-SYS-052 | Camera added/removed server-side → device added/removed without a reload | SYS | P2 | AD-12 | — |
| 2.4-SYS-053 | Hub health (CPU, memory, camera count, cert expiry) and per-camera health (fps, data rate, last error) exist and are `EntityCategory.DIAGNOSTIC` | SYS | P1 | FR-23 | — |
| 2.4-INT-054 | Health polling uses the light status endpoint; the heavy one only where a value demands it | INT | P1 | §11.1 | R-013 |
| 2.5-SYS-055 | Update entity reports availability and offered version; no install path exists in v1 | SYS | P2 | FR-24 | — |
| 2.6-SYS-056 | Camera entities exist but `entity_registry_enabled_default = False`; a fresh install adds **zero** enabled camera entities (**SM-8**) | SYS | P0 | FR-22 | — |
| 2.6-SYS-057 | Enabling a camera entity yields working live video against the fake server | SYS | P2 | FR-22 | — |
| 2.7-SYS-058 | Permission matrix: for each combination, the created entity set matches the expected snapshot — arming controls omitted without arming permission, capture entities omitted without file access | SYS | P0 | FR-28 | TC-7 |
| 2.7-SYS-059 | Every omitted capability raises a repair issue naming the missing permission | SYS | P0 | FR-28 | — |
| 2.7-SYS-060 | **No entity is created that is permanently unavailable due to permissions** — asserted across the whole matrix | SYS | P0 | FR-28 | TC-7 |
| 2.8-INT-061 | Auth counter: 2 consecutive failures → no reauth; 3rd → `ConfigEntryAuthFailed` and both planes stop | INT | P0 | FR-27, AD-18 | R-014 |
| 2.8-INT-062 | Counter is fed by **both** planes and resets on any authenticated success on either | INT | P0 | AD-18 | R-014, ASR-8 |
| 2.8-INT-063 | Completing reauth restarts both planes without removing the config entry | INT | P0 | FR-27 | — |
| 2.9-SYS-064 | Reconfigure host/port/credentials preserves devices, entities, and recorded history | SYS | P1 | FR-29 | R-006 |

#### Epic 3 — Resilience

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 3.1-SYS-065 | Server unreachable → **all** entry entities unavailable, none retaining a last-known value | SYS | P0 | FR-30, AD-17 | ASR-7 |
| 3.1-SYS-066 | One camera offline, server reachable → only that camera device's entities unavailable; no error raised | SYS | P0 | FR-30, AD-17 | ASR-7 |
| 3.1-SYS-067 | Stream lost, poll healthy → poll-derived entities stay **available**; only push-derived presence entities go unavailable | SYS | P0 | AD-17 | ASR-7, R-005 |
| 3.1-SYS-068 | No platform overrides `available` with its own logic (source guard) | SYS | P1 | AD-17 | — |
| 3.2-SYS-069 | Stream drop → reconnect → **exactly one** reconciliation triggered by the `reconnected` signal | SYS | P0 | FR-31, FR-3 | R-007 |
| 3.2-SYS-070 | Recovery requires no restart, no reload, no re-authentication | SYS | P0 | FR-31 | — |
| 3.2-SYS-071 | **Four-disruption suite** (SM-7): SecuritySpy restart, host reboot, network drop, HA restart — each recovers unattended | SYS | P0 | FR-31, SM-7 | R-007 |
| 3.3-INT-072 | Loss logged once at ERROR; retries at DEBUG; recovery once at WARNING — asserted against message constants | INT | P0 | FR-32 | TC-5 |
| 3.3-INT-073 | Simulated multi-hour outage with an injected clock produces a bounded, non-proportional log volume | INT | P1 | FR-32 | R-009 |
| 3.4-SYS-074 | Unload closes the stream and cancels every poll; zero tasks, timers, or connections survive | SYS | P0 | FR-33 | R-015 |
| 3.4-SYS-075 | Unload → reload → unload cycle succeeds without an HA restart | SYS | P0 | FR-33 | R-015 |

#### Epic 4 — The Observation Record

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 4.1-LIVE-076 | **SPIKE:** measure when SecuritySpy writes classification against a capture — at close, or later, and by how much | LIVE | **P0 — BLOCKING** | Open Q3 | **R-001** |
| 4.2-SYS-077 | Exactly three Observation Record values per camera, one per built-in class, `device_class: timestamp` | SYS | P0 | FR-1 | — |
| 4.2-SYS-078 | Values are absent (`None`) — not zero, not epoch — when no capture of that class exists in the window | SYS | P0 | FR-1, FR-4 | — |
| 4.2-SYS-079 | Values are usable in automation conditions and templates, and render as relative time | SYS | P1 | FR-1 | — |
| 4.2-UNIT-080 | **Watermark merge**: push may only advance a timestamp (max-wins); poll reconciliation overwrites authoritatively, **including regressions** (capture deleted server-side) | UNIT | P0 | AD-16 | R-005, ASR-2 |
| 4.2-UNIT-081 | Out-of-order interleaving of push updates and poll results converges to the poll result — no flicker | UNIT | P0 | AD-16 | R-005 |
| 4.2-SYS-082 | No code path outside the merge function writes an Observation Record or Latest Capture value (source guard) | SYS | P1 | AD-16 | R-005 |
| 4.2-INT-083 | One reconciliation cycle issues **≤ 1 `caplist` request per class**, batched across 11 cameras — never 33 | INT | P0 | AD-10, §10.2 | ASR-9 |
| 4.2-INT-084 | Reconciliation fires on: startup, `reconnected`, debounced `FILE` event, slow fallback — and each carries its reason | INT | P0 | AD-10 | TC-3 |
| 4.2-INT-085 | A burst of `FILE` events collapses into a single debounced cycle (no poll storm) | INT | P0 | AD-10 | R-013 |
| 4.3-SYS-086 | **Restart correctness**: values populated on the first refresh after restart, without waiting for a new detection | SYS | P0 | FR-2, SM-1 | R-001 |
| 4.3-SYS-087 | Setup is **not blocked** on hydration — the entry loads before the first reconciliation completes | SYS | P0 | FR-2 | R-013 |
| 4.3-SYS-088 | Values after restart equal values before, where no new capture intervened | SYS | P0 | FR-2 | — |
| 4.3-SYS-089 | Restarting mid-Detection-Episode neither corrupts nor blanks the record | SYS | P0 | FR-2 | R-005 |
| 4.3-SYS-090 | **ASR-1 invariant**: with the stream permanently dead from boot, every persistent value is still correct from the poll plane alone | SYS | P0 | AD-1, FR-1 | ASR-1 |
| 4.4-SYS-091 | Detections recorded while disconnected appear after the next reconciliation, with no operator action, restart, or reload | SYS | P0 | FR-3, SM-1 | R-007 |
| 4.5-SYS-092 | Latest Capture image served **by Home Assistant**; the consumer never needs to reach SecuritySpy directly | SYS | P0 | FR-9 | — |
| 4.5-SYS-093 | Image URL stays valid across image updates and HA restarts | SYS | P0 | FR-9 | — |
| 4.5-SYS-094 | Image state is the capture timestamp; changes on a new capture; usable as a state trigger | SYS | P0 | FR-10 | — |
| 4.5-SYS-095 | On startup the state reflects the newest existing capture, not an empty or restart-time value | SYS | P0 | FR-10 | R-001 |
| 4.6-SYS-096 | Detected-class set readable alongside the image; empty list when none, never absent | SYS | P1 | FR-11 | R-001 |
| 4.7-SYS-097 | `download_latest_recording` writes the most recent completed recording to an allowlisted destination | SYS | P1 | FR-44 | — |
| 4.7-SYS-098 | Distinct errors: no recording (`ServiceValidationError`), destination outside `allowlist_external_dirs` (`ServiceValidationError`), unwritable / insufficient permission (`HomeAssistantError`) | SYS | P0 | FR-44 | — |
| 4.7-SYS-099 | The service never deletes or modifies anything on the server | SYS | P0 | FR-44, §7.2 | ASR-6 |
| 4.x-LIVE-100 | Lookback-window cost measured at 7 d and 30 d against 11 real cameras; startup cost recorded | LIVE | P2 | FR-4, Open Q2 | R-013 |

#### Epic 5 — Live Detection

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 5.1-SYS-101 | Per-class presence entities exist for human/vehicle/animal and are discoverable as **device triggers in the UI automation editor** | SYS | P0 | FR-5 | R-020 |
| 5.1-SYS-102 | Presence turns on when an episode opens and off when it closes | SYS | P0 | FR-5 | — |
| 5.2-SYS-103 | Exactly one Classification Event per episode per class; the 191-signal corpus does **not** produce 191 events | SYS | P0 | FR-6, §11.1 | R-004, ASR-4 |
| 5.2-SYS-104 | Event payload keys and types: `object_class` str, `peak_confidence` int 0–100, `camera_number` int, `capture_ref` nullable | SYS | P0 | FR-6, AD-15 | R-016 |
| 5.2-SYS-105 | **State-write budget**: HA state-machine writes during corpus replay stay O(episodes), not O(signals) | SYS | P0 | §11.1 | R-004 |
| 5.3-SYS-106 | Motion presence clears on the inactivity timeout with no `MOTION_END` from the server | SYS | P0 | FR-7 | R-007 |
| 5.3-SYS-107 | The motion timeout is adjustable without a restart, with a documented default | SYS | P1 | FR-7 | — |
| 5.4-SYS-108 | Per-camera override beats global; absent an override, global applies | SYS | P0 | FR-8 | — |
| 5.4-SYS-109 | Options changes take effect via the update listener with **no reload and no restart** | SYS | P0 | FR-8 | — |
| 5.4-SYS-110 | Shipped defaults produce working presence on the reference corpus without tuning | SYS | P1 | FR-8 | — |
| 5.5-SYS-111 | Trigger events fire with decoded reasons; disabled reasons simply never fire and that is not an error | SYS | P1 | FR-43 | — |
| 5.6-SYS-112 | Every entity selector in both blueprints resolves against the entity set the integration actually creates | SYS | P0 | FR-37, SM-3 | R-020, TC-9 |
| 5.7-LIVE-113 | **SPIKE:** Custom Model event payload shape — runs only if a camera with a custom model exists | LIVE | P2 (gated) | Open Q1 | R-018 |
| 5.8-SYS-114 | Presence entity created per discovered custom class, honoring the same threshold/debounce — **spike-gated, auto-defers to v2** | SYS | P2 (gated) | FR-35 | R-018 |
| 5.8-SYS-115 | Users without a custom model see no additional entities | SYS | P1 | FR-35 | R-018 |

#### Epic 6 — Control SecuritySpy

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 6.1-SYS-116 | Three independent arm switches per camera; setting one leaves the other two untouched; **all eight combinations** expressible | SYS | P0 | FR-12 | — |
| 6.1-SYS-117 | Arming writes only the Arm Override; the camera's schedule assignment is unchanged afterwards | SYS | P0 | FR-13 | ASR-14 |
| 6.1-SYS-118 | Arming, camera-enable, trigger, and sensitivity controls all carry `EntityCategory.CONFIG` | SYS | P1 | FR-12, AD-12 | — |
| 6.1-SYS-119 | Override transience (≤ 6 h / next scheduled event) is reflected in state on the next poll and stated in the translation string | SYS | P1 | FR-13 | — |
| 6.2-SYS-120 | A change made server-side is reflected in HA within one reconciliation cycle, without restart — for arm mode, camera enable, triggers, and sensitivities | SYS | P0 | FR-14 | R-005 |
| 6.2-SYS-121 | HA never indefinitely reports a control state contradicting the server's (local echo yields to the next poll) | SYS | P0 | FR-14, AD-1 | R-005 |
| 6.3-SYS-122 | Schedule select is populated dynamically from `schedule-list`, never hardcoded, and is not writable from any HA surface | SYS | P0 | FR-15 | ASR-14 |
| 6.4-SYS-123 | Disabling a camera from HA disables it in SecuritySpy; its entities then behave per FR-30 rather than going stale | SYS | P1 | FR-16 | — |
| 6.5-SYS-124 | Detection Trigger toggles per class write through and survive a server restart | SYS | P1 | FR-17 | R-012 |
| 6.6-SYS-125 | Sensitivity values are constrained to the range SecuritySpy accepts; out-of-range input is rejected | SYS | P1 | FR-18 | — |
| 6.x-LIVE-126 | **Settings snapshot diff**: full settings payload before/after each single-key write, asserting zero collateral change | LIVE | P0 | AD-8 | R-012, TC-12 |
| 6.x-LIVE-127 | Enabling per-class triggers on a real camera actually produces the corresponding trigger signals (Open Q6) | LIVE | P2 | FR-43 | R-002 |
| 6.7-SYS-128 | With every camera's per-class triggers disabled, the trap is detected and guidance naming the setting is surfaced | SYS | P0 | FR-45 | R-011 |
| 6.7-SYS-129 | Guidance is dismissible and does not recur once any per-class trigger is enabled | SYS | P0 | FR-45 | R-011 |
| 6.7-SYS-130 | The integration never silently enables Detection Triggers on the user's behalf | SYS | P0 | FR-45 | R-011 |

#### Epic 7 — Ship It

| ID | Scenario | Level | Pri | Covers | Risk |
| --- | --- | --- | --- | --- | --- |
| 7.1-INT-131 | hassfest, HA pylint plugin, and HACS Action pass in CI on every change | INT | P0 | FR-36, FR-38 | ASR-12 |
| 7.1-INT-132 | Min HA version declared and enforced; CI matrix runs min + latest, plus a weekly scheduled run | INT | P0 | FR-36, §11.5 | R-008 |
| 7.1-INT-133 | Min SecuritySpy version enforced at setup with a clear message — asserted at the named constant, not a literal | INT | P1 | §11.5 | TC-11, ASR-18 |
| 7.2-INT-134 | Both blueprints pass YAML/schema validation; each uses entity selectors filtered to this integration, never a hardcoded `entity_id`; each carries its canonical source URL | INT | P0 | FR-37 | R-020 |
| 7.2-LIVE-135 | Manual import-and-fire checklist for both blueprints (**SM-3**) — the honest, un-automatable half | LIVE | P0 | FR-37, SM-3 | R-020, TC-9 |
| 7.3-INT-136 | Coverage gate: `pytest-cov` `fail_under` in CI with an explicit module list; complete config-flow coverage incl. every error/abort path | INT | P0 | FR-38 | TC-10 |
| 7.3-INT-137 | Every Bronze rule satisfied or explicitly exempted with a stated reason, declared in the repo | INT | P0 | FR-38, SM-6 | — |
| 7.4-INT-138 | Silver gate: > 95 % coverage across integration modules, plus the Silver rules for logging, availability, and reauth | INT | P0 | FR-39, SM-6 | TC-10 |
| 7.x-LIVE-139 | **SM-2 soak**: one end-to-end narrated-alert automation runs continuously on the reference system for ≥ 7 days | LIVE | P1 | SM-2 | R-004, R-007 |
| 7.x-LIVE-140 | **SM-5**: one person other than the builder completes install and setup without asking a question | LIVE | P2 | SM-5 | — |
| 7.x-INT-141 | Library is installable from PyPI and usable in a plain script with no HA present (**SM-9**) | INT | P1 | FR-40, SM-9 | — |

**Totals:** 141 scenarios. By level: UNIT 27, INT 44, SYS 62, LIVE 8.

**Priority re-triage (Step 5).** The first-pass priorities above were re-triaged in `test-design-qa.md` under the strict P0 test — blocks core **and** links to a risk ≥ 6 **and** has no workaround — which moved 17 scenarios from P0 to P1. **Final distribution: P0 72, P1 49, P2 20, P3 0.** `test-design-qa.md` is the source of record for priority; this file is the source of record for the full per-epic scenario list.

The P0 share (51 %) is high and stays high after re-triage: Bronze demands complete config-flow coverage, and most of this integration's surface is either correctness-of-the-headline or resilience — the two things the predecessor failed at. What keeps that from becoming bloat is the level distribution: half the P0s are UNIT or INT and run in milliseconds.

### 4.2 NFR Coverage and Evidence Plan

| NFR category | Validation scenarios | Level / tool | Evidence artifact for `nfr-assess` | Blocker / assumption |
| --- | --- | --- | --- | --- |
| **Performance — signal reduction** | 1.5-UNIT-023, 5.2-SYS-103, 5.2-SYS-105 | UNIT/SYS replay of the recorded corpus | Episode count + HA state-write count in the test report | — |
| **Performance — poll fan-out** | 4.2-INT-083, 4.2-INT-085, 2.4-INT-054 | INT request counting against the fake server | Request-count assertion output | — |
| **Performance — startup / lookback** | 4.x-LIVE-100 | LIVE timing run | Recorded timings at 7 d / 30 d | **UNKNOWN threshold** (Open Q2 → R-013) |
| **Performance — detection latency** | 1.3-INT-009, 5.2-SYS-103, 7.x-LIVE-139 | INT injected clock + LIVE observation | Measured classify→event latency from the soak | **PARTIAL** — "a few seconds" has no numeric bound |
| **Security — credential containment** | 1.7-UNIT-035/036/038, 1.7-INT-037, 1.x-INT-039 | UNIT/INT negative guards + CI secret scan | Guard-test results + secret-scan report | — |
| **Security — destructive surface** | 1.1-INT-002, 4.7-SYS-099 | INT surface assertion | Public-API snapshot | — |
| **Security — TLS** | 1.2-INT-006, 2.2-INT-044/045 | INT against certs | Config-flow test output | — |
| **Reliability — availability layers** | 3.1-SYS-065…068 | SYS fault injection | Three-layer availability results | — |
| **Reliability — recovery** | 3.2-SYS-069/070/071, 1.3-INT-009…013 | SYS + INT injected clock | Four-disruption suite report (**SM-7**) | **PARTIAL** — backoff schedule unspecified |
| **Reliability — poll plane is truth** | 4.3-SYS-090, 4.2-UNIT-080/081 | SYS invariant + UNIT merge | ASR-1 invariant result | — |
| **Reliability — teardown** | 3.4-SYS-074/075 | SYS | Task/timer leak assertion | — |
| **Observability — log discipline** | 3.3-INT-072/073 | INT `caplog` + injected clock | Log-volume report over a simulated outage | — |
| **Observability — diagnostics** | 1.7-UNIT-035/036 | UNIT snapshot | Redacted diagnostics snapshot | — |
| **Maintainability — coverage** | 7.3-INT-136, 7.4-INT-138 | CI `pytest-cov` | Coverage report (Bronze gate, then > 95 % Silver) | Tooling decision pending (**TC-10**) |
| **Maintainability — typing / layer purity** | 1.1-INT-001, 4.2-SYS-082, 3.1-SYS-068 | CI mypy `--strict` + import guards | mypy report + guard results | — |
| **Compatibility — versions** | 7.1-INT-132, 7.1-INT-133 | CI matrix + INT | CI matrix results | **UNKNOWN** — min SecuritySpy version (Open Q8 → TC-11) |
| **Compatibility — ONVIF coexistence** | 2.6-SYS-056 | SYS | Fresh-install entity snapshot (**SM-8**) | — |
| **Correctness — classification freshness** | 4.1-LIVE-076 | LIVE spike | Measured write-timing delta | **BLOCKER — R-001** |

### 4.3 Execution Strategy

| Stage | Contents | Budget | Gate |
| --- | --- | --- | --- |
| **Pre-commit** | ruff + mypy `--strict` on changed files | < 10 s | Local |
| **PR** | Entire UNIT + INT + SYS suite, both repos, HA min + latest matrix | **< 5 min** (library < 30 s, integration < 3 min) | Blocking merge |
| **PR (integration repo only)** | hassfest, HA pylint plugin, HACS Action, coverage `fail_under`, fixture secret scan | +2 min | Blocking merge |
| **Nightly** | Burn-in: stream, reducer, coordinator, and availability modules run 20× to surface timing flakiness (R-010); full-corpus replay at 50 simulated cameras (scalability probe) | ~15 min | Non-blocking; failures open an issue |
| **Weekly (scheduled)** | Full suite against HA `dev`/latest to catch upstream breakage before it lands in a release (R-008) | ~5 min | Non-blocking alert |
| **Pre-release (manual)** | The LIVE suite: 4.1, 4.x-100, 5.7, 6.x-126, 6.x-127, 7.2-135, plus the blueprint import checklist | ~1–2 h | **Blocking release** |
| **Continuous (reference system)** | 7.x-LIVE-139 soak — the narrated-alert automation running in production (**SM-2**) | ongoing | Blocking announcement |

The whole CI path stays under the 15-minute PR rule with an order of magnitude to spare, which is the point: per R-009, a slow suite is a direct accelerant of the risk that kills this project.

### 4.4 Resource Estimates

Ranges, not points. Assumes a single builder who is also the developer, and that test authoring is interleaved with implementation rather than following it.

| Bucket | Scope | Estimate |
| --- | --- | --- |
| **Test infrastructure** | `FakeSecuritySpyServer` + fault switches, injected clock plumbing, fixture capture + anonymization pipeline, pytest plugin export, CI wiring for both repos | **~30–45 h** |
| **P0 scenarios** (89) | The correctness, resilience, security, and quality-gate core | **~70–100 h** |
| **P1 scenarios** (32) | Control surface, diagnostics, reconfiguration, blueprint validation | **~25–40 h** |
| **P2 scenarios** (18) | Secondary flows, update entity, custom-model paths, scalability probe | **~10–20 h** |
| **LIVE suite + checklists** (8) | Spike harnesses, settings snapshot-diff tooling, manual checklists, soak setup | **~12–20 h** |
| **Total** | | **~150–225 h** |

Spread across the seven epics at the PRD's sequencing, that is roughly **4–7 weeks of concentrated effort**, or considerably longer at hobby cadence — which is the realistic case here and worth stating plainly rather than discovering later. The largest single lever is the test-infrastructure bucket: underinvesting there does not save 30 hours, it converts them into flaky-test debugging spread over the whole project.

### 4.5 Quality Gates

| Gate | Threshold |
| --- | --- |
| P0 pass rate | **100 %** — no exceptions, no retries-to-green |
| P1 pass rate | **≥ 95 %**, with every failure triaged and owned |
| P2/P3 | Tracked, not blocking |
| High-risk mitigations | Every score-≥6 risk has its mitigation scenarios implemented and passing before release |
| Critical risk | **R-001 must be resolved by the 4.1 spike before Epic 4 work is committed.** Until then Epic 4's gate is **FAIL** |
| Coverage — Bronze (release) | Complete config-flow coverage incl. every error and abort path; `fail_under` ≥ 80 % overall |
| Coverage — Silver (announcement) | **> 95 %** across integration modules |
| Quality scale | Full Bronze rule set passing in CI before the HACS release; full Silver before public announcement |
| Flakiness | Zero quarantined tests at a release tag; nightly burn-in green for 3 consecutive nights |
| Suite runtime | Library < 30 s, integration < 3 min — a regression here is treated as a defect (R-009) |
| Security | Credential guard tests and fixture secret scan passing; zero findings |
| LIVE suite | All pre-release LIVE scenarios executed and recorded within the release window |
| NFR status | Evidence source identified for every in-scope NFR category; **PASS/CONCERNS/FAIL deferred to `nfr-assess`** once implementation evidence exists |

## Step 5: Output Generation & Validation

**Execution mode resolved:** `sequential`. Config is `tea_execution_mode: auto`; subagent/agent-team orchestration was not used because this session's operating rules forbid spawning agents unless the user asks. Both documents were written and reconciled in-session.

**Outputs:**

- `_bmad-output/test-artifacts/test-design-architecture.md` (274 lines)
- `_bmad-output/test-artifacts/test-design-qa.md` (460 lines)
- `_bmad-output/test-artifacts/test-design/ha-securityspy-handoff.md` (139 lines)

### Checklist validation

**Passed:** prerequisites (PRD + spine + epics present, requirements testable); context loading; risk assessment (20 risks, unique IDs, categories, P and I in 1–3, scores correct, ≥6 flagged, mitigations/owners/timelines assigned); NFR planning (categories identified, thresholds extracted, unknowns marked UNKNOWN and converted to risks — none guessed, evidence sources named, no PASS/FAIL verdicts); coverage design (atomic scenarios, levels selected, duplicate-coverage guard applied, priorities assigned, data and tooling prerequisites documented); deliverables (risk matrix, coverage matrix, execution strategy in the simple PR/Nightly/Weekly shape, interval-only estimates, quality gates); two-document structure with actionable-first ordering; cross-document consistency (same risk IDs, same priorities, same blockers, no duplicated content); handoff document populated.

**Deviations, stated rather than papered over:**

1. **P0 share is 51 %, not the checklist's < 10 % guideline.** Strict P0 criteria were applied and moved 17 scenarios to P1; the remainder genuinely qualify. This is a protocol client whose core *is* correctness-under-restart and resilience-under-absence, with a release gate (Bronze) that mandates exhaustive config-flow coverage. Rationale documented in the QA doc's Executive Summary.
2. **Architecture doc is 274 lines against a ~150–200 target.** The overage is the 20-row risk register and the twelve mitigation plans, both explicitly required by the same checklist. Trimming would delete mandated content.
3. **Playwright-specific checklist items are N/A** (playwright-utils imports, Playwright parallelization note, k6 nightly): the stack is Python/pytest with no browser surface. Equivalents are documented — pytest markers for selection, and the reasoning for why load testing does not apply.
4. **Browser/CLI session cleanup: N/A** — no browser session was opened, so none was orphaned.
5. **Temp artifacts:** all outputs are under `_bmad-output/test-artifacts/`; nothing was written elsewhere.

**Open assumptions carried forward (none resolved by this workflow):** lookback window, fallback interval, FILE debounce, detection threshold/debounce defaults, motion timeout, min SecuritySpy version, reauth count, heartbeat-miss count, backoff schedule, upper bound on camera count, numeric detection-latency bound.
