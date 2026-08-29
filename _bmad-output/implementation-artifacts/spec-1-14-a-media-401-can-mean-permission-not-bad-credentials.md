---
title: "Story 1.14: A 401 can mean permission, not bad credentials"
type: 'bugfix'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '54e31ace17e48d73ee8a4b55bb71d786273e1995'
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
baseline_revision: 'f10aa927daca9b3d851e99d7c206f8d2f18311b8'
---

<intent-contract>

## Intent

**Problem:** SecuritySpy 6.21 answers a *permission* failure with `401`, not `403`, on every endpoint tested except the settings pages. Verified live (§5.9): an account holding **Live**-only permission gets `401` from `++getfile`, `++getfilehb`, `++getfilelb` and `++getpreview` while the same credentials return `200` from `++systemInfo` in the same second. It is not a media quirk: `++ssSetSchedule` also returns `401` to an account lacking `PERM_SCHED`, while `++settings-cameras` returns `403` to the same account in the same second and `++systemInfo` returns `200`. Which code a denial carries is a property of the individual endpoint and is not predictable from its kind, so the `403` case is the exception rather than the rule. `_map_status` maps every `401` to `SecuritySpyAuthError`, whose documented meaning is "the credentials were rejected outright" -- a claim its docstring attributes to research §4.1/§5.2, which turn out to describe the *settings* pages only. In Home Assistant a `SecuritySpyAuthError` starts a reauth flow, so a Live-only user is asked to re-enter credentials that are already correct, fails identically, and loops forever. The true cause -- this account may not read captures -- is never surfaced.

**Approach:** The response cannot settle it: a permission `401` is byte-identical to a wrong-password `401` (same status, same `WWW-Authenticate`, same 16-byte body). So on any `401` other than one raised by the disambiguation itself, ask a second question the account is known to be allowed: re-read `++systemInfo`. If it succeeds the credentials are valid and the failure is a permission denial, raised as `SecuritySpyPermissionError` carrying the camera the request targeted. If it also returns `401`, the credentials really are bad and the existing `SecuritySpyAuthError` stands.

## Boundaries & Constraints

**Always:** The disambiguation runs **only** on the error path and adds exactly one request to a request that has already failed. It is keyed on the `401` status, not on a list of endpoints -- a list would have to be revised every time an untested endpoint turns out to deny with `401`, and `++ssSetSchedule` is already the second such surprise. `_map_status` stays the single seam that decides what a status means (AD-6); the media paths pass it what they know rather than growing a parallel ladder. The resulting `SecuritySpyPermissionError` carries the camera number and the implied permission name whenever the call site knows them -- `_map_status` already accepts both for the `403` path, and the media paths have the camera in the path they just built. A successful request is never slowed, never probed, and issues no extra call. If the probe itself fails for any reason other than a clean `200`/`401` answer -- timeout, TLS, connect error -- the original `SecuritySpyAuthError` is raised unchanged: an inconclusive probe must never upgrade or downgrade the verdict. Docstrings on `_map_status`, `SecuritySpyAuthError` and every accessor that can raise it are corrected to state that `401` is endpoint-dependent.

**Block If:** the probe would need credentials, a session, or state the client does not already hold. It does not -- `async_get_server_info` is an ordinary method on the same client -- but if the implementation finds otherwise, stop rather than introducing a second credential path (AD-13).

**Never:** No probing on a successful response, and none on the disambiguating read itself. No caching of the verdict: a permission can change on the server between calls, and a cached "credentials are fine" would mask a genuine credential change. No parsing of the response body or reason phrase to tell the two `401`s apart -- they are byte-identical, and §5.3 already records the reason phrase as unreliable. No recursion: the probe must not itself be able to trigger another probe. No change to the `403` mapping, which remains correct for the settings pages. No new public exception type -- `SecuritySpyPermissionError` already means exactly this.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Permitted fetch | Full-permission account, `++getfile` | The stream is returned; no probe is issued | No error expected |
| Schedule write without `PERM_SCHED` | Account with mask `839`, `++ssSetSchedule` | `SecuritySpyPermissionError` naming the schedule permission and the camera | Probe returns `200`; a non-media endpoint reaches the same path |
| Live-only capture fetch | Live-only account, `++getfile` for camera 5 | `SecuritySpyPermissionError` naming the files permission and camera 5 | Probe returns `200`, so the `401` is reclassified |
| Live-only preview fetch | Live-only account, `++getpreview` | Same, for the camera requested | As above |
| Genuinely wrong password | Bad credentials, `++getfile` | `SecuritySpyAuthError`, exactly as today | Probe also `401`; verdict stands |
| Probe cannot answer | Media `401`, then the probe times out or fails TLS | `SecuritySpyAuthError` -- the original verdict, unmodified | An inconclusive probe never changes the outcome |
| The probe endpoint itself `401`s | `++systemInfo` returns `401` | `SecuritySpyAuthError`; no probe issued, no recursion | Unchanged behaviour |
| Settings `403` | Non-settings account, `++settings-cameras` | `SecuritySpyPermissionError` as today | Unchanged; no probe |
| Streamed media path | `401` on the streaming accessor | Same reclassification, and the response is still released before raising | Must not leak the pooled connection |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/client.py` -- `_map_status` (line 845): the mapping seam. Its `401` branch (line 882) and the docstring at lines 859-865 both assert that `401` means rejected credentials; that claim is what is wrong.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `_stream_bytes` (`_map_status` call at line 1075) and `_request_bytes` (line 1006): the media transport paths. Both already build a path containing the camera number and already release the response before raising -- preserve that ordering.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `async_get_server_info` (line 532): the probe. It is an ordinary method needing no extra state.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `async_set_camera_arming` (line 1225) already passes `permission=PERMISSION_NAMES[PERM_SCHED]` and `camera_number` down to `_map_status`; that context is exactly what the reclassified error should carry, and it is already threaded.
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- `SecuritySpyAuthError` and `SecuritySpyPermissionError`; the latter already carries a permission name and an optional camera number.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- the four media operations document their `401`; AD-19 requires the description to say what it now means.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §5.9 -- the live evidence, including the byte-identical comparison.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- disambiguate a `401` before it escapes, keeping `_map_status` the only place a status is interpreted -- a second status ladder would be exactly the divergence AD-6 exists to prevent.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- correct every docstring asserting that `401` means rejected credentials -- the false claim is cited as verified, which is how it survived review.
- [x] `aiosecurityspy/docs/securityspy-openapi.yaml` -- describe the endpoint-dependent meaning of `401` on the media operations -- a shipped description that lags the client reads as authoritative.
- [x] `aiosecurityspy/tests/test_client.py` -- cover every row of the matrix, including the inconclusive probe and the connection-release ordering -- a fixture that only ever returns one kind of `401` is what let this ship.

**Acceptance Criteria:**
- Given an account missing the permission an endpoint requires, when that endpoint is called, then the caller receives a permission error naming the camera where one is known, and Home Assistant does not start a reauth flow. Verified live for the four media endpoints and for `++ssSetSchedule`.
- Given credentials that are genuinely wrong, when a media endpoint is fetched, then the caller receives an authentication error, unchanged from today.
- Given a successful media fetch, when it completes, then exactly one HTTP request was issued.

## Spec Change Log

Implemented as specified. `_map_status` became `async` (it now awaits the disambiguating probe on its `401` branch); every call site already ran inside an async method, so this added no new constraint. `async_get_server_info` always issues its own request with `disambiguate=False` -- not only when called internally as the probe -- since a direct `401` from `++systemInfo` itself has nothing further to disambiguate against (matrix row "The probe endpoint itself 401s"); this reads as a direct consequence of that row rather than a deviation from it.

## Review Triage Log

### 2026-08-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1: (high 1, medium 0, low 0)
- defer: 0
- reject: 11: (high 0, medium 2, low 9)
- addressed_findings:
  - `[high]` `[patch]` `_stream_bytes`/`_request_bytes` called `_map_status` (which, on a `401`, awaits the disambiguating `++systemInfo` probe) *before* releasing the original failed response, so the probe ran while the original response was still holding a connection out of the caller's pool -- exactly the leak the pre-existing "still holding a connection" comment had been written to warn about, now silently defeated by the probe becoming a second live request inside that window. Fixed by releasing the response as soon as its status is seen to be non-2xx, before `_map_status` (and therefore the probe) is ever awaited, in both `_stream_bytes` and `_request_bytes`. Added `test_streamed_media_401_releases_the_connection_before_probing` and `test_buffered_media_401_releases_the_connection_before_probing`, which fail if the probe request fires before the prior response is released -- the pre-existing `test_streamed_media_401_releases_the_connection_before_reclassifying` only checked release happens before the exception is raised, which the bug also satisfied.

Rejected (all reviewer-flagged, not spec violations): applying disambiguation to `++camStatus`/`++caplist` without endpoint-specific evidence -- this is the explicit design (`Boundaries & Constraints`: "keyed on the `401` status, not on a list of endpoints"), not a gap; the extra round-trip on every `401` including genuinely-wrong-password -- explicitly accepted in the same constraint ("adds exactly one request to a request that has already failed"); no test for camStatus/caplist 401s -- not in the spec's I/O matrix; no cross-request dedup of concurrent probes -- would require caching a verdict across calls, which the spec's `Never` section forbids; probe uses `request_timeout()` not `media_timeout()` -- `++systemInfo` is a small JSON endpoint regardless of what the original call was, so this is correct as-is; probe swallowing the specific failure reason -- deliberate, matches the "inconclusive probe must never upgrade or downgrade the verdict" rule; PERM_FILES lookup duplicated at two call sites; OpenAPI quirk wording nuance; test docstring "verified live" phrasing; `disambiguate` param not threaded through `_request_text`/`_post_form` (unused by any current caller); `_map_status` docstring phrasing about `403` reliability -- all cosmetic/style, no behavior impact.

## Design Notes

Story 1.13 sets a rule worth reading before implementing: *"no implicit `++systemInfo` fetch to serve a decode ... the client does not acquire data behind the caller's back to serve a request."* This story does not breach it. Nothing here acquires data to satisfy a caller's request -- the request has already failed, no value is returned from the probe, and its only effect is which exception type the caller sees. The rule guards against hidden ordering dependencies on the success path; this is strictly an error path. Keep it that way: the moment a probe result is retained or reused, it becomes the hidden state 1.13 forbids.

The alternative -- surfacing a third "ambiguous" exception and making the consumer decide -- was rejected. It pushes a protocol quirk into every consumer, and AD-2 puts protocol knowledge in the library.

An earlier revision of this spec scoped the fix to the four media endpoints. `++ssSetSchedule` then turned out to deny with `401` as well, so the endpoint list was wrong within a day of being written. Keying on the status rather than on a list is what stops the next untested endpoint from reopening this story.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest` -- expected: all tests pass, including the new matrix rows
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src` -- expected: clean
- `cd aiosecurityspy && uv run python -c "import openapi_spec_validator,yaml;openapi_spec_validator.validate(yaml.safe_load(open('docs/securityspy-openapi.yaml')))"` -- expected: no output

**Manual checks (if no CLI):**
- Against the live server, a Live-only account fetching `++getfile` must raise a permission error naming the camera; the same fetch with a full-permission account must succeed and issue one request.

## Auto Run Result

**Summary:** `_map_status` now disambiguates any `401` (unless `disambiguate=False`) with one follow-up read of `++systemInfo`. A clean success there reclassifies the `401` as `SecuritySpyPermissionError` carrying the permission and camera when known; any other outcome leaves `SecuritySpyAuthError` unchanged. `async_get_server_info` always passes `disambiguate=False` to avoid probing itself.

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `_map_status` made async and disambiguates `401`; new `_probe_confirms_permission_denial` helper; media accessors thread `permission`/`camera_number` through; corrected docstrings claiming `401` always means rejected credentials; `_stream_bytes`/`_request_bytes` release their response before the status is interpreted (and thus before the probe fires) rather than only before the exception propagates.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- documents the endpoint-dependent `401` meaning on the media operations and `++ssSetSchedule`.
- `aiosecurityspy/tests/test_client.py` -- ten tests covering every I/O matrix row, plus two added during review to pin down that the probe never fires while a prior response is still held open.

**Review findings:** 1 patch applied (high-severity connection-holding bug where the disambiguating probe fired while the original failed response was still held open, doubling pool usage on every reclassified `401`); 11 rejected as either explicit spec design (endpoint-agnostic disambiguation, the extra round-trip, no verdict caching) or cosmetic/style with no behavior impact.

**Verification:** `uv run pytest` -- 912 passed. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict src` -- all clean. OpenAPI validator -- no output (valid).

**Residual risks:** None identified beyond the two rejected-as-by-design tradeoffs (extra round-trip per ambiguous `401`; disambiguation applies uniformly rather than to a maintained endpoint list, which is the explicit point of the design).
