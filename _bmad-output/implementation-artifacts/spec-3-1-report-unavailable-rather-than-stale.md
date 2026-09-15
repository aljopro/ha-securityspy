---
title: 'Story 3.1 — Report unavailable rather than stale'
type: 'feature'
created: '2026-09-14'
status: 'done'
baseline_revision: '22dd88a0'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: 'b760083f'
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** Both coordinator polls swallow `SecuritySpyError` and keep old data, so `last_update_success` never goes False and every entity keeps showing stale values when the server is unreachable. Per-camera state is also not handled: an offline camera, or one missing from the inventory, still looks available. Reconcile auto-deletes devices for cameras that leave the inventory, and nothing tracks stream health (FR-30, FR-16a, Silver `entity-unavailable`).

**Approach:** Availability is decided in one place, a shared base entity in `entity.py`, from four layers:
1. Coordinator poll success.
2. The camera is in the inventory.
3. The camera is online.
4. Stream health, only for push-derived entities.

The coordinator marks poll failures and exposes a `stream_connected` flag. Reconcile stops auto-removing devices. `async_remove_config_entry_device` allows removal only for cameras absent from the inventory.

## Boundaries & Constraints

**Always:**
- **Poll failures:** when `_async_reconcile` or `_async_poll_light_status` catches a `SecuritySpyError` (auth included) or an unexpected `Exception`, set `self.last_update_success = False` and call `self.async_update_listeners()` only if it was True. Keep the existing logging and auth counting. Success keeps going through `async_set_updated_data`, which restores True. The registry-sync failure guard in `_async_reconcile` is unchanged, because the server did answer.
- **Shared base:** a new `SecuritySpyEntity(CoordinatorEntity)` in `entity.py` is the only place `available` is defined.
  - Hub and camera entities are available iff `super().available`, and additionally `coordinator.stream_connected` when the class attribute `_attr_push_derived` is True. It defaults to False.
  - `SecuritySpyCameraEntity` also requires two things:
    - `camera_number in coordinator.data.server.cameras`
    - The camera is online: `camera_statuses[n].online` when a status exists, otherwise `server.cameras[n].connected`.
  - `SecuritySpyHubEntity` and `SecuritySpyCameraEntity` subclass `SecuritySpyEntity`.
- **Stream health:** the coordinator gains `stream_connected: bool` (initially False, since no stream is wired yet; Story 3.2 wires it) and `@callback async_set_stream_connected(connected: bool)`, which updates listeners only on change.
- **Device registry:** `_sync_device_registry` still creates or updates the hub and every inventoried camera, including self-healing recreation, but never removes devices.
- **Manual removal:** `__init__.py` gains `async_remove_config_entry_device(hass, entry, device_entry) -> bool`. It returns True only when all of these hold:
  - The entry is loaded (`entry.state is ConfigEntryState.LOADED`).
  - The device has a `(DOMAIN, f"{uuid}_{n}")` identifier (reuse `SecuritySpyDataUpdateCoordinator._camera_number_for`).
  - `n not in coordinator.data.server.cameras`.
  
  It returns False for the hub, for present-but-offline cameras, and for unknown devices.
- **Docstrings:** update the module docstrings in `entity.py` and `coordinator.py` that say availability or stream health is "Epic 3's addition".

**Block If:**
- HA's `CoordinatorEntity`/`DataUpdateCoordinator` in the pinned HA version does not let `last_update_success` be set this way, or making it work needs a library change.

**Never:**
- Overriding `available` in `camera.py`, `sensor.py`, or `update.py`.
- Wiring the event stream, adding reconnect/backoff, or changing log levels (Stories 3.2 and 3.3).
- Distinguishing disabled, deleted, and de-permissioned cameras.
- Adding entities for cameras that appear without a reload.
- Raising repairs for an offline camera.
- Changing the auth counter semantics.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Server unreachable | Light poll or reconcile raises `SecuritySpyConnectionError` | Every hub and camera entity is unavailable | Next success restores availability |
| Unexpected poll error | Light poll raises `RuntimeError` | All entities unavailable | Logged via existing `exception` |
| Camera offline | Status `online=False` for cam 1 only | Cam 1 entities unavailable; hub and cam 2 available | Not an error, no repair |
| No status yet | Empty `camera_statuses`, `Camera.connected=False` | That camera unavailable | — |
| Camera leaves inventory | Reconcile returns server without cam 2 | Cam 2 entities unavailable; its device stays in the registry | — |
| Remove absent camera device | Loaded entry, device for cam 2 not in inventory | `async_remove_config_entry_device` returns True | — |
| Remove present or hub device | Offline cam 1, or the hub | Returns False | — |
| Stream down | `stream_connected=False`, polls OK | Poll-derived entities available; a push-derived test entity is unavailable, and becomes available after `async_set_stream_connected(True)` | — |

</intent-contract>

## Code Map

- `custom_components/securityspy/entity.py` -- base entities; new `SecuritySpyEntity` holds all availability.
- `custom_components/securityspy/coordinator.py` -- poll failure handlers, `_sync_device_registry` removal loop, `_camera_number_for`, new stream flag.
- `custom_components/securityspy/__init__.py` -- add `async_remove_config_entry_device`.
- `custom_components/securityspy/camera.py`, `sensor.py`, `update.py` -- platform classes; must not override `available`.
- `tests/conftest.py` -- `make_camera`, `make_camera_status`, `make_server_info_with_cameras`, `mock_client`.
- `tests/test_coordinator.py` -- registry tests `test_reconcile_removes_a_camera_device` and `test_reconcile_removes_a_device_with_no_recognisable_camera_identifier` currently assert auto-removal.

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/coordinator.py` -- mark poll failure (transition-only listener update); add `stream_connected` and `async_set_stream_connected`; remove the stale-device removal loop; update docstrings -- layers 1, 3, 4.
- [x] `custom_components/securityspy/entity.py` -- add `SecuritySpyEntity` with `_attr_push_derived` and the layered `available`; rebase hub/camera bases; camera base adds inventory + online checks -- single availability implementation.
- [x] `custom_components/securityspy/__init__.py` -- add `async_remove_config_entry_device` per constraints -- Gold `stale-devices` pattern.
- [x] `tests/test_coordinator.py` -- replace the two auto-removal tests with "device is kept" tests; add stream-flag change/no-op listener tests.
- [x] `tests/test_entity_availability.py` (new) -- cover every I/O matrix row through a real entry setup with the mocked client and `async_fire_time_changed`, checking entity `state == STATE_UNAVAILABLE`. Define the push-derived test entity by subclassing a camera sensor with `_attr_push_derived = True`. Assert no class in `camera`/`sensor`/`update` defines `available` in its own `__dict__`.
- [x] `tests/test_init.py` -- `async_remove_config_entry_device` True for an absent camera, False for the hub, a present offline camera, and an unloaded entry.

**Acceptance Criteria:**
- Given a server that was unreachable and then answers again, when the next poll succeeds, then all entities return to available without reload.
- Given the full test suite, lint, format and mypy, when run, then all pass.

## Verification

**Commands:**
- `uv run pytest -q` -- expected: all pass
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean
- `uv run mypy custom_components tests` -- expected: no errors
## Review Triage Log

### 2026-09-14 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 1, low 2)
- defer: 2: (high 0, medium 1, low 1)
- reject: 13: (high 0, medium 3, low 10)
- addressed_findings:
  - `[medium]` `[patch]` `async_remove_config_entry_device` judged removal against a stale inventory during an outage; now refuses while `last_update_success` is False (test added).
  - `[low]` `[patch]` `_camera_number_for` docstring claimed `None` only for the hub, which no longer holds once reconcile keeps devices; reworded.
  - `[low]` `[patch]` The no-override guard hard-coded three platform modules; it now asserts the list matches `PLATFORMS`.

## Auto Run Result

**Summary:** Entities now report unavailable instead of stale values, with the logic in one shared base class (`SecuritySpyEntity`).
- Any poll failure marks the whole entry unavailable.
- A camera device is unavailable when it is offline (light-poll `online`, falling back to `Camera.connected`) or missing from the inventory.
- Push-derived entities are also gated on a new `coordinator.stream_connected` flag, set through `async_set_stream_connected`.
- Reconcile no longer removes devices. `async_remove_config_entry_device` allows deletion only of camera devices absent from a freshly polled inventory.

**Files changed:**
- `custom_components/securityspy/entity.py` -- `SecuritySpyEntity` with layered `available`; hub/camera bases rebased.
- `custom_components/securityspy/coordinator.py` -- poll-failure marking (transition-only notify), stream-health flag, reconcile catches unexpected errors, no auto-removal.
- `custom_components/securityspy/__init__.py` -- `async_remove_config_entry_device`.
- `tests/test_entity_availability.py` (new) -- I/O matrix, push-derived variant, no-override guard.
- `tests/test_coordinator.py`, `tests/test_init.py`, `tests/test_sensor.py` -- keep-device, stream flag, removal, stale-sensor-becomes-unavailable tests.

**Review:** 3 patches applied, 2 deferred (heavy-poll failure masked by light-poll success; unparseable or foreign-UUID devices can no longer be removed), 13 rejected. Several rejects fall to later Epic 3 stories: log-when-unavailable (3.3), stream flag reset and wiring (3.2/3.4).

**Verification:**
- `uv run pytest -q`: 177 passed.
- `ruff check` and `ruff format --check`: clean.
- `mypy`: no issues.

**Residual risks:**
- A heavy `++systemInfo` outage while `++camStatus` still succeeds leaves inventory-derived data stale but available (deferred).
- `stream_connected` stays False until Story 3.2 wires the stream, so no push-derived entities exist yet.
