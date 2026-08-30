---
title: "Story 1.18: One call for the cameras you may see, in their current state"
type: 'feature'
created: '2026-08-29'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/planning-artifacts/research/verification-gaps.md']
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** There is no single way to ask "which cameras may this account see, and what state are they in?" A consumer must call `async_get_server_info()` for membership and `async_get_camera_status()` for fresh health, then know — from research, not from the API — that `++systemInfo` is the only permission-scoped surface while `++camStatus` returns **every** camera on the server to any authenticated account (gap G8). Getting that intersection wrong creates entities for cameras the user may not see and copies SecuritySpy's disclosure into Home Assistant's logs and diagnostics. It is protocol knowledge (AD-2), it is easy to get wrong, and it currently lives only in a research document.

**Approach:** Give the library the question as a first-class call: a permission-scoped camera list carrying current state. **Permission is established first and enablement is reported second** — a disabled camera is one you may see that is not currently enabled, not one that has ceased to exist. That ordering is not free: disabling removes the camera from `++systemInfo`, taking its permission evidence with it, so the only proof it was ever permitted is prior membership. The caller supplies that as an argument rather than the library retaining it. Add the pure pieces a consumer needs around it — capability predicates that turn the permission bitmask into questions, and a reason for a camera that has left the inventory. Actions stay on the client and data stays inert.

## Boundaries & Constraints

**Always:** Permission is decided **before** enablement is reported, and a camera never appears in the result unless its permission is established — either by presence in `++systemInfo` now, or by presence in the prior membership the caller supplied. Without prior membership the result contains exactly what `++systemInfo` reports and nothing else, which is the safe cold-start behaviour. A camera whose permission was never established appears by no path. `++camStatus` rows are intersected against that membership and **non-member rows are discarded at the point of receipt**, never returned, never logged (a count may be logged, never a camera number). The cheap-poll path stays cheap: refreshing health must not force a 27 KB `++systemInfo` read when the caller already holds membership. Capability predicates distinguish **permission** from **liveness** -- the mask is not static, and an offline camera loses `PERM_AUDIORCV`/`PERM_AUDIOSND` and regains them on reconnect (research §5.11), so a predicate must never let "the camera is unplugged" read as "you are not allowed". The client remains stateless: it holds no camera inventory between calls.

**Block If:** answering "why is this camera no longer in the inventory?" would require the library to remember a previous call. It must not -- the library computes from what it is given; remembering membership across polls is the consumer's job, and the helper takes the prior membership as an argument. If a design cannot avoid retained state, stop.

**Never:** No methods on `Camera` that perform I/O. It stays a frozen value object: binding a client to it couples object lifetime to session lifetime, inverts `models.py`'s dependency direction, and puts an active object inside the frozen coordinator container (AD-15). Actions stay on the client and take the camera. No Home Assistant concepts in the library -- it answers *may this account see it* and *what does the server say*, never *should this entity be unavailable*, which is AD-17's and belongs in `entity.py`. No implicit fetching to serve a decode (story 1.13's rule): a call that reads two endpoints does so because the caller asked for both, and says so.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordinary account | 11 cameras, all permitted | 11 cameras with current state | No error expected |
| Restricted account | Permitted one camera; `camStatus` returns 11 | **Exactly 1** camera; the other ten appear nowhere in the result | Non-member rows dropped at receipt |
| Disabled camera, no prior membership | Cold start; camera disabled in SecuritySpy | **Absent** -- permission was never established, so it is not ours to show | Not an error |
| Disabled camera, previously permitted | Prior membership supplied; absent from `++systemInfo`; `camStatus` says `enabled:false` | **Returned, marked not enabled** -- present but not currently enabled | Not an error |
| De-permissioned camera, previously permitted | Prior membership supplied; absent; `camStatus` says `enabled:true` | **Not returned** -- permission was withdrawn, and permission gates visibility | Not an error |
| Health refresh | Caller holds membership, asks for fresh health | Only `++camStatus` is issued; no `++systemInfo` read | No error expected |
| Status for an unknown camera | `camStatus` row with no matching member | Discarded; a count may be logged, never the number | Never raises |
| Absence reason, previously seen, `enabled:false` | Prior membership passed in | `DISABLED` | No error expected |
| Absence reason, previously seen, `enabled:true` | Prior membership passed in | `NOT_PERMITTED` | No error expected |
| Absence reason, never seen | No prior membership | `UNKNOWN` -- the caller creates nothing | No error expected |
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
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- add the permission-scoped camera accessor with current state, taking optional prior membership so a permitted-but-disabled camera is reported as present-and-not-enabled rather than vanishing -- a camera the user disabled should not look like a camera they may not see.
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- add a health-refresh path that does not re-read `++systemInfo` -- the coordinator polls on a cycle and a 27 KB read per cycle is not viable.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- intersect status against membership as a pure function, discarding non-members -- data that never enters the result cannot leak from a log or a diagnostics dump.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- add capability predicates that separate permission from liveness -- the mask changes with camera state, so conflating them would make an unplugged camera look forbidden.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- add the absence reason, taking prior membership as an argument -- the truth table exists only in a research document today, and every consumer would otherwise re-derive it.
- [ ] `aiosecurityspy/tests/` -- cover every matrix row, above all the restricted-account case asserting the other ten cameras appear in **no** returned value and in **no** log record -- this is the row that protects story 2.7.
- [ ] `aiosecurityspy/docs/securityspy-openapi.yaml` + `CHANGELOG.md` -- keep the description and release notes in step (AD-19).

**Acceptance Criteria:**
- Given an account permitted one camera of eleven, when the camera list is requested, then exactly one camera is returned and no other camera's number appears in any returned value or log record.
- Given a caller that already holds membership, when it refreshes health, then only `++camStatus` is issued.
- Given a camera that has left the inventory and prior membership, when its absence is explained, then the reason distinguishes disabled from de-permissioned without the library retaining state.
- Given a previously permitted camera that is now disabled, when the camera list is requested with prior membership, then the camera is present in the result and reports as not enabled, so a consumer can show it rather than delete it.
- Given a previously permitted camera whose permission has been withdrawn, when the camera list is requested with prior membership, then the camera is absent from the result.

## Spec Change Log

## Review Triage Log

## Design Notes

The point of the story, in one line: **the consumer should be able to ask "which cameras may I see, and how are they right now?" and not have to know why that is a hard question.**

**The ambiguous cell, and why it is accepted.** A camera that is *both* de-permissioned and disabled reads `enabled:false` and will be reported as permitted-but-disabled. That is the one case the truth table cannot separate (gap G8). It is accepted rather than solved: the camera was previously permitted, so its existence is already known to this consumer and nothing new is disclosed, and it is shown as not enabled — never as usable. The conservative alternative, dropping on any ambiguity, was rejected because it makes an ordinary disabled camera vanish, which is the behaviour this story exists to prevent.

`Camera` staying a frozen value object is the load-bearing constraint. `camera.get_stream()` reads better at a call site than `client.async_stream_url(camera)`, and it was considered and rejected: it couples object lifetime to session lifetime, makes `models.py` depend on the client, and puts an active object inside a frozen coordinator container. `require_permission(camera, "files")` is the existing precedent for the chosen shape -- pure, synchronous, refuses before any round trip.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest` -- expected: all tests pass
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src` -- expected: clean
- `cd aiosecurityspy && uv run python -c "import openapi_spec_validator,yaml;openapi_spec_validator.validate(yaml.safe_load(open('docs/securityspy-openapi.yaml')))"` -- expected: no output

**Manual checks (if no CLI):**
- Against a live server with an account permitted a single camera, confirm the accessor returns that camera alone, and that a debug-level run mentions no other camera number.
