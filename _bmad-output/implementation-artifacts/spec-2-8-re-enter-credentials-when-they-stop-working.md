---
title: 'Story 2.8 — Re-enter credentials when they stop working'
type: 'feature'
created: '2026-09-14'
status: 'done'
baseline_revision: 'ba329347'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '4a3fc2d9'
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** When the stored SecuritySpy password stops working while the entry is running, both periodic polls fail with `SecuritySpyAuthError`, log it at DEBUG and retry forever. The user is never told, and there is no reauth flow to fix it.

**Approach:** The coordinator gets one consecutive-auth-failure counter (AD-18), shared by the heavy poll, the light poll and a stream-facing hook that Epic 3 will wire. On the third consecutive failure it stops both poll timers and starts reauth. The config flow gains `reauth`/`reauth_confirm` steps. They validate the new credentials, reject a different server and update the entry in place, and the reload restarts the planes.

## Boundaries & Constraints

**Always:**
- Counter on `SecuritySpyDataUpdateCoordinator` (`AUTH_FAILURE_THRESHOLD = 3` in `const.py`):
  - `record_auth_failure()`: increments. When it reaches the threshold, it cancels both poll timers and calls `config_entry.async_start_reauth(hass)` exactly once.
  - `record_auth_success()`: resets to 0.
  - Both are public `@callback`s so the Epic 3 stream's `on_auth_failed`/connected callbacks can call them.
- Only `SecuritySpyAuthError` counts. `SecuritySpyPermissionError`, connect errors and other errors neither count nor reset. Any successful heavy or light fetch resets the counter.
- Timer cancel callbacks are kept by the coordinator (and still registered with `async_on_unload`), so cancelling early and then unloading is safe.
- Config flow:
  - `async_step_reauth(entry_data)` → `async_step_reauth_confirm`.
  - The form asks for username (prefilled from the entry) and password only.
  - On submit it probes with the entry's host/port/ssl/verify_ssl plus the new credentials, reusing `_async_probe` and its error keys. The form redisplays on error without echoing the password.
  - On success: `async_set_unique_id(server.uuid)`, `_abort_if_unique_id_mismatch(reason="wrong_server")`, then `async_update_reload_and_abort(entry, data_updates={username, password})`.
- `strings.json` and `translations/en.json` stay identical:
  - `config.step.reauth_confirm` (title, description, data, data_description).
  - `config.abort.reauth_successful` and `config.abort.wrong_server`.
- No credential in logs, messages or form descriptions. The reauth trigger logs one WARNING with no credential.

**Block If:**
- Detecting auth failure requires a library change (the library would have to count failures, or `SecuritySpyAuthError` would not be raised by the polls).

**Never:**
- Starting reauth on the first or second failure. Counting permission denials as auth failures. Removing or recreating the entry, devices or entities. Implementing the event stream (Epic 3). A reconfigure step (story 2.9). Changing setup-time `ConfigEntryAuthFailed` mapping.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Three strikes | 3 consecutive poll `SecuritySpyAuthError`, mixed heavy/light | Reauth flow in progress for entry; timers cancelled; no further fetches | WARNING once |
| Mixed planes | 2 poll failures + 1 `record_auth_failure()` (stream hook) | Reauth started | — |
| Transient | 2 failures then a successful poll | Counter 0; no flow; 2 more failures still no flow | — |
| Permission, not auth | 3 `SecuritySpyPermissionError` | No flow; counter unchanged | DEBUG as before |
| Beyond threshold | 4th failure recorded | No second reauth start | — |
| Reauth success | Valid creds, same UUID | Abort `reauth_successful`; entry data updated; same entry_id; devices/entities kept | — |
| Wrong server | Valid creds, other UUID | Abort `wrong_server`; entry data unchanged | — |
| Bad creds | Probe raises auth/connect/etc. | Form again, `errors.base` key; password not suggested | — |

</intent-contract>

## Code Map

- `custom_components/securityspy/coordinator.py` -- `async_start` timer registration, `_async_reconcile`, `_async_poll_light_status` except-clauses.
- `custom_components/securityspy/const.py` -- add `AUTH_FAILURE_THRESHOLD`.
- `custom_components/securityspy/config_flow.py` -- `SecuritySpyConfigFlow`, `_async_probe`, `_build_client`, `_preserved_values`.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- config step/abort blocks.
- `tests/test_coordinator.py`, `tests/test_config_flow.py`, `tests/test_translations.py`, `tests/conftest.py` -- fixtures.

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/const.py` -- add threshold constant.
- [x] `custom_components/securityspy/coordinator.py` -- counter, record methods, timer cancel handles, counting in both polls.
- [x] `custom_components/securityspy/config_flow.py` -- reauth steps per contract.
- [x] `custom_components/securityspy/strings.json`, `translations/en.json` -- new strings.
- [x] `tests/test_coordinator.py` -- matrix rows 1–5.
- [x] `tests/test_config_flow.py` -- matrix rows 6–8, incl. every error key and prefilled username; assert devices/entities survive reauth.

**Acceptance Criteria:**
- Given an entry in reauth, when working credentials are submitted, then the entry reloads with the same entry_id and its device and entity registry entries are unchanged.
- Given the full suite, when verification runs, then all pass with 100% coverage.

## Spec Change Log

## Review Triage Log

### 2026-09-14 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 1: (high 0, medium 0, low 1)
- reject: 16: (high 0, medium 3, low 13)
- addressed_findings:
  - `[medium]` `[patch]` A poll in flight when the threshold stopped the timers could succeed and reset the counter. Three later failures (e.g. from the Epic 3 stream) would then start a second reauth and a second WARNING, which would reappear if the user had dismissed the first. Fix: a `_reauth_started` latch freezes the counter, so both `record_*` calls are no-ops until the reload builds a fresh coordinator. Test: `test_a_late_success_after_the_threshold_does_not_rearm_reauth`.
  - `[low]` `[patch]` `test_non_auth_failures_neither_count_nor_reset` accepted a DEBUG or WARNING record from any logger. It now filters to the integration's own logger.

## Design Notes

The counter lives on the coordinator: it runs both polls, and Epic 3 will attach the stream to it. Setup (`__init__.py`) keeps the AD-6 mapping of a failure at startup, where HA already starts reauth on `ConfigEntryAuthFailed`. A running entry cannot raise that from a timer callback, so it calls `entry.async_start_reauth` directly. That call is what `ConfigEntryAuthFailed` does internally. Stopping the timers means a dead password is not hammered every poll, which could also trip lockouts. `async_update_reload_and_abort` reloads the entry, and the reload recreates the coordinator with a zero counter and fresh timers.

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` -- expected: all pass, 100%.
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `uv run mypy custom_components tests` -- expected: clean.

## Auto Run Result

Status: done

**Summary.** The coordinator now owns AD-18's consecutive-auth-failure counter. Both polls count `SecuritySpyAuthError` into it, and the public `record_auth_failure`/`record_auth_success` hooks are ready for Epic 3's stream. Any authenticated fetch resets the counter; permission denials and connect errors are not counted. On the third consecutive failure the coordinator stops both poll timers, logs one WARNING with no credential, and starts reauth once. The counter is then latched until reload. The config flow's new `reauth_confirm` step asks for username (prefilled) and password only. It probes the entry's own address, rejects a different server with `wrong_server`, and updates the entry in place with `async_update_reload_and_abort`, so entry, devices and entities persist. Commit: `4a3fc2d9`.

**Files changed**
- `custom_components/securityspy/const.py` -- `AUTH_FAILURE_THRESHOLD = 3`.
- `custom_components/securityspy/coordinator.py` -- counter, reauth latch, `record_auth_failure`/`record_auth_success`, idempotent timer cancel, counting in both polls.
- `custom_components/securityspy/config_flow.py` -- `reauth`/`reauth_confirm` steps and schema.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- `reauth_confirm` step; `reauth_successful` and `wrong_server` aborts.
- `tests/test_coordinator.py`, `tests/test_config_flow.py` -- every matrix row, every error key, a real reauth flow, registry preservation, the latch.
- `tests/test_init.py` -- the setup-time auth test now expects the reauth flow HA starts from `ConfigEntryAuthFailed` (setup mapping unchanged).

**Review findings:** 2 patched (medium 1, low 1), 1 deferred (heavy poll lacks the light poll's `except Exception` guard; pre-existing), 16 rejected. Rejected findings include:
- Entities not going unavailable while reauth is pending (Epic 3 availability).
- Polling not resuming if reauth is dismissed (designed: a reload or reauth restarts it).
- A single setup-time 401 prompting reauth (the contract forbids changing the setup mapping).
- Reauth accepting a different account on the same server.
- An orphan prompt if the threshold is hit mid-unload.

**Follow-up review recommended: no.** The one medium fix is a small, localized latch covered by a dedicated test.

**Verification**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100`: 151 passed, 100.00% coverage.
- `uv run ruff check .`, `uv run ruff format --check .`: clean.
- `uv run mypy custom_components tests`: clean.

**Residual risks**
- The stream plane is not wired yet; Epic 3 must call `record_auth_failure` from `on_auth_failed` and `record_auth_success` on connect.
- While reauth is pending, entities keep showing their last data. Nothing marks them unavailable until Epic 3's availability layers.
- A server that returns 401 for about 90 seconds (three light polls), for example during an account edit, prompts reauth even though the stored password recovers.
