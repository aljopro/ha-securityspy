---
title: 'Test Design for QA — SecuritySpy Home Assistant Integration'
date: 2026-08-09
author: Murat (Master Test Architect) for Jensen
status: Ready for implementation planning
project: ha-securityspy
prd: ../planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md
adr: ../planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md
companion: test-design-architecture.md
---

# Test Design for QA — SecuritySpy Home Assistant Integration

**Purpose:** The execution recipe — what to test, at which level, in what order, with what infrastructure. Architectural concerns and risk mitigation plans live in [test-design-architecture.md](test-design-architecture.md); risks are referenced here by the same IDs.

---

## Executive Summary

**Risk summary:** 20 risks — 1 critical (R-001, score 9, spike-gated), 11 high (6–8), 5 medium, 3 low.

**Coverage summary:** 141 scenarios — **72 P0**, 49 P1, 20 P2, 0 P3. By level: 27 UNIT, 44 INT, 62 SYS, 8 LIVE.

**On the P0 share (51 %).** The usual heuristic is that P0 should be under ~10 % of scenarios. That heuristic assumes a feature application with a long tail of secondary flows; this is a protocol client whose *core* is correctness-under-restart and resilience-under-absence, and whose release gate (Bronze) mandates complete config-flow coverage including every error and abort path. Applying the strict P0 test — blocks core **and** high risk **and** no workaround — still leaves 72. The deviation is stated rather than engineered away; what keeps it affordable is the level distribution, since half the P0s are UNIT or INT and run in milliseconds.

**Level taxonomy for this stack:**

| Level | Meaning | Where |
| --- | --- | --- |
| **UNIT** | Pure Python, zero I/O — models, reducer, `class_slug()`, decoders, anonymizer, merge function | Library repo (mostly) |
| **INT** | One component against a double — client/stream vs. `FakeSecuritySpyServer`, or an HA-side unit vs. a mocked library | Both repos |
| **SYS** | Full in-process stack: real library + fake server + real HA via `pytest-homeassistant-custom-component`. The CI-runnable "E2E" | Integration repo |
| **LIVE** | Against the real SecuritySpy server. `pytest -m live`, credentials from env, excluded from CI, blocking release | Manual |

---

## Not in Scope

| Excluded | Reasoning | Mitigation |
| --- | --- | --- |
| Pact / consumer-driven contract tests | No consumer/provider pair under our control; the external contract is an undocumented third-party API no broker can verify | Recorded-fixture parity + the LIVE suite (H-1) |
| Browser automation (Playwright/Cypress) | No web UI of ours; the UI is Home Assistant's own | Config-flow coverage via `pytest-homeassistant-custom-component` |
| Load testing (k6 or equivalent) | Load is not user-driven; the only load source is the integration itself, and AD-10 bounds it by design | Request-count assertions + the 50-camera nightly probe |
| Video/stream quality verification | Explicit PRD non-goal — a relay, not a video pipeline | Assert the relay plays through go2rtc and no credential appears in any log or diagnostics |
| v2 features (media browser, clip extraction, PTZ, audio, multi-server) | Out of MVP scope per PRD §7.2 | None needed; the seed forecloses none of them |
| Automated blueprint *execution* | Home Assistant provides no blueprint execution harness | Automate selector resolution; the import-and-fire check stays an explicit manual gate (TC-9) |

---

## Dependencies & Test Blockers

### Backend / architecture dependencies (pre-implementation)

These are the blockers from the architecture document. Test development on the affected epics cannot start until they land.

| ID | What QA needs | Blocks | Owner |
| --- | --- | --- | --- |
| B-1 | The classification-write-timing spike result (R-001) | All of Epic 4's freshness assertions | Builder |
| B-2 | `FakeSecuritySpyServer` with independent fault switches, exported as a pytest plugin | Epics 2–7 (nearly everything above transport) | Library |
| B-3 | Injectable time source on the stream client and reducer | Epics 1, 3, 5 timing scenarios | Library |
| B-4 | `async_reconcile(reason)` seam on the coordinator | Epic 4 reconciliation scenarios | Adapter |
| B-5 | Coverage tooling + `fail_under` decision | Epic 7 gates | CI |
| B-6 | Verified minimum SecuritySpy version | 7.1-INT-133 | Builder |
| H-3 | Log-message constants | 3.3-INT-072/073 | Adapter |

### QA infrastructure setup (pre-implementation)

1. **Fixture corpus, anonymized at capture time.** Recorded CR-framed stream frames (including the reference 191-signal/95-second classification corpus and the 467-motion-signal/zero-`MOTION_END` corpus), `caplist` responses, light and heavy status payloads, settings payloads, permission bitmasks, schedule lists. Every fixture passes through `anonymize.py` **before** it reaches disk, and CI secret-scans the corpus (TC-8, R-017).
2. **`FakeSecuritySpyServer`** — aiohttp test server serving both planes from the corpus, with `set_server_down()`, `set_camera_offline(n)`, `stall_stream()`, `drop_stream()`, `fail_auth()`, and a request recorder for fan-out assertions. Parameterizable by camera count (11 default, 50 for the nightly probe).
3. **Clock control** — the library's injected time source in library tests; `async_fire_time_changed` on the HA side. **No `asyncio.sleep` in any test.**
4. **Permission matrix fixture** — parameterized over the decoded permission bitmask, with an entity-set snapshot helper (TC-7).
5. **Entity-set snapshot helper** — used by identity, permission, ONVIF-coexistence, and blueprint-selector scenarios.
6. **LIVE suite harness** — `pytest -m live`, server credentials from environment, deselected by default in CI, plus the settings snapshot-diff tool (TC-12).

---

## Risk Assessment

Full descriptions, scores, and mitigation plans are in the architecture document. This is the QA-coverage view.

### High-priority risks (score ≥ 6)

| ID | Risk | Score | QA test coverage |
| --- | --- | --- | --- |
| R-001 | Classification write timing unknown | 9 | 4.1-LIVE-076 (spike); gates 086, 095, 096 |
| R-002 | Undocumented API drift | 6 | 1.3-UNIT-007/008, 1.4-UNIT-015, 7.1-INT-133, 6.x-LIVE-127, fixture-vs-live parity |
| R-003 | Credential leakage | 6 | 1.7-UNIT-035/036/038, 1.7-INT-037, 1.x-INT-039 |
| R-004 | Signal reduction failure | 6 | 1.5-UNIT-019…024, 5.2-SYS-103, 5.2-SYS-105 |
| R-005 | Push/poll merge regressions | 6 | 4.2-UNIT-080/081, 4.2-SYS-082, 6.2-SYS-120/121 |
| R-006 | Permanent identity errors | 6 | 2.3-SYS-047/048/049, 2.9-SYS-064 |
| R-007 | Silent stream death | 6 | 1.3-INT-009…013, 3.2-SYS-069/071, 4.4-SYS-091 |
| R-008 | HA breaking changes | 6 | 7.1-INT-131/132 (CI matrix + weekly run) |
| R-009 | Maintainer fatigue | 6 | Suite runtime budget enforced in CI; scenario-count discipline |
| R-010 | Async/timing flakiness | 6 | Injected clock everywhere; nightly burn-in |
| R-011 | Default-install trap | 6 | 6.7-SYS-128/129/130 |
| R-012 | Settings collateral damage | 6 | 1.6-INT-032, 6.x-LIVE-126 |
| R-017 | Fixture corpus leakage | 6 | 1.x-INT-039 + capture-time anonymization |

### Medium / low risks

| ID | Risk | Score | QA test coverage |
| --- | --- | --- | --- |
| R-013 | Lookback startup cost | 4 | 4.3-SYS-087, 4.x-LIVE-100, 4.2-INT-085 |
| R-014 | Auth-counter double-ownership | 4 | 2.8-INT-061/062/063 |
| R-015 | Unclean teardown | 4 | 3.4-SYS-074/075, 1.3-INT-014 |
| R-016 | Slug collisions / unknown classes | 4 | 1.5-UNIT-027/028, 5.2-SYS-104 |
| R-020 | Blueprint drift | 4 | 5.6-SYS-112, 7.2-INT-134, 7.2-LIVE-135 |
| R-018 | Custom Model spike unrunnable | 3 | 5.7-LIVE-113, 5.8-SYS-114/115 (gated) |
| R-019 | Cert verification normalization | 2 | 2.2-INT-044/045 |

---

## NFR Test Coverage Plan

| NFR category | Requirement / threshold | Planned validation | Level | Evidence artifact | Pri |
| --- | --- | --- | --- | --- | --- |
| PERF — signal reduction | ~190:1; per-signal writes are a defect | Corpus replay asserting episode count + HA state-write count | UNIT, SYS | Test report counters | P0 |
| PERF — poll fan-out | ≤ 1 `caplist` per class per cycle | Request-count assertion at 11 cameras | INT | Fake-server request log | P0 |
| PERF — startup / lookback | **UNKNOWN** (Open Q2) | Timed measurement at 7 d and 30 d | LIVE | Recorded timings | P2 |
| PERF — detection latency | "a few seconds", no numeric bound | Injected-clock assertion (debounce + transport); observed in soak | INT, LIVE | Soak observations | P1 |
| SEC — credential containment | Absolute, all levels | Negative guards + fixture secret scan | UNIT, INT | Guard results + scan report | P0 |
| SEC — destructive surface | Absolute absence | Public-API and endpoint-table assertion | INT | API snapshot | P0 |
| SEC — TLS | Verify on by default; consequence stated | Config-flow default + string assertion | INT | Config-flow report | P1 |
| REL — availability layers | Three distinct behaviors | Independent fault injection | SYS | Availability matrix | P0 |
| REL — recovery | No restart, reload, or reauth needed | Four-disruption suite (SM-7) | SYS | Suite report | P0 |
| REL — stream loss | 3 missed beats (~30 s) | Injected-clock boundary test at 2 and 3 | INT | Timing assertions | P0 |
| REL — backoff | Indefinite exponential, schedule unspecified | Monotonic, capped, never-stops assertion | INT | Backoff trace | P0 |
| REL — poll plane is truth | Absolute (AD-1) | ASR-1 invariant: stream dead from boot | SYS | Invariant result | P0 |
| REL — motion clearing | No dependence on `MOTION_END` | 467-signal / zero-end corpus replay | UNIT, SYS | Replay result | P0 |
| OPS — log discipline | Once / DEBUG / once; no proportional volume | `caplog` over a simulated multi-hour outage | INT | Log-volume report | P0 |
| OPS — diagnostics | Downloadable and redacted | Snapshot through the anonymizer | UNIT | Diagnostics snapshot | P0 |
| MAINT — coverage | Bronze full config-flow; Silver > 95 % | `pytest-cov` `fail_under` in CI | CI | Coverage report | P0 |
| MAINT — typing / layer purity | `mypy --strict`; no cross-layer imports | CI gate + import guards | INT | mypy + guard results | P1 |
| COMPAT — versions | Min SecuritySpy **UNKNOWN**; min HA 2026.3 | CI matrix; behavior-at-constant test | INT | Matrix results | P0/P1 |
| SEC — stream credential containment | No password or base64 credential in any log record or diagnostics during live video | All-logger capture + diagnostics snapshot (SM-8) | SYS | Capture | P0 |
| CORRECTNESS — freshness | **UNKNOWN — blocking** (Open Q3) | Live spike | LIVE | Spike report | P0 |

**Missing thresholds / evidence sources:** lookback window, fallback interval, FILE debounce, detection threshold and debounce defaults, minimum SecuritySpy version, upper bound on camera count, numeric detection-latency bound, backoff schedule. Each is tracked as an assumption or risk in the architecture document; none are guessed here.

**Boundary:** this plan identifies evidence sources. Final PASS/CONCERNS/FAIL belongs to `nfr-assess` once implementation evidence exists.

---

## Entry Criteria

- B-2 (fake server) and B-3 (injectable clock) merged — without these, most scenarios cannot be written at all.
- Fixture corpus captured, anonymized, and secret-scanned.
- Both repos scaffolded with pytest, ruff, mypy `--strict`, and CI wired.
- Live reference server reachable with a least-privileged test user, credentials available to the LIVE suite via environment.
- B-1 (spike result) before Epic 4 test development specifically.

## Exit Criteria

| Criterion | Threshold |
| --- | --- |
| P0 pass rate | 100 % — no exceptions, no retries-to-green |
| P1 pass rate | ≥ 95 %, every failure triaged and owned |
| P2 | Tracked, not blocking |
| Open defects | Zero open P0 or P1 defects at a release tag |
| High-risk mitigations | Every score-≥6 risk has its scenarios implemented and passing |
| Critical risk | R-001 resolved; Epic 4's gate flipped from FAIL |
| Coverage — release (Bronze) | Complete config-flow coverage incl. every error/abort path; `fail_under` ≥ 80 % overall |
| Coverage — announcement (Silver) | > 95 % across integration modules |
| Flakiness | Zero quarantined tests at a release tag; nightly burn-in green 3 consecutive nights |
| Suite runtime | Library < 30 s, integration < 3 min |
| Security | Credential guards and fixture secret scan clean |
| LIVE suite | All pre-release LIVE scenarios executed and recorded within the release window |

---

## Test Coverage Plan

> **P0/P1/P2/P3 denote priority and risk, not execution timing.** Everything CI-runnable runs on every PR regardless of priority — see Execution Strategy.

### P0 (Critical) — 72 scenarios

*Criteria:* blocks core functionality **and** links to a high risk (≥ 6) **and** has no workaround.

| Test ID | Requirement | Level | Risk | Notes |
| --- | --- | --- | --- | --- |
| 1.1-INT-002 | AD-2 — no destructive/remote-exec endpoint on the public surface or in `const.py` | INT | ASR-6 | You cannot call what does not exist |
| 1.2-INT-005 | AD-6 — each library exception maps to exactly one HA outcome | INT | ASR-17 | Table-driven; no raw `aiohttp` error escapes |
| 1.3-UNIT-007 | CR framing: multi-frame, split, trailing partial, empty, oversized | UNIT | R-002 | Highest-drift-exposure parser |
| 1.3-UNIT-008 | Malformed frame skipped without killing the stream or corrupting the next | UNIT | R-002 | |
| 1.3-INT-009 | Loss declared at exactly 3 missed heartbeats, not 2 | INT | R-007 | Injected clock |
| 1.3-INT-010 | **Stall** (socket open, no bytes) detected as loss, distinct from a drop | INT | R-007 | The failure users never report |
| 1.3-INT-011 | Backoff monotonic, capped, retries indefinitely | INT | R-007 | Injected clock |
| 1.3-INT-012 | Connection callbacks fire once per transition, in order | INT | R-007 | |
| 1.3-INT-013 | `auth_failed` pauses reconnection and defers to the adapter | INT | R-014 | Library never self-retries auth |
| 1.3-INT-014 | `disconnect()` idempotent; cancels every task and timer | INT | R-015 | |
| 1.4-UNIT-015 | `caplist` decoding: `f`+`s` → UTC datetime; `o` bitmask → class set | UNIT | R-002 | |
| 1.4-UNIT-018 | Absent value is `None` — never epoch, never zero | UNIT | — | Across every timestamp field |
| 1.5-UNIT-019 | Sub-threshold signals open no episode, however frequent | UNIT | R-004 | |
| 1.5-UNIT-020 | Isolated qualifying signals below debounce open no episode | UNIT | R-004 | No flicker |
| 1.5-UNIT-021 | Peak confidence is the episode maximum, not the crossing value | UNIT | — | |
| 1.5-UNIT-022 | Exactly one episode per contiguous qualifying run per class per camera | UNIT | R-004 | |
| 1.5-UNIT-023 | **Reference corpus**: 191 signals / 95 s → O(1) episodes | UNIT | R-004 | The ~190:1 requirement |
| 1.5-UNIT-026 | Motion clears on inactivity timeout with a zero-`MOTION_END` corpus | UNIT | R-007 | 467-signal reference camera |
| 1.5-UNIT-028 | Unknown Object Class carries end-to-end without disturbing built-ins | UNIT | R-016 | |
| 1.6-UNIT-029 | Permission bitmask decoding across the full matrix | UNIT | TC-7 | Feeds FR-28 gating |
| 1.6-UNIT-031 | Bool asymmetry: `true/false` read, `1/0` write | UNIT | R-012 | |
| 1.6-INT-032 | Settings write is a single-key partial POST | INT | R-012 | Payload contains only the changed key |
| 1.6-INT-034 | No code path issues a schedule-mutating request | INT | ASR-14 | Asserted across the arming surface |
| 1.7-UNIT-035 | Anonymizer redacts usernames, passwords, tokens, device credentials | UNIT | R-003 | |
| 1.7-UNIT-036 | **Negative guard**: no fixture credential substring survives into diagnostics | UNIT | R-003 | |
| 1.7-INT-037 | Settings payloads never logged at any level, DEBUG included | INT | R-003 | |
| 1.7-UNIT-038 | No credentials in exception messages or stack traces | UNIT | R-003 | Includes credential-bearing URLs |
| 1.x-INT-039 | Fixture corpus secret scan in CI | INT | R-017 | Fixtures are a distribution surface |
| 1.x-INT-040 | Fake-server self-test: every fault switch behaves as declared | INT | TC-1/TC-4 | Infrastructure correctness |
| 2.1-INT-041 | Config flow happy path, no YAML | INT | — | Bronze requirement |
| 2.1-INT-042 | Distinct strings for every error and abort path | INT | R-002 | Bronze mandates completeness |
| 2.1-INT-043 | Duplicate server (same UUID) aborts regardless of address used | INT | R-006 | |
| 2.3-SYS-047 | **Identity format frozen** — exact unique-ID strings asserted | SYS | R-006 | Permanent after release |
| 2.3-SYS-048 | Camera rename → device renamed, zero unique-ID churn | SYS | R-006 | |
| 2.3-SYS-049 | Host/IP/port change → no duplicates, no orphans | SYS | R-006 | |
| 2.3-SYS-050 | Eleven cameras correctly named; no IP names, no "Generic" | SYS | — | **SM-4** |
| 2.6-SYS-056 | Live video plays via relay; no credential in any log or diagnostics; option off removes entities | SYS | — | **SM-8**, credentials contained |
| 2.7-SYS-058 | Permission matrix → expected entity set per combination | SYS | TC-7 | |
| 2.7-SYS-060 | No entity created that is permanently unavailable by permission | SYS | TC-7 | |
| 2.8-INT-061 | 2 failures → no reauth; 3rd → `ConfigEntryAuthFailed`, both planes stop | INT | R-014 | |
| 2.8-INT-062 | Counter fed by both planes; resets on success on either | INT | R-014 | |
| 3.1-SYS-065 | Server unreachable → all entities unavailable, none stale | SYS | ASR-7 | |
| 3.1-SYS-066 | One camera offline → only that device's entities, no error | SYS | ASR-7 | |
| 3.1-SYS-067 | Stream lost, poll healthy → only push-derived presence unavailable | SYS | ASR-7 | The layer most likely to collapse |
| 3.2-SYS-069 | Reconnect triggers **exactly one** reconciliation | SYS | R-007 | |
| 3.2-SYS-071 | **Four-disruption suite** — restart, reboot, network drop, HA restart | SYS | R-007 | **SM-7** |
| 3.3-INT-072 | Loss once ERROR, retries DEBUG, recovery once WARNING | INT | TC-5 | Asserted against constants |
| 3.4-SYS-074 | Unload leaves zero tasks, timers, connections | SYS | R-015 | |
| 4.1-LIVE-076 | **SPIKE** — when SecuritySpy writes classification to a capture | LIVE | **R-001** | **Blocking; gate is FAIL until this returns** |
| 4.2-SYS-077 | Three Observation Record values per camera, `device_class: timestamp` | SYS | — | The headline |
| 4.2-SYS-078 | Absent (`None`) when no capture of that class is in the window | SYS | — | |
| 4.2-UNIT-080 | **Watermark merge** — push advances only; poll overwrites incl. regressions | UNIT | R-005 | |
| 4.2-UNIT-081 | Out-of-order interleaving converges to the poll result, no flicker | UNIT | R-005 | |
| 4.2-INT-083 | ≤ 1 `caplist` per class per cycle at 11 cameras — never 33 | INT | ASR-9 | §10.2 |
| 4.2-INT-084 | Reconciliation fires on startup, reconnect, debounced FILE, fallback | INT | TC-3 | Each carries its reason |
| 4.2-INT-085 | A burst of FILE events collapses into one debounced cycle | INT | R-013 | No poll storm |
| 4.3-SYS-086 | **Restart correctness** — populated on first refresh, no new detection needed | SYS | R-001 | **SM-1** |
| 4.3-SYS-087 | Setup is not blocked on hydration | SYS | R-013 | |
| 4.3-SYS-088 | Post-restart values equal pre-restart where nothing intervened | SYS | — | |
| 4.3-SYS-089 | Restart mid-episode neither corrupts nor blanks the record | SYS | R-005 | |
| 4.3-SYS-090 | **ASR-1 invariant** — stream dead from boot, all values still correct | SYS | ASR-1 | The predecessor's defect, inverted |
| 4.4-SYS-091 | Detections missed while disconnected appear after reconciliation | SYS | R-007 | **SM-1** |
| 4.5-SYS-092 | Latest Capture served by HA; consumer needs no SecuritySpy access | SYS | — | |
| 4.5-SYS-093 | Image URL survives image updates and HA restarts | SYS | — | |
| 4.5-SYS-094 | Image state is the capture timestamp; usable as a state trigger | SYS | — | |
| 4.5-SYS-095 | Startup state reflects the newest existing capture | SYS | R-001 | Not empty, not restart-time |
| 4.7-SYS-098 | Distinct errors: no recording / disallowed path / unwritable | SYS | — | Validation vs. operational |
| 4.7-SYS-099 | The download service never deletes or modifies anything server-side | SYS | ASR-6 | |
| 5.1-SYS-101 | Per-class presence discoverable as UI device triggers | SYS | R-020 | The automation-editor promise |
| 5.1-SYS-102 | Presence on at episode open, off at close | SYS | — | |
| 5.2-SYS-103 | Exactly one event per episode — 191 signals ≠ 191 events | SYS | R-004 | |
| 5.2-SYS-104 | Event payload keys and types per AD-15 | SYS | R-016 | Schema is permanent |
| 5.2-SYS-105 | HA state writes stay O(episodes), not O(signals) | SYS | R-004 | |
| 5.3-SYS-106 | Motion clears on timeout with no server-side end signal | SYS | R-007 | |
| 5.6-SYS-112 | Every blueprint selector resolves against the real entity set | SYS | R-020 | The entity-model design test |
| 6.1-SYS-117 | Arming writes only the override; schedule assignment unchanged | SYS | ASR-14 | Destroys user config if violated |
| 6.2-SYS-120 | Server-side change reflected within one cycle, no restart | SYS | R-005 | All four writable control types |
| 6.2-SYS-121 | HA never indefinitely contradicts the server's state | SYS | R-005 | Local echo yields to poll |
| 6.3-SYS-122 | Schedule select dynamic, never hardcoded, never writable | SYS | ASR-14 | |
| 6.x-LIVE-126 | **Settings snapshot diff** — zero collateral change per single-key write | LIVE | R-012 | Unit tests are blind to this |
| 6.7-SYS-128 | All-triggers-disabled → trap detected, guidance names the setting | SYS | R-011 | First-run trust |
| 6.7-SYS-129 | Guidance dismissible, non-recurring once any trigger is enabled | SYS | R-011 | |
| 6.7-SYS-130 | Never silently enables Detection Triggers | SYS | R-011 | |
| 7.1-INT-131 | hassfest + HA pylint plugin + HACS Action green on every change | INT | ASR-12 | |
| 7.2-INT-134 | Blueprints validate; selectors filtered to this integration; source URL present | INT | R-020 | No hardcoded entity IDs |
| 7.2-LIVE-135 | Manual blueprint import-and-fire checklist | LIVE | R-020 | **SM-3**; the honest manual half |
| 7.3-INT-136 | Coverage gate with explicit module list; full config-flow coverage | INT | TC-10 | Bronze |
| 7.3-INT-137 | Every Bronze rule satisfied or explicitly exempted in-repo | INT | — | **SM-6** |
| 7.4-INT-138 | Silver gate: > 95 % coverage + Silver logging/availability/reauth rules | INT | TC-10 | Gates announcement |

### P1 (High) — 49 scenarios

*Criteria:* important features, medium risk, or common workflows with a workaround.

| Test ID | Requirement | Level | Risk | Notes |
| --- | --- | --- | --- | --- |
| 1.1-INT-001 | Build, `mypy --strict`, ruff, no HA imports in the library | INT | ASR-6 | CI catches it before users do |
| 1.2-INT-003 | Caller-injected session, never self-constructed | INT | — | Platinum-adjacent constraint |
| 1.2-INT-004 | Auth success returns typed models; no raw dicts cross the boundary | INT | — | |
| 1.2-INT-006 | HTTPS: matching cert, mismatched cert, verification off | INT | R-019 | |
| 1.4-UNIT-016 | Unclassified capture → empty class set, never absent | UNIT | — | |
| 1.4-UNIT-017 | Server-side class filter + `cams=` batching request shape | UNIT | R-013 | |
| 1.5-UNIT-024 | Concurrent classes and 11-camera isolation, no cross-talk | UNIT | R-004 | |
| 1.5-UNIT-025 | Per-camera/class threshold and debounce injection, mid-stream change | UNIT | — | |
| 1.5-UNIT-027 | `class_slug()` normalization, idempotence, collision → one warning | UNIT | R-016 | Never a silent merge |
| 1.6-UNIT-030 | Trigger reasons decoded to names, never a raw bitmask | UNIT | — | |
| 1.6-UNIT-033 | Schedule model parses user-defined schedules; no hardcoded list | UNIT | — | |
| 2.2-INT-044 | Verification defaults on; consequence string present | INT | R-019 | |
| 2.2-INT-045 | LAN IP + dyndns cert: clear failure on, success off | INT | R-019 | |
| 2.3-SYS-046 | Hub device `entry_type=SERVICE`; cameras `via_device` → hub | SYS | — | |
| 2.3-SYS-051 | Camera keys are `int` throughout `SecuritySpyData` | SYS | — | AD-15 |
| 2.4-SYS-053 | Hub and camera health entities exist, categorized DIAGNOSTIC | SYS | — | |
| 2.4-INT-054 | Light status endpoint preferred over heavy | INT | R-013 | 794 B vs 27 KB |
| 2.7-SYS-059 | Omitted capability raises a repair issue naming the permission | SYS | — | |
| 2.8-INT-063 | Completing reauth restarts both planes without removing the entry | INT | — | |
| 2.9-SYS-064 | Reconfigure preserves devices, entities, recorded history | SYS | R-006 | |
| 3.1-SYS-068 | No platform overrides `available` with its own logic | SYS | — | Source guard |
| 3.2-SYS-070 | Recovery needs no restart, reload, or reauth | SYS | — | Covered partly by 071 |
| 3.3-INT-073 | Simulated multi-hour outage → bounded log volume | INT | R-009 | Injected clock |
| 3.4-SYS-075 | Unload → reload → unload cycle without an HA restart | SYS | R-015 | |
| 4.2-SYS-079 | Values usable in conditions/templates; render as relative time | SYS | — | |
| 4.2-SYS-082 | Nothing outside the merge function writes those values | SYS | R-005 | Source guard |
| 4.6-SYS-096 | Detected-class set alongside the image; empty list when none | SYS | R-001 | |
| 4.7-SYS-097 | `download_latest_recording` writes to an allowlisted destination | SYS | — | |
| 5.3-SYS-107 | Motion timeout adjustable without restart, documented default | SYS | — | |
| 5.4-SYS-108 | Per-camera override beats global; global applies when absent | SYS | — | |
| 5.4-SYS-109 | Options changes apply via update listener, no reload | SYS | — | |
| 5.4-SYS-110 | Shipped defaults produce working presence on the corpus | SYS | — | Validates Open Q5 provisional values |
| 5.5-SYS-111 | Trigger events fire with decoded reasons; disabled ones simply don't | SYS | — | Absence is not an error |
| 5.8-SYS-115 | Users without a custom model see no extra entities | SYS | R-018 | |
| 6.1-SYS-116 | Three independent arm switches; all eight combinations expressible | SYS | — | |
| 6.1-SYS-118 | Config controls carry `EntityCategory.CONFIG` | SYS | — | |
| 6.1-SYS-119 | Override transience reflected in state and stated in strings | SYS | — | Never implies permanence |
| 6.4-SYS-123 | Camera disable writes through; entities then follow FR-30 | SYS | — | |
| 6.5-SYS-124 | Detection Trigger toggles survive a server restart | SYS | R-012 | |
| 6.6-SYS-125 | Sensitivity constrained to SecuritySpy's accepted range | SYS | — | |
| 7.1-INT-132 | CI matrix at min + latest HA, plus a weekly scheduled run | INT | R-008 | |
| 7.1-INT-133 | Min SecuritySpy version enforced at the named constant | INT | TC-11 | Blocked on B-6 |
| 7.x-LIVE-139 | **SM-2 soak** — narrated-alert automation running ≥ 7 days | LIVE | R-004 | Production evidence |
| 7.x-INT-141 | Library installable from PyPI and usable with no HA present | INT | — | **SM-9** |

The remaining P1 rows are the per-epic scenarios enumerated in [test-design-progress.md §4.1](test-design-progress.md), which holds the complete 141-row matrix organized by epic. That file is the source of record for scenario IDs; this document is the source of record for **priority**, which was re-triaged here under the strict P0 criteria.

### P2 (Medium) — 20 scenarios

*Criteria:* secondary features, low risk, or edge cases.

| Test ID | Requirement | Level | Risk | Notes |
| --- | --- | --- | --- | --- |
| 2.3-SYS-052 | Cameras appearing/disappearing server-side add/remove devices without reload | SYS | — | Gold pattern, adopted early |
| 2.5-SYS-055 | Update entity reports availability and version; no install path in v1 | SYS | — | |
| 2.6-SYS-057 | Enabling a camera entity yields working live video | SYS | — | |
| 4.x-LIVE-100 | Lookback cost measured at 7 d and 30 d, 11 real cameras | LIVE | R-013 | Resolves Open Q2 |
| 5.7-LIVE-113 | **SPIKE** — Custom Model payload shape | LIVE | R-018 | Runs only if such a camera exists |
| 5.8-SYS-114 | Presence entity per discovered custom class | SYS | R-018 | Spike-gated; auto-defers to v2 |
| 6.x-LIVE-127 | Enabling per-class triggers actually produces trigger signals | LIVE | R-002 | Open Q6 |
| 7.x-LIVE-140 | One other person installs successfully without asking | LIVE | — | **SM-5** |

The remaining P2 rows — diagnostics detail, secondary error paths, the 50-camera scale probe, and the balance of the epic tables — are enumerated in [test-design-progress.md §4.1](test-design-progress.md).

### P3 (Low)

None. Benchmark-style work is folded into the LIVE measurements rather than split into a separate tier — a P3 bucket here would be scenarios nobody ever runs, which is worse than not writing them.

---

## Execution Strategy

**Philosophy:** run everything in PRs unless it is expensive or genuinely cannot run in CI. The entire CI-runnable suite fits in ~5 minutes, an order of magnitude under the 15-minute rule — which matters, because per R-009 a slow suite is the most direct way a test strategy causes the failure it exists to prevent.

### Every PR (~5 min)

- Full UNIT + INT + SYS suite, both repos (139 CI-runnable scenarios).
- HA version matrix: declared minimum and latest.
- hassfest, HA pylint plugin, HACS Action, `pytest-cov` `fail_under`, ruff, `mypy --strict`.
- Fixture secret scan.
- **Blocking merge.**

### Nightly (~15 min)

- Burn-in: stream, reducer, coordinator, and availability modules run 20× to surface timing flakiness (R-010).
- 50-camera scale probe against the parameterized fake server.
- **Non-blocking**; a failure opens an issue.

### Weekly (scheduled, ~5 min)

- Full suite against the current HA release, independent of commit activity, so upstream breakage surfaces before a user finds it (R-008).
- **Non-blocking alert.**

### Pre-release, manual (~1–2 h) — **blocking release**

The LIVE suite: 4.1-LIVE-076, 4.x-LIVE-100, 5.7-LIVE-113, 6.x-LIVE-126, 6.x-LIVE-127, 7.2-LIVE-135, plus the fixture-vs-live parity diff.

### Continuous, on the reference system — **blocking announcement**

7.x-LIVE-139: the narrated-alert automation running in production (SM-2), and 7.x-LIVE-140 (SM-5) when an opportunity arises.

---

## QA Effort Estimate

QA effort only; production-code effort is not included.

| Bucket | Estimate |
| --- | --- |
| Test infrastructure (fake server, fault switches, clock plumbing, fixture capture + anonymization, pytest plugin, CI wiring) | **~30–45 h** |
| P0 scenarios (72) | **~65–95 h** |
| P1 scenarios (49) | **~30–45 h** |
| P2 scenarios (20) | **~10–20 h** |
| LIVE suite + manual checklists (8) | **~12–20 h** |
| **Total** | **~150–225 h** |

At concentrated effort that is roughly **4–7 weeks**; at hobby cadence, considerably longer — worth stating now rather than discovering in month three. The single largest lever is the infrastructure bucket: underinvesting there does not save 30 hours, it converts them into flaky-test debugging spread across every epic.

---

## Implementation Planning Handoff

| Task | Owner | Target |
| --- | --- | --- |
| Fake server + fault switches + pytest plugin export | Library / QA | Epic 1, first |
| Injectable clock in stream client and reducer | Library | Epic 1, first |
| Fixture capture procedure + anonymization + secret scan | Library / QA | Epic 1 |
| Classification-write-timing spike | Builder | Before Epic 4 |
| `async_reconcile(reason)` seam | Adapter | Epic 4 |
| Coverage tooling decision + CI wiring | CI | Epic 1 (not Epic 7 — retrofitting is the trap) |
| Settings snapshot-diff harness | Builder | Epic 6, with the first writable control |
| Blueprint selector-resolution test | QA | Epic 5, alongside the blueprint draft |

---

## Tooling & Access

| Tool / access | Purpose | Status |
| --- | --- | --- |
| pytest + pytest-asyncio | Both suites | Standard |
| pytest-homeassistant-custom-component 0.13.x | SYS level | Standard |
| pytest-cov | Bronze/Silver coverage gates | **Pending decision (B-5)** |
| aiohttp test utils | Fake server | Standard |
| ruff, mypy `--strict` | Static gates | Standard |
| hassfest, HA pylint plugin, HACS Action | Quality-scale verification | Standard (GitHub Actions) |
| Secret scanner (e.g. gitleaks) | Fixture corpus | **To add** |
| Live SecuritySpy reference server + least-privileged user | LIVE suite | **Required — Jensen's own system** |
| A camera running a Custom Model | FR-35 spike | **Not available** — FR-35 auto-defers |

---

## Interworking & Regression

| Impacted component | Regression scope |
| --- | --- |
| `aiosecurityspy` (library) | Any protocol change re-runs the full UNIT + INT suite and the fixture-vs-live parity diff |
| Integration adapter (coordinator, config flow) | Coordinator changes re-run all SYS scenarios in Epics 3 and 4 — the merge and availability behaviors are the fragile ones |
| Entity platforms | Platform changes re-run the entity-set snapshots (identity, permissions, ONVIF coexistence) and the blueprint selector test |
| Home Assistant (external) | Weekly scheduled run; a breaking HA release triggers a full-suite regression pass |
| SecuritySpy server (external) | A server upgrade on the reference system triggers the LIVE parity diff before any release |
| ONVIF / Generic Camera (coexistence) | Never modified by us; regression is limited to asserting our option removes our camera entities and touches no other integration's |

---

## Appendix A: Tagging & Selection

Markers: `live` (excluded from CI), `burnin` (nightly repetition targets), `slow` (anything above the per-test budget), plus per-epic markers for selective runs.

```
pytest -m "not live"                  # default CI selection
pytest -m live                        # pre-release manual gate (needs env credentials)
pytest -m burnin --count=20           # nightly flakiness hunt
pytest tests/unit                     # library fast loop (<30 s)
```

## Appendix B: Knowledge Base References

- `risk-governance.md` — scoring thresholds and gate decision rules
- `probability-impact.md` — 1–3 probability/impact definitions
- `test-levels-framework.md` — level selection and the duplicate-coverage guard
- `test-priorities-matrix.md` — P0–P3 criteria
- `nfr-criteria.md` — NFR validation patterns
- `test-quality.md` — determinism, isolation, and the no-hard-waits definition of done
- `adr-quality-readiness-checklist.md` — the 8-category testability frame behind TC-1…TC-12
