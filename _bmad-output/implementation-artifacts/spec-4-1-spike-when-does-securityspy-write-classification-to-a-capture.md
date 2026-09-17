---
title: 'Spike: when does SecuritySpy write classification to a capture?'
type: 'chore'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
baseline_revision: '5fc9fd6'
final_revision: '519a2ac159b5cb1b62bf506112eda34ebd0f0728'
---

<intent-contract>

## Intent

**Problem:** Epic 4's freshness claims (FR-2/FR-3/FR-11, PRD Open Q3) hang on an unmeasured fact: whether SecuritySpy writes a capture's object classification (`o` in `caplist`) at capture close or some time afterwards. No research doc, spec, or test has ever measured that delta; the 7-day lookback and AD-10 poll-cycle assumptions were never checked against it.

**Approach:** A live probe against the reference server triggers the test camera, polls capture history from the moment the recording ends, and measures when the capture's class set becomes populated. Write up the measurement with its consequences, record the finding in the architecture memlog, and confirm or correct the lookback and polling assumptions. The epic proceeds regardless with the honest latency documented.

## Boundaries & Constraints

**Always:**
- Never print, log, or commit a credential value anywhere (probe output, write-up, memlog). Read `.env` only through the library's `live_env.py`; follow AD-13.
- Any probe write (manual trigger) is gated on `SECURITYSPY_ALLOW_WRITES=1`; the probe and any live test skip cleanly when it is unset.
- The write-up states the exact SecuritySpy build and camera tested, and marks any sub-finding that could not be exercised live (e.g. no classified capture in the window) as explicitly untested — never fabricate a number.
- The probe uses only the library's existing public surface (`SecuritySpyClient`, `Capture`, `async_get_captures`, `async_get_server_info`), plus a raw manual-trigger request confined to the library repo, where wire knowledge lives per AD-2.
- The measurement is recorded verbatim: per-trigger capture appearance time, recording-close time (`start + duration`), classification-populated time, and the deltas.

**Block If:** (none — the reference server, a triggerable test camera, and a write-enabled `.env` already exist; nothing here requires a decision only a human can make)

**Never:**
- No production changes to `client.py`, `connection.py`, `relay.py`, `diagnostics.py`, or `episodes.py`; no library release.
- No raw SecuritySpy endpoint knowledge in the integration repo's code — the probe (which carries the manual-trigger call) lives in the library repo.
- No fabricated or hard-coded latency numbers; no flaky wall-clock-bound assertion in the permanent test suite — a live test may assert mechanism (a triggered capture appears and its class set is decodable), not a timing bound.
- No changes to Epic 4's acceptance criteria; an unfavourable result means the epic proceeds with the honest latency documented.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Manual trigger creates a motion movie | Trigger via the endpoint documented in `research/securityspy-api-reference.md` §2.1, ADMIN account | A new capture for the test camera appears in `caplist` within the poll window | Keep polling; record appearance time |
| Capture appears already classified | First poll shows a non-empty `object_classes` | Delta from recording close is ~0 — classification present at close | Record as "classified at first sight" |
| Capture appears unclassified, then populates | Later poll flips `object_classes` from empty to non-empty | Measure delta between classification-populated time and recording close | Record the measured lag |
| `object_classes` stays empty for the full window | No human/vehicle/animal detected in the scene | Unclassified capture | Report as an unclassified sample, never invent a class |
| Trigger produces no capture | Camera not armed for recording | No capture matches the trigger window | Report as a setup constraint, do not fabricate a latency |

</intent-contract>

## Code Map

- `aiosecurityspy/scripts/measure_classification_write_timing.py` (new, in the standalone library repo `/Users/jensen/projects/aiosecurityspy`) -- the measurement probe: trigger, poll `async_get_captures(capture_filter=0)` on a short cadence, emit a per-trigger table.
- `aiosecurityspy/tests/test_live_server.py` (standalone repo) -- one soft live regression test for the mechanism, `@pytest.mark.live`, gated on `SECURITYSPY_ALLOW_WRITES`.
- `_bmad-output/planning-artifacts/research/securityspy-classification-write-timing.md` (new, this repo) -- the write-up Story 4.1's ACs require.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` -- append one `(finding)` line.
- Reference reads (no edits): `aiosecurityspy/src/aiosecurityspy/client.py` (`async_get_captures`, `async_get_server_info`, `CAPTURE_FILTER_ALL`), `models.py` (`Capture` fields `start`/`duration`/`object_classes`), `tests/live_env.py` (env access, `_test_camera` pattern).

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/scripts/measure_classification_write_timing.py` -- trigger the test camera, poll `caplist` (via `async_get_captures`, `capture_filter=0`) every few seconds from before recording end until the class set settles or a timeout, print a per-trigger measurement row (appearance time, close time, classified time, deltas) -- this is the instrument behind Story 4.1's first AC.
- [x] `aiosecurityspy/tests/test_live_server.py` -- add one soft live test: a manual-triggered capture appears in `caplist` and, if classified, exposes a non-empty decodable `object_classes`; skip when `SECURITYSPY_ALLOW_WRITES` is unset -- locks in the mechanism without a brittle timing bound.
- [x] `_bmad-output/planning-artifacts/research/securityspy-classification-write-timing.md` -- write up: build and camera tested, method, per-trigger measurements, whether classification is present at capture close or lags (and by how long), the consequence for restart correctness and for whether the capture's class set can lag the image by one poll, and the confirmed-or-corrected lookback (7-day) and AD-10 poll-cycle assumptions -- satisfies Story 4.1's write-up ACs.
- [x] architecture `.memlog.md` -- append one `(finding)` line dated 2026-09-16 pointing to the research doc, summarizing the headline result and the lookback/polling conclusion -- satisfies "recorded in the architecture memlog".

**Acceptance Criteria:**
- Given a configured `.env` (host, `SECURITYSPY_TEST_CAMERA`, a trigger-capable account, `SECURITYSPY_ALLOW_WRITES=1`), when the probe runs, then it measures and records, per trigger, the elapsed time between the capture appearing and its classification being populated, relative to recording close.
- Given the write-up, when it is read, then it states whether classification is present at capture close or lags and by how long, states the consequence for restart correctness and for whether the capture's class set can lag the image by one poll, and records the finding in the architecture memlog with the lookback and polling assumptions confirmed or corrected.
- Given an unfavourable result, when the spike concludes, then Epic 4 proceeds regardless with the honest latency documented and no epic AC changes.
- Given `SECURITYSPY_ALLOW_WRITES` unset, when the library live suite runs, then the new test skips and no other test is affected.
- Given the write-up and memlog entry, when scanned for credentials, then they contain no password/token/host-scoped secret values.

## Spec Change Log

## Review Triage Log

### 2026-09-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 24: (high 4, medium 7, low 13)
- defer: 0
- reject: 1: (low 1)
- addressed_findings:
  - `[high]` `[patch]` Probe stopped at the first classified sighting, computing `close` from a possibly non-final `duration` — exactly the measurement the spike exists to make. Now keeps polling past a classified sighting until the recording has closed with a stable duration (two consecutive identical durations) before emitting the delta.
  - `[high]` `[patch]` The live test kept the password and its base64 Authorization header in the test frame past the trigger; a `--showlocals` failure could print them (the 1.22 exposure class). The credentials and header are now deleted from the frame before any assertion.
  - `[high]` `[patch]` Probe `seen`-set consumed captures with `start=None` or out-of-window `start` so they could never be rematched, falsely reporting "no new capture". Selection now requires a bounded match; an unmatchable capture is left in the poll to be re-judged.
  - `[high]` `[patch]` Probe could attribute an unrelated or future-dated same-camera capture inside the epsilon window. Match now enforces an upper bound (`start <= trigger + 10s`), prefers motion movies, and ranks by closeness to the trigger instant.
  - `[medium]` `[patch]` Write-up claimed "a few seconds of pre-roll", contradicted by its own table (measured `start` = trigger + ~2-3 s). Removed; the derived start offset is now stated honestly with no pre-roll observed.
  - `[medium]` `[patch]` Write-up's "close time was stable from first sight" was unsupported (the probe recorded one close per trigger). Reworded to state exactly what was tracked.
  - `[medium]` `[patch]` Write-up consequences (a) claimed the spike showed the AD-1 two-plane separation as a class-lag mechanism. Reworded: the spike observed capture-present-with-empty-class only; class-lag after capture remains unproven.
  - `[medium]` `[patch]` Memlog said the measurement "confirms AD-10" while the write-up only says "consistent with". Memlog now matches the weaker, supported claim.
  - `[medium]` `[patch]` Clock-skew caveat (probe-host wall clock vs server-declared timestamps) was missing from the write-up. Added.
  - `[medium]` `[patch]` The live test matched any new same-camera capture with no trigger-window or type check (a scheduled recording could false-pass). It now matches only captures whose `start` is bounded around the trigger instant, preferring motion movies.
  - `[medium]` `[patch]` Capture deleted/rotated server-side mid-poll was silently reused as stale. The probe now breaks with a "capture disappeared mid-poll" note.
  - `[low]` `[patch]` Live test asserted `status == HTTPStatus.OK`; now accepts the 2xx band.
  - `[low]` `[patch]` Live test required ADMIN while the probe falls back to CONTROL; the test now mirrors the fallback.
  - `[low]` `[patch]` Dead `assert account is not None` removed (superseded by the credential-frame cleanup).
  - `[low]` `[patch]` Probe and test fetched only "today"'s folder; a trigger straddling the server's local midnight would miss its capture. Date window widened ±1 day in both.
  - `[low]` `[patch]` `--timeout <= --interval` would run at most one poll; now validated and rejected.
  - `[low]` `[patch]` `--epsilon 0` silently unmatchable for any pre-roll; documented in the constant's help text.
  - `[low]` `[patch]` IPv6 host literal produced a malformed trigger URL; the host is now bracketed.
  - `[low]` `[patch]` Probe's `main()` printed the library auth error verbatim, which can carry the credential-derived `API_`-prefix diagnostic; `SecuritySpyAuthError` is now reported without its message.
  - `[low]` `[patch]` `classes={{}}` double-brace cosmetic bug in the probe's row printer; fixed.
  - `[low]` `[patch]` CLI options were parsed only after config resolution, so `--help`/invalid flags misbehaved on machines without `.env`; options are now parsed and validated first.
  - `[low]` `[patch]` Write-up's "start within 15 s of the trigger instant" restated the probe's epsilon filter as a finding; reworded as a one-sided bound plus the derived start offset.
  - `[low]` `[patch]` `epic-4-context.md` (compiled during step-01) was unlisted in the spec's Files changed; added.
  - `[low]` `[patch]` Probe is outside the library's `mypy --strict src tests` gate (it imports `tests/live_env.py` via `sys.path`); documented in Verification rather than forcing a config change.

## Design Notes

**Why a probe script plus write-up rather than only a live test.** The spike's value is a measured number, and the honest output of an empty scene is "unclassified", not a test failure. A permanent live test asserting a wall-clock bound would flake on scene activity, camera FPS, and model speed. The probe records whatever the server does; the write-up reports the sample and its limits.

**Why the probe lives in the library repo.** The manual trigger is wire knowledge (AD-2). The integration repo's `scripts/` and `custom_components/` must not carry raw endpoints; the probe, which does, belongs with the library that owns the API reference.

**Why no library release.** The probe consumes only the already-published public surface (`SecuritySpyClient`, `Capture`, `async_get_captures`, `async_get_server_info`). No public API changes, no version bump.

## Verification

**Commands:**
- `cd /Users/jensen/projects/aiosecurityspy && uv run python scripts/measure_classification_write_timing.py --triggers 3` -- expected: per-trigger rows with appearance/close/classified times and deltas, no credential values printed.
- `cd /Users/jensen/projects/aiosecurityspy && uv run pytest -q -m live -k classification_write` -- expected: new test passes, or skips when `SECURITYSPY_ALLOW_WRITES` is unset.
- `cd /Users/jensen/projects/aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests` -- expected: clean. The probe script is deliberately excluded from the `mypy` gate: it imports `tests/live_env.py` via a `sys.path` insert that mypy cannot resolve; it is covered by ruff and by live execution, and it is not part of the published package.

**Manual checks (if no CLI):**
- Confirm the research doc and memlog entry contain no secret values and no fabricated numbers.

## Auto Run Result

**Summary:** Ran Story 4.1's spike against the live reference server (SecuritySpy 6.22b10, camera 7) with a new measurement probe in the library repo. Five manual-triggered motion captures were measured: each appeared in `++caplist` within one 3s poll of the trigger and closed ~21s after it (duration ~18s), but none ever received an object classification (`o` stayed empty 40–70s post-close). The headline answer is therefore a null result on this camera — classification-population latency is not observable in the sample (no model assigned and/or empty scene), so FR-2/FR-3/FR-11 freshness is neither proven nor disproven. The capture-plane half of R-001 is settled (appearance ≤3s, close ≈ trigger+21s), which is consistent with AD-10's FILE-debounced ~5s and ~10min-fallback poll cycles catching newly-closed captures and does not contradict the 7-day lookback. No production library code changed.

**Files changed:**
- `aiosecurityspy/scripts/measure_classification_write_timing.py` (new) — the probe: trigger via `++triggermd` (raw aiohttp GET, `aiohttp.encode_basic_auth` header), poll `async_get_captures(capture_filter=CAPTURE_FILTER_ALL)` on a short cadence, print a per-trigger table (appearance / close / classified times and deltas); skips with exit 0 when `SECURITYSPY_ALLOW_WRITES` or creds/camera are missing; prints no credential value.
- `aiosecurityspy/tests/test_live_server.py` — one `@pytest.mark.live` test `test_live_classification_write_timing_mechanism`: triggers the test camera, polls `++caplist` bounded, asserts a new motion-movie capture appears and its `object_classes` is a decodable `frozenset[str]`; skips when `SECURITYSPY_ALLOW_WRITES` is unset; no wall-clock timing bound.
- `_bmad-output/planning-artifacts/research/securityspy-classification-write-timing.md` (new) — the write-up: build/camera tested, method, per-trigger table, consequences for restart correctness and FR-9-vs-FR-11, confirmed/corrected lookback + AD-10 assumptions, untested sub-findings, and the `4.1-LIVE-076` gate resolution.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` — one `(finding)` line dated 2026-09-16 pointing to the research doc.
- `_bmad-output/implementation-artifacts/epic-4-context.md` (new, compiled during step-01) — epic context for Epic 4, needed to route this story.

**Review findings:** 24 patched (4 high, 7 medium, 13 low; all applied), 0 deferred, 1 rejected (test-skip-on-permission request — a permission error from the ADMIN account is a config error worth failing on, not a skip).

**Verification:**
- `uv run python scripts/measure_classification_write_timing.py --triggers 1 --timeout 90 --interval 3` — ran live post-review; measured one capture (appeared +3s, close +22s, unclassified); no credential output.
- `uv run pytest -q -m live -k classification_write` — 1 passed (the new test, post-review).
- `uv run pytest -q -k "not live"` — 1079 passed (offline suite fully green).
- `uv run ruff check .` — clean.
- `uv run ruff format --check .` — clean (32 files).
- `uv run mypy --strict src tests` — clean (26 files).

**Residual risks:**
- No classified capture was produced in the sample, so the spike's positive number (classification-write latency relative to close) remains unmeasured on this server/camera. If a camera with an active classification model or a scene with motion becomes available, re-running the probe will yield the number; the honest bound is documented in the write-up.
- The probe's measurement math assumes the probe host and server clocks agree within the poll interval (documented in the write-up).
- The pre-existing `test_live_relay_stream_decodes_through_ffprobe` failure is unrelated to this spike and remains open in the repo.