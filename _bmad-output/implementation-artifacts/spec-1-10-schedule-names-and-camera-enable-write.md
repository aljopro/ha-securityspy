---
title: 'Story 1.10: Schedule names and the camera enable write'
type: 'feature'
created: '2026-08-29'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** A camera's `*-schedule-id` values decode today, but nothing turns an id into the name a user would recognise, so a consumer can show "schedule 2" and nothing better. And a camera's enabled state is readable through `++camStatus` yet not writable at all, so a camera cannot be taken out of service through the library.

**Approach:** Decode `systemInfo`'s top-level `schedule-list` into an id-to-name mapping on `ServerInfo`, and give `CameraScheduleAssignment` a pure resolver that turns its three ids into names against that mapping. Add `async_set_camera_enabled`, writing the single `enabled` field through the existing verified partial-write path.

## Boundaries & Constraints

**Always:** `schedule-list` is a sibling of `server` in the `systemInfo` body, decoded from the same `system` mapping `_decode_cameras` already receives. Resolution is a **pure, synchronous** operation on already-decoded data -- no request, no second fetch. An id with no matching schedule resolves to `None`; so does an absent id. Schedules stay **read-only** (AD-7): nothing here assigns, creates or edits one. The enable write goes through `async_set_camera_settings`'s mechanism, so the sentinel-first body rule, the `1`/`0` boolean asymmetry and the percent-encoding all keep living in exactly one place. `enabled` is a checkbox key: it is serialised by element **id**, which is why it is absent from the named-field list in research §8.1 (verification §5.5).

**Block If:** the `PERM_SETTINGS` constant from story 1.11 is absent -- the permission acceptance criterion cannot be met without it, and inventing a second definition would leave two. 1.11 lands first.

**Never:** No read-modify-write of the settings page, and no fetch of the camera inventory to serve the write. No caller-supplied form key or raw body -- only a camera and a boolean. No use of `settings-cameras-multi` or its `x`-prefixed apply-toggles; the single-camera page is the mechanism. No new transport path: if the write needs anything `async_set_camera_settings` cannot express, that is a finding, not a second POST helper. No decoding of `schedule-preset-list` or `group-list` -- both are out of scope, and the former was empty on the reference server so its element shape is unverified. Schedule *override* names are not decoded here either, though `schedule-override-list` sits beside `schedule-list`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Decode schedule list | `systemInfo` carries `schedule-list: [{"name":"Armed 24/7","id":1}, ...]` | `ServerInfo` exposes a read-only `{1: "Armed 24/7", ...}` mapping | No error expected |
| Absent schedule list | The key is missing entirely | An empty mapping, not an exception -- the rest of `systemInfo` still decodes | No error expected |
| Malformed entry | An entry lacks `id`, lacks `name`, or is not an object | That entry is skipped; every well-formed entry still decodes | No error expected |
| Resolve a camera's schedules | Camera with `cc/mc/a-schedule-id = 1`, mapping as above | All three resolve to `"Armed 24/7"` | No error expected |
| Unknown schedule id | Camera references id `7`, absent from the mapping | Resolves to `None` | Never raises |
| Absent schedule id | The camera's id is already `None` | Resolves to `None` | Never raises |
| Enable a camera | `async_set_camera_enabled(4, enabled=True)` | POSTs `formData&cameraNum=4&enabled=1` to `++settings-cameras` | No error expected |
| Disable a camera | `enabled=False` | The body carries `enabled=0` | No error expected |
| Invalid camera number | A negative or non-integer camera number | `ValueError` before any request is issued | Raised, not sent |
| Account lacks the permission | Server answers `403` to the write | `SecuritySpyPermissionError` naming the `settings` permission (story 1.11) | Typed, never reported as success |
| Credentials rejected | Server answers `401` | `SecuritySpyAuthError` | Typed |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: `ServerInfo` (~line 810) gains a `schedules: Mapping[int, str]` field, wrapped in `MappingProxyType` exactly as `cameras` already is; `ServerInfo.from_api` (~line 860) decodes it from `system.get("schedule-list")`, beside the existing `_decode_cameras(system)` call. `CameraScheduleAssignment` (~line 413) gains a pure `resolve_names(schedules)` returning the three names. The list is an **array of `{name, id}`**, not an object keyed by id (verification §5.4).
- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: `CameraSettingsPatch` gains `enabled: bool | None = None`, wired into `_SETTINGS_BOOL_FIELDS` (~line 1152) as `("enabled", "enabled")` so `form_fields()` renders it `1`/`0` with no new asymmetry logic.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: add `async_set_camera_enabled(self, camera_number: int, *, enabled: bool) -> None` next to `async_set_camera_settings` (~line 1087), delegating to it with a single-field patch. A thin, named accessor rather than making callers hand-build a patch, because "take a camera out of service" is the operation FR-16 names.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export any new public name in sorted (RUF022) order.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- read: `PERM_SETTINGS` arrives from story 1.11; this story consumes it and must not redefine it.
- `aiosecurityspy/tests/test_models.py` -- the `ServerInfo.from_api` and `Camera` fixtures the schedule-list cases extend.
- `aiosecurityspy/tests/test_client.py` -- the `FakeSession` harness and the existing `async_set_camera_settings` body-assembly tests, which pin the sentinel-first ordering the enable write inherits.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §4.3, §5.4, §5.5 -- the verified shapes for everything above.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- decode `schedule-list` onto `ServerInfo` and add `CameraScheduleAssignment.resolve_names` -- the id-to-name data and the pure resolver the read half of this story exists to deliver.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- add `enabled` to `CameraSettingsPatch` and its boolean field table -- reuses the existing write asymmetry rather than introducing a second one.
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- add `async_set_camera_enabled` delegating to `async_set_camera_settings` -- the named accessor for FR-16.
- [ ] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export new public names in sorted order.
- [ ] `aiosecurityspy/tests/test_models.py`, `aiosecurityspy/tests/test_client.py` -- cover every I/O-matrix row, including the malformed and absent schedule-list forms, the unknown-id resolution, and the exact `enabled=1`/`enabled=0` body.
- [ ] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document schedule-name resolution and the enable write, including that schedules remain read-only.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a captured real-server `systemInfo` payload, when it is decoded, then the four built-in schedules resolve by name and each camera's three ids resolve through them without a second request.

## Spec Change Log

## Review Triage Log

## Design Notes

**Resolution is a method on the assignment, not a field on the camera.** Storing resolved names on `Camera` would freeze them at decode time and duplicate the same four strings across every camera. A pure `resolve_names(schedules)` keeps one copy of the mapping on `ServerInfo`, keeps `Camera` decode independent of server-level data, and lets a consumer resolve whenever it likes.

**Unknown ids resolve to `None`, never raise.** Schedules are user-editable and the two documents are fetched as one payload but need not stay consistent forever -- a schedule can be deleted while a camera still references it. That is a display gap, not a decode failure, and the acceptance criterion says so explicitly.

**The enable write reuses the settings path rather than wrapping a new one.** `enabled` is one more id-keyed checkbox among the 82 on that page; the only thing that made it invisible to earlier work is that research §8.1 catalogued named fields and this checkbox carries no `name`. Nothing about it needs a new transport.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, every pre-existing test included

**Manual checks (if no CLI):**
- The enable write's field name is read from the shipped 6.21 client, not confirmed by a live round-trip. If a live write is ever performed, confirm the camera's `enabled` flips in `++camStatus` and that no other settings key changes.
