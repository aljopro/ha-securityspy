---
title: 'Close Story 1.21''s unmet sub-ACs and decide on shape-based key detection'
type: 'chore'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
baseline_revision: '974a30984837d4b897a1e2be160fce79ed08a279'
final_revision: '17a89dd'
---

<intent-contract>

## Intent

**Problem:** Story 1.21 (done) shipped without exercising its own AC that a password beginning with `API_` but not matching the full key shape be tested, and left two sub-ACs (key regenerate/delete; a key on a camera the account cannot see) explicitly open. Sprint-change-proposal-2026-09-16-b.md requires these closed, and one final adopt/defer recommendation made on shape-based key detection, before PRD Open Q11 can move past "reopened."

**Approach:** For each of the three remaining sub-ACs, add a `.env`-gated live test that exercises it when the operator has configured the fixture, and update the research write-up to state the result (or, if the fixture is absent, state explicitly why it stays open) — same pattern Story 1.21 used for its own untestable sub-ACs. Close with one written recommendation on shape-based key detection; implement nothing from that recommendation. Make no change to production auth, redaction, or relay behavior.

## Boundaries & Constraints

**Always:**
- Never print, log, or commit an actual API key or password value anywhere. Use sentinel/placeholder text and `.env`-driven fixtures only, mirroring `tests/live_env.py`'s existing rule and Story 1.21's incident-avoidance pattern (draining responses before assertion; no `-v`/verbose pytest output that could print secret-bearing locals).
- New live tests follow existing conventions: `@pytest.mark.live`, skip cleanly (with a message naming the missing `.env` var) when their fixture is absent, read `.env` only through `live_env.py`, never assert on or interpolate secret values into test names/messages, use `aiohttp.encode_basic_auth()` (not the deprecated `aiohttp.BasicAuth`), and drain each response with `await response.read()` before asserting status.
- The research write-up update states the exact SecuritySpy build tested and, for each of the three sub-ACs, either the live result or an explicit "left open, here's why" statement — never fabricate a result.
- `.env.example` documents any new variables with the same comment style as existing entries; no real values.

**Block If:** (none — every sub-AC here is designed to degrade to "left open, documented" when its fixture is absent, exactly as Story 1.21's own open sub-ACs did; nothing requires a decision only a human can make)

**Never:**
- Do not change `client.py`, `connection.py`, `relay.py`, or `diagnostics.py` production logic, and do not add `API_[A-Za-z0-9]{32}` shape-based secret detection — that decision is this story's recommendation output, not its implementation.
- Do not attempt to create new SecuritySpy accounts, regenerate/delete a live key, or reconfigure camera permissions through the web UI — those are manual actions this run cannot perform; if the needed `.env` fixture doesn't already exist, document the sub-AC as open rather than fabricating or skipping silently.
- Do not update PRD Open Q11's status beyond what the write-up supports. It stays "reopened" unless this story's recommendation explicitly says to close it — and even then, closing it is a follow-up correct-course decision, not something this spec does directly.
- Do not remove or edit Story 1.21's existing tests, research doc sections, or deferred-work.md history entries.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Password shaped like a partial key | `SECURITYSPY_PARTIALKEY_USER`/`_PASS` set, where `_PASS` begins with `API_` but is not the full 32-char base62 shape (e.g. wrong length or a non-base62 char) | Basic auth with that password to `++systemInfo` returns 200 under the account's own username (ordinary password behavior, not the SAMEKEY lock-out) | If unset, test skips with a message naming the missing vars; research doc marks this sub-AC open with that reason |
| Key on a camera the account cannot see | `SECURITYSPY_PERCAM_KEY` set for the existing PERCAM account, and a camera number outside its per-camera grants | Request for that camera's `++image` with the key as Basic password returns the library's existing permission-denied mapping (401/403 per `_map_status`), not a crash | If `SECURITYSPY_PERCAM_KEY` is unset, test skips; research doc marks this sub-AC open with that reason |
| Key regenerate/delete | N/A — requires a manual SecuritySpy UI action (regenerating or deleting a live account's key) that this run cannot perform without invalidating the fixtures other live tests depend on | Not exercised | Research doc explicitly states this sub-AC remains open and why, same as Story 1.21's original treatment |

</intent-contract>

## Code Map

- `_bmad-output/planning-artifacts/research/securityspy-api-keys-6.22.md` (in `ha-securityspy` repo) — append findings for the three sub-ACs and the final adopt/defer recommendation.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` — append one `(finding)` line pointing to the updated research doc.
- `aiosecurityspy/.env.example` — add `SECURITYSPY_PARTIALKEY_USER`/`_PASS` (partial-key-shaped password fixture) and `SECURITYSPY_PERCAM_KEY` (API key for the existing PERCAM account) under the pattern of existing blocks.
- `aiosecurityspy/tests/test_live_server.py` — add three `@pytest.mark.live` tests (or two plus one explicitly-skipped/open one) for the sub-ACs above, next to the existing Story 1.21 key tests.
- `aiosecurityspy/tests/live_env.py` — read-only reference; no code change expected since it already passes through arbitrary `SECURITYSPY_*` vars via `credentials()`/`get()`.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/.env.example` -- add `SECURITYSPY_PARTIALKEY_USER`/`_PASS` and `SECURITYSPY_PERCAM_KEY` entries, each with a comment explaining the fixture's purpose and that it's optional (tests skip cleanly without it) -- makes the new live-test setup reproducible.
- [x] `aiosecurityspy/tests/test_live_server.py` -- add `test_live_partial_key_shaped_password_authenticates_normally` (skips when `SECURITYSPY_PARTIALKEY_USER`/`_PASS` unset) and `test_live_percam_key_on_unpermitted_camera_is_denied` (skips when `SECURITYSPY_PERCAM_KEY` unset) -- turns the two potentially-testable sub-ACs into regression checks when the operator configures the fixtures.
- [x] `_bmad-output/planning-artifacts/research/securityspy-api-keys-6.22.md` -- append a "Story 1.22 follow-up" section: result (or explicit open-with-reason) for each of the three sub-ACs, and one final recommendation — adopt shape-based key detection now, or continue deferring it — with rationale grounded in the evidence gathered across 1.21 and 1.22.
- [x] `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` -- append one `(finding)` line dated 2026-09-16 pointing to the updated research doc and summarizing the recommendation.

**Acceptance Criteria:**
- Given `SECURITYSPY_PARTIALKEY_USER`/`_PASS` set in `.env` to a password beginning `API_` but not matching the full key shape, when `uv run pytest -m live` runs, then the new test passes, confirming the account authenticates normally (not treated as key-authenticated).
- Given `SECURITYSPY_PERCAM_KEY` set in `.env` for the PERCAM account, when the new test runs against a camera number outside that account's per-camera grants, then it asserts the library's existing permission-denied exception/status mapping, not a crash or an unhandled 200.
- Given either new fixture is unset, when the full test suite runs, then the corresponding test skips and no other test is affected.
- Given the research write-up, when it is read, then each of the three sub-ACs has either a live result or an explicit "left open, here's why" statement, and the document ends with exactly one adopt/defer recommendation on shape-based key detection.
- Given PRD Open Q11, when this story completes, then its status is unchanged ("reopened") unless the recommendation explicitly says to close it.

## Spec Change Log

## Review Triage Log

### 2026-09-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 1, low 4)
- defer: 0
- reject: 12
- addressed_findings:
  - `[medium]` `[patch]` `test_live_percam_key_on_unpermitted_camera_is_denied` only checked a client-side guard (`async_get_camera_image` refusing a camera absent from its own just-fetched inventory), which holds regardless of whether a key or password authenticated the account and so never actually tested server-side key permission scoping. Rewrote it to fetch the PERCAM account's inventory under both its password and its key and assert the two camera sets are identical, then use the shared scope to pick a genuinely unpermitted camera number.
  - `[low]` `[patch]` The unpermitted-camera search only checked numbers 0-63, which could miss real out-of-scope cameras on a server with more than 64 defined and wrongly conclude "sees every camera." Widened the search to scale with the account's own highest visible camera number.
  - `[low]` `[patch]` `sprint-status.yaml` recorded `1-22-...: backlog` even though the story is now complete, inconsistent with Story 1.21's `done` entry and with the research doc's own past-tense narrative. Updated to `done`.
  - `[low]` `[patch]` `SECURITYSPY_PARTIALKEY_PASS`'s `.env.example` comment didn't say precisely what shape disqualifies it from being a full key, so a misconfigured fixture could silently test the wrong scenario. Tightened the comment and added a runtime shape assertion to the test itself so a misconfigured fixture fails loudly.
  - `[low]` `[patch]` The research doc's deferral rationale argued "no fixture was set up by accident" as evidence there's no real-world demand for shape-based detection -- circular, since the project's own deliberately-built fixtures can't speak to accidental real-world use. Reworded to state plainly that this is an open question with no data either way, rather than treating the absence of self-generated evidence as evidence of absence.
  - `[reject]` Regenerate/delete write-up "dismisses a disposable-account workaround in one clause" -- correct that it's asserted rather than attempted, but creating a disposable SecuritySpy account is itself a manual web-UI action this run cannot perform, same constraint as every other manual-UI item in this and the prior story; no code or doc change resolves that.
  - `[reject]` "Recommending 'continue deferring' isn't a decision on the merits" -- the epic's own AC frames the choice as adopt-now-or-defer, and "defer" is offered as an explicit valid outcome with its own required rationale, which the doc supplies.
  - `[reject]` "1.22's conclusion is the same as 1.21's" -- the two recommendations answer different questions (relay upstream auth strategy vs. client-side key-shape detection); a shared "not yet" isn't duplication.
  - `[reject]` AD-13 "unrecognized fields default to redacted" lacks a verification artifact in this diff -- pre-existing architecture-decision text carried over by the epic-context recompilation, not a claim introduced or touched by this story.
  - `[reject]` `SECURITYSPY_PERCAM_KEY` and the regenerate/delete sub-AC are both "requires manual UI action" yet treated differently -- correctly so: creating a key for an existing account is additive and doesn't disturb other fixtures, while regenerating/deleting a live key is destructive to fixtures other live tests depend on.
  - `[reject]` `_base_url()` inside the partial-key test could crash on a missing `SECURITYSPY_HOST` -- incorrect; `_base_url()` already calls `pytest.skip` internally when the host is unset, matching every other live test's pattern.
  - `[reject]` New `session.get` calls lack an explicit per-request timeout -- matches the existing convention of every other raw `session.get` call in this file (none of them set one either); not a deviation this story introduced.
  - `[reject]` Assertion failures in the new tests carry no diagnostic message -- matches the existing convention in this file's other raw-`session.get` tests.
  - `[reject]` `pytest.raises(SecuritySpyPermissionError)` could "misreport" an unrelated network/timeout exception as this AC failing -- incorrect; `pytest.raises` re-raises a non-matching exception with its own distinct traceback, it does not relabel it as an assertion failure.

## Design Notes

**Why two fixtures instead of three test cases.** Regenerate/delete cannot be exercised without a manual SecuritySpy UI action that would invalidate fixtures other live tests already depend on (the same constraint Story 1.21 hit). Rather than inventing a workaround, this story follows 1.21's own precedent: document it as open with reason, and let a human operator close it later if they choose to perform that UI action deliberately, out of band from any automated run.

**Why `SECURITYSPY_PERCAM_KEY` rather than a new account.** The PERCAM account already has documented per-camera permission variance (`SECURITYSPY_PERCAM_FULL_CAMERA`/`_LIMITED_CAMERA`), which is exactly the shape needed for "a camera the account cannot see." Adding a key to that existing account (an operator action, not a code action) is simpler than provisioning a new one.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass; live tests skip without `.env` configuration.
- `cd aiosecurityspy && uv run pytest -m live -q` -- expected: pass or skip cleanly depending on which optional fixtures are configured; no failures.
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: clean.

**Manual checks (if no CLI):**
- Confirm the research doc and memlog entry contain no secret values, matching every other artifact in this run.

## Auto Run Result

**Summary:** Closed Story 1.21's three unmet sub-ACs on SecuritySpy 6.22+ API keys: added two `.env`-gated live regression tests (both currently skipping, since no operator has configured the new optional fixtures yet), documented all three sub-ACs as explicitly open with reason where unconfirmed, and made one final recommendation — continue deferring shape-based `API_[A-Za-z0-9]{32}` key detection. No production auth/redaction code changed; PRD Open Q11 stays "reopened."

**Files changed:**
- `aiosecurityspy/.env.example` -- documents `SECURITYSPY_PARTIALKEY_USER`/`_PASS` and `SECURITYSPY_PERCAM_KEY`, with shape guidance for the partial-key fixture.
- `aiosecurityspy/tests/test_live_server.py` -- two new `@pytest.mark.live` tests: partial-key-shaped-password authentication, and PERCAM key-vs-password camera-scope comparison with a runtime fixture-shape assertion.
- `_bmad-output/planning-artifacts/research/securityspy-api-keys-6.22.md` -- "Story 1.22 follow-up" section: per-sub-AC results/open-status and the final defer recommendation.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` -- one `(finding)` line.
- `_bmad-output/planning-artifacts/epics.md` -- added Story 1.22 (via preceding correct-course pass).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` -- `1-22-...: done`.
- `_bmad-output/implementation-artifacts/epic-1-context.md` -- recompiled to include Story 1.22 (done during step-01, ahead of this spec).
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-16-b.md` -- the correct-course proposal that added this story (preceding this dev-auto run).

**Review findings:** 5 patched (1 medium, 4 low; all applied), 0 deferred, 12 rejected as noise (inherent manual-UI limits mirroring Story 1.21's own precedent, matches to existing file conventions, and one reviewer misunderstanding of `pytest.raises` semantics). The medium finding was substantive: the original PERCAM test only checked a client-side guard that would hold regardless of server behavior, so it was rewritten to actually compare key- vs password-authenticated camera visibility — the real question the AC asks.

**Verification:**
- `uv run ruff check . && uv run ruff format --check .` -- clean.
- `uv run mypy --strict src tests` -- clean, 25 source files.
- `uv run pytest -q -k "not live"` -- 1075 passed.
- `uv run pytest -m live -q` -- 20 passed, 3 skipped (including both new tests, skipping with their expected "not set" messages), 1 failed (`test_live_relay_stream_decodes_through_ffprobe`, the same pre-existing, unrelated RTSP-connectivity failure documented in Story 1.21 — confirmed not caused by this change).

**Residual risks:** all three of Story 1.21's original sub-ACs remain unconfirmed against a live server — two now have regression tests ready for whenever an operator configures `SECURITYSPY_PARTIALKEY_USER`/`_PASS` and `SECURITYSPY_PERCAM_KEY`, and the third (key regenerate/delete) stays undocumented-by-design, unchanged from Story 1.21, since exercising it would risk every other live test's fixtures. The pre-existing RTSP relay test failure remains open in the repo, unrelated to this story.

Status: done
