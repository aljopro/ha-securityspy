# Epic 2 Context: Connect and Model

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

This epic makes the integration exist for a user for the first time: they add their SecuritySpy server entirely through the Home Assistant UI — over HTTP or HTTPS, with a certificate-verification toggle for the common LAN-IP/dynamic-DNS certificate mismatch — and their cameras appear immediately as correctly-named devices beneath a single server hub, with no manual renaming and nothing named after an IP address. Only entities the configured SecuritySpy account is actually permitted to use are created, and credentials can be repaired or connection details changed later without orphaning devices, entities, or recorded history. It matters disproportionately because this is where the permanent identity scheme, the single coordinator, the typed coordinator data container, and the exception-mapping seam are established — decisions that cannot be revised later without destroying every customization a user has built on top of them.

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

- Setup is UI-only; no YAML at any point. Credentials are validated against the live server before a config entry is created, and each failure class (unreachable host, bad credentials, unsupported SecuritySpy version) gets its own distinct, translated, actionable message with the form redisplayed rather than aborted.
- A minimum supported SecuritySpy version is declared and enforced at setup, failing clearly rather than misbehaving. A minimum Home Assistant version is likewise declared.
- Re-adding an already-configured server, by any address that resolves to it, aborts as already configured.
- Certificate verification defaults to on; disabling it is an explicit user choice whose consequence is stated in the UI, and the choice persists with the entry and applies to every connection including the event stream.
- Naming and identity are treated as permanent — changing them later orphans user customizations. Renames on the server update device names without changing any entity ID or unique ID; address changes create no duplicates; cameras added or removed on the server reconcile without a reload.
- Only entities the configured account can use are created. Omissions raise a repair issue naming the missing permission, the cameras affected, and where in SecuritySpy to grant it; granting it and reloading creates the entities and clears the issue.
- Reauthentication fires only after three *consecutive* auth failures counted across both the polling and streaming paths together; any success resets the counter. Reauth and reconfigure both preserve devices, entities, and history, and both reject credentials/details pointing at a *different* server rather than silently repointing the entry.
- Health values are diagnostic-categorized, never primary controls, and health polling prefers the cheap status endpoint over the heavy one except where a value requires it (roughly 800 B vs 27 KB per call). Polling cost must scale sanely with camera count.
- Running alongside an existing ONVIF setup is the expected topology: installation must leave it working and untouched.
- The integration must never assume it is SecuritySpy's only client; server-side state is truth.
- Credentials never appear in logs, exception messages, or diagnostics; settings payloads are never logged at any level.
- The config flow module carries 100% test coverage, including every abort and error path.
- Reference validation: eleven cameras on the reference system with zero manual renaming, and an untouched ONVIF setup. More entities is not better — every entity must answer a question a user actually asks.

## Technical Decisions

- **Identity (permanent, non-negotiable):** hub device identified by the server UUID with service entry type; camera devices identified by server UUID plus camera number, linked to the hub as parent. Entity unique IDs combine server UUID, camera number, and a stable snake_case entity key; hub entity keys are a reserved namespace camera keys may not reuse. Config entry unique ID is the server UUID. Never hostname, IP, camera name, fabricated MAC, or device connections.
- **One coordinator per config entry**, push-fed with no update interval, updated via explicit set-updated-data calls. No entity performs its own I/O.
- **Coordinator data is a single frozen, fully-typed container** owned by the library's models: server state plus a camera map keyed by SecuritySpy camera number as `int` everywhere (never stringly-typed). The coordinator is its sole writer.
- **All protocol knowledge stays in the library.** The integration contains zero knowledge of wire formats, bitmasks, or endpoint URLs. Entity modules may import library types but never call library I/O.
- **One exception-mapping seam** in the adapter layer: library-typed errors map exactly once to not-ready (transient), auth-failure (per the shared counter), or permanent-error, all with translation keys.
- **One adapter-owned consecutive-auth-failure counter** fed by both planes; the library never counts, persists auth state, or initiates reauth.
- **Permission gating is one shared helper** consulted by every platform before creating an entity, evaluated per camera, applied once at setup. Later epics' platforms bind to this same helper.
- **HA runtime conventions:** typed config-entry alias plus runtime data (never the legacy hass-data dict); zero-parallel-updates constant in every platform module; entity descriptions with translation keys and icons in the icons file; local-push IoT class; live-video camera entities disabled by default; config entity category on user-facing controls and diagnostic category on health sensors; the update entity is read-only in v1 with no install action.
- **Device lifecycle follows the dynamic-devices and stale-devices patterns** from the start — cheap now, expensive to retrofit — without committing to that quality tier.
- Connection details and credentials live in config-entry data; tuning lives in options as a typed options dataclass consumed via an update listener without reload.
- Timestamps are timezone-aware UTC datetimes; absent means null, never epoch. Library models are frozen dataclasses; raw dicts never cross the library boundary.
- Stack: Python 3.14+, aiohttp with the caller-injected HA session, hatchling/`src` layout for the library, ruff and mypy on both repos, pytest with the HA custom-component test kit for the integration. CI runs hassfest plus the HA pylint plugin (the parallel-updates check moved to pylint) plus the HACS action and coverage.
- Two repositories: the library on PyPI, the integration as a HACS custom repository pinning the library as a versioned dependency in its manifest.

## Cross-Story Dependencies

- Depends on Epic 1's library for the authenticated client, typed exception hierarchy, permission decoding, and server metadata; nothing in this epic may re-implement those.
- **Health and update data are NOT yet in the library.** Stories 1.1–1.7 delivered no server health fields (CPU, memory pressure, certificate expiry), no offered-update version, no per-camera health counters (frame rate, data rate, last error), and no `++camStatus` client method. Story **1.8** adds all of them and is a hard prerequisite for **2.4** and **2.5** — neither may be dispatched before it is done. Do not work around this: the invariant below forbids the integration from decoding wire formats itself, so there is no legal HA-side substitute.
- Story 2.1 establishes the config entry, unique ID, and validation path that 2.2, 2.8, and 2.9 all extend; 2.3's identity scheme is a prerequisite for every entity-producing story here and in every later epic.
- Story 2.7's gating helper is the mechanism later epics (arming, capture images, the download action) must consult; this epic owns the mechanism and proves it only on the entities that exist now.
- The auth-failure counter in 2.8 spans both the poll path built here and the stream path built in Epic 3 — it must be designed to accept failures from both planes even before the stream exists.
- Epic 3 layers availability, backoff, and reconnect-driven reconciliation onto the coordinator and base entities created here; Epics 4–6 add platforms on top of this coordinator data container.
- Epic 7's release gating depends on CI scaffolding established here alongside Epic 1's.
