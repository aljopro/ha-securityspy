# Epic 2 Context: Connect and Model

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A user adds their SecuritySpy server through the Home Assistant UI — over HTTP or HTTPS, with a verification toggle for a LAN-IP/certificate mismatch — and their cameras appear as correctly-named devices beneath one server hub, with zero manual renaming and no entity named after an IP address. Only controls the configured SecuritySpy account can actually use are created. This epic makes the identity, naming, and permission-gating decisions that can never change later without orphaning every customization a user has built, so it must land before any user-facing surface exists.

## Stories

- Story 2.1: Add a SecuritySpy server through the UI
- Story 2.2: Connect over HTTPS with a verification toggle
- Story 2.3: Cameras appear as devices under one server hub
- Story 2.4: See server and camera health
- Story 2.5: Know when a SecuritySpy update is available
- Story 2.6: Live video exists but stays out of the way
- Story 2.7: Only create entities the user is permitted to use
- Story 2.8: Re-enter credentials when they stop working
- Story 2.9: Change connection details without losing history

## Requirements & Constraints

- Setup happens entirely through the config flow UI; no YAML at any point. Credentials are validated against the live server before a config entry is created.
- The config entry's unique ID is the server UUID; adding an already-configured server (by any address that resolves to it) aborts rather than duplicating.
- Distinct, translated, actionable error messages are required per failure case (unreachable host, bad credentials, unsupported version), with the form redisplayed and entered values preserved rather than the flow aborting.
- Both HTTP and HTTPS must be selectable; a certificate-verification toggle, on by default, must state the consequence of disabling it, and persists with the entry for every subsequent connection including the event stream.
- Cameras become HA devices named and identified correctly with no manual intervention; a rename in SecuritySpy updates the HA device name without changing any entity ID, unique ID, or orphaning customizations.
- Server/host/port changes must never create duplicate devices or orphan entities. Cameras added or removed on the server must reconcile (add/remove the device) without a reload.
- Health values (CPU, memory pressure, camera count, certificate expiry, per-camera frame rate, data rate, last error) are diagnostic-only and must not appear among primary controls; health polling prefers the cheap status endpoint over the heavy one except for fields only the heavy endpoint provides.
- An update entity reports available/installed SecuritySpy versions but offers no install action (out of scope for v1).
- Live video entities exist per camera but ship disabled by default so an existing ONVIF setup is undisturbed; enabling one and reloading must produce working video.
- Entity creation is permission-gated through one shared gating helper that every platform (including later epics' arming, capture-image, and download entities) must consult — no platform invents its own rule. A missing capability that would omit an entity raises a repair issue naming the specific missing permission and the affected cameras, worded to tell the user where in SecuritySpy to grant it; granting it and reloading creates the previously-omitted entities and clears the issue.
- Reauthentication triggers only after three consecutive authentication failures counted across both the polling and streaming paths together; a transient failure or two, followed by success, resets the counter without starting reauth. A successful reauth must preserve devices, entities, and history, and must reject credentials for a different SecuritySpy server rather than silently repointing the entry.
- Reconfiguring connection details in place must validate before saving, preserve all devices/entities/history on success, and abort with a clear mismatch message (not orphan everything) if the new details point at a different server.
- Config flow test coverage target: 100%, including every abort and error path.

## Technical Decisions

- Layering: `custom_components/securityspy/` (adapter: `__init__`, `coordinator`, `config_flow`) owns lifecycle and maps library signals/exceptions to HA concepts; platform modules are thin declarative projections of coordinator data with no protocol knowledge or I/O of their own. All SecuritySpy wire-format knowledge stays in the `aiosecurityspy` library.
- One `DataUpdateCoordinator` per config entry, `update_interval=None`, fed via `async_set_updated_data()` from stream callbacks and scheduled polls. All entities read only the coordinator's data; no entity does its own I/O.
- Permanent identity scheme (never change without orphaning users): hub device `identifiers = {(DOMAIN, server_uuid)}`, `entry_type=SERVICE`; camera device `identifiers = {(DOMAIN, f"{server_uuid}_{camera_number}")}`, `via_device` → hub. Never hostname, IP, camera name, or a fabricated MAC; no `connections`. Entity unique IDs: `f"{server_uuid}_{camera_number}_{entity_key}"` (camera) / `f"{server_uuid}_{entity_key}"` (hub), with hub entity keys reserved from camera entity keys. `_attr_has_entity_name = True` plus a `translation_key` on every entity description. Config entry `unique_id = server_uuid`.
- Single exception-mapping seam: the library raises its own typed hierarchy (`SecuritySpyAuthError`, `SecuritySpyConnectError`, `SecuritySpyPermissionError`, `SecuritySpyUnsupportedVersionError`), never raw `aiohttp` errors. The adapter maps these exactly once to `ConfigEntryAuthFailed` (per the shared auth-failure counter), `ConfigEntryNotReady` (transient), or `ConfigEntryError` (permanent) — all with translation keys.
- One adapter-owned consecutive-auth-failure counter spans both the poll and stream planes; any authenticated success on either resets it; at 3 it raises `ConfigEntryAuthFailed` and stops both planes, and completing reauth restarts them. The library itself never counts or initiates reauth.
- Coordinator data is one frozen, fully-typed `SecuritySpyData` container (library-defined) with a `dict[int, CameraData]` keyed by camera number as `int` — never stringly-typed. The coordinator is the sole writer.
- Device/entity model follows Gold `dynamic-devices` / `stale-devices` patterns (cameras appearing/disappearing add/remove devices without reload) without committing to Gold tier overall.
- Permission→entity gating happens once at setup: no entity is created for a capability the configured user lacks; omissions raise repair issues. This is the mechanism story 2.7 owns; later epics' platforms are bound to reuse it.
- `EntityCategory.DIAGNOSTIC` on health sensors; the update entity is read-only. Camera (live video) entities set `entity_registry_enabled_default = False`.
- Typed `SecuritySpyConfigEntry` alias + `entry.runtime_data` (never `hass.data[DOMAIN]`); `PARALLEL_UPDATES = 0` in every platform module; icons in `icons.json`; `iot_class: local_push`.
- Config vs. options split: connection + credentials live in Config Entry data; tuning (thresholds, debounce, timeouts, lookback, per-camera overrides) lives in a typed options dataclass owned by `config_flow.py` and consumed by the coordinator via an update listener, without requiring reload.
- Three-layer availability (implemented once, in `entity.py`, never overridden by a platform): (1) server unreachable → whole entry unavailable; (2) single camera offline (status-poll connected flag) → only that camera's entities unavailable; (3) stream loss alone does not mark poll-derived entities unavailable (poll plane still holds truth), but push-derived entities go unavailable via a coordinator stream-health flag. A fourth layer (camera absent from the permission-scoped inventory — disabled, deleted, or de-permissioned) also makes that camera's entities unavailable; these causes are deliberately not distinguished from each other. The device is never auto-removed; `async_remove_config_entry_device` returns `True` only when the camera is absent from the current inventory, `False` otherwise, since HA's `stale-devices` pattern requires certainty the device is really gone.

## Cross-Story Dependencies

- Story 2.7's shared permission-gating helper is a hard dependency for entities added by Epic 4 (capture images, download action), Epic 5, and Epic 6 (arming) — those epics must consult it rather than invent their own gating.
- Story 2.3's identity scheme (hub/camera device identifiers, unique IDs) is permanent and is the foundation every later epic's entities are keyed against.
- Story 2.8's auth-failure counter and reauth flow depend on both the poll path (this epic) and the stream path (Epic 3); Epic 3 owns stream connection/reconnect logic that feeds the same counter.
- Story 2.4's health fields and Story 2.5's update-available signal depend on Epic 1 Story 1.8 (server/camera health decoding) already being available in the library.
- Story 2.1/2.9's config-flow validation and Story 2.7's entity gating depend on Epic 1's permission and version-check decoding (library Stories 1.2, 1.6, 1.11, 1.18).
- Epic 3 (Resilience) builds its three-layer/four-layer availability logic on the base entities this epic establishes in `entity.py`; Epic 3 must not duplicate or override it.
