---
name: ha-securityspy
type: architecture-spine
purpose: build-substrate
altitude: initiative
paradigm: 'layered client/adapter with two-plane data flow (lossy push + authoritative poll)'
scope: 'SecuritySpy HA integration + standalone aiosecurityspy library (greenfield, full system)'
status: final
created: '2026-08-09'
updated: '2026-08-09'
binds: [FR-1..FR-45]
sources:
  - ../../prds/prd-ha-securityspy-2026-08-09/prd.md
  - ../../prds/prd-ha-securityspy-2026-08-09/addendum.md
  - ../../research/architecture-implications.md
  - ../../research/securityspy-api-reference.md
companions: []
---

# Architecture Spine — ha-securityspy

## Design Paradigm

**Layered client/adapter with a two-plane data flow.** Three layers, one dependency direction:

1. **Protocol layer** — `aiosecurityspy` (PyPI): everything that knows SecuritySpy exists. Transport, framing, decoding, episode reduction, anonymization. No Home Assistant imports.
2. **Adapter layer** — `custom_components/securityspy/` core modules (`__init__`, `coordinator`, `config_flow`): owns lifecycle, maps library signals/exceptions to HA concepts, holds the single coordinator.
3. **Entity layer** — platform modules: thin declarative projections of coordinator data. No protocol knowledge, no I/O of their own.

Data flows on two planes with different jobs (AD-1): the **push plane** (event stream) drives latency-sensitive state; the **poll plane** (capture history / status endpoints) is the only source of persistent truth.

```mermaid
graph TD
    P[Platform modules - entity layer] --> C[coordinator.py / config_flow.py - adapter layer]
    C --> L[aiosecurityspy - protocol layer]
    L --> A[aiohttp - injected session]
    P -. never .-> L
```

Entity modules may import library *types* (dataclasses, exceptions for isinstance) but never call library I/O; all calls go through the adapter layer.

## Invariants & Rules

### AD-1 — Two-plane data flow; poll plane is the only truth

- **Binds:** all (esp. FR-1..FR-4, FR-30, FR-31, NFR §11.3)
- **Prevents:** stream-accumulated persistent state that blanks on restart or drifts on stream loss — the predecessor's core defect.
- **Rule:** Every persistent value (Observation Record, Latest Capture state, control states) must be fully derivable from the poll plane alone. The push plane may only *advance* state the next poll would confirm, never be its sole source. On startup: hydrate from poll. On stream reconnect: reconcile from poll. The integration never assumes it is SecuritySpy's only client: server-side changes by other clients are truth, and locally-echoed control state yields to the next poll.

### AD-2 — All protocol knowledge lives in `aiosecurityspy` [ADOPTED]

- **Binds:** FR-40..FR-42, all features
- **Prevents:** protocol parsing leaking into the integration, blocking Bronze `dependency-transparency` and forcing the retrofit the PRD names as the fatal refactor; destructive server capabilities becoming reachable.
- **Rule:** CR-framed stream parsing, endpoint URLs, `caplist` field decoding (`f`+`s` → absolute time, `o` bitmask), permission/trigger bitmask decoding, schedule model, bool read/write asymmetry (JSON `true/false` read, `1/0` write), credential handling, and the diagnostics anonymizer live only in the library. The integration contains zero knowledge of SecuritySpy's wire formats. The library's public surface excludes SecuritySpy's destructive and remote-execution endpoints (capture deletion, shell/shortcut execution) entirely — not wrapped, not private-but-present.

### AD-3 — Detection-episode reduction is a library component

- **Binds:** FR-5..FR-8, FR-43, NFR §11.1
- **Prevents:** the integration (or a future consumer) re-implementing signal→episode semantics divergently; per-signal load reaching the HA state machine.
- **Rule:** The library ships a pure, configurable reducer: Classification Signals in → Detection Episodes out (open/close + Peak Confidence), with Detection Threshold and Detection Debounce injected per camera per class. The integration configures it from options and consumes episodes only. Raw signals never cross the adapter boundary. Motion presence uses the same reducer pattern with an inactivity timeout, never `MOTION_END`.

### AD-4 — One coordinator, push-fed, no `update_interval`

- **Binds:** FR-1..FR-11, FR-14, FR-30
- **Prevents:** two units inventing separate polling machinery or a hand-rolled data hub (the legacy `unifiprotect` shape).
- **Rule:** One `DataUpdateCoordinator` per Config Entry with `update_interval=None`, updated via `async_set_updated_data()` from (a) library stream callbacks and (b) polls the adapter schedules per AD-10. All entities subscribe to this coordinator; no entity performs its own I/O.

### AD-5 — Identity scheme (permanent) [ADOPTED]

- **Binds:** FR-19..FR-21, FR-29
- **Prevents:** duplicate/orphaned devices on rename or address change; irreversible unique-ID churn.
- **Rule:** Hub device `identifiers = {(DOMAIN, server_uuid)}`, `entry_type=SERVICE`. Camera device `identifiers = {(DOMAIN, f"{server_uuid}_{camera_number}")}`, `via_device` → hub. Never hostname, IP, camera name, or fabricated MACs; no `connections`. Entity unique IDs: `f"{server_uuid}_{camera_number}_{entity_key}"`; hub entities `f"{server_uuid}_{entity_key}"`, where hub entity keys are a reserved namespace no camera entity key may reuse. `_attr_has_entity_name = True` and a `translation_key` on every entity description. Config Entry `unique_id = server_uuid`.

### AD-6 — Single exception-mapping seam

- **Binds:** FR-25, FR-27, FR-30, FR-31, NFR §11.4
- **Prevents:** two platforms classifying the same failure differently; auth-failure flapping into reauth on one 401.
- **Rule:** The library raises its own typed hierarchy (`SecuritySpyAuthError`, `SecuritySpyConnectError`, `SecuritySpyPermissionError`, `SecuritySpyUnsupportedVersionError`); it never raises raw `aiohttp` errors and never imports HA. The adapter layer maps them exactly once: `ConfigEntryAuthFailed` per AD-18's counter, `ConfigEntryNotReady` for transient, `ConfigEntryError` for permanent — all with translation keys. Service handlers map user error → `ServiceValidationError`, operational failure → `HomeAssistantError`.

### AD-7 — Arming writes override, never schedule [ADOPTED]

- **Binds:** FR-12..FR-15
- **Prevents:** Home Assistant destroying user-built schedules in SecuritySpy; controls implying an indefinite HA-set state.
- **Rule:** The three arm switches write the Arm Override exclusively. Schedule assignment is exposed read-only (dynamic `select` populated from `schedule-list`, options never hardcoded). No code path calls a schedule-mutating write. The override's transience (bounded at ≤ 6 hours or the next scheduled event, after which the Arm Schedule resumes) is reflected in entity state on the next poll and stated in docs and translation strings — never hidden.

### AD-8 — Settings writes are direct partial POSTs [ADOPTED]

- **Binds:** FR-16..FR-18
- **Prevents:** read-modify-write caching and its lost-update races.
- **Rule:** Settings-backed controls (enable, Detection Triggers, sensitivities) write a single-key partial POST on state change, verified non-destructive. No settings cache is held for write purposes; state reflects the next poll/echo per FR-14.

### AD-9 — Object Class is open string data, slugged once [ADOPTED]

- **Binds:** FR-34, FR-35, FR-6, event schema, AD-5 unique IDs
- **Prevents:** a three-value enum that locks out Custom Model users; unique-ID collisions or blueprint mismatches from ad-hoc class-name normalization.
- **Rule:** Object Class is `str` end-to-end — library models, reducer, event payloads, entity keys. `HUMAN/VEHICLE/ANIMAL` are constants, not a closed type. Unknown classes parse and carry without error; the event schema carries arbitrary classes from day one even though v1 creates entities only for built-ins. Wherever a class name enters a permanent key (unique ID, entity key, translation key), it passes through the library's single `class_slug()` normalization (lowercase, `[a-z0-9_]`); a class whose slug collides with an existing key is skipped with one warning, never silently merged.

### AD-10 — Observation Record polling shape

- **Binds:** FR-1..FR-4, FR-9..FR-11, §10.2, §11.1
- **Prevents:** cameras × classes request fan-out; poll storms per stream event.
- **Rule:** One reconciliation cycle = at most one `caplist` request per built-in Object Class, batched across all cameras (`cams=` list), bounded by the lookback window. Cycles run: at startup (non-blocking for setup per FR-2), on the library's reconnect signal, debounced after a `FILE` stream event, and on a slow fallback interval. Health polling uses the light status endpoint; the heavy endpoint only where a value requires it. `[ASSUMPTION: lookback window 7 days, fallback interval 10 minutes, FILE-event debounce 5 s.]`

### AD-11 — Stream lifecycle owned by the library

- **Binds:** FR-31..FR-33
- **Prevents:** reconnect/backoff logic split across layers; missed reconciliation on silent reconnects.
- **Rule:** The library's stream client owns CR framing, heartbeat watch (loss declared after 3 missed heartbeats ≈ 30 s), indefinite exponential backoff, and emits explicit `connected` / `disconnected` / `reconnected` / `auth_failed` callbacks. On `auth_failed` it pauses reconnection and defers to the adapter (AD-18). The adapter triggers AD-10 reconciliation on `reconnected`. Log discipline at the adapter: loss once at ERROR, retries at DEBUG, recovery once at WARNING. `disconnect()` is idempotent and cancels everything (FR-33).

### AD-12 — HA runtime conventions [ADOPTED]

- **Binds:** all integration code
- **Prevents:** drift from the machine-validated quality-scale rules; ONVIF coexistence breakage; devices going stale.
- **Rule:** Typed `SecuritySpyConfigEntry` alias + `entry.runtime_data`; never `hass.data[DOMAIN]`. `PARALLEL_UPDATES = 0` in every platform module. Services registered in `async_setup` (`action-setup`). Entity descriptions with `translation_key`; icons in `icons.json`. `iot_class: local_push`, `appropriate-polling` exempted with comment. Permission→entity gating happens once at setup (FR-28): no entity is created that the configured user cannot use; omissions raise repair issues. Camera (live video) entities set `entity_registry_enabled_default = False`. `EntityCategory.CONFIG` on arming, camera-enable, Detection Trigger, and sensitivity controls; `EntityCategory.DIAGNOSTIC` on health sensors; the update entity is read-only in v1. The device model follows Gold `dynamic-devices` / `stale-devices` patterns from Phase 1 (cameras appearing/disappearing on the server add/remove devices without reload) without committing the Gold tier.

### AD-13 — Credential containment [ADOPTED]

- **Binds:** FR-42, §11.2
- **Prevents:** the observed live hazard — plaintext camera credentials in settings payloads and stream URLs reaching logs/diagnostics.
- **Rule:** Credential-bearing URLs are constructed only inside the library. Settings payloads are never logged at any level. Diagnostics output passes through the library's anonymizer as the only exit path; the anonymizer redacts usernames, passwords, tokens, and per-camera device credentials. Exception messages carry no credentials. The README documents a least-privileged SecuritySpy user as the recommended setup.

### AD-14 — Two repositories; Bronze gates release, Silver gates announcement [ADOPTED]

- **Binds:** FR-36..FR-40, CI
- **Prevents:** HACS's one-integration-per-repo rule colliding with library CI; the predecessor's death pattern of a high bar blocking any release; an unannounced quality claim drifting from what CI verifies.
- **Rule:** `aiosecurityspy` (library repo: PyPI trusted-publisher OIDC release from semver tags, public CI, mypy `--strict` gate) and `ha-securityspy` (integration repo: hassfest + HA pylint plugin + HACS Action + pytest coverage in CI on every change). Both release via semver tags with GitHub Releases and a changelog. The HACS custom-repository release ships when the full Bronze rule set passes in CI; public announcement happens only when the full Silver rule set (including > 95 % coverage across integration modules) passes. The integration pins the library as a versioned dependency in `manifest.json`. `[ASSUMPTION: two repos, not a monorepo.]`

### AD-15 — Coordinator data contract

- **Binds:** all entity platforms, `coordinator.py`, library models
- **Prevents:** platforms, coordinator, and library each inventing incompatible shapes for shared data; string-vs-int camera keys.
- **Rule:** Coordinator data is one frozen, fully-typed `SecuritySpyData` container defined in the library's models: server state plus a `dict[int, CameraData]` keyed by SecuritySpy camera number (`int` everywhere — never stringly-typed). Per camera it carries: Observation Record timestamps per class, latest Capture, open Detection Episodes, control states, health, and per-camera availability (AD-17). The coordinator is the sole writer; entities read only this container.

### AD-16 — Push/poll merge is one watermark function

- **Binds:** FR-1..FR-3, FR-9, FR-10, AD-1, AD-15
- **Prevents:** the two planes both legitimately writing *last seen* / Latest Capture with no conflict rule — timestamps regressing or flickering between sources.
- **Rule:** All merges of push-derived and poll-derived state go through a single merge function in `coordinator.py`: incremental push updates may only advance a timestamp (monotonic watermark, max-wins); a full poll reconciliation is authoritative and overwrites, including regressions (e.g. captures deleted server-side). No other code path writes Observation Record or Latest Capture values.

### AD-17 — Three-layer availability, implemented once

- **Binds:** FR-30, FR-31, all platforms
- **Prevents:** each platform choosing its own availability definition (stream state vs poll success vs camera flag).
- **Rule:** Availability is computed in the shared base entities (`entity.py`) from `SecuritySpyData`, nowhere else. (1) Server unreachable — poll plane failing — → all entities of the entry unavailable. (2) A single camera offline (status-poll connected flag) while the server responds → only that Camera Device's entities unavailable, not an error. (3) Stream loss alone does **not** mark entities unavailable — the poll plane still holds truth — but push-derived presence entities (motion, per-class presence) become unavailable via a coordinator stream-health flag, since their liveness cannot be trusted. Platforms never override `available` with their own logic.

### AD-18 — Auth-failure escalation has one owner

- **Binds:** FR-27, AD-6, AD-11
- **Prevents:** the "3 consecutive failures" reauth counter living in both planes — reauth never firing, or double-firing, or one 401 on either plane triggering it.
- **Rule:** The adapter owns a single consecutive-auth-failure counter fed by auth errors from **both** planes (poll exceptions and the stream's `auth_failed` callback). Any authenticated success on either plane resets it. At 3, the adapter raises `ConfigEntryAuthFailed` (starting reauth) and stops both planes; completing reauth restarts them. The library never counts, never persists auth state, and never initiates reauth.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| Entity keys / unique IDs | snake_case stable keys (`last_human_seen`, `arm_motion_capture`, `trigger_human`); unique ID per AD-5; class names in keys via `class_slug()` (AD-9); keys are permanent once released |
| Object Class in keys | class name embedded lowercase (`last_{class}_seen`, `{class}_detected`); generation parameterized over the class list, not copy-pasted per class |
| Timestamps | timezone-aware `datetime` (UTC internally) everywhere; absent = `None`, never epoch/zero; sensors use `device_class: timestamp` |
| Library models | frozen dataclasses, fully typed, `from_api()` constructors; raw dicts never cross the library boundary |
| Event payloads | keys: `object_class` (str), `peak_confidence` (int 0–100), `camera_number` (int), `capture_ref` (nullable), `trigger_reason` (decoded str, never bitmask); the Latest Capture's detected-class set is an empty list when none, never absent |
| Config vs options | connection + credentials in Config Entry data; tuning in options as a typed options dataclass — global keys (threshold, debounce, motion timeout, lookback) plus `cameras: dict[int, PerCameraOptions]` overrides — owned by `config_flow.py`, consumed by the coordinator via update listener without reload |
| Services | `download_latest_recording` validates the destination against `allowlist_external_dirs`; user error → `ServiceValidationError`, operational failure → `HomeAssistantError`, translation keys on both |
| Logging | module loggers; loss/recovery once per AD-11; no payload logging; DEBUG never includes settings bodies |
| Tests & typing | library: no HA imports, protocol fixtures from HAR/recorded frames, mypy `--strict`; integration: pytest + `pytest-homeassistant-custom-component`, fixtures from anonymized real captures, ruff + mypy on both repos |
| Blueprints | the two canonical blueprints are the entity-model design test: drafted early against the Phase-3 entity surface; an awkward blueprint is an entity-model defect, not a blueprint problem |
| Docs vocabulary | PRD Glossary §4 terms verbatim in code comments, docs, and translation strings |

## Stack

| Name | Version |
| --- | --- |
| Python | ≥ 3.14 (HA 2026.3+ floor; library `requires-python >= 3.14`) |
| Home Assistant (min declared) | 2026.3 `[ASSUMPTION]` (current 2026.8.1; 2026.3 is the Python-3.14 boundary) |
| aiohttp | caller-injected session (HA's); library declares `>=3.12,<4` (current 3.14.3) |
| Build backend | hatchling, `src/` layout, `pyproject.toml` only |
| Tooling | uv (env/lock/publish via OIDC `id-token: write`), ruff, mypy |
| Integration test kit | pytest + pytest-homeassistant-custom-component (0.13.x, active) |
| CI | GitHub Actions: hassfest + HA pylint plugin + HACS Action (integration); build/typecheck/publish (library) |
| Distribution | PyPI (`aiosecurityspy`, name verified free 2026-08-09 — register early); HACS custom repository (integration) |

## Structural Seed

```text
aiosecurityspy/                    # repo 1 — protocol layer
  src/aiosecurityspy/
    client.py        # SecuritySpyClient: REST calls, injected session
    stream.py        # event-stream client: CR framing, heartbeat, backoff, callbacks
    episodes.py      # pure signal→episode reducer (threshold/debounce injected)
    models.py        # frozen dataclasses: SecuritySpyData, Server, CameraData, Capture, Permissions, Schedule, Event
    const.py         # endpoints, bitmasks, built-in class constants, class_slug()
    exceptions.py    # typed hierarchy (AD-6)
    anonymize.py     # diagnostics redaction (AD-13)

ha-securityspy/                    # repo 2 — integration
  custom_components/securityspy/
    __init__.py      # setup/unload, runtime_data, exception mapping (AD-6), auth counter (AD-18)
    coordinator.py   # the single coordinator (AD-4), watermark merge (AD-16), reconciliation scheduling (AD-10)
    config_flow.py   # user/reauth/reconfigure steps, HTTPS verify toggle, options flow
    entity.py        # base entities (hub/camera), device_info per AD-5, availability per AD-17
    diagnostics.py   # via library anonymizer only
    repairs.py       # permission omissions, default-install trap (FR-45)
    services.py      # download_latest_recording (FR-44)
    {sensor,binary_sensor,event,image,switch,select,number,camera,update}.py
    icons.json / strings.json / translations/
  blueprints/automation/securityspy/   # the two canonical blueprints (FR-37)
  hacs.json / README.md
```

```mermaid
graph LR
    SS[SecuritySpy server] -->|event stream - push plane| ST[stream.py]
    SS -->|caplist / status - poll plane| CL[client.py]
    ST --> R[episodes.py reducer]
    R -->|episodes| CO[coordinator.py]
    ST -->|conn signals + FILE events| CO
    CL -->|captures, settings, health| CO
    CO -->|SecuritySpyData - AD-15| E[entity platforms]
    E -->|writes: override, partial POST| CL
```

## Capability → Architecture Map

| Capability / Area | Lives in | Governed by |
| --- | --- | --- |
| Observation Record (FR-1..4) | `client.py` caplist + `coordinator.py` → `sensor.py` | AD-1, AD-10, AD-15, AD-16 |
| Live detection (FR-5..8, 43) | `stream.py` + `episodes.py` → `binary_sensor.py`, `event.py` | AD-3, AD-9, AD-17 |
| Latest Capture + download (FR-9..11, 44) | `client.py` → `image.py`, `services.py` | AD-1, AD-10, AD-16, services convention |
| Arming + schedule visibility (FR-12..16) | `switch.py`, `select.py` | AD-7, AD-8, AD-12 |
| Detection tuning + trap (FR-17, 18, 45) | `number.py`, `switch.py`, `repairs.py` | AD-8, AD-12 |
| Device model (FR-19..24) | `entity.py`, platform modules | AD-5, AD-12 |
| Setup/connection (FR-25..29) | `config_flow.py`, `__init__.py` | AD-6, AD-18, AD-5 |
| Resilience (FR-30..33) | `stream.py` + `coordinator.py` + `entity.py` | AD-11, AD-17, AD-1 |
| Custom Model (FR-34, 35) | schema everywhere; entities spike-gated | AD-9 |
| Distribution/quality (FR-36..39) | repo layout, CI, blueprints | AD-14, AD-12, blueprints convention |
| Library (FR-40..42) | `aiosecurityspy` | AD-2, AD-13 |

## Deferred

- **Custom Model entity-creation mechanism (FR-35)** — spike-gated on payload discovery; AD-9 keeps the schema and key-space safe meanwhile. Auto-defers to v2 if the spike cannot run.
- **Default Detection Threshold / Debounce values** — provisional 70% / 3 signals, motion timeout 30 s; tuned against real footage before release (PRD Open Q5). Options-flow adjustable, so not load-bearing.
- **Reconciliation freshness bound** — gated on the Phase-2 spike (classification write timing, PRD Open Q3); AD-10's shape is unaffected, only the honest latency claim.
- **Media source browser, clip service, PTZ, manual trigger, audio, capture tagging** — v2 candidates; nothing in the seed forecloses them (clip/media reuse `client.py` + `getfile` Range support). Any future clip service must clean up or expose deletion — but via new, deliberate surface, not by relaxing AD-2's exclusion.
- **Multi-server** — out for v1; AD-5's uuid-prefixed identity already leaves room.
- **Resource-scoped auth tokens** — v1 uses credentials + AD-13 discipline; investigate for camera-entity URLs later (PRD Open Q11).
- **HACS default-store listing and brands PR** — post-launch; start the brands PR early but nothing downstream depends on it.
- **Gold/Platinum tier commitment** — Platinum's library constraints and Gold's device-lifecycle patterns are already ADs; the tier decisions themselves are deferred.
- **SecuritySpy minimum-version floor** — assumed 6.x; verify the earliest sufficient 6.x release before hardcoding the check (PRD Open Q8).
- **Repair-issue fine behavior (FR-45 dismissal/recurrence)** — code-level detail within `repairs.py`; the trap-detection requirement itself is mapped.
