---
title: "Story 1.16: mode selects which capture modes a write targets"
type: 'bugfix'
created: '2026-08-29'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `async_set_camera_arming` misreads the `++ssSetSchedule` wire contract. Verified by live write (§5.14): **`mode` selects which of the three capture modes a write applies to — it is not their armed state.** `schedule` and `override` are the values applied to the selected modes. The method passes its three booleans as `mode` and sends no `schedule`, so it has no way to express arming at all. A call with all three modes true and a real override happens to work, because it targets all three and applies the override. A call with all three false sends `mode=` empty, targets nothing, and returns `200 OK` having done nothing — while its docstring calls that "the legal instruction 'disarm all three'". The endpoint answers `200 OK` with body `OK` even when it applied nothing, so no caller can detect this. Epic 6's arming stories rest on this method.

**Approach:** Model the endpoint as it actually behaves: a write that applies a schedule and/or an override to a selected set of capture modes. The mode set becomes the *target* of the write, and the value applied becomes explicit. AD-7 survives intact and is now verified achievable — `override` applies with no `schedule` — so the library still never reassigns a schedule; it simply has to say which modes the override lands on.

## Boundaries & Constraints

**Always:** The mode set is named and documented as the write's target, never as an armed state -- the current naming is what made the defect invisible. A caller must be able to express "apply this override to exactly these modes". Targeting no modes is a caller error caught before the request, not a request that returns `200 OK` having done nothing. `schedule=` is still never sent (AD-7) and the library still exposes no method that reassigns a schedule. Every docstring that describes `mode` as an armed state -- including `CaptureModes.mode_string`'s "disarm all three" claim -- is corrected in the same change. This is a **breaking behavioural change** to a shipped public method: version bump, changelog and `manifest.json` pin move together (AD-19).

**Block If:** the fix would require sending `schedule=` to express arming. It should not -- `override` alone is verified sufficient -- but if a real arming requirement cannot be met by an override, stop: sending `schedule=` overturns AD-7 and is an architecture decision, not an implementation choice.

**Never:** No inference of "applied" from the `200 OK` status -- it is returned for no-op writes too, so it proves only that the request was accepted. No read-back inside the library to confirm a write took effect: that is a second request the caller did not ask for, and the same rule 1.13 sets against implicit fetches applies. No modelling of `ssSetPreset` in this story (§5.14) -- it is a real endpoint but a separate capability. No attempt to enumerate what each override id does beyond what §5.2 already publishes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Override on one mode | Actions only, override 2 | `override=2&mode=A`; `a-schedule-override` becomes 2, the other two untouched | No error expected |
| Override on all three | All three modes, override 1 | `override=1&mode=CMA`; all three overrides change | No error expected |
| Clear an override | All three modes, override 0 | `override=0&mode=CMA`; overrides return to 0 | No error expected |
| No modes targeted | An empty mode set | `ValueError` before any request is issued | Refuses to send a request that provably does nothing |
| Schedule never sent | Any call | The query string contains no `schedule=` | Enforced by test |
| Server accepts but applies nothing | `200 OK`, body `OK` | The call returns normally; the library claims only that it was accepted | Documented, not inferred |
| Permission denied | Account without `PERM_SCHED` | A permission error, not an authentication one | Depends on story 1.14 |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/client.py` -- `async_set_camera_arming` (line 1225): the method. Its docstring (lines 1232-1243) states the wrong semantic twice and cites AD-7 correctly; keep the AD-7 reasoning, replace the mode reasoning.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `CaptureModes.mode_string` (line 374): produces the `C`/`M`/`A` letters in a fixed order, which stays correct. Its docstring's claim that an empty string means "disarm all three" (lines 379-380) is the defect in one sentence.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `CaptureModes` (line ~366) and `ArmOverride` / `arm_override` (line ~478): the override record already carries the right idea -- transient and bounded -- and needs no change.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- `MODE_CONTINUOUS`, `MODE_MOTION`, `MODE_ACTIONS`: the letters, unchanged.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- `/++ssSetSchedule` already carries the corrected description and the live A/B evidence; the library must now agree with it.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §5.14 -- the five-step live write log and the shipped client's `ScheduleSetterPanelApply`.
- `.../architecture/.../ARCHITECTURE-SPINE.md` -- AD-7. Its rule is unchanged and now live-verified; note the verification rather than restating the rule.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- express the write as "apply this override to these modes", rejecting an empty target -- a request that returns `200 OK` having done nothing is worse than an error, because nothing downstream can detect it.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- correct `mode_string`'s documented meaning -- the "disarm all three" sentence is the whole defect and would re-teach the wrong model to the next reader.
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- state in the docstring that `200 OK` means accepted, not applied -- callers will otherwise treat it as confirmation.
- [ ] `aiosecurityspy/tests/` -- assert the query string for each matrix row, including that `schedule=` never appears and that an empty target raises before any request -- the previous tests asserted a `mode` string that was wrong in meaning while being right in spelling, which is exactly why they passed.
- [ ] `aiosecurityspy/CHANGELOG.md` -- record the breaking behavioural change -- a consumer relying on the old all-false call is relying on a no-op.

**Acceptance Criteria:**
- Given an override and a set of capture modes, when the write is issued, then only those modes' overrides change on the server and the others are untouched.
- Given an empty set of capture modes, when a write is attempted, then it fails before any HTTP request is made.
- Given any call this library makes, when the query string is inspected, then it contains no `schedule=` parameter.

## Spec Change Log

## Review Triage Log

## Design Notes

AD-7 is **not** overturned by this story -- it is vindicated. Step 5 of §5.14 proved `override` applies with no `schedule` present, so "write the transient override, never reassign the schedule" is achievable exactly as the decision states. Only the mode semantics were wrong.

The reason this survived review is worth keeping: `mode_string` produced *correct output* -- `"CMA"` is what the server wants for "all three" -- for an incorrect reason. Every test asserting the string passed. Only a live write against a server, reading back the fields afterwards, could distinguish "targets all three" from "arms all three", because the endpoint returns `200 OK` either way.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest` -- expected: all tests pass
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src` -- expected: clean
- `cd aiosecurityspy && uv run python -c "import openapi_spec_validator,yaml;openapi_spec_validator.validate(yaml.safe_load(open('docs/securityspy-openapi.yaml')))"` -- expected: no output

**Manual checks (if no CLI):**
- Against a live server with a `PERM_SCHED` account: apply an override to one mode, read `++systemInfo` back, and confirm exactly that mode's `*-schedule-override` changed. Restore and confirm zero fields differ.
