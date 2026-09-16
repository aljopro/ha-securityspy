---
title: 'Story 3.4: Unload and reload cleanly'
type: 'feature'
created: '2026-09-15'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false # judged in step-04 repair pass: 1 localized, low-volume test-only patch plus a mechanical mypy-narrowing fix; no behavior/API/security/data impact
context: []
warnings: []
baseline_revision: '894e22287e13724c5720ecaf4158859e6cbe1f24'
final_revision: '15a2253c5aa2bf42380ac3dda544763856cd8001'
---

<intent-contract>

## Intent

**Problem:** Story 3.4 (FR-33) requires that unloading or removing the config entry leaves nothing behind -- no surviving task, connection, timer, or listener, no accumulation across repeated unload/reload cycles, and no orphaned registry entries on removal. `__init__.py` and `coordinator.py` already wire every task/timer/connection introduced by stories 3.1-3.3 (the reconciliation timer, the light-poll timer, the RTSP relay, and the Event Stream) through `entry.async_on_unload`, but no test exercises a full unload-then-reload cycle on the same entry, so nothing currently proves setup is safe to run twice without double-registering timers/listeners or leaking the prior client/stream/relay.

**Approach:** No new production teardown logic is expected -- investigation found every task/timer/connection already registered via `entry.async_on_unload` (coordinator.py's `_cancel_timers` for both `async_track_time_interval` timers, `relay.async_stop`, `stream.disconnect`). The work is adding test coverage that proves this wiring holds across a real unload-then-reload cycle and across repeated cycles, plus a test proving entry removal clears the device/entity registries. If investigation during implementation finds a real gap (a task/timer/listener not registered for cleanup), fix it in the same file it was found in, following the existing `entry.async_on_unload` pattern.

## Boundaries & Constraints

**Always:** Use the existing `entry.async_on_unload` pattern for any new cleanup registration found to be missing. Assert cleanup through real behavior (timer not firing after unload, mock `async_stop`/`disconnect` awaited, registry actually empty) rather than reflection over internal callback lists, matching the existing tests in `tests/test_init.py`. New tests follow the file's existing fixture and naming conventions (`mock_client`, `mock_relay`, `mock_event_stream`, `_add_entry`).

**Block If:** A real, unfixable teardown gap is found that requires a public API from `aiosecurityspy` that does not exist (e.g., no idempotent disconnect/stop method) -- HALT, this would need a library change out of this story's scope.

**Never:** Do not add a coordinator `stop`/`close`/`shutdown` method -- the existing docstring in `async_unload_entry` explains why `entry.async_on_unload` callbacks alone are sufficient (they run unconditionally on unload, independent of `PLATFORMS`). Do not touch `async_remove_config_entry_device` (already implemented in story 3.1, out of scope). Do not change the RTSP relay or Event Stream's own reconnect/backoff behavior (owned by the library, epic-3-context AD).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unload then reload same entry | A loaded entry is unloaded, then `async_setup_entry` runs again on it | Entry reaches `LOADED` again; coordinator, relay, and stream are freshly constructed and started exactly once each for the second load | No error expected |
| Repeated unload/reload cycles | Unload/reload run twice in sequence on the same entry | Second cycle's teardown calls (`_cancel_timers` effect, `relay.async_stop`, `stream.disconnect`) fire again without error, and no timer from the first cycle still fires after the second unload | No error expected |
| Entry removed entirely | A loaded entry's device(s) and entities exist in the registries, then the entry is removed via `hass.config_entries.async_remove` | Device registry and entity registry hold no entries for that config entry afterward | No error expected |

</intent-contract>

## Code Map

- `custom_components/securityspy/__init__.py` -- `async_setup_entry`/`async_unload_entry`; verify no double-registration of `entry.async_on_unload` callbacks on a second setup of the same entry.
- `custom_components/securityspy/coordinator.py` -- `async_start`/`_cancel_timers`; confirm the reconciliation and light-poll timers are cleanly recreated after unload.
- `tests/test_init.py` -- existing unload/relay/stream tests to extend with reload-cycle and registry-removal coverage; reuse `_add_entry`, `mock_client`, `mock_relay`, `mock_event_stream` fixtures already defined there and in `tests/conftest.py`.

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_init.py` -- add a test that unloads a loaded entry, then calls `hass.config_entries.async_setup(entry.entry_id)` again on the same entry, and asserts it reaches `LOADED` with a fresh coordinator/relay/stream and no leftover state from the first load -- proves AC1's "reloads successfully without a Home Assistant restart".
- [x] `tests/test_init.py` -- add a test that runs two full unload/reload cycles and asserts the reconciliation timer only fires for the current cycle (old timer's unsub was cancelled, new timer is live) and that `relay.async_stop`/`stream.disconnect` are called once per unload with no accumulation -- proves AC2's "repeated unload-reload cycles leave no accumulating tasks or connections".
- [x] `tests/test_init.py` -- add a test that sets up an entry with a camera present (so a device and entities exist), removes the entry via `hass.config_entries.async_remove`, and asserts `device_registry.async_entries_for_config_entry` and `entity_registry.async_entries_for_config_entry` are both empty afterward -- proves AC3.
- [x] During implementation, re-verify with a targeted grep (`async_on_unload`, `async_track_time_interval`, `create_task`, `async_listen`) across `custom_components/securityspy/` that no task/timer/listener introduced since the last investigation is missing cleanup registration; if one is found, add `entry.async_on_unload(...)` for it at its creation site. -- verified clean, no gap found, no production code changed.

**Acceptance Criteria:**
- Given a loaded config entry, when it is unloaded, then the event stream connection is closed and all scheduled polling is cancelled, and no task, connection, timer, or listener created by the integration survives.
- Given an unloaded config entry, when the user reloads it, then it loads successfully without a Home Assistant restart, and repeated unload-reload cycles leave no accumulating tasks or connections.
- Given a config entry being removed entirely, when removal completes, then its devices and entities are removed and nothing is left in the registries.

## Verification

**Commands:**
- `uv run pytest tests/test_init.py -v` -- expected: all existing and new tests pass.
- `uv run pytest --cov=custom_components.securityspy --cov-report=term-missing` -- expected: coverage does not regress on `__init__.py`/`coordinator.py`.
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `uv run mypy custom_components/securityspy` -- expected: clean.

## Review Triage Log

### 2026-09-15 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2 (medium 1, low 1)
- defer: 1
- reject: 7
- addressed_findings:
  - `[medium]` `[patch]` The two-cycle test asserted only the reconciliation timer's non-accumulation, not the coordinator's second, independently-registered light-poll timer (`_async_poll_light_status`/`LIGHT_POLL_INTERVAL`), leaving a leak isolated to that timer undetected. Added a matching `mock_client.async_get_camera_status` await-count assertion around the same clock tick and corrected the docstring's "one piece of state" claim.
  - `[low]` `[patch]` `test_unload_then_reload_loads_again_with_fresh_state` requested `mock_client` directly with a justifying `noqa: ARG001` comment, but `mock_relay`/`mock_event_stream` already depend on `mock_client` in `tests/conftest.py`, so the client fixture activates regardless. Removed the redundant parameter and comment.

### 2026-09-15 — Repair + review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1 (medium 1)
- defer: 0
- reject: 10
- addressed_findings:
  - `[medium]` `[patch]` Deterministic verification (`uv run mypy custom_components tests`) failed on the committed `test_unload_then_reload_loads_again_with_fresh_state`: mypy narrowed `entry.state` to `Literal[NOT_LOADED]` from the mid-test assert and then flagged the later `is ConfigEntryState.LOADED` check as a non-overlapping/unreachable comparison. Fixed by binding `entry.state` to fresh local variables (`state_after_unload`, `state_after_reload`) at each checkpoint instead of re-narrowing the same attribute expression -- no behavior change, test-only. Both Blind Hunter and Edge Case Hunter independently flagged that `test_repeated_unload_reload_cycles_leave_no_accumulating_state`'s final "nothing survives the second unload" check re-verified only the reconciliation timer's (`async_get_server_info`) await count, not the light-poll timer's (`async_get_camera_status`), leaving a light-poll-timer leak specifically after the *second* unload undetected despite the docstring's claim that both timers are checked. Added the matching `async_get_camera_status` await-count assertion alongside the existing one.

## Auto Run Result

Status: done

**Summary:** Resumed an in-progress session after the previously committed work (commit `a6933155`, already reviewed and marked `done`) failed a subsequent deterministic verification pass: `uv run mypy custom_components tests` reported a non-overlapping identity check / unreachable statement on `entry.state` comparisons in `test_unload_then_reload_loads_again_with_fresh_state`, caused by mypy narrowing the `entry.state` attribute expression across an intervening `is ConfigEntryState.NOT_LOADED` assert. Fixed by binding `entry.state` to distinct local variables at each checkpoint instead of re-checking the same narrowed attribute expression -- a pure type-checker fix with no behavioral change. Re-ran the full review (Blind Hunter + Edge Case Hunter) on the story's diff since baseline; both independently surfaced the same real gap -- `test_repeated_unload_reload_cycles_leave_no_accumulating_state`'s final assertion block re-verified only the reconciliation timer's await count after the second unload, not the light-poll timer's, contradicting the test's own docstring claim that both timers are covered. Patched by adding the missing `async_get_camera_status` await-count assertion. No production code changed in either pass; no changes to the frozen `<intent-contract>`.

**Files changed:**
- `tests/test_init.py` -- fixed a mypy false-positive via local-variable rebinding in `test_unload_then_reload_loads_again_with_fresh_state`; added the missing light-poll-timer await-count assertion after the second unload in `test_repeated_unload_reload_cycles_leave_no_accumulating_state`.

**Review findings breakdown:** 1 patch applied (medium: missing light-poll-timer re-check after the second unload, confirmed independently by both reviewers), 0 deferred, 10 rejected (style/naming/docstring-colocation/scope observations with no regression risk -- see Review Triage Log above).

**Verification performed:** `uv run pytest tests/test_init.py -v` (35/35 passed), `uv run pytest --cov=custom_components.securityspy --cov-report=term-missing` (193/193 passed, 99% overall coverage, no regression), `uv run ruff check .` and `uv run ruff format --check .` (clean), `uv run mypy custom_components tests` (clean -- the specific failure from the verification-evidence file no longer reproduces).

**Residual risks:** None assessed as blocking. This was a narrow, test-only repair; the underlying production teardown wiring was already verified sound in the prior review pass and is untouched here.

This story requires no action a human must perform outside the repo (no domain, DNS, API key, or vendor-console step) -- `status: done` is final, not `awaiting-operator`.
