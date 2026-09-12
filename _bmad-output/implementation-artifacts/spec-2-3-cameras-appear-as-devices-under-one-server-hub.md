---
title: 'Story 2.3 — Cameras appear as devices under one server hub'
type: 'feature'
created: '2026-09-12'
status: 'ready-for-dev'
baseline_revision: 'b6f530911e09015378eff2af7474d6fcaa63e63e'
final_revision: ''
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** Stories 2.1 and 2.2 can create and validate a config entry, but `PLATFORMS` is empty and no device or entity of any kind exists yet. A user who adds their server sees a config entry and nothing else — eleven cameras stay invisible. This is also the story every later Epic-2 story is blocked on: 2.4's health sensors, 2.5's update entity, 2.6's camera stream, and 2.7's permission gating are all written against a hub device, per-camera devices, and a coordinator that this story alone creates (confirmed by the halted 2.4 auto-dev run, which refused to invent this scope itself).

**Approach:** Add the coordinator (`coordinator.py`) and the entity base module (`entity.py`) the architecture names as the two permanent seams (AD-4, AD-5), and use them to register exactly one hub device and one device per inventoried camera through the device registry — directly, with no platform entity yet, since no per-camera data worth exposing as an entity exists until story 2.4. The coordinator also owns a slow periodic re-fetch of `async_get_server_info()` so camera renames, additions, and removals reconcile without a manual reload, which the epic's acceptance criteria require even before Epic 3's push stream exists.

## Boundaries & Constraints

**Always:**
- Identity is exactly AD-5, verified against `ARCHITECTURE-SPINE.md`: hub `identifiers={(DOMAIN, server.uuid)}`, `entry_type=DeviceEntryType.SERVICE`; camera `identifiers={(DOMAIN, f"{server.uuid}_{camera.number}")}`, `via_device=(DOMAIN, server.uuid)`. Never hostname, IP, camera name, or a fabricated MAC; `connections` is never populated.
- `server.uuid` and `camera.number` are the only two facts identity may depend on. Both already exist on `entry.runtime_data.server` (`ServerInfo`, from `async_get_server_info()` in `__init__.py`) — no new library call is added for identity.
- Exactly one hub device, and exactly one camera device per entry in `server.cameras` (a `Mapping[int, Camera]`, already includes every camera the account's inventory call returns) — **not** filtered by `camera.enabled` or by permission. Permission-based *entity* gating is story 2.7's job and does not apply to devices; the AC for this story tests device existence only.
- The coordinator (`SecuritySpyDataUpdateCoordinator(DataUpdateCoordinator[ServerInfo])`) is constructed with `update_interval=None` (AD-4) — the only interval-driven behavior this story adds is a self-scheduled reconciliation timer via `async_track_time_interval`, started explicitly by the coordinator itself, never the base class's own polling.
- One coordinator per config entry (AD-4), stored on `entry.runtime_data` alongside the existing `client` (extend `SecuritySpyRuntimeData`, do not replace it — 2.1/2.2 already rely on `.client` and `.server`).
- Device registration and reconciliation run once at startup (from `async_setup_entry`, before `async_forward_entry_setups`) and on every subsequent scheduled re-fetch — never inside an entity, since no entity performs its own I/O (AD-4).
- A camera renamed on the server updates the device's `name` via `device_registry.async_update_device()` on the next reconciliation; its device `id`, its `identifiers`, and (once they exist) any entity `unique_id` are untouched.
- A camera added to the inventory gets a new device on the next reconciliation; a camera removed from the inventory gets its device removed via `device_registry.async_remove_device()` — device removal must not touch the hub or any other camera's device.
- `entity.py` is introduced now, exporting the pure `hub_device_info(server) -> DeviceInfo` and `camera_device_info(server, camera) -> DeviceInfo` builder functions AD-5 requires, so the coordinator and every future platform module compute identity from one place. No entity *class* exists yet — that starts in 2.4 — but the module and its two functions must exist under this name for `common-modules` (Bronze) to be satisfiable when platforms do arrive, and so the identity computation is written exactly once.
- `manufacturer="Ben Software"` and `sw_version=server.version` on the hub; the camera device carries no `sw_version` (SecuritySpy does not report one per camera) and no `model` (the library's `Camera` model has no model field — do not invent one).
- Diagnostic and Repair conventions untouched by this story: no options flow, no repair issue, no diagnostics platform change (`diagnostics.py` does not exist yet and is out of scope).

**Block If:**
- Nothing new is blocked; everything this story needs (`ServerInfo.uuid`, `ServerInfo.cameras`, `Camera.number`, `Camera.name`) already ships in `aiosecurityspy` (stories 1.12, 1.18).

**Never:**
- No platform module (`sensor.py`, `binary_sensor.py`, etc.) and no `Platform` entry added to `PLATFORMS` — there is no per-camera data yet worth exposing as an entity (health is 2.4, the update entity is 2.5, live video is 2.6). Devices with zero entities are a supported, documented Home Assistant pattern (`device_registry.async_get_or_create` does not require an entity to exist) and are exactly what this story's AC asks for.
- No permission gating (2.7), no reauth or auth-failure counter (2.8, already partially covered by 2.1's error mapping — untouched here), no reconfigure flow (2.9).
- No use of the library's event stream — it does not exist yet (Epic 3). The reconciliation timer this story adds is a stand-in the stream will eventually make redundant for the "no reload needed" AC; do not attempt to build stream-driven reconciliation here.
- No change to `config_flow.py` or to any `strings.json`/`translations/en.json` key — this story has no new user-facing flow surface.
- No `SecuritySpyData` typed container in the library. `ServerInfo` already satisfies what AD-15 asks of the coordinator's data at this stage — a frozen, fully-typed container with `cameras: Mapping[int, Camera]` keyed by `int`. Introducing a wrapping library type before a later epic actually needs additional fields (episodes, latest capture, control state) would be speculative; extending or wrapping `ServerInfo` when that need arrives is cheap. Flagged as a design decision for review, not settled by the epic context.
- No `async_get_or_create` call outside the coordinator. Only the coordinator writes to the device registry, mirroring "the coordinator is the sole writer" even though there is no `SecuritySpyData` write happening yet — the invariant is about I/O ownership, not the specific method name.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Fresh setup, N cameras | `server.cameras` has N entries | Exactly 1 hub device (`entry_type=SERVICE`) + N camera devices, each `via_device` the hub | No error expected |
| Zero cameras | `server.cameras` is empty | Hub device only; no camera devices; setup still succeeds | No error expected |
| Camera renamed on the server | Next reconciliation sees a new `camera.name` for an existing `camera.number` | Device `name` updates | No error; device `id`/`identifiers` unchanged |
| Camera added on the server | Next reconciliation sees a `camera.number` not yet in the device registry for this entry | New camera device created, `via_device` the hub | No error expected |
| Camera removed on the server | Next reconciliation no longer sees a previously-known `camera.number` | That camera's device is removed; hub and other camera devices untouched | No error expected |
| Host/IP/port changed, same server | Config entry reloaded (2.9 territory, but must not regress here) | No duplicate hub or camera devices — identity keys off `server.uuid`/`camera.number` only | No error expected |
| Reconciliation poll fails transiently | `async_get_server_info()` raises `SecuritySpyConnectError` on a scheduled re-fetch | Device registry is left as-is; failure logged once at `DEBUG`; the *next* scheduled attempt retries | No exception escapes the timer callback; nothing crashes the event loop |
| Reconciliation poll fails permanently | `async_get_server_info()` raises `SecuritySpyAuthError`/`SecuritySpyUnsupportedVersionError` on a scheduled re-fetch | Same as transient for *this story* — the auth-failure counter and reauth flow are story 2.8's job, not introduced here | Logged once at `DEBUG`; devices untouched |
| Unload | `async_unload_entry` runs | The reconciliation timer is cancelled; devices are **not** removed (Home Assistant's own config-entry removal handles that) | No leaked timer (FR-33) |

</intent-contract>

## Code Map

- `custom_components/securityspy/__init__.py` — `async_setup_entry()` currently builds `client`, calls `async_get_server_info()`, and sets `entry.runtime_data = SecuritySpyRuntimeData(client=client, server=server)` (lines ~117-197 as of this baseline). This story adds coordinator construction and the first device-registry sync **after** that assignment and **before** `await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)` (`PLATFORMS` stays `[]`). `async_unload_entry()` must cancel the coordinator's reconciliation timer.
- `custom_components/securityspy/coordinator.py` — **new file.** `SecuritySpyDataUpdateCoordinator(DataUpdateCoordinator[ServerInfo])`; owns the device-registry sync and the reconciliation timer. Update the module docstring in `__init__.py` (it currently says "No coordinator, platform or entity exists yet — `PLATFORMS` is deliberately empty until story 2.3 introduces them") to describe the post-2.3 state accurately: coordinator and `entity.py` exist, `PLATFORMS` remains empty until 2.4.
- `custom_components/securityspy/entity.py` — **new file.** `hub_device_info(server: ServerInfo) -> DeviceInfo` and `camera_device_info(server: ServerInfo, camera: Camera) -> DeviceInfo` per AD-5. Pure functions, no HA I/O, no entity classes yet.
- `custom_components/securityspy/const.py` — add a `RECONCILE_INTERVAL` constant (`timedelta`, see Design Notes for the value and its source) so the interval is named once and importable by tests.
- `homeassistant.helpers.device_registry` — new dependency for this module: `async_get(hass)`, `async_get_or_create(config_entry_id=entry.entry_id, identifiers=..., ...)`, `async_update_device(device_id, name=...)`, `async_remove_device(device_id)`. Look these up against the installed `homeassistant` package's `helpers/device_registry.py` before writing calls — do not guess the current signature from memory.
- `docs/ha-integration-reference.md` §§2-4 — the target end-state shapes for `SecuritySpyRuntimeData`, the coordinator, and `DeviceInfo` construction. That doc describes the *full* eventual coordinator (stream-fed, `SecuritySpyData`-typed); this story implements a deliberately smaller slice of it (no stream, `ServerInfo`-typed) and should not be over-built to match the doc's end state prematurely.
- `tests/conftest.py` — `MOCK_USER_INPUT`, `SERVER_UUID`, `SERVER_NAME` already exist; a fixture producing a `ServerInfo` with a small camera map (e.g. 2-3 `Camera` entries) is needed for coordinator/device tests and does not yet exist — check before adding a duplicate.
- `tests/test_init.py` — existing setup tests assert on `entry.runtime_data.client`/`.server`; extend rather than restructure. New coverage: coordinator is constructed and started, devices exist after setup, timer is cancelled on unload.
- `tests/test_coordinator.py` — **new file.** Device creation, rename, add, remove, and the two poll-failure rows from the I/O matrix.

## Tasks & Acceptance

**Execution:**
- [ ] `custom_components/securityspy/entity.py` — add `hub_device_info()` and `camera_device_info()`, both returning `homeassistant.helpers.device_registry.DeviceInfo` per the AD-5 identifiers/`via_device`/`entry_type` rules above. Pure, synchronous, fully typed, no imports beyond `homeassistant.helpers.device_registry` and `aiosecurityspy` model types.
- [ ] `custom_components/securityspy/const.py` — add `RECONCILE_INTERVAL: Final[timedelta]` (see Design Notes for the chosen value and rationale).
- [ ] `custom_components/securityspy/coordinator.py` — add `SecuritySpyDataUpdateCoordinator(DataUpdateCoordinator[ServerInfo])`:
  - `__init__(hass, entry, client, server)`: `super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)`; store `client`; set `self.data = server` via `async_set_updated_data` or direct assignment consistent with `DataUpdateCoordinator` semantics — confirm the correct way to seed initial data without triggering a listener callback with no listeners yet.
  - `async def async_start(self) -> None`: run one reconciliation immediately, then schedule the periodic re-fetch via `async_track_time_interval(self.hass, self._async_reconcile, RECONCILE_INTERVAL)`, registered through `entry.async_on_unload(...)` so cancellation is automatic on unload (do not hand-track the unsub callback).
  - `async def _async_reconcile(self, *_args) -> None`: call `self.client.async_get_server_info()`; on `SecuritySpyConnectError | SecuritySpyAuthError | SecuritySpyUnsupportedVersionError | SecuritySpyError`, log once at `DEBUG` (per the I/O matrix — this story does not escalate) and return without updating `self.data` or the registry. On success: `async_set_updated_data(new_server)`, then sync the device registry (create/rename/remove) by diffing `new_server.cameras` keys and names against the previous `self.data.cameras` (or against the registry's current camera devices for this entry — pick whichever is verifiably correct and covered by a test; document the choice).
  - A synchronous or async helper that performs the hub `async_get_or_create` once and the per-camera create/update/remove diff — extracted so it is unit-testable without going through the timer.
- [ ] `custom_components/securityspy/__init__.py` — in `async_setup_entry`, after `entry.runtime_data = SecuritySpyRuntimeData(...)` (extend the dataclass with `coordinator: SecuritySpyDataUpdateCoordinator`), construct the coordinator and `await coordinator.async_start()` before forwarding platform setups. In `async_unload_entry`, no explicit coordinator shutdown call should be needed if the timer unsub is registered via `entry.async_on_unload` — verify and add an explicit `async_shutdown()`/cancel only if `DataUpdateCoordinator` does not already tear down cleanly through unload alone.
- [ ] `custom_components/securityspy/__init__.py` docstring — correct the "no coordinator, platform or entity exists yet" claim to reflect what this story adds.
- [ ] `tests/conftest.py` — add a fixture building a small `ServerInfo` with 2+ `Camera` entries for coordinator/device tests, and a `device_registry` fixture per the HA test-kit convention if not already provided globally by the test harness.
- [ ] `tests/test_coordinator.py` — one test per I/O-matrix row: fresh setup device count, zero-camera setup, rename, add, remove, host-change non-duplication, transient poll failure, permanent poll failure (this story's failure handling, not 2.8's), timer cancelled on unload.
- [ ] `tests/test_init.py` — setup constructs and starts the coordinator; `entry.runtime_data.coordinator` is set; unload cancels the timer (assert via `async_track_time_interval`'s returned unsub being called, or equivalent).

**Acceptance Criteria** (from epics.md Story 2.3, restated as test targets):
- Given a configured server with N cameras, when setup completes, then exactly one hub device (`entry_type=SERVICE`) and N camera devices exist, each `via_device` the hub, each named from the server with zero manual renaming, and none named after an IP or reporting manufacturer "Generic".
- Given the created devices, when identifiers are inspected, then the hub is keyed by `server.uuid` and each camera by `server.uuid` + `camera.number`, never hostname/IP/name/MAC, and are stable across restarts (re-running setup with the same server produces the same device `id`s, not duplicates).
- Given a camera renamed on the server, when the coordinator next reconciles, then the device name updates and its `id`/`identifiers`/unique IDs (none exist yet, but the invariant must hold once they do) are unchanged.
- Given the server's host/IP/port changes, when the integration reconnects, then no duplicate devices are created.
- Given a camera added or removed on the server, when the coordinator next reconciles, then the corresponding device is added or removed without a manual reload.

## Design Notes

**Why direct `device_registry` calls instead of an entity.** `has_entity_name`/`DeviceInfo`-on-an-entity is the idiomatic way devices normally appear in Home Assistant, and every later platform in this project will use exactly that (see `docs/ha-integration-reference.md` §4). But no per-camera *data* worth exposing as an entity exists before story 2.4 (health) — inventing a placeholder entity (a name sensor, a presence binary sensor with no real signal) just to hang a device off it would be exactly the "more entities is not better" anti-pattern the epic context calls out, and it would need its own translation keys, `entity_category`, and disabled-by-default decision that no requirement asks for yet. `device_registry.async_get_or_create(config_entry_id=...)` creating a device with no entities is a supported, documented pattern for exactly this "device now, entity capability later" situation, and every field this story needs (`entry_type`, `identifiers`, `via_device`, `name`, `manufacturer`, `sw_version`) is available on `DeviceInfo`/the registry API independent of any entity.

**Why `ServerInfo` and not a new `SecuritySpyData` library type.** AD-15 (in the architecture spine, written with the full epic roadmap in view) describes an eventual coordinator container carrying Observation Records, Latest Capture, Detection Episodes, control state, and health per camera — none of which exist in the library yet. `ServerInfo` already is "one frozen, fully-typed container... server state plus a `Mapping[int, Camera]` keyed by camera number" for everything this story's coordinator needs. Introducing a wrapping type now, with fields for data that doesn't exist, would be speculative scaffolding built to a shape nobody can verify yet. The cost of composing/renaming later, when a real epic needs a field `ServerInfo` cannot hold, is small; the cost of guessing that shape now and being wrong is a rewrite either way. Flagged in Boundaries as a decision for review rather than settled fact, because the architecture doc is explicit that this container belongs in the library "from the start" — a reviewer with more context on the epic-4/5 timeline may reasonably override this.

**Why a self-scheduled reconciliation timer instead of waiting for Epic 3.** The epic's own acceptance criteria ("a camera added or removed... reconciles without requiring a reload") describe live reconciliation, but the push stream (Epic 3) and the caplist-driven reconciliation cycle (AD-10, Epics 4-5) don't exist yet. Without *some* scheduled re-fetch, "without a reload" cannot be satisfied honestly in this story — the only truthful alternative would be to narrow the AC to "on next reload," which is not what epics.md says. `RECONCILE_INTERVAL` reuses AD-10's own stated fallback-interval assumption (10 minutes) for consistency, since AD-10 documents that exact number as the intended slow-fallback cadence for this class of problem, even though AD-10 itself is scoped to Observation Records rather than device inventory. This mechanism is explicitly a stand-in: Epic 3's `reconnected` callback and AD-10's real reconciliation cycle will likely subsume or replace this timer, and that migration is out of scope here — noted for the epic-3 dispatch to pick up.

**Diff strategy: registry state vs. `self.data`.** Diffing `new_server.cameras` against the previous `self.data.cameras` is simpler and avoids reading the device registry as a source of truth for "what cameras did we already know about," but risks drifting from the registry if a device is ever deleted out-of-band (e.g. by a user manually removing it in the HA UI) — HA would not recreate it until the coordinator's own view changes. Diffing against the registry's actual current devices for this config entry is more defensive (self-healing) but couples the coordinator to registry-query patterns this codebase hasn't used before. Left as an implementation choice for the dev agent, with the constraint that whichever is chosen must be covered by a test proving a manually-deleted-then-still-present camera is *not* silently left missing forever (i.e. prefer the registry-diff approach unless a strong reason emerges during implementation; record the final choice in Completion Notes).

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` — expected: all tests pass, 100% coverage including the new `coordinator.py` and `entity.py` modules.
- `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests` — expected: clean.
- `uv run mypy --strict custom_components/securityspy` — expected: clean (note: `docs/ha-integration-reference.md`'s own coordinator snippet is not `--strict`-clean as written; do not copy it verbatim without adding types).
- `uv run python -m script.hassfest` or the project's equivalent hassfest CI step — expected: clean; confirms `coordinator.py`/`entity.py` satisfy `common-modules`.

**Manual checks (if no CLI):**
- After setup against a real or faked multi-camera server, the HA device registry (Settings → Devices & Services → the entry) shows one hub device and one device per camera, each linked via the hub as parent, with no device named after an IP and no manufacturer "Generic".
- Renaming a camera in SecuritySpy and waiting one reconciliation interval (or manually invoking the coordinator's reconcile method in a dev environment) updates the HA device name without changing its device page URL (i.e. its underlying `id`).

## Spec Change Log

## Review Triage Log

