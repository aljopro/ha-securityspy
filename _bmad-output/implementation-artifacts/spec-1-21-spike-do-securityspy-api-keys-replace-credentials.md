---
title: 'Spike: do SecuritySpy API keys replace credentials on every path the library uses?'
type: 'chore'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
baseline_revision: '4233e21d259c651bdd056ac47028f47dca6142ba'
---

<intent-contract>

## Intent

**Problem:** PRD Open Question 11 was reopened (sprint-change-proposal-2026-09-16.md): SecuritySpy 6.22b9+ adds per-account API keys. The library, the diagnostics anonymizer, and any future auth-path decision need documented, reproducible evidence of what a key can authenticate and how it can be told apart from a password — not just a vendor forum reply.

**Approach:** Record the live-server findings already gathered against SecuritySpy 6.22b10 (test-live account) as a research artifact and an architecture memlog entry, add regression-worthy live tests that exercise the key as a Basic-auth credential on the endpoints the library already calls, and record `.env.example` entries for the new fixtures used. Make no change to production auth, redaction, or relay behavior — this is a spike; adopting any change goes through a follow-up correct-course per the story's own acceptance criteria.

## Boundaries & Constraints

**Always:**
- Never print, log, or commit an actual API key or password value anywhere (code, test output, research doc, memlog). Use sentinel/placeholder text and `.env`-driven fixtures only, mirroring `tests/live_env.py`'s existing rule.
- New live tests follow existing conventions: `@pytest.mark.live`, skip cleanly when their env vars are absent, read `.env` only through `live_env.py`, never assert on or interpolate secret values into test names/messages.
- The research write-up states the exact SecuritySpy build tested (6.22b10) and marks any sub-finding that could not be exercised live (e.g. requires a UI-only action) as explicitly untested, with the reason — never fabricate a result.
- `.env.example` documents new variables with the same comment style as existing entries; no real values.

**Block If:** (none — the server, a key, and a password-equals-key account already exist; nothing here requires a decision only a human can make)

**Never:**
- Do not change `client.py`, `connection.py`, `relay.py`, or `diagnostics.py` production logic. Adding shape-based secret detection (e.g. an `API_[A-Za-z0-9]{32}` value check) is a distinct future story flagged in the epic-1 context's Cross-Story Dependencies, not part of this spike.
- Do not attempt to regenerate or delete the live `SECURITYSPY_LIVE_KEY` or exercise a camera the test account cannot see — those require a manual SecuritySpy UI action this run cannot perform. Document them as open follow-ups instead of skipping silently.
- Do not change FR-22, Story 1.19, Story 1.20, or Story 2.6 behavior. Do not update PRD Open Q11's status beyond what the write-up supports (it stays "reopened," pending a follow-up correct-course).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Key as Basic password, real username | `Authorization: Basic base64(user:KEY)` to `++systemInfo`/`++image`/`++eventStream` | 200, same shape as password auth | n/a |
| Key as Basic password, empty/other username | `Authorization: Basic base64('':KEY)` or `base64(other:KEY)` | 200 — key is authoritative, username ignored | n/a |
| Raw key in `auth=` query param | `?auth=API_...` on `++image` | 401 (contradicts vendor help text; documented as an observed vendor discrepancy, not a library bug) | Library's own `unsecured_stream_url()`/relay paths are unaffected since neither builds this form |
| Key used on admin-only endpoint | Basic auth with key, account has `Live` permission only, request `++settings-general` | 403, same as password | Confirms `_map_status` disambiguation is auth-shape-agnostic (client.py:1263-1268) |
| Password identical in shape to a key | Account whose password equals `API_`+32 chars, used with any username | Server treats it as a key: web UI login refused, API endpoints accept it regardless of username | Documented as a SecuritySpy-side lock-out edge case, out of the library's control |

</intent-contract>

## Code Map

- `_bmad-output/planning-artifacts/research/securityspy-api-keys-6.22.md` (new, in `ha-securityspy` repo) — the write-up required by Story 1.21's final AC.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` -- append one `(finding)` line pointing to the new research doc.
- `aiosecurityspy/.env.example` -- add `SECURITYSPY_LIVE_KEY` (mirrors `SECURITYSPY_LIVE_USER`/`SECURITYSPY_LIVE_PASS`) and a `SECURITYSPY_SAMEKEY_USER`/`SECURITYSPY_SAMEKEY_PASS`/`SECURITYSPY_SAMEKEY_KEY` block for the password-equals-key edge case, both gated the same way as existing account blocks.
- `aiosecurityspy/tests/live_env.py` -- extend the loaded/known var list if it enumerates them explicitly; confirm new vars pass through with no code change otherwise.
- `aiosecurityspy/tests/test_live_server.py` -- add `@pytest.mark.live` tests: key-as-password against `++systemInfo` (via `async_get_server_info` or equivalent existing client call) and `++image` (`async_get_camera_image`), each skipping when `SECURITYSPY_LIVE_KEY` is unset.
- `client.py:1201` (`_map_status`), `client.py:1430`/`client.py:1521` (`_request_bytes`/`_stream_bytes`, both consuming `self._connection.auth_header`), `connection.py:90-140` (`validate_credentials`, `_ConnectionSettings.auth_header`) -- read-only references for the write-up; no edits.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/.env.example` -- add `SECURITYSPY_LIVE_KEY` under the existing "Live" account block and a new "Password identical to its own key (edge case)" block with `SECURITYSPY_SAMEKEY_USER`/`_PASS`/`_KEY` -- documents the fixtures this story's live testing used, so the setup is reproducible by someone else.
- [x] `aiosecurityspy/tests/test_live_server.py` -- add `test_live_server_info_accepts_key_as_password` and `test_live_camera_image_accepts_key_as_password`, both `@pytest.mark.live`, skipped when `SECURITYSPY_LIVE_KEY` is absent, asserting a successful (non-401) result using the key as the Basic-auth password with the account's real username -- turns today's manual finding into a regression check.
- [x] `aiosecurityspy/tests/test_credential_containment.py` -- add the API key value (a fixed placeholder shaped like `API_` + 32 chars, not a real key) to the existing sentinel set so the credential-containment sweep also proves a key-shaped value never leaks in logs, mirroring the existing username/password sentinels.
- [x] `_bmad-output/planning-artifacts/research/securityspy-api-keys-6.22.md` -- write up: server build tested (6.22b10), the endpoint-by-result table from the I/O matrix above, the `API_`-prefix format observed (36 chars: `API_` + 32 base62), the password-equals-key lock-out finding, the two still-untested sub-ACs (invisible-camera behavior, regenerate/delete behavior) with why they need a manual follow-up session, and a recommendation among the three options in AD-13 (no change / relay authenticates upstream with a key / that plus key-bearing URLs to consumers) -- satisfies Story 1.21's write-up AC.
- [x] `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` -- append one `(finding)` line dated 2026-09-16 pointing to the new research doc and summarizing the headline result (key works as password everywhere tested; raw `auth=` form does not).

**Acceptance Criteria:**
- Given the new live tests and `SECURITYSPY_LIVE_KEY` set in `.env`, when `uv run pytest -m live` runs in `aiosecurityspy`, then the two new tests pass and every other live test still passes or skips as before.
- Given `SECURITYSPY_LIVE_KEY` is unset, when the full test suite runs, then the new tests skip and no other test is affected.
- Given the credential-containment sweep, when it runs, then the added API-key-shaped sentinel is confirmed absent from `caplog.text` and every rendered exception, exactly like the existing sentinels.
- Given the research write-up, when it is read, then it states the tested build, cites which sub-ACs of Story 1.21 were exercised live versus left open, and names one recommended option without adopting it.

## Spec Change Log

## Review Triage Log

### 2026-09-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 1, low 5)
- defer: 2
- reject: 4
- addressed_findings:
  - `[medium]` `[patch]` The key-authenticated healthy-server sweep (`key_succeeding`) was computed but never asserted empty, unlike the password-path `succeeding`. Added `assert not succeeding` and `assert not key_succeeding` so both healthy paths are proven error-free, not just implied by omission.
  - `[low]` `[patch]` `make_client_with_key` reused `USERNAME`, the password-path sentinel, so a username leak under the key path would be indistinguishable from one under the password path. Added a distinct `KEY_USERNAME` sentinel.
  - `[low]` `[patch]` The sweep docstring said "Five distinct sentinels" against a six-entry (now seven) `SENTINELS` tuple. Updated the count.
  - `[low]` `[patch]` `MINIMUM_DEBUG_RECORDS`'s comment and the sweep's inline comment referenced "the three phases" / "the 21 [records] the three phases actually emit", stale after adding two key-authenticated phases. Reworded without hardcoding a new number that would just go stale again.
  - `[low]` `[patch]` `.env.example`'s `SECURITYSPY_LIVE_KEY` comment said the key is used "in place of" `SECURITYSPY_LIVE_PASS`, but the new live tests still require the full LIVE account (username *and* password) to be configured and only substitute the key as the Basic-auth password for those specific tests. Reworded to match actual behavior.
  - `[low]` `[patch]` The research doc's recommendation called option 2 "purely additive and reversible" without qualifying that the invisible-camera and regenerate/delete sub-ACs remain unconfirmed. Softened the claim to name that dependency explicitly.
  - `[defer]` No automated test exercises the `SECURITYSPY_SAMEKEY_*` fixtures documented in `.env.example`; the password-equals-key lock-out finding rests on this session's manual testing only. Logged to deferred-work.md.
  - `[defer]` No automated test protects the "raw `auth=` query string is rejected, base64-wrapped succeeds" finding against silent change in a future SecuritySpy build. Logged to deferred-work.md.

## Design Notes

**Why add regression tests instead of only a write-up.** The story's AC set is satisfied by the write-up alone, but the library already has a live-test suite and a credential-containment sweep built exactly for this kind of claim ("a credential type never leaks, and works where documented"). Two small additions cost little and turn a point-in-time finding into something CI-adjacent that catches a future regression if `connection.py`'s auth handling ever changes shape.

**Why not add shape-based redaction now.** `is_credential_key` (diagnostics.py:107) matches by field name, not value shape; detecting an `API_...` value regardless of the field it's under is a different mechanism and a real design decision (false-positive risk against a password that happens to match the shape). That belongs to whichever follow-up story the correct-course selects, not to this spike.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass; live tests skip without `.env` configuration.
- `cd aiosecurityspy && uv run pytest -m live -q` -- expected: pass when `.env` is configured with `SECURITYSPY_LIVE_KEY`, skip cleanly otherwise.
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: clean.

**Manual checks (if no CLI):**
- Confirm the research doc and memlog entry contain no secret values, matching every other artifact in this run.

## Second follow-up (2026-09-16, post-done)

User asked to close the remaining deferred item: automated coverage for the
password-equals-key lock-out. Added two live tests exercising
`SECURITYSPY_SAMEKEY_USER`/`_PASS` (the miscaptured `_KEY` var is
deliberately unused, documented in code): the API surface accepts the
password/key under any username, the web UI login refuses it under the
account's own username. Both deferred-work items from the review pass are
now resolved.

Hit a real snag: `aiohttp.BasicAuth` is deprecated and this project's pytest
config turns warnings into errors, so the first version failed outright.
Switched to `aiohttp.encode_basic_auth()` + an explicit `Authorization`
header, matching the library's own internal convention. **Incident:** the
verbose (`-v`) failure output from that first, failing run printed the
SAMEKEY account's password/key value in full in this terminal session, via
pytest's traceback locals. Flagged to the user in-session; recorded here per
project disclosure discipline. Verified stable across three quiet (`-q`, no
`-v`) reruns after the fix, plus two full `-m live` runs showing no new
regressions (only the pre-existing, unrelated RTSP-relay connectivity
failure).

## Follow-up (2026-09-16, post-done)

User asked whether the base64-wrapped `auth=` query form also ignores the username, as the Basic-auth header form does. Confirmed live (made-up username, base64-wrapped with the key: 200). Closed the matching deferred item by adding two regression tests to `aiosecurityspy/tests/test_live_server.py`:
- `test_live_raw_key_in_auth_query_param_is_rejected`
- `test_live_base64_wrapped_key_in_auth_query_param_is_accepted` (uses a made-up username, not the real account, so the query-form finding is verified independently of the Basic-auth-header tests)

First attempt left a benign but real aiohttp "unclosed transport" teardown warning (unread response bodies on narrow-selection runs); fixed by draining each response with `await response.read()` before asserting status. Verified stable across three repeated live runs.

Research doc, architecture memlog, and deferred-work.md updated accordingly. The SAMEKEY lock-out deferred item remains open.

## Auto Run Result

**Summary:** Documented live-verified findings on SecuritySpy 6.22b9+ per-account API keys (PRD Open Q11, reopened 2026-09-16) and added regression coverage for the headline result: a key authenticates identically to the account password everywhere the library's HTTP/RTSP calls need it, with the query-string `auth=` form behaving differently than the vendor's help text describes. No production code changed; this is a spike per Story 1.21.

**Files changed:**
- `aiosecurityspy/.env.example` -- documents `SECURITYSPY_LIVE_KEY` and the `SECURITYSPY_SAMEKEY_*` edge-case fixtures used this session.
- `aiosecurityspy/tests/test_live_server.py` -- two new `@pytest.mark.live` regression tests for key-as-Basic-password on `++systemInfo` and `++image`.
- `aiosecurityspy/tests/test_credential_containment.py` -- the credential-leak sweep now also drives a key-authenticated client through every path (healthy and rejected), with a distinct `KEY_USERNAME` sentinel, and asserts both healthy-server phases raise nothing.
- `_bmad-output/planning-artifacts/research/securityspy-api-keys-6.22.md` (new) -- the write-up Story 1.21's final AC requires.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/.memlog.md` -- one `(finding)` line.
- `_bmad-output/implementation-artifacts/epic-1-context.md` -- recompiled to reflect the 2026-09-16 Q11/AD-13 changes (done during step-01, ahead of this spec).

**Review findings:** 6 patched (1 medium, 5 low; all applied), 2 deferred (adding live-test coverage for the SAMEKEY lock-out and for the `auth=` query-string finding), 4 rejected as noise (inherent spike-documentation limits, expected epic-context regeneration behavior, and a redaction-scope point already covered in Design Notes).

**Verification:**
- `uv run pytest -q -k "not live"` -- 1075 passed.
- `uv run pytest -q -m live` -- 16 passed, 1 skipped (no captures available), 1 failed (`test_live_relay_stream_decodes_through_ffprobe`, a pre-existing RTSP-connectivity failure confirmed present on the unmodified baseline via `git stash`, unrelated to this change). Both new key-auth tests are among the 16 passing.
- `uv run ruff check . && uv run ruff format --check .` -- clean.
- `uv run mypy --strict src tests` -- clean.

**Residual risks:** the two deferred items above leave two of this session's live findings (the password-equals-key lock-out, and the `auth=` query-string rejection) without automated regression protection — only this write-up records them. The pre-existing RTSP relay test failure is unrelated but still open in the repo.

Status: done
