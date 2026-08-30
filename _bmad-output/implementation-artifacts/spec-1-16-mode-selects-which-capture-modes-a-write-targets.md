---
title: "Story 1.16: mode selects which capture modes a write targets"
type: 'bugfix'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
baseline_revision: 'a94231a89747a6260e1bdfcbf20b35531c8d3e15'
final_revision: 'e40982a8b4900764faf63c20a02589d89b357546'
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
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- express the write as "apply this override to these modes", rejecting an empty target -- a request that returns `200 OK` having done nothing is worse than an error, because nothing downstream can detect it.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- correct `mode_string`'s documented meaning -- the "disarm all three" sentence is the whole defect and would re-teach the wrong model to the next reader.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- state in the docstring that `200 OK` means accepted, not applied -- callers will otherwise treat it as confirmation.
- [x] `aiosecurityspy/tests/` -- assert the query string for each matrix row, including that `schedule=` never appears and that an empty target raises before any request -- the previous tests asserted a `mode` string that was wrong in meaning while being right in spelling, which is exactly why they passed.
- [x] `aiosecurityspy/CHANGELOG.md` -- record the breaking behavioural change -- a consumer relying on the old all-false call is relying on a no-op.

**Acceptance Criteria:**
- Given an override and a set of capture modes, when the write is issued, then only those modes' overrides change on the server and the others are untouched.
- Given an empty set of capture modes, when a write is attempted, then it fails before any HTTP request is made.
- Given any call this library makes, when the query string is inspected, then it contains no `schedule=` parameter.

## Spec Change Log

### 2026-08-29 — Review pass (adversarial + edge-case)
- Docstrings in `models.py` refined after review: the first-pass rewrite said the letter string "is not an armed state", which contradicted the read path — `from_api` decodes `cc-mode`/`mc-mode`/`a-mode` as the camera's current armed state (research §10, "armed/disarmed per mode"), and `mode_string` is used to *display* that state in `Camera.__repr__` and the README. Amended to state the meaning is direction-dependent: decoded from the server they are the armed state; used as a `++ssSetSchedule` write target they select which modes the write applies to. The core correction (an empty string is not "disarm all three"; an empty *target* is refused before any request) is unchanged.
- Added to the `async_set_camera_arming` docstring: a disarm recipe (target the modes and apply an `ARM_OVERRIDE_DISARMED_*` override, or `ARM_OVERRIDE_NONE` to clear an override) and an explicit warning that `CaptureModes` read back from the server are armed state, not a drop-in write target — the read→write round trip of an all-false camera now raises, and a non-empty read result is a different instruction than restoring the state.
- Added a real-socket transport test proving a one-letter `mode=A` (the story's flagship §5.14 case) survives yarl's query encoding un-dropped; the stub asserts the params dict it was handed, which cannot distinguish a dropped letter.
- Renamed `test_arming_200_ok_means_accepted_not_applied` to `test_arming_never_reads_back_after_an_ok_write` — the "applied" half of the claim is a documentation promise with no observable signal, so the test's name now matches the machine-checkable property it pins (exactly one request, no read-back).
- Fixed a stale `# noqa: FBT003` comment that defended "the positional all-false form must stay expressible" — all-false is now refused, so the comment now states the form stays constructible so the test can prove it is refused.
- KEEP: the empty-target `ValueError` before any request (the story's core), the `mode_string`/const/method docstring corrections, `schedule=` never sent, `200 OK` accepted-not-applied documented, and the matrix tests asserting the full query-params shape.

## Review Triage Log

### 2026-08-29 — Block resolved by architecture decision (Jensen)

The `Block If` this story tripped is resolved at the level it belonged to. Jensen's ruling: **schedules and overrides are two different ideas, and one control cannot express both.** AD-7 is split accordingly (`ARCHITECTURE-SPINE.md`, "[ADOPTED; split 2026-08-29]"): arm switches write the transient override exclusively and never send `schedule=`; a persistent schedule *assignment* is permitted as a separate, explicitly invoked operation; creating, editing or deleting a schedule *definition* stays forbidden, which preserves AD-7's original Prevents. Home Assistant performs no implicit record-and-restore of a prior assignment — reversal is the same explicit operation against the id FR-15 already makes readable.

PRD amended in the same pass: FR-12 split into FR-12 (transient override control) and FR-12a (persistent assignment via explicit action); FR-13 rewritten from "override-only writes" to "switches write the override; only the explicit action writes a schedule"; FR-15's read-only claim narrowed to entities and now names FR-12a as the single writer.

**This story is unblocked and closed.** Its scope — `mode` is the write's target, not an armed state — was correct and is unchanged by the split; the split adds an operation this story never claimed to provide. The one defect the follow-up review found *inside* this story's scope is fixed:

- `async_set_camera_arming`'s `override` argument no longer has a default. `ARM_OVERRIDE_UNCHANGED` as a default guaranteed the undetectable no-op this story exists to abolish (target modes, apply nothing, `200 OK`); it is now required, so a caller who wants "leave as-is" states it. `test_arming_defaults_to_the_unchanged_override` is replaced by `test_arming_has_no_override_default` (asserts the signature carries no default) and `test_arming_still_accepts_an_explicit_unchanged_override`. BREAKING entry added to the library CHANGELOG.
- Docstrings citing AD-7 as an absolute ban on `schedule=` (`client.py`, `models.py`, `securityspy-openapi.yaml`) now state the split, so the next reader is not re-taught the pre-split rule.

**Carried forward, not done here:** `aiosecurityspy` still has no schedule-assignment method. Per AD-19 the operation lands in the library first and the integration consumes it; Epic 6 (6.1, 6.4) unblocks only once it exists. That is new scope, not a residual of this story.


### 2026-08-29 — Follow-up review pass (intent gap; Block If tripped)
- intent_gap: 1: (high 1, medium 0, low 0)
- bad_spec: 0
- patch: 0
- defer: 0
- reject: 0
- addressed_findings:
  - none

**Intent-gap finding (both reviewers, independently):** under the corrected model this story adopts, `mode` is only the *target* and `override` is the only value the library ever applies — because AD-7 forbids sending `schedule=`. The method's default is `override=ARM_OVERRIDE_UNCHANGED` (`-1`), which research §5.15.5 now confirms **on the wire** is genuinely the "leave as-is" sentinel. A default call therefore sends `mode=<target>&override=-1`, targets modes, applies nothing, and returns `200 OK` having done nothing — verbatim the undetectable no-op class this story exists to abolish. The story refused the empty *target* and left the empty *value* not merely permitted but test-locked (`test_arming_defaults_to_the_unchanged_override`).

**This trips the spec's `Block If` clause verbatim.** Research §5.15.5 states it outright: the UI's disarm control is `/ssSetSchedule?cameraNum=4&schedule=0&override=-1&mode=CMA` — persistent arming and disarming is expressed by **assigning a schedule, not an override**, which is exactly the operation AD-7 forbids. An override is transient and bounded by design and cannot express "disarmed until I say otherwise". The spec's `Block If` says: *"if a real arming requirement cannot be met by an override, stop: sending `schedule=` overturns AD-7 and is an architecture decision, not an implementation choice."* Research reaches the same conclusion independently and names Epic 6 stories 6.1 and 6.4 as blocked on it.

The intent contract cannot resolve this: it simultaneously requires that a caller "be able to express 'apply this override to exactly these modes'" and that no request return `200 OK` having done nothing, while retaining a default value that guarantees exactly that outcome. There is no single reading — refusing `ARM_OVERRIDE_UNCHANGED` removes the documented default and breaks every default call; keeping it preserves the defect the story was written to remove. Resolving it requires an architecture decision about AD-7, not an implementation choice.

Code changes were **not** reverted: the implementation is already committed and shipped (`e40982a8`, `5b1be67d`), so reverting is destructive to published history and is left to a human decision.

### 2026-08-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 0, low 6)
- defer: 0
- reject: 4: (high 0, medium 0, low 4)
- addressed_findings:
  - `[low]` `[patch]` `CaptureModes` class + `mode_string` docstrings over-claimed "not an armed state", contradicting the read path (`from_api` decodes armed/disarmed per mode; research §10) and the README's read-back display. Reworded to the direction-dependent meaning: server decode = current armed state; write target = which modes the write applies to. The empty-string correction ("not 'disarm all three'", refused before any request) is preserved.
  - `[low]` `[patch]` No documented way to express disarming under the corrected semantics. Added a recipe to the method docstring: target the modes and apply an `ARM_OVERRIDE_DISARMED_*` override, or `ARM_OVERRIDE_NONE` to clear an override and let the schedule rule.
  - `[low]` `[patch]` The read→write round trip of an all-false camera now raises with no warning that `from_api` output is armed state, not a write target. Documented in the method docstring.
  - `[low]` `[patch]` The single-mode write (`mode=A`, the §5.14 flagship) was only asserted through the stub's params dict; a dropped letter would pass. Added `test_real_arming_single_mode_survives_query_encoding` against a real in-process aiohttp server.
  - `[low]` `[patch]` `test_arming_200_ok_means_accepted_not_applied` named a property (not applied) the method cannot observe. Renamed to `test_arming_never_reads_back_after_an_ok_write`, matching the property it actually pins (exactly one request).
  - `[low]` `[patch]` Stale `# noqa: FBT003` comment defended "the positional all-false form must stay expressible" — now refused. Updated to state the form stays constructible so the test can prove it is refused.
- rejected_findings:
  - The matrix tests assert the same letter strings that passed before the fix and so cannot detect a reversion of the *semantic*; "only those modes' overrides change" is verified only by a manual live check not recorded in the diff. Rejected: the spec's own Design Notes acknowledge that only a live write can distinguish "targets" from "arms" because the endpoint returns `200 OK` either way — the wire shape is identical by design. The machine-checkable semantic (empty target refused) IS tested and verified to fail against pre-fix code, and the live A/B for the one-mode case is already recorded in research §5.14 (step 5: `override=2&mode=A` moved `a-schedule-override` 0→2 alone).
  - The default `override=-1` is untested and becomes newly load-bearing. Rejected: pre-existing `test_arming_defaults_to_the_unchanged_override` already asserts `override=-1` reaches the wire, and the server-tolerance question for `-1` is already tracked in `deferred-work.md` (story 1.6 entry) — not something this story re-opens.
  - Validation precedence changed silently (empty-target before override), so `CaptureModes()` + a bad override reports the wrong error first. Rejected: both are pre-request `ValueError`s; the empty-target error is the more fundamental one (the whole write is meaningless), the precedence is deliberate and documented in the Raises section, and the spec does not mandate an order.
  - `models.py` docstring cross-references the client method name, coupling the model to the client. Rejected after reword: the docstring now describes the refusal behavior ("the client refuses before any request") without naming the method.

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

## Auto Run Result

**Summary:** `async_set_camera_arming` now models `++ssSetSchedule` as it actually behaves — `mode` selects *which* capture modes a write applies to (the target), and `override` is the value applied to exactly those modes (live-verified, research §5.14). An all-false target raises `ValueError` before any request instead of sending `mode=` empty and getting `200 OK` having done nothing. Validation order: camera number → empty target → override. `schedule=` is still never sent (AD-7); `200 OK` is documented as accepted-not-applied. The broken "disarm all three" framing is corrected in `CaptureModes`, `mode_string`, the `const.py` mode comment, the README and the CHANGELOG (BREAKING entry). The `mode_string` property's letters are unchanged; only its documented meaning and the method's rejection changed.

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/client.py` — `async_set_camera_arming` rejects an empty target before any request; docstring reframed (mode = target, override = applied value, `200 OK` = accepted, disarm recipe, read-vs-write distinction).
- `aiosecurityspy/src/aiosecurityspy/models.py` — `CaptureModes` class and `mode_string` docstrings corrected to the direction-dependent meaning (armed state when decoded, target selector in a write); empty string never means "disarm all three".
- `aiosecurityspy/src/aiosecurityspy/const.py` — corrected the `mode=` comment carrying the same "empty disarms all three" framing.
- `aiosecurityspy/tests/test_settings.py` — replaced the empty-but-present-mode test with `test_arming_rejects_an_empty_mode_set_before_any_request`; added the 3-row override-target matrix test (one mode / all three / clear) asserting the full params dict; added `test_arming_never_reads_back_after_an_ok_write`; updated the undocumented-override test to a non-empty mode set.
- `aiosecurityspy/tests/test_client_transport.py` — replaced the real-transport empty-mode test with `test_real_arming_refuses_an_empty_mode_set_before_the_socket` (handler never invoked); added `test_real_arming_single_mode_survives_query_encoding` (one-letter `mode=A` reaches a real socket).
- `aiosecurityspy/CHANGELOG.md` — BREAKING entry under `[Unreleased] → Changed`.
- `aiosecurityspy/README.md` — corrected the "all-false disarms all three" comment.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended the version-bump deferral (matching the 1.13/1.15 precedent).

**Review findings:** 6 low patches applied (read/write docstring direction fix; disarm recipe; round-trip warning; real-socket single-mode test; accepted-not-applied test renamed to what it pins; stale FBT003 comment). 4 rejected: matrix tests cannot distinguish the semantic (spec acknowledges only a live write can; the empty-target test catches the machine-checkable part and §5.14 already records the live A/B), the default `override=-1` is already tested and its server-tolerance already deferred (DW 1.6), the empty-target-before-override precedence is deliberate and both are pre-request ValueErrors, and the models↔client docstring coupling was removed by rewording rather than naming the method. Edge-case hunter returned no findings (deletion of the empty-mode wire emission is intentional, BREAKING-noted, and live-verified a no-op).

**Verification:** `uv run pytest` — 933 passed (baseline 928; removed 2 obsolete tests, added 7). `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict src tests` — all clean. OpenAPI validator — valid. Repository root `uv run pytest` — 54 passed. Both empty-target regression tests verified to fail against the pre-fix code (guard removed by mutation). The new single-mode transport test passes against the fix.

**Residual risks:** The version bump / manifest pin for this breaking pre-1.0 behavioral change is deferred to the first-release pass (documented in `deferred-work.md`). The method name still reads as "arming" while expressing target+override writes — kept by design (spec); a later release may rename it. `followup_review_recommended: true` because this is a public behavior change.
