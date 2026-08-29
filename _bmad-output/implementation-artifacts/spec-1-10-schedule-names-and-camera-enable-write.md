---
title: 'Story 1.10: Schedule names and the camera enable write'
type: 'feature'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
baseline_revision: '917da39c23ac19ace253af4ea7dad4f507fb74b4'
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
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- decode `schedule-list` onto `ServerInfo` and add `CameraScheduleAssignment.resolve_names` -- the id-to-name data and the pure resolver the read half of this story exists to deliver.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add `enabled` to `CameraSettingsPatch` and its boolean field table -- reuses the existing write asymmetry rather than introducing a second one.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- add `async_set_camera_enabled` delegating to `async_set_camera_settings` -- the named accessor for FR-16.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export new public names in sorted order.
- [x] `aiosecurityspy/tests/test_models.py`, `aiosecurityspy/tests/test_client.py` -- cover every I/O-matrix row, including the malformed and absent schedule-list forms, the unknown-id resolution, and the exact `enabled=1`/`enabled=0` body.
- [x] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document schedule-name resolution and the enable write, including that schedules remain read-only.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a captured real-server `systemInfo` payload, when it is decoded, then the four built-in schedules resolve by name and each camera's three ids resolve through them without a second request.

## Spec Change Log

- `ServerInfo.schedules` is decoded from `schedule-list` on the same `system` mapping
  `_decode_cameras` already receives (per the Code Map). The fixture
  `real_server_camera_list.json` used the XML-form schedule key spellings
  (`schedule-id-cc`), which verification §3 confirms are **not** what the JSON sends
  (`cc-schedule-id`); the fixture was corrected so the story's "camera ids resolve
  against the decoded map" acceptance criterion is testable, and that correction is
  pinned by a regression test that fails against the pre-fix fixture.
- The `__init__.py` export task was a no-op: every new name is a method or field on an
  already-exported class (`async_set_camera_enabled` is a `SecuritySpyClient` method;
  `ServerInfo.schedules` is a field; `resolve_names` is a `CameraScheduleAssignment`
  method), so no module-level public name changed and RUF022 stayed satisfied.
- Tests landed in `test_settings.py` rather than `test_client.py` for the enable-write
  coverage, matching where the existing settings-write body tests already live; the
  story's Code Map named both files, and the settings file is the one that owns the
  byte-exact `formData` body assertions.

## Review Triage Log

- **Adversarial + edge-case: duplicate schedule ids and silent malformed-entry drops.**
  `_decode_schedules` initially let a later duplicate win and dropped id-less/name-less
  entries with no trace, where `_decode_cameras` keeps-first and logs every skip.
  **Accepted:** the decoder now keeps the first entry for a duplicated id and logs each
  malformed skip at debug, matching its sibling.
- **Adversarial: `enabled` read default `False` differs from inventory `Camera.enabled`
  default `True`.** The settings read model defaults every boolean to `False` (its
  existing convention); the inventory `Camera.enabled` defaults `True`. The two are
  different endpoints with different documents and this story adds no new
  inconsistency -- `enabled` follows the settings model's established default. Rejected
  as non-defect.
- **Edge-case: adding `enabled` widens `SETTINGS_PAGE_KEYS` near the quorum gate.** The
  quorum is an explicit, documented trade-off (its comment warns against raising it
  without a second server version); `enabled` joining the bool field table is the spec's
  chosen mechanism. Rejected.
- **Adversarial: body order renders `enabled` before named int fields.** The spec
  deliberately wires `enabled` through the existing `_SETTINGS_BOOL_FIELDS` mechanism
  (one asymmetry, one ordering), and only single-field writes are live-verified. The
  spec chose reuse over a second ordering rule. Rejected.
- **Adversarial: `ServerInfo.schedules` vs `Camera.schedules` name collision.**
  `schedules` on `ServerInfo` is the spec's chosen name for the id-to-name map; the
  README example makes the resolution explicit. Rejected.
- **Adversarial: no "located" flag for `schedule-list`.** The spec's I/O matrix
  explicitly requires an absent list to decode to an empty mapping (never a raise) --
  the opposite of the camera-list policy. Rejected.
- **Adversarial: `async_set_camera_enabled(3, enabled=None)` raises "patch is empty".**
  The parameter is keyword-only `bool`; mypy --strict rejects non-bool at every call
  site, and `CameraSettingsPatch` already raises `ValueError` before any request.
  Rejected.
- **Adversarial: §5.5 citation reads as "unverified by write".** The committed research
  §5.5 documents the wire mechanism (id-only checkbox, `enabled=1|0` body); live
  confirmation (§5.8, G3/G4) is uncommitted research left for a later pass and is not
  cited here. Rejected.

## Auto Run Result

- **Status:** done
- **Follow-up review recommended:** true -- the fixture correction and the two-source
  `enabled` semantics are worth an independent pass.

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
