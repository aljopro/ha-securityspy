---
title: 'Story 2.7 — Only create entities the user is permitted to use'
type: 'feature'
created: '2026-09-13'
status: 'done'
baseline_revision: '839d85c4'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '8edf5bc3'
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** Platforms create entities without checking the account's per-camera permissions. A restricted account can therefore end up with entities that fail permanently, and nothing tells the user why.

**Approach:** Decode each camera's permissions onto coordinator data and add one shared gate (`permissions.py`). Every platform asks the gate before creating a permission-dependent entity. Setup then turns the gate's recorded denials into one repair issue per missing permission and clears issues for permissions no longer denied. The camera platform (live video) is the first consumer.

## Boundaries & Constraints

**Always:**
- `SecuritySpyData` gains `camera_permissions: Mapping[int, frozenset[str]]`, built from each camera's library `Camera.permission_names` for every camera in `server.cameras`. It is set at construction and on every heavy refresh, and wrapped in `MappingProxyType`.
- `permissions.py` defines `PermissionGate`, stored on `SecuritySpyRuntimeData.permission_gate`:
  - `permitted(camera_number, permission) -> bool` reads `coordinator.data.camera_permissions`. It records a denial of `(permission, camera_number)` when the camera lacks the permission or is absent.
  - A permission name not in `aiosecurityspy.PERMISSION_NAMES.values()` raises `ValueError`, so a typo can't silently deny every camera.
  - `async_update_issues(hass)`:
    - For each denied permission, it creates an issue with id `missing_permission_{permission}` via `ir.async_create_issue`. It is not fixable, severity `WARNING`, and uses translation key `missing_permission`. Its placeholders are `permission` (the library name) and `cameras`: the affected camera names from `server.cameras`, sorted by camera number and comma-joined.
    - For every other name in `PERMISSION_NAMES.values()`, it deletes that issue.
- `camera.py` creates a `SecuritySpyCamera` only where `gate.permitted(number, "live_video")` is true. With `create_camera_entities` off, it consults nothing.
- `__init__.py` creates the gate before forwarding platforms, then awaits `async_forward_entry_setups`, then calls `gate.async_update_issues(hass)`.
- `async_unload_entry` leaves issues in place; a reload re-evaluates them. Removing the config entry deletes all `missing_permission_*` issues through `async_remove_entry`.
- `strings.json` and `translations/en.json` get an identical `issues.missing_permission` block. Its title names `{permission}`; its description lists `{cameras}` and says to grant it in SecuritySpy under Settings → Web → Accounts (edit this account's camera permissions), then reload the integration.
- `tests/conftest.py`'s `make_camera` default `permissions` changes from `0` to `PERM_LIVEVIDEO`, so existing fixtures describe cameras the inventory can actually contain (DW-5).

**Block If:**
- Meeting an AC requires widening the inventory beyond `++systemInfo`. DW-5 Option 1 forbids it.

**Never:**
- Using `++camStatus` to find or name cameras `++systemInfo` withheld; platform-local permission rules; gating sensors or the update entity, which need no per-camera permission; a fixable repair flow; library changes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| All permitted | Cameras 1 and 2 with `PERM_LIVEVIDEO` | Both camera entities; no issue; `camera_permissions[1]` contains `"live_video"` | None |
| Per-camera denial | Camera 1 mask `PERM_LIVEVIDEO`, camera 2 mask `PERM_SCHED` | Camera 1 entity only; issue `missing_permission_live_video` with `cameras="Camera 2"` | None |
| Several denied | Cameras 2 and 3 lack live video | One issue; `cameras="Camera 2, Camera 3"` | None |
| Granted and reloaded | After denial, mask fixed, entry reloaded | Entity created; issue deleted | None |
| Option off | `create_camera_entities=False` with a denial present | No camera entities; stale issue deleted | None |
| Unknown name | `gate.permitted(1, "live_vidoe")` | — | `ValueError` |
| Absent camera | `gate.permitted(99, "live_video")` | `False`, denial recorded | None |
| Entry removed | Config entry deleted | All `missing_permission_*` issues removed | None |

</intent-contract>

## Code Map

- `custom_components/securityspy/coordinator.py` -- `SecuritySpyData` (~line 53), its construction at `__init__` (~99), and the heavy refresh `replace(...)` (~161).
- `custom_components/securityspy/__init__.py` -- `SecuritySpyRuntimeData`, `async_setup_entry` (forwarding), `async_unload_entry`; add `async_remove_entry`.
- `custom_components/securityspy/permissions.py` -- **new** gate.
- `custom_components/securityspy/camera.py` -- `async_setup_entry` entity generator.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- new `issues` block.
- Library (read-only, `.venv`): `Camera.permission_names`, `PERMISSION_NAMES` (`const.py`), `PERM_LIVEVIDEO`, `PERM_SCHED`.
- `tests/conftest.py` -- `make_camera(permissions=...)` default.
- `tests/test_permissions.py` (new), `tests/test_camera.py`, `tests/test_coordinator.py`, `tests/test_init.py`, `tests/test_translations.py`.

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/coordinator.py` -- add and maintain `camera_permissions`.
- [x] `custom_components/securityspy/permissions.py` -- `PermissionGate` per contract.
- [x] `custom_components/securityspy/__init__.py` -- create the gate, sync issues after forwarding, `async_remove_entry`.
- [x] `custom_components/securityspy/camera.py` -- consult the gate.
- [x] `custom_components/securityspy/strings.json`, `translations/en.json` -- `issues.missing_permission`.
- [x] `tests/conftest.py` -- default permissions to `PERM_LIVEVIDEO`.
- [x] `tests/test_permissions.py` -- unit tests for the gate: unknown name, absent camera, deduplicated denials, issue create and delete.
- [x] `tests/test_camera.py` / `tests/test_init.py` -- one integration test per matrix row, using `issue_registry`.
- [x] `tests/test_coordinator.py` -- `camera_permissions` present at start and refreshed on the heavy poll.

**Acceptance Criteria:**
- Given setup, when coordinator data is read, then each visible camera's decoded permission names are available per camera.
- Given the issue for a denied permission, when its translated text is rendered, then it names the permission, the affected cameras and where to grant it in SecuritySpy.
- Given the full suite, when verification runs, then all pass with 100% coverage.

## Spec Change Log

## Review Triage Log

### 2026-09-13 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 0
- reject: 13: (high 0, medium 2, low 11)
- addressed_findings:
  - `[medium]` `[patch]` Issue ids were shared by all config entries (`missing_permission_{permission}`). With two SecuritySpy servers, one entry's setup deleted or overwrote the other's issue, and removing one entry deleted every entry's issues. Ids are now `missing_permission_{entry_id}_{permission}`, built by one helper, `permissions.issue_id`. The gate and `async_remove_entry` touch only their own entry's issues. **This deviates from the id format written in the intent contract**, which did not consider more than one entry; the id's only purpose there, one issue per missing permission, is unchanged. Test: `test_missing_permission_issues_are_scoped_per_entry`.
  - `[low]` `[patch]` A denial for a camera absent from the inventory produced an issue with an empty camera list. Absent cameras are now named `camera {number}`. Test: `test_absent_camera_is_denied_and_recorded`.

## Design Notes

**Why the gate records denials instead of platforms raising issues.** A platform that sees one camera cannot know about the others. Collecting denials across all platforms and syncing once after forwarding gives one issue per permission, listing every affected camera. It also gives one place to delete issues for permissions that are no longer denied. Later epics (arming `schedule`, capture images `files`) only call `gate.permitted`.

**Live-video gating is mostly defensive today.** Under DW-5, `++systemInfo` never lists a camera without live video, so against a real server the live-video denial should not occur. The mechanism is still proven on it, as the story asks, with fixture masks. Later permissions (`schedule`, `files`) will deny for real.

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` -- expected: all pass, 100%.
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `uv run mypy custom_components tests` -- expected: clean.

## Auto Run Result

Status: done

**Summary.** Each camera's decoded permission names now live on coordinator data as `camera_permissions`, taken from the library's `Camera.permission_names` at start and on every heavy refresh. `permissions.PermissionGate` is the one shared gate: platforms call `permitted(camera_number, permission)`, which refuses unknown names with `ValueError` and records each denial. After platforms are set up, `async_update_issues` creates one non-fixable warning issue per denied permission. The issue is scoped to the config entry and names the affected cameras, and issues for permissions no longer denied are deleted. Removing the entry deletes that entry's issues. Live video entities are the first consumer. Commit: `8edf5bc3`.

**Files changed**
- `custom_components/securityspy/permissions.py` (new) -- `PermissionGate` and the `issue_id` helper.
- `custom_components/securityspy/coordinator.py` -- `SecuritySpyData.camera_permissions`.
- `custom_components/securityspy/__init__.py` -- gate on runtime data, issue sync after platform setup, `async_remove_entry`.
- `custom_components/securityspy/camera.py` -- live video entities only where the gate permits.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- `issues.missing_permission`, naming the permission, the cameras, and where to grant it in SecuritySpy (Settings → Web → Accounts).
- `tests/conftest.py` -- `make_camera` defaults to `PERM_LIVEVIDEO` and takes a `permissions` kwarg.
- `tests/test_permissions.py` (new), `tests/test_camera.py`, `tests/test_init.py`, `tests/test_coordinator.py`, `tests/test_translations.py` -- every matrix row, plus a two-entry scoping test.

**Review findings:** 2 patched (medium 1, low 1), 0 deferred, 13 rejected. The medium fix changed the issue id format written in the intent contract to include the entry id; see the Review Triage Log. Rejected findings include permission changes needing a reload (the AC is written around a reload), orphaned issues if a future library renames a permission, raw permission names in the issue text (the contract specifies the library name), and the fixture default change (intended, per DW-5).

**Follow-up review recommended: no.** The per-entry id fix is small and covered by a dedicated test.

**Verification**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100`: 129 passed, 100.00% coverage.
- `uv run ruff check .`, `uv run ruff format --check .`: clean.
- `uv run mypy custom_components tests`: clean.

**Residual risks**
- Against a real server the live-video denial should never occur: under DW-5, `++systemInfo` omits any camera without live video. The mechanism is proven with fixture masks, and gating becomes load-bearing when Epics 4 and 6 gate on `files` and `schedule`.
- A permission granted or revoked while running takes effect only after a reload. Nothing re-evaluates the gate on the heavy refresh.
- The issue text shows the library's permission name (e.g. `live_video`) rather than SecuritySpy's checkbox label.
