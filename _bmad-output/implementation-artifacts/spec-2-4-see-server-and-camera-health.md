---
title: 'Story 2.4 — See server and camera health'
type: 'feature'
created: '2026-09-12'
status: 'done'
baseline_revision: '5a8ee08ea269d185cea4bb4ab841862c8ec6c73f'
final_revision: '26df01296858d059cf05b1b1410fd1d842b12c04'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** `PLATFORMS` is empty and `entity.py` has no `CoordinatorEntity` base class — a user who adds a server and sees devices (story 2.3) still has no way to notice a problem before it costs a recording: no CPU/memory/cert-expiry visibility on the hub, no per-camera frame rate, data rate, or last-error visibility.

**Approach:** Add the first sensor platform (`sensor.py`) plus the first `CoordinatorEntity` base classes in `entity.py`, sourcing hub-level values (CPU usage, memory pressure, camera count, cert expiry) and camera-level frame rate / data rate from the existing heavy `ServerInfo` the coordinator already fetches every `RECONCILE_INTERVAL`, and sourcing per-camera `last_error`/`last_error_description` from a new, faster light-endpoint poll (`async_refresh_camera_status`) added to the coordinator — because `last_error` is the one field both endpoints provide, and the epic requires preferring light where a value exists there.

## Boundaries & Constraints

**Always:**
- Every sensor is `entity_category=EntityCategory.DIAGNOSTIC`; none is a primary control.
- Hub sensors: `cpu_usage` (%), `memory_pressure` (%), `camera_count` (int), `cert_expiry_days` (int, may be negative — already-expired). Source: `coordinator.data.server` fields of the same name (already decoded by library story 1.8). No new library call for these — they ride the existing `RECONCILE_INTERVAL` (10 min) heavy poll.
- Per-camera sensors: `current_fps`, `data_rate` (both from `coordinator.data.server.cameras[number]`, heavy-poll-only, no light equivalent) and `last_error`/`last_error_description` as one sensor (native value = `last_error`, `last_error_description` as an extra state attribute) sourced from a **new** faster light poll.
- Add `SecuritySpyData` (frozen dataclass, integration-owned, `custom_components/securityspy/coordinator.py` or a new `models.py` — Code Map decides) wrapping `server: ServerInfo` and `camera_statuses: Mapping[int, CameraStatus]`; change `SecuritySpyDataUpdateCoordinator` to `DataUpdateCoordinator[SecuritySpyData]`. This is the wrapping-type moment story 2.3's Design Notes explicitly flagged for review — Epic 1's `visible_camera_views()` helper is not used here because it drops cameras absent from `CameraStatus`'s wider set, which would be permission-*filtering* logic this story does not own (that's story 2.7); this story's `CameraStatus` map is keyed by every camera number already in `server.cameras` (the account's permitted inventory), looked up by number, defaulting to `None` if a status poll hasn't completed yet or omits a camera.
- Add `LIGHT_POLL_INTERVAL: Final[timedelta] = timedelta(seconds=30)` to `const.py` for the new light poll, scheduled via `async_track_time_interval` exactly like `RECONCILE_INTERVAL`'s existing timer, registered through `entry.async_on_unload`. On success, merge the new `CameraStatus` tuple into `self.data` (replacing `camera_statuses`, keeping `server` from the last heavy fetch) and call `async_set_updated_data`. On `SecuritySpyError`, log once at `DEBUG` and return, exactly mirroring `_async_reconcile`'s existing failure handling — do not touch `self.data`.
- The existing heavy `_async_reconcile` timer, on success, must also refresh `self.data.server` while preserving the last-known `camera_statuses` (do not reset them to empty) — it already updates `self.data`; extend rather than replace its assignment.
- `SecuritySpySensorEntityDescription` (frozen, `kw_only=True`, extends `SensorEntityDescription`) with a `value_fn: Callable[[SecuritySpyData], ...]` for hub sensors and a per-camera equivalent taking `(SecuritySpyData, int)` (camera number) for camera sensors — built as tuples, one descriptor per field, per `docs/ha-integration-reference.md`'s AD-9 pattern. No copy-pasted per-field entity subclasses.
- `entity.py` gains `SecuritySpyHubEntity(CoordinatorEntity[SecuritySpyDataUpdateCoordinator])` and `SecuritySpyCameraEntity(CoordinatorEntity[SecuritySpyDataUpdateCoordinator])` base classes: `_attr_has_entity_name = True`, `_attr_device_info` built from the existing `hub_device_info`/`camera_device_info` functions (reused, not duplicated), unique IDs per the epic's permanent scheme (`f"{uuid}_{key}"` hub, `f"{uuid}_{camera_number}_{key}"` camera).
- A camera absent from `coordinator.data.server.cameras` at entity-setup time gets no sensor entities (mirrors 2.3's per-camera-device existence, not a new gating rule — story 2.7 owns permission gating specifically; this story only follows "no device, no entity").
- `PLATFORMS` gains `Platform.SENSOR`; `sensor.py` sets `PARALLEL_UPDATES = 0`.
- `None` values (e.g. `cpu_usage` unavailable, `last_error` absent) render as the sensor being unavailable-for-that-value via `native_value` returning `None` — HA's own convention, not a custom availability rule. Entity-level `available` still follows the base `CoordinatorEntity` behavior (whole coordinator success/failure), since per-camera availability layering is Epic 3's job.

**Block If:**
- Nothing found requiring human input — all fields, methods, and conventions already exist in the pinned `aiosecurityspy==0.2.0`; no library change or version bump needed.

**Never:**
- No entity-level custom availability logic (three/four-layer availability is Epic 3's `entity.py` addition, not this story's).
- No permission gating beyond "camera has a device" (2.7's job).
- No new coordinator write path outside the two existing timers (heavy reconcile, new light poll) — no entity performs its own I/O.
- No use of `visible_camera_views()` for filtering purposes (see Boundaries) — this story is not permission-scoped.
- No change to `config_flow.py`, `strings.json`/`translations/en.json` beyond the new sensors' translation keys, or to the device-registry sync logic in `coordinator.py` (untouched apart from the `SecuritySpyData` type change and the new timer).
- No install-action, update-entity, or live-video work (stories 2.5, 2.6).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Fresh setup | `server.cpu_usage=42.0`, camera has `current_fps=15.0` | Hub CPU sensor reads `42.0`; camera FPS sensor reads `15.0` | No error expected |
| Field not reported | `server.cert_expiry_days is None` | Sensor `native_value` is `None` (HA renders "unknown") | No error expected |
| Cert already expired | `server.cert_expiry_days=-3` | Sensor reads `-3` (not clamped, not hidden) | No error expected |
| Light poll succeeds | `async_get_camera_status()` returns fresh statuses | `last_error` sensor updates from the new light data; `current_fps`/`data_rate` unchanged (still last heavy value) | No error expected |
| Light poll fails transiently | `async_get_camera_status()` raises `SecuritySpyConnectError` | Logged once at `DEBUG`; `self.data` untouched; next scheduled attempt retries | No exception escapes the timer callback |
| Heavy poll succeeds after light poll | `_async_reconcile` fires | `self.data.server` refreshed; `self.data.camera_statuses` preserved from the last successful light poll, not reset | No error expected |
| Camera removed from inventory before light poll returns | Camera present when poll started, gone from `server.cameras` by the time it applies | That camera's status entry is dropped from `camera_statuses`; no orphaned sensor state, no crash (device removal already handled by 2.3's reconcile) | No error expected |
| Zero cameras | `server.cameras` is empty | Hub sensors created; no per-camera sensors; setup succeeds | No error expected |

</intent-contract>

## Code Map

- `custom_components/securityspy/coordinator.py` — added `SecuritySpyData` (frozen dataclass wrapping `server`/`camera_statuses`, kept in this file rather than a new `models.py`: it stayed small enough not to warrant the split), retyped `SecuritySpyDataUpdateCoordinator` to `DataUpdateCoordinator[SecuritySpyData]`, added the `LIGHT_POLL_INTERVAL` timer + `_async_poll_light_status()`, extended `_async_reconcile()` to preserve (and prune, via `_pruned_statuses()`) `camera_statuses` across heavy refreshes. Review pass 1 patched `_async_poll_light_status` to also prune against the current inventory (mirroring `_pruned_statuses`), wrap both write paths' `camera_statuses` in `MappingProxyType`, and catch unexpected (non-`SecuritySpyError`) exceptions the same way `_async_reconcile` already does.
- `custom_components/securityspy/const.py` — added `LIGHT_POLL_INTERVAL: Final[timedelta] = timedelta(seconds=30)`.
- `custom_components/securityspy/entity.py` — added `SecuritySpyHubEntity` / `SecuritySpyCameraEntity` `CoordinatorEntity` base classes, reusing existing `hub_device_info`/`camera_device_info`.
- `custom_components/securityspy/sensor.py` — **new file.** `SecuritySpyHubSensorEntityDescription` and `SecuritySpyCameraSensorEntityDescription` (two variants per the Boundaries: one `value_fn(data)`, one `value_fn(data, camera_number)`), `HUB_SENSORS`/`CAMERA_SENSORS` tuples, `SecuritySpyHubSensor`/`SecuritySpyCameraSensor` generic entity classes, `async_setup_entry` building hub sensors + per-camera sensors from `coordinator.data.server.cameras`, `PARALLEL_UPDATES = 0`.
- `custom_components/securityspy/__init__.py` — added `Platform.SENSOR` to `PLATFORMS`.
- `custom_components/securityspy/strings.json` / `translations/en.json` — added an `entity.sensor.*` block with a `name` for each of the seven new sensors' `translation_key`s.
- `custom_components/securityspy/icons.json` — **new file.** Icons for the seven new sensors (cpu/memory/cctv/certificate/filmstrip/network/alert icons).
- `tests/conftest.py` — extended `make_server_info` (`cpu_usage`, `memory_pressure`, `cert_expiry_days`) and `make_camera` (`current_fps`, `data_rate`, `last_error`, `last_error_description`) with `None`-default kwargs; added `make_camera_status()` builder; added a `mock_client.async_get_camera_status` stub returning `()` by default.
- `tests/test_sensor.py` — **new file.** One test per I/O-matrix row plus entity-setup/unique-ID/device-linkage/diagnostic-category assertions.
- `tests/test_coordinator.py` — extended with light-poll-timer tests (scheduled, cancelled on unload, transient-failure handling, merges fresh statuses, preserves `camera_statuses` across heavy refresh, prunes a removed camera's status); updated pre-existing `coordinator.data` assertions to `coordinator.data.server` for the new wrapper shape.

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/coordinator.py` — introduce `SecuritySpyData`, retype the coordinator, add the light-poll timer and its handler, extend `_async_reconcile` to preserve `camera_statuses`.
- [x] `custom_components/securityspy/const.py` — add `LIGHT_POLL_INTERVAL = timedelta(seconds=30)`.
- [x] `custom_components/securityspy/entity.py` — add `SecuritySpyHubEntity`/`SecuritySpyCameraEntity` base classes.
- [x] `custom_components/securityspy/sensor.py` — implement hub + per-camera sensor descriptions and `async_setup_entry`.
- [x] `custom_components/securityspy/__init__.py` — add `Platform.SENSOR` to `PLATFORMS`.
- [x] `custom_components/securityspy/strings.json`, `translations/en.json`, `icons.json` — add entries for every new sensor.
- [x] `tests/conftest.py` — extend fixtures/builders per Code Map.
- [x] `tests/test_sensor.py` — cover every I/O-matrix row, unique IDs, device linkage, `EntityCategory.DIAGNOSTIC` on every sensor.
- [x] `tests/test_coordinator.py` — cover the new light-poll timer's scheduling, cancellation, failure handling, and data-merge behavior.

**Acceptance Criteria** (from epics.md Story 2.4):
- Given a configured server, when the hub device is viewed, then it exposes CPU usage, memory pressure, camera count, and certificate expiry, all diagnostic-categorized and absent from primary controls.
- Given a configured camera, when its device is viewed, then it exposes current frame rate, data rate, and last error, all diagnostic-categorized.
- Given the health polling cycle, when its requests are measured, then `last_error` is sourced from the light status endpoint on a faster cadence, and only CPU/memory/cert/fps/data-rate — values the light endpoint cannot provide — come from the heavy endpoint's existing cadence.

## Design Notes

**Why a new `SecuritySpyData` wrapper now, reversing 2.3's deferral.** Story 2.3 explicitly deferred wrapping `ServerInfo` because nothing yet needed a second data source alongside it. This story does: `last_error` must come from the light `CameraStatus` poll (per the epic's own "prefer light" requirement) while `current_fps`/`data_rate`/hub fields still only exist on the heavy `ServerInfo`. Coordinator data must hold both without diverging, so `SecuritySpyData{server, camera_statuses}` is the smallest wrapper that satisfies today's real need, not a speculative one.

**Why not `visible_camera_views()`.** That library helper intersects `CameraStatus` against `ServerInfo.cameras` for permission-boundary reasons — it silently drops any camera not already in the account's inventory. This story indexes `CameraStatus` by camera number directly instead, because the "which cameras get sensors" decision here is "the camera has a device" (2.3's job), not a permission decision (2.7's job); reusing the permission-scoped helper for a non-permission purpose would blur that ownership line.

**Why 30 seconds for `LIGHT_POLL_INTERVAL`.** No existing constant to reuse (unlike 2.3's 10-minute reuse of AD-10). Chosen as a reasonable "notice a stuck camera quickly" cadence for a ~800B request; flagged here as a tunable, not an architectural commitment — a later story may move this to options.

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` — expected: all tests pass, 100% coverage including `sensor.py` and the extended `coordinator.py`/`entity.py`.
- `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests` — expected: clean.
- `uv run mypy --strict custom_components/securityspy` — expected: clean.

**Manual checks (if no CLI):**
- After setup, Settings → Devices & Services → the hub device shows CPU/memory/camera-count/cert-expiry sensors under Diagnostic; a camera device shows frame-rate/data-rate/last-error sensors under Diagnostic.

## Spec Change Log

No `bad_spec` findings this run — nothing to log.

## Review Triage Log

### 2026-09-12 — Review pass 1
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 2, low 4)
- defer: 1: (high 0, medium 0, low 1)
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[medium]` `[patch]` `_async_poll_light_status` published `camera_statuses` unfiltered, so a status the light endpoint still reports for a camera the last heavy reconcile already dropped would linger up to `RECONCILE_INTERVAL` (10 min) before `_pruned_statuses` caught up — the spec's own stated invariant ("keyed by every camera number already in `server.cameras`") was only enforced on one of the two write paths. Fixed: the light poll now filters against `self.data.server.cameras` before publishing, same as the heavy path. New test: `test_light_poll_drops_a_status_for_a_camera_not_in_the_current_inventory`.
  - `[medium]` `[patch]` `_async_poll_light_status` only caught `SecuritySpyError`, unlike `_async_reconcile`'s established broad-except guard (added in story 2.3's own review pass 2 for exactly this reason) — an unmodelled exception from `client.async_get_camera_status()` would have escaped the timer callback uncaught. Added a matching `except Exception` (logs once at `ERROR`, returns without publishing). New test: `test_light_poll_survives_an_unexpected_failure`.
  - `[low]` `[patch]` `camera_statuses` was seeded as `MappingProxyType({})` but every subsequent write (`_async_poll_light_status`, `_pruned_statuses`) produced a plain mutable `dict`, silently dropping the read-only contract after the first update. Both write paths now wrap their result in `MappingProxyType`.
  - `[low]` `[patch]` `current_fps`/`cpu_usage`/`memory_pressure` sensors either had no unit at all or used a bare `"%"` string literal instead of `homeassistant.const.PERCENTAGE`. Added `native_unit_of_measurement="fps"` to `current_fps` and swapped both percentage sensors to the `PERCENTAGE` constant. `data_rate` deliberately stays unitless — the library's own `data_rate` docstring says the unit is undocumented by SecuritySpy and is carried through as-is; inventing one would be a guess.
  - `[low]` `[patch]` No test exercised more than one camera's sensor fan-out, so a bug only manifesting with multiple cameras (e.g. an off-by-one or accidental cross-camera de-duplication in `async_setup_entry`'s loop) would not have been caught. Added `test_multiple_cameras_each_get_their_own_full_set_of_sensors` (3 cameras, asserts per-camera sensor counts and global uniqueness).
  - `[low]` `[defer]` A camera added to the inventory after setup gets a device (story 2.3) but no sensor entities until reload — `sensor.py` has no coordinator-listener wiring to add entities for a camera that appears later. Real, but not a broken AC of this story (2.4's ACs only require sensors for a camera whose device already exists); logged to `deferred-work.md`.
  - `[low]` `[reject]` The Intent section's prose named the light-poll method as `async_refresh_camera_status`; the code (correctly) calls `async_get_camera_status`. Purely a documentation inaccuracy inside the read-only `<intent-contract>` with zero effect on any Boundaries/Tasks text or on the implementation — cosmetic, not fixed per the intent-contract's read-only rule.
  - `[low]` `[reject]` No `suggested_display_precision` on the float-valued sensors (`cpu_usage`, `memory_pressure`, `current_fps`, `data_rate`) — decoration; the library and HA both already round sensibly, no reported user-facing inconsistency.
  - `[low]` `[reject]` `_camera_last_error_attributes` always returns a `last_error_description` key even when `None` — harmless attribute noise, not a functional defect.
  - `[low]` `[reject]` Two tests infer "is this a camera sensor" from unique-ID string-shape rather than filtering against `CAMERA_SENSORS`/`HUB_SENSORS` directly — a test-style preference, not a functional gap; the string shape is exactly the spec's own permanent identity scheme (AD-5), unlikely to change silently.
  - `[low]` `[reject]` No test asserts `last_error`'s `state_class` is `None` — guards against a hypothetical future copy-paste regression with no current evidence of one; speculative.
  - `[low]` `[reject]` `SecuritySpyCameraEntity.__init__` indexes `server.cameras[camera_number]` without `.get()`/a defensive guard — the sole call site (`sensor.py`'s `async_setup_entry`) already only ever passes camera numbers known to be in `server.cameras`; matches this project's established "trust internal invariants" convention (same reasoning story 2.3's review applied to `_camera_number_for`).
  - `[low]` `[reject]` `_async_poll_light_status`'s `by_number` dict comprehension silently drops a duplicate camera number (last wins) with no logging — speculative, no evidence the library or SecuritySpy ever returns duplicate camera numbers in one `++camStatus` response.

## Auto Run Result

**What was implemented.** The full Tasks & Acceptance list above: `SecuritySpyData` (wrapping `server`/`camera_statuses`) added to `coordinator.py`; the coordinator retyped to `DataUpdateCoordinator[SecuritySpyData]`; a new `LIGHT_POLL_INTERVAL` (30s) timer polling `async_get_camera_status()` for `last_error`, alongside the existing 10-minute heavy `_async_reconcile` for CPU/memory/cert/fps/data-rate; `SecuritySpyHubEntity`/`SecuritySpyCameraEntity` `CoordinatorEntity` base classes added to `entity.py`; a new `sensor.py` platform with 4 hub sensors and 3 per-camera sensors, all `EntityCategory.DIAGNOSTIC`, built from `SecuritySpyHubSensorEntityDescription`/`SecuritySpyCameraSensorEntityDescription` tuples per AD-9; `Platform.SENSOR` added to `PLATFORMS`; translation keys, icons, and test fixtures/coverage added throughout.

**Files changed:**
- `custom_components/securityspy/coordinator.py` — `SecuritySpyData`, retyped coordinator, light-poll timer, pruning on both write paths.
- `custom_components/securityspy/const.py` — `LIGHT_POLL_INTERVAL`.
- `custom_components/securityspy/entity.py` — `SecuritySpyHubEntity`/`SecuritySpyCameraEntity`.
- `custom_components/securityspy/sensor.py` — new platform file.
- `custom_components/securityspy/__init__.py` — `Platform.SENSOR` added.
- `custom_components/securityspy/strings.json`, `translations/en.json`, `icons.json` — new sensor entries (`icons.json` is a new file).
- `tests/conftest.py`, `tests/test_sensor.py` (new), `tests/test_coordinator.py`, `tests/test_init.py` — fixtures and coverage for every I/O-matrix row plus the review pass's patches.
- `_bmad-output/implementation-artifacts/deferred-work.md` — one new entry (dynamic sensor addition for a post-setup camera).

**Review findings breakdown:** 14 total findings from Blind Hunter + Edge Case Hunter, deduplicated. 6 patched directly (2 medium: light-poll inventory pruning, light-poll broad-exception handling; 4 low: `MappingProxyType` consistency, sensor units, multi-camera fan-out test). 1 deferred (dynamic sensor addition for cameras added post-setup — real but out of this story's ACs). 7 rejected as cosmetic, speculative, or already-settled precedent (see Review Triage Log for the full list). No `intent_gap` or `bad_spec` — the spec itself needed no repair.

**Verification performed (all green after patches):**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100`: **86 passed**, **100.00%** coverage across all 6 modules.
- `uv run ruff check custom_components tests` / `uv run ruff format --check custom_components tests`: **clean**.
- `uv run mypy --strict custom_components/securityspy`: **clean**, 6 source files.

**Residual risks / follow-ups.**
- The deferred dynamic-sensor-addition gap (see `deferred-work.md`): a camera added after setup won't get sensors until reload. Low severity — the device still appears promptly via 2.3's own reconciliation, and a manual reload immediately backfills the sensors.
- Two independent timers (`LIGHT_POLL_INTERVAL` 30s, `RECONCILE_INTERVAL` 10min) both call `async_set_updated_data` independently; an interleaving where the light poll's publish immediately follows and is followed by a heavy reconcile's publish was reviewed and found self-correcting within one more cycle of either timer (worst case ~30s), not a data-loss risk — not fixed as a distinct patch, but worth naming here since it's a real (if narrow) timing subtlety in a piece of shared coordinator state every future health-consuming story will build on.
