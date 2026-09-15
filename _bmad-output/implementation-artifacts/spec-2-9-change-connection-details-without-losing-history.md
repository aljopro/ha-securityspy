---
title: 'Story 2.9 — Change connection details without losing history'
type: 'feature'
created: '2026-09-14'
status: 'done'
baseline_revision: 'c3883aeb'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '83a56fde'
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** A user whose SecuritySpy server moves to a new address, port or TLS setup cannot change it in place. The only way out is to delete and re-add the entry, which orphans every device, entity, customization and its history (FR-29).

**Approach:** Add a config-flow `reconfigure` step (Gold `reconfiguration-flow`). It shows the full connection form prefilled from the entry (except the password), validates the submission against the live server, rejects a different server UUID, and updates the entry in place with `async_update_reload_and_abort`.

## Boundaries & Constraints

**Always:**
- `async_step_reconfigure(user_input)` uses `self._get_reconfigure_entry()` and the existing `STEP_USER_DATA_SCHEMA` (host, port, username, password, ssl, verify_ssl).
- First display suggests every current `entry.data` value except the password. A redisplay after an error suggests the submitted values via `_preserved_values` (password never suggested).
- On submit, validate with `_async_probe(user_input)` and its existing error keys. On error, show the form again with `errors["base"]`.
- On success: `async_set_unique_id(server.uuid)`, `_abort_if_unique_id_mismatch(reason="wrong_server")`, then `async_update_reload_and_abort(entry, data_updates=user_input)`. Entry id, title, options, devices and entities are unchanged.
- `strings.json` and `translations/en.json` stay identical. Add `config.step.reconfigure` (title, description, `data` and `data_description` for all six fields) and `config.abort.reconfigure_successful`. Reuse the existing `wrong_server` abort.
- `tests/test_translations.py`: the `reconfigure` step's `data`/`data_description` keys match `STEP_USER_DATA_SCHEMA`.
- No credential in logs, messages, suggested values or descriptions (AD-13).

**Block If:**
- Reconfigure needs a library change, or HA 2026.3 lacks `_get_reconfigure_entry`/`async_update_reload_and_abort(data_updates=)`.

**Never:**
- Removing or recreating the entry, devices or entities. Changing the reauth or user steps, the setup exception mapping, or options. Storing the password as a suggested value. Changing the entry title on reconfigure. Closing the deferred `_abort_if_unique_id_configured` re-add path (it stays deferred; reconfigure is the supported route).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Open form | Loaded entry | Form `reconfigure`, no errors; suggestions = entry data minus password | — |
| Same server, new address | New host/port/ssl/verify/creds; probe returns same UUID | Abort `reconfigure_successful`; `entry.data` == submitted input; same entry_id; entry reloaded; device/entity registry entries unchanged | — |
| Different server | Probe returns another UUID | Abort `wrong_server`; `entry.data` unchanged | — |
| Probe failure | Probe raises cert/auth/permission/version/connect/unexpected error, or no UUID | Form again with the matching `errors.base` key; password not suggested; other submitted values kept | — |
| Unusable host | Host with scheme/path | Form again, `invalid_host`; no network call | — |
| Recover after error | Error, then valid submission | Abort `reconfigure_successful` | — |

</intent-contract>

## Code Map

- `custom_components/securityspy/config_flow.py` -- `SecuritySpyConfigFlow`; reuse `_async_probe`, `_preserved_values`, `STEP_USER_DATA_SCHEMA`; mirror `async_step_reauth_confirm`.
- `custom_components/securityspy/__init__.py` -- reads host/port/ssl/verify/creds from `entry.data` only at setup, so the reload applies the change (no edit).
- `custom_components/securityspy/strings.json`, `translations/en.json` -- config step and abort blocks.
- `tests/test_config_flow.py` -- `_set_up_entry`, `_suggestions`, `mock_client`/`mock_client_class`, `MOCK_USER_INPUT`, `SERVER_UUID`, reauth tests as the pattern.
- `tests/test_translations.py` -- the `user`-step schema key check to mirror.

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/config_flow.py` -- add `async_step_reconfigure` per contract -- FR-29 in-place address change.
- [x] `custom_components/securityspy/strings.json`, `custom_components/securityspy/translations/en.json` -- add `reconfigure` step and `reconfigure_successful` abort -- translated UI; the files must stay identical.
- [x] `tests/test_config_flow.py` -- one test per matrix row, including every error key (parametrized), the prefill without the password, and registry preservation across the real reload -- 100% flow coverage.
- [x] `tests/test_translations.py` -- `reconfigure` step labels match the schema -- catches untranslated fields.

**Acceptance Criteria:**
- Given a reconfigured entry, when the reload finishes, then the entry is loaded, the client was built with the new host and port, and no second entry exists.
- Given the full suite, when verification runs, then all tests pass with 100% coverage.

## Spec Change Log

## Review Triage Log

### 2026-09-14 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 0, low 2)
- defer: 0
- reject: 20: (high 0, medium 3, low 17)
- addressed_findings:
  - `[low]` `[patch]` The `reconfigure_successful` text claimed a new address even when only TLS settings or the account changed, and the step description said "confirm" although a changed account is stored. Reworded both in `strings.json`/`en.json`.
  - `[low]` `[patch]` The success test never asserted `verify_ssl` reached the rebuilt client. Added the assertion.

## Design Notes

This mirrors reauth. The UUID mismatch check keeps devices keyed on `server_uuid` attached (AD-5). The password is required and never prefilled: prefilling would send the stored credential back to the browser. Retyping it is the AD-13 cost. The reload in `async_update_reload_and_abort` rebuilds the client from the new data.

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` -- expected: all pass, 100%.
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `uv run mypy custom_components tests` -- expected: clean.

## Auto Run Result

Status: done

**Summary.** The config flow has a `reconfigure` step (FR-29, Gold `reconfiguration-flow`). It shows the full connection form prefilled from the entry, except the password. It validates the submission with the existing probe and error keys, and rejects a different server UUID with `wrong_server`. On success it updates the same entry in place with `async_update_reload_and_abort`, so the entry id, title, devices and entities are kept, and the reload rebuilds the client from the new details. Commit: `83a56fde`.

**Files changed**
- `custom_components/securityspy/config_flow.py` -- `async_step_reconfigure`.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- `reconfigure` step and `reconfigure_successful` abort.
- `tests/test_config_flow.py` -- every matrix row: prefill, in-place update with registry preservation and the rebuilt client, wrong server, all eight probe errors, invalid host, recovery.
- `tests/test_translations.py` -- reconfigure labels match the schema.

**Review findings:** 2 patched (low), 0 deferred, 20 rejected. Rejected findings include:
- The password must be retyped (a spec decision, AD-13).
- An unchanged submission still reloads.
- Entries with no `unique_id` (every entry gets one at creation).
- A reauth prompt left open during reconfigure.
- Leftover entities after switching to a less-privileged account (story 2.7's repair covers it).

**Follow-up review recommended: no.** The only fixes were two low-severity wording and test-assertion changes.

**Verification**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-fail-under=100`: 165 passed, 100.00%.
- `uv run ruff check .`, `uv run ruff format --check .`: clean.
- `uv run mypy custom_components tests`: clean.

**Residual risks**
- The deferred re-add path (the user step discards a new address on `already_configured`) is still open, on purpose. Reconfigure is the supported way to change the address.
- A reauth flow left open during reconfigure could later overwrite the new credentials if the user completes it.
