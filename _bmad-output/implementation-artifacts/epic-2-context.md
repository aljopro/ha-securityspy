# Epic 2 Context: Connect and Model

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A user adds their SecuritySpy server entirely through the Home Assistant UI, including over HTTPS with a certificate-verification toggle for the LAN-IP/dynamic-DNS mismatch. Their cameras then appear as correctly named devices under one server hub, with health diagnostics, an update-available signal, and credential-free live video. Only entities the account is allowed to use get created, and credential failures and address changes are handled without losing history. Nothing user-facing exists before this epic. It also fixes the identity scheme, which can never change afterwards without orphaning every user customization. Validated by eleven cameras needing zero manual renaming, and by live video working with credentials kept inside the library.

## Stories

- Story 2.1: Add a SecuritySpy server through the UI
- Story 2.2: Connect over HTTPS with a verification toggle
- Story 2.3: Cameras appear as devices under one server hub
- Story 2.4: See server and camera health
- Story 2.5: Know when a SecuritySpy update is available
- Story 2.6: Live video without exposing credentials
- Story 2.7: Only create entities the user is permitted to use
- Story 2.8: Re-enter credentials when they stop working
- Story 2.9: Change connection details without losing history

## Requirements & Constraints

- Setup is UI-only. Credentials are tested before any entry is created. Unreachable host, bad credentials, a certificate mismatch and an unsupported SecuritySpy version each get their own translated error, and the form keeps the values the user entered. A duplicate server aborts as already configured, whatever address was used to reach it. Config flow test coverage must be 100%, including every abort and error path.
- Certificate verification is on by default. The UI must state what turning it off means. The setting is stored with the entry and applies to every connection, including the event stream.
- Names come from SecuritySpy with no manual steps. No device may be named after an IP address or report manufacturer "Generic". Renames, host/IP/port changes and reconfiguration must not create duplicates or orphan anything.
- Cameras added or removed on the server add or remove devices without a reload (Gold dynamic-devices/stale-devices patterns, adopted now without committing to the Gold tier).
- Health polling uses the cheap status endpoint (`camStatus`, about 800 B). The heavy `systemInfo` endpoint (about 27 KB) is used only for values nothing else provides.
- The update entity is read-only in v1 and offers no install action.
- No credential may ever appear in logs (at any level), diagnostics, exception messages or stream URLs, including the password's base64 form. Settings payloads are never logged. Diagnostics go out only through the library anonymizer. Unknown fields count as identifying until shown otherwise.
- Must coexist with ONVIF/Generic Camera setups without touching them, and must not assume it is SecuritySpy's only client.
- A minimum SecuritySpy version (assumed 6.x; earliest sufficient release still unverified) and a minimum HA version (2026.3) are declared and enforced at setup with a clear message.
- Errors must separate transient failure, authentication failure and permanent incompatibility, so HA retries only what can be retried.
- No failure mode may require an HA restart.

## Technical Decisions

- **Layering:** the integration contains no SecuritySpy wire-format or endpoint knowledge. Entity modules may import library types but never call library I/O. Anything missing from the library gets fixed in `aiosecurityspy` first, released and pinned, then consumed here. No subclassing, wrapping or vendoring library behavior.
- **Coordinator:** one `DataUpdateCoordinator` per entry with `update_interval=None`, fed by `async_set_updated_data()`. Its data is the frozen, typed `SecuritySpyData` from the library, keyed by `int` camera number. The coordinator is the only writer.
- **Identity (permanent):** hub `identifiers={(DOMAIN, server_uuid)}` with `entry_type=SERVICE`. Camera `identifiers={(DOMAIN, f"{server_uuid}_{camera_number}")}` with `via_device` pointing at the hub. No `connections` and no MACs. Camera entity unique IDs are `f"{server_uuid}_{camera_number}_{entity_key}"`; hub entity unique IDs are `f"{server_uuid}_{entity_key}"`, and hub keys are a reserved namespace. Every entity uses `_attr_has_entity_name = True` and a `translation_key`. Config entry `unique_id = server_uuid`. Keys are snake_case and permanent once released.
- **Exception seam:** the library raises `SecuritySpyAuthError`, `SecuritySpyConnectError`, `SecuritySpyPermissionError` and `SecuritySpyUnsupportedVersionError`. The adapter maps them exactly once: `ConfigEntryAuthFailed` (driven by the auth counter), `ConfigEntryNotReady` for transient errors, `ConfigEntryError` for permanent ones, all with translation keys.
- **Auth escalation:** the adapter owns one consecutive-auth-failure counter shared by the poll and stream planes. Any authenticated success resets it. At 3 the adapter raises reauth and stops both planes; finishing reauth restarts them. The library never counts failures.
- **Permission vs. authentication:** a 401 from media endpoints can mean a permission denial with valid credentials, and must not feed the reauth counter as if the credentials were bad.
- **Inventory:** `systemInfo` is the permission-scoped inventory of record. `camStatus` is not scoped and lists every camera, so it must never decide membership. Its health rows are intersected with the `systemInfo` set, never unioned. A camera missing from the inventory makes its device's entities unavailable but does not auto-remove the device. `async_remove_config_entry_device` returns True only for cameras absent from the current inventory.
- **Permission gating:** per-camera permissions are decoded by the library into named capabilities on coordinator data. A single shared gating helper runs at setup and every platform (including later epics) must consult it. Omitted entities raise a repair issue that names the missing permission, the affected cameras and where to grant it in SecuritySpy. The issue clears after the permission is granted and the entry reloaded.
- **Live video:** camera entities are enabled by default and exist only while the `create_camera_entities` option is on. Turning it off removes them and stops the relay handing out their addresses; turning it back on restores the original unique IDs. The stream source is a library RTSP relay address (`rtsp://<bind>:<port>/<random id>`), and the credentialed `auth=` value is built only inside the relay. The still image comes from the library's `async_get_camera_image(server_info, camera_number, width=, quality=)`, which hits the snapshot endpoint with header auth (never a frame from the stream). It refuses cameras not in the visible inventory with `SecuritySpyPermissionError`, and a media 401 there may be a permission denial. No stream opens until one is requested.
- **Runtime conventions:** typed `SecuritySpyConfigEntry` with `entry.runtime_data`, never `hass.data[DOMAIN]`. `PARALLEL_UPDATES = 0` in every platform. `EntityCategory.DIAGNOSTIC` on health sensors. Icons go in `icons.json`. `iot_class: local_push`, with `appropriate-polling` exempted and a comment. Connection and credentials live in entry data, tuning in options. Timestamps are timezone-aware, and a missing value is `None`.
- **Availability:** computed only in the base entities (`entity.py`) from `SecuritySpyData`. Epic 3 fills this in; do not override `available` in platforms.
- **Module layout:** `__init__.py` (setup, exception mapping, auth counter), `coordinator.py`, `config_flow.py` (user/reauth/reconfigure steps plus options), `entity.py`, `diagnostics.py`, `repairs.py`, and the `sensor`, `camera` and `update` platforms.
- **Stack/CI:** Python 3.14+, pytest with `pytest-homeassistant-custom-component`, ruff, mypy, hassfest plus the HA pylint plugin, HACS Action. The library is pinned in `manifest.json`.

## Cross-Story Dependencies

- Story 2.1's flow and exception mapping are the base for 2.2 (HTTPS toggle), 2.8 (reauth step) and 2.9 (reconfigure). Reauth and reconfigure must both reject credentials or addresses that point at a different server UUID.
- Story 2.3 (devices, identity, base entities) must land before 2.4, 2.5, 2.6 and 2.7 can attach entities.
- Story 2.6 depends on library Stories 1.19 (RTSP relay) and 1.20 (`async_get_camera_image` still image); both must be released and pinned first. Stories 2.4 and 2.5 depend on library Story 1.8 (health decoding). Library Stories 1.11, 1.14 and 1.18 cover permission-vs-auth errors and the scoped camera inventory.
- Story 2.7's gating helper binds the later platforms in Epics 4 and 6 (arming, capture images, the download action). Its first proof is the live video entities from 2.6.
- The auth counter from 2.8 is fed by the stream's `auth_failed` callback, which Epic 3's resilience work relies on. Epic 3 also builds the availability layers on 2.3's base entities.
