# Epic 3 Context: Resilience

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

The Mac reboots at three in the morning and nobody has to do anything. When SecuritySpy goes away, entities report unavailable instead of showing stale values. The integration retries with backoff and keeps the log quiet while it does. When the server comes back, the integration reconnects and reconciles on its own, with no Home Assistant restart, reload, or re-authentication. Unload and reload leave nothing behind. This is what makes people keep an integration instead of uninstalling it, and it is the reliability the predecessor's users lost.

## Stories

- Story 3.1: Report unavailable rather than stale
- Story 3.2: Recover from connection loss without being asked
- Story 3.3: Log problems once, not continuously
- Story 3.4: Unload and reload cleanly

## Requirements & Constraints

- Entities go unavailable when their data can't be trusted. They never keep their last-known values.
- A single offline camera is an availability state, not an error that needs user action. Only that camera's device is affected. The hub and other cameras stay unaffected.
- No user-visible failure mode may require a Home Assistant restart.
- Stream loss is declared after 3 missed heartbeats (about 30 s), a bounded interval that must be documented. Reconnection uses exponential backoff with no attempt limit.
- It must work unattended after a SecuritySpy restart, a Mac reboot, a network drop, and a Home Assistant upgrade.
- Logging: log the loss once at ERROR and name the server. Log retries only at DEBUG. Log recovery once (WARNING). The once-only state resets for each loss/recovery cycle. A multi-hour outage produces a small, bounded number of non-debug lines. Never log payloads, and never log settings bodies at any level.
- Unload closes the event stream and cancels all polling. No task, connection, timer, or listener survives. Repeated unload/reload cycles leave nothing piling up. Removing an entry leaves nothing in the device or entity registries.
- These map to the Silver rules `entity-unavailable`, `log-when-unavailable`, and `config-entry-unloading`. Silver gates the public announcement, so coverage should be solid.
- Malformed or unexpected stream data should fall back to poll-derived state. It must not crash or wedge the integration. The stream is not vendor-tested.

## Technical Decisions

- **Two planes:** Every persistent value must be derivable from the capture-history/status poll plane. Push may only advance state that a poll would confirm. Hydrate from poll on startup and reconcile from poll on reconnect. The integration is never SecuritySpy's only client.
- **Availability in the shared base entities (`entity.py`), from `SecuritySpyData`.** Platforms never override `available`. There are four layers:
  1. Poll plane failing (server unreachable): every entity in the entry is unavailable.
  2. A camera's status-poll connected flag is false while the server responds: only that camera device is unavailable.
  3. Stream down: poll-derived entities stay available. The coordinator exposes a stream-health flag. A push-derived base-entity variant goes unavailable when that flag is down. Epic 5's presence entities adopt it, and this epic proves it with a test.
  4. Camera absent from the permission-scoped `++systemInfo` inventory (disabled, deleted, or de-permissioned; causes deliberately not distinguished): that camera device is unavailable. It is not auto-removed, and a reload simply doesn't create it. Implement `async_remove_config_entry_device` so it returns True only for a camera absent from the current inventory and False otherwise (the Gold `stale-devices` pattern).
- **Who owns what in the stream client:** The library's stream client owns CR framing, heartbeat watch, indefinite exponential backoff, and the explicit `connected` / `disconnected` / `reconnected` / `auth_failed` callbacks. On `auth_failed` it pauses reconnecting and hands off to the adapter. `disconnect()` is idempotent and cancels everything. The integration holds no reconnect or backoff logic of its own.
- **Adapter responsibilities:** Log discipline lives in the adapter, not the library. `reconnected` triggers a full reconciliation cycle. All reconciliation triggers go through a single scheduler in `coordinator.py`, and `__init__.py` only starts and stops it, so there is never a double fan-out.
- **Coordinator:** One `DataUpdateCoordinator` per config entry with `update_interval=None`, fed through `async_set_updated_data()`. It is the only writer of the frozen `SecuritySpyData` container, which is keyed by int camera number.
- **Auth:** One consecutive-auth-failure counter lives in the adapter and covers both planes. It escalates to reauth at 3. A transient outage must never look like an auth failure. Errors distinguish transient, auth, and incompatibility failures through the single exception-mapping seam.
- Protocol knowledge stays in `aiosecurityspy`, which is consumed as a pinned PyPI dependency. Library changes need a release or pre-release pin.

## Cross-Story Dependencies

- Builds on Epic 2's coordinator, data container, base entities, identity scheme, exception seam, and reauth counter (Story 2.8). It uses the library stream client from Story 1.3.
- 3.1 owns the stream-health flag and the push-derived entity variant. Epic 5's presence and motion entities consume them.
- 3.2 owns the reconnect-triggered reconciliation signal. Epic 4 (FR-3, missed-detection recovery) hangs off it.
- 3.3's log-once state follows the connection lifecycle that 3.2 establishes.
- 3.4's teardown must cover every task, listener, and timer that 3.1 to 3.3 add.
