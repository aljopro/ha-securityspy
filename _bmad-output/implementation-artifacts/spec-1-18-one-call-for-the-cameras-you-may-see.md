---
title: "Story 1.18: One call for the cameras you may see, in their current state"
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '6c93a3ae67fbe1116dc9007112497fb6df66ef68'
context: ['{project-root}/_bmad-output/planning-artifacts/research/verification-gaps.md']
warnings: [oversized]
baseline_revision: '816ee634a3a16d48929ab8f8551e8457e669b9af'
---

<intent-contract>

## Intent

**Problem:** There is no single way to ask "which cameras may this account see, and what state are they in?" A consumer must call `async_get_server_info()` for membership and `async_get_camera_status()` for fresh health, then know — from research, not from the API — that `++systemInfo` is the only permission-scoped surface while `++camStatus` returns **every** camera on the server to any authenticated account (gap G8). Getting that intersection wrong creates entities for cameras the user may not see and copies SecuritySpy's disclosure into Home Assistant's logs and diagnostics. It is protocol knowledge (AD-2), it is easy to get wrong, and it currently lives only in a research document.

**Approach:** Give the library the question as a first-class call: a permission-scoped camera list carrying current state. **Visibility is one state, and absence from `++systemInfo` is the whole of it.** A camera that is disabled and a camera the account may not see are treated identically, because Home Assistant has one thing to say about both — not currently visible — and because distinguishing them requires guessing from an ambiguous signal in the direction that leaks. Add the pure pieces a consumer needs around it: capability predicates that turn the permission bitmask into questions, and the intersection that keeps `++camStatus` from widening membership. Actions stay on the client and data stays inert.

## Boundaries & Constraints

**Always:** The result contains **exactly** the cameras `++systemInfo` reports, and a camera absent from it appears by no path and for no reason. Disabled and unpermitted are one case, not two. The library retains nothing between calls and needs no prior membership to answer, so the same inputs always give the same answer. `++camStatus` rows are intersected against that membership and **non-member rows are discarded at the point of receipt**, never returned, never logged (a count may be logged, never a camera number). The cheap-poll path stays cheap: refreshing health must not force a 27 KB `++systemInfo` read when the caller already holds membership. Capability predicates distinguish **permission** from **liveness** -- the mask is not static, and an offline camera loses `PERM_AUDIORCV`/`PERM_AUDIOSND` and regains them on reconnect (research §5.11), so a predicate must never let "the camera is unplugged" read as "you are not allowed". The client remains stateless: it holds no camera inventory between calls.

**Block If:** any part of the answer would require the library to remember a previous call. It must not -- the library computes from what it is given, and this story's whole point is that the answer needs no memory. If a design cannot avoid retained state, stop.

**Never:** No methods on `Camera` that perform I/O. It stays a frozen value object: binding a client to it couples object lifetime to session lifetime, inverts `models.py`'s dependency direction, and puts an active object inside the frozen coordinator container (AD-15). Actions stay on the client and take the camera. No Home Assistant concepts in the library -- it answers *may this account see it* and *what does the server say*, never *should this entity be unavailable*, which is AD-17's and belongs in `entity.py`. No implicit fetching to serve a decode (story 1.13's rule): a call that reads two endpoints does so because the caller asked for both, and says so.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordinary account | 11 cameras, all permitted | 11 cameras with current state | No error expected |
| Restricted account | Permitted one camera; `camStatus` returns 11 | **Exactly 1** camera; the other ten appear nowhere in the result | Non-member rows dropped at receipt |
| Disabled camera | Camera disabled in SecuritySpy, so absent from `++systemInfo` | **Absent** from the result | Not an error |
| De-permissioned camera | Permission withdrawn, so absent from `++systemInfo` | **Absent** from the result -- identical treatment, by design | Not an error |
| Health refresh | Caller holds membership, asks for fresh health | Only `++camStatus` is issued; no `++systemInfo` read | No error expected |
| Status for an unknown camera | `camStatus` row with no matching member | Discarded; a count may be logged, never the number | Never raises |
| Live-video predicate | Camera holding `PERM_LIVEVIDEO` | True | No error expected |
| Audio predicate on an offline camera | Camera offline, audio bits absent from the mask | Does **not** report a permission denial; the liveness cause is distinguishable | Documented, tested |
| Permission denied mid-call | Account loses rights between calls | The existing typed permission error | Per story 1.14 |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/client.py` -- `async_get_server_info` (line ~532) is already the permission-scoped read; `async_get_camera_status` (line ~553) is the cheap poll. The new accessor composes them; neither changes shape.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `Camera` (line 654), frozen with `permissions: int` and a decoding property. Capability predicates belong here as pure properties.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `require_permission` (line 624) and `CameraScheduleAssignment.resolve_names` (line 460): the two shape precedents -- pure, module-level or method, taking the other half of the data as an argument and holding no state.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `CameraStatus` (line 754) and `ServerInfo` (line 876): the two halves being intersected.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- `PERMISSION_NAMES`, `decode_permissions`, the `PERM_*` bits; predicates read these rather than re-encoding bit values.
- `_bmad-output/planning-artifacts/research/verification-gaps.md` -- **G8** (the permission-scoping inversion), the visibility/enablement two-axis model, and the boundary rule requiring non-member rows to be dropped at receipt. This story implements what those record.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- `++systemInfo` and `++camStatus` already carry the scoping quirks; keep them in step (AD-19).

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- add the permission-scoped camera accessor with current state -- one call for "which cameras may I see, and how are they right now".
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- add a health-refresh path that does not re-read `++systemInfo` -- the coordinator polls on a cycle and a 27 KB read per cycle is not viable.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- intersect status against membership as a pure function, discarding non-members -- data that never enters the result cannot leak from a log or a diagnostics dump.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add capability predicates that separate permission from liveness -- the mask changes with camera state, so conflating them would make an unplugged camera look forbidden.
- [x] `aiosecurityspy/tests/` -- cover every matrix row, above all the restricted-account case asserting the other ten cameras appear in **no** returned value and in **no** log record -- this is the row that protects story 2.7.
- [x] `aiosecurityspy/docs/securityspy-openapi.yaml` + `CHANGELOG.md` -- keep the description and release notes in step (AD-19).

**Acceptance Criteria:**
- Given an account permitted one camera of eleven, when the camera list is requested, then exactly one camera is returned and no other camera's number appears in any returned value or log record.
- Given a caller that already holds membership, when it refreshes health, then only `++camStatus` is issued.
- Given a camera that is disabled and a camera whose permission has been withdrawn, when the list is requested, then both are absent and the result is identical -- the two are indistinguishable by construction, not by accident.

## Spec Change Log

- **2026-08-29 -- implemented.** Added `SecuritySpyClient.async_get_visible_cameras()`
  (composes `async_get_server_info()` + `async_get_camera_status()`) and
  `async_refresh_camera_status(server_info)` (camStatus-only refresh) to `client.py`;
  added the pure `visible_camera_views()` intersection and the `CameraView` value object,
  plus `Camera.can_receive_audio` / `Camera.can_send_audio` liveness-vs-permission
  predicates, to `models.py`. Non-member `camStatus` rows are discarded at the point of
  receipt and never logged by number (only a discard count is logged). Disabled and
  de-permissioned cameras are indistinguishable by construction -- both are absent from
  `ServerInfo.cameras` and so absent from the result. Updated
  `docs/securityspy-openapi.yaml` (`++systemInfo`/`++camStatus` quirks now record the G8
  permission-scoping inversion) and `CHANGELOG.md` (AD-19). New tests in
  `tests/test_client.py` and `tests/test_models.py` cover every I/O matrix row, including
  the restricted-account no-leak case, the unknown-status-row discard, the health-refresh
  single-call case, and the offline-camera audio-predicate distinction. `pytest`, `ruff
  check`/`format --check`, `mypy --strict src` (and `src tests`), and the OpenAPI
  validator all pass.

## Review Triage Log

### 2026-08-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3 (low 3, medium 0, high 0)
- defer: 0
- reject: 9
- addressed_findings:
  - `[low]` `[patch]` `visible_camera_views` discard count was computed from a number-deduped dict, undercounting raw dropped rows when duplicate camera numbers appear in a `++camStatus` payload; rewrote the loop to count discards from the raw `statuses` iterable directly (`models.py`).
  - `[low]` `[patch]` `test_visible_cameras_unknown_status_row_is_discarded_and_only_counted` asserted `"99" not in combined` over all captured log records (including transport logs that legitimately contain digits), inconsistent with the adjacent restricted-account test's careful logger-name filtering; aligned it to filter to `aiosecurityspy.models` records first.
  - `[low]` `[patch]` No test exercised the fully-empty-`++camStatus`-response case (all members present, none statused); added `test_visible_camera_views_empty_statuses_returns_all_members_unstatused`.

## Design Notes

The point of the story, in one line: **the consumer should be able to ask "which cameras may I see, and how are they right now?" and not have to know why that is a hard question.**

**Why disabled and unpermitted are deliberately not distinguished (Jensen, 2026-08-29).** They could be told apart most of the time, by remembering prior membership and reading `camStatus.enabled`. That was specced and then withdrawn. Home Assistant has exactly one thing to say about both — *not currently visible* — so the distinction buys nothing a user would see, while costing retained state, a dependence on an unscoped endpoint, and an ambiguous case (a camera both disabled and de-permissioned) that could only be resolved by guessing in the direction that leaks. Collapsing them makes the leak structurally impossible rather than merely unlikely. Gap G8 records the ambiguity this avoids.

`Camera` staying a frozen value object is the load-bearing constraint. `camera.get_stream()` reads better at a call site than `client.async_stream_url(camera)`, and it was considered and rejected: it couples object lifetime to session lifetime, makes `models.py` depend on the client, and puts an active object inside a frozen coordinator container. `require_permission(camera, "files")` is the existing precedent for the chosen shape -- pure, synchronous, refuses before any round trip.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest` -- expected: all tests pass
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src` -- expected: clean
- `cd aiosecurityspy && uv run python -c "import openapi_spec_validator,yaml;openapi_spec_validator.validate(yaml.safe_load(open('docs/securityspy-openapi.yaml')))"` -- expected: no output

**Manual checks (if no CLI):**
- Against a live server with an account permitted a single camera, confirm the accessor returns that camera alone, and that a debug-level run mentions no other camera number.

## Auto Run Result

**Summary:** Added a permission-scoped "which cameras may this account see, and how are they now?" accessor to `aiosecurityspy`, closing research gap G8 (`++camStatus` is not permission-scoped; `++systemInfo` is the only membership surface). A disabled camera and a de-permissioned camera are indistinguishable in the result, by design.

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `async_get_visible_cameras()` (composes both reads) and `async_refresh_camera_status(server_info)` (camStatus-only cheap poll).
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `CameraView` frozen pairing, pure `visible_camera_views()` intersection, `Camera.can_receive_audio`/`can_send_audio` liveness-vs-permission predicates.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- exported the two new public names.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- documented the G8 scoping asymmetry on both endpoints.
- `aiosecurityspy/CHANGELOG.md` -- `[Unreleased] > Added` entries.
- `aiosecurityspy/tests/test_client.py`, `aiosecurityspy/tests/test_models.py` -- coverage for every I/O matrix row plus the review-driven additions below.

**Review findings breakdown:** 3 patches applied (all low severity: a discard-count-undercount bug in `visible_camera_views` when duplicate `++camStatus` rows target a dropped camera, a fragile/inconsistent log-scoping assertion in one test, and a missing empty-`++camStatus`-response test), 0 deferred, 9 rejected as noise or already-documented behavior (see Review Triage Log for detail -- notably: sequential-read TOCTOU, debug-only log level, `CameraView` lacking runtime-enforced construction, stale-`server_info` behavior in the refresh path -- all consistent with the spec's stated design and existing module conventions).

**Verification:** `uv run pytest` (949 passed), `uv run ruff check .` and `uv run ruff format --check .` (clean), `uv run mypy --strict src` (clean), OpenAPI validator (no output/passed) -- all re-run after the review patches and all green.

**Residual risks:** None blocking. Noted-but-rejected items worth future attention if priorities shift: `CameraView`'s membership invariant is documentation-only, not enforced by a constructor guard; `async_refresh_camera_status` trusts caller-supplied `server_info` freshness with no staleness signal.
