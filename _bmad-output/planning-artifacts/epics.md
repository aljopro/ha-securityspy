---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - prds/prd-ha-securityspy-2026-08-09/prd.md
  - prds/prd-ha-securityspy-2026-08-09/addendum.md
  - architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md
  - architecture/architecture-ha-securityspy-2026-08-09/SOLUTION-DESIGN.md
  - research/architecture-implications.md
  - research/securityspy-api-reference.md
---

# ha-securityspy - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for ha-securityspy, decomposing the requirements from the PRD and Architecture requirements into implementable stories. No UX design contract exists for this project: the entire user-facing surface is Home Assistant's own entity, device, config-flow, and blueprint UI, so visual design is inherited from Home Assistant rather than authored here.

## Requirements Inventory

### Functional Requirements

Numbering is taken verbatim from the PRD (FR-1…FR-45) so downstream references stay stable.

**The Observation Record (§5.1)**

- FR-1: A Home Assistant user can read, per Camera Device, the time a human, a vehicle, and an animal was each last seen.
- FR-2: The Observation Record is correct immediately after a Home Assistant restart, without waiting for a new detection.
- FR-3: The Observation Record recovers detections that occurred while Home Assistant was disconnected from SecuritySpy.
- FR-4: The Observation Record queries a bounded window of Capture History rather than unbounded history.

**Live Detection (§5.2)**

- FR-5: A Home Assistant user can trigger automations on whether a given Object Class is currently present on a Camera Device.
- FR-6: A Home Assistant automation can react to a completed detection and read its Object Class and Peak Confidence.
- FR-7: A Home Assistant user can trigger automations on motion per Camera Device, independent of classification.
- FR-8: A Home Assistant user can adjust the Detection Threshold and Detection Debounce globally and per Camera Device.
- FR-43: A Home Assistant automation can react to SecuritySpy deciding to record, and read why (decoded trigger reason, never a raw bitmask).

**Latest Capture Image (§5.3)**

- FR-9: A Home Assistant automation can fetch the most recent Capture for a Camera Device from a stable Home Assistant URL.
- FR-10: A Home Assistant user can trigger an automation on a new Capture appearing (image state is the capture timestamp).
- FR-11: A Home Assistant automation can read which Object Classes were detected in the Latest Capture.
- FR-44: A Home Assistant automation can save the most recent recording for a Camera Device to a file.

**Arming Control (§5.4)**

- FR-12: A Home Assistant user can arm and disarm each Arm Mode independently per Camera Device.
- FR-13: Arming from Home Assistant writes the Arm Override and never modifies an Arm Schedule.
- FR-14: State changed in SecuritySpy is reflected in Home Assistant, and vice versa, for every control this integration writes.
- FR-15: A Home Assistant user can see which Arm Schedule governs each Arm Mode on a Camera Device (read-only).
- FR-16: A Home Assistant user can enable and disable a camera in SecuritySpy.

**Detection Tuning in SecuritySpy (§5.5)**

- FR-17: A Home Assistant user can control, per Camera Device, whether each Object Class causes SecuritySpy to record.
- FR-18: A Home Assistant user can adjust per-Object-Class detection sensitivity per Camera Device.
- FR-45: A user whose SecuritySpy has per-class triggering disabled is told so, rather than left with an empty Observation Record.

**Device and Entity Model (§5.6)**

- FR-19: Cameras appear as devices beneath a single server device.
- FR-20: Devices and entities are correctly named on creation, with no manual intervention.
- FR-21: Entity and device identity survives renames, address changes, and reconfiguration.
- FR-22: Live video entities exist but do not appear unless the user enables them.
- FR-23: A Home Assistant user can see server and camera health (diagnostic entities).
- FR-24: A Home Assistant user is informed when a SecuritySpy update is available.

**Setup and Connection (§5.7)**

- FR-25: A Home Assistant user can add a SecuritySpy Server entirely through the UI.
- FR-26: A user can connect over HTTPS, including where the certificate does not match the address used.
- FR-27: A user is prompted to re-enter credentials when they stop working, rather than the integration failing silently.
- FR-28: The integration creates only controls the configured SecuritySpy user can actually use.
- FR-29: A user can change connection details without losing history.

**Resilience (§5.8)**

- FR-30: Entities report unavailable when their data cannot be trusted, rather than retaining stale values.
- FR-31: The integration recovers from connection loss without user action.
- FR-32: Connection problems are logged once, not continuously.
- FR-33: A Config Entry can be unloaded and removed cleanly.

**Custom Model Support (§5.9)**

- FR-34: The integration carries arbitrary Object Classes without modification (open vocabulary).
- FR-35: A Custom Model user gets presence entities for the classes their model emits. *(Spike-gated; auto-defers to v2.)*

**Distribution and Adoption (§5.10)**

- FR-36: A user can install the integration through HACS as a custom repository.
- FR-37: A user can import working automations without writing YAML (two canonical blueprints).
- FR-38: The integration meets Home Assistant's Bronze quality scale rule set in full, verified in CI.
- FR-39: The integration releases at Bronze and announces publicly only at Silver.

**The API Library (§5.11)**

- FR-40: The SecuritySpy API client is a separately published PyPI package, OSI-licensed, built in public CI.
- FR-41: The library is fully async, accepts a caller-provided HTTP session, and ships type information passing strict type checking.
- FR-42: Neither the library nor the integration exposes credentials in diagnostics or logs.

### NonFunctional Requirements

**Performance (§11.1)**

- NFR-1: Detection latency from SecuritySpy classifying to Home Assistant firing a Classification Event is within a few seconds, dominated by Detection Debounce rather than transport.
- NFR-2: Classification Signal reduction is approximately 190:1 in the measured reference case; per-signal writes to the Home Assistant state machine or recorder are a defect, not an inefficiency.
- NFR-3: Observation Record polling must not scale as cameras × classes in request count (11 cameras × 3 classes = 33 requests per cycle is the failure case).
- NFR-4: Health reconciliation must prefer cheap endpoints (`camStatus` at ~794 B over `systemInfo` at ~27 KB).
- NFR-5: The Latest Capture is not a sub-second signal — SecuritySpy completes a recording only after its post-roll (~96 s measured). Documentation and blueprints must not imply otherwise.

**Security (§11.2)**

- NFR-6: Credential redaction in all diagnostics and anonymized output, including per-camera device credentials returned by settings endpoints.
- NFR-7: Settings payloads are never logged at any level, including debug.
- NFR-8: Certificate verification is on by default; disabling it is an explicit user choice with the consequence stated in the UI.
- NFR-9: A least-privileged SecuritySpy user is documented.

**Reliability (§11.3)**

- NFR-10: No user-visible failure mode requires a Home Assistant restart.
- NFR-11: Persistent state derives from the Capture History, never from Event Stream accumulation alone.
- NFR-12: Motion clearing must not depend on SecuritySpy signalling motion end (measured as never firing on some cameras).

**Observability (§11.4)**

- NFR-13: Connection loss and recovery are logged once each; retries at debug level.
- NFR-14: Diagnostics are downloadable from the Config Entry, credential-redacted.
- NFR-15: Errors distinguish transient failure, authentication failure, and permanent incompatibility, so Home Assistant retries what is retryable and stops on what is not.

**Compatibility (§11.5)**

- NFR-16: A minimum supported SecuritySpy version is declared and enforced at setup, failing with a clear message rather than misbehaving. `[ASSUMPTION: 6.x]`
- NFR-17: A minimum supported Home Assistant version is declared and enforced.
- NFR-18: Identity and naming schemes are treated as permanent; changing them orphans user customizations.

**Sustainability and Coexistence (§10.2, §10.3)**

- NFR-19: Polling cost must scale sanely with camera count.
- NFR-20: Running alongside ONVIF is the expected topology, not a failure mode; installation must not disturb an existing ONVIF setup.
- NFR-21: The integration must not assume it is SecuritySpy's only client (HomeHelper, the iOS app, and the web client may be connected concurrently).

### Additional Requirements

**Starter template: none.** The Architecture specifies no starter or scaffolding template. This is a greenfield two-repository build whose Epic 1 Story 1 must therefore create the project scaffold by hand: `src/` layout, `pyproject.toml` with hatchling, uv-managed environments, ruff and mypy configuration, and GitHub Actions CI.

From the architecture spine (AD-1…AD-18) and stack:

- Two separate public repositories (AD-14): `aiosecurityspy` (library, PyPI trusted-publisher OIDC release) and `ha-securityspy` (integration, HACS custom repository). HACS permits exactly one integration per repository.
- Two-plane data flow (AD-1): the event stream drives latency-sensitive state only; the capture-history poll plane is the sole source of persistent truth. Push may only advance state; poll reconciliation is authoritative.
- All protocol knowledge confined to the library (AD-2), which excludes SecuritySpy's destructive and remote-execution endpoints (capture deletion, `doShell`, `doShortcut`) from its public surface entirely.
- The signal→episode reducer is a pure library component with injected threshold and debounce (AD-3); raw classification signals never cross into the integration.
- One `DataUpdateCoordinator` per Config Entry with `update_interval=None`, fed by `async_set_updated_data()` (AD-4).
- Permanent identity scheme (AD-5): hub `(DOMAIN, server_uuid)`, camera `(DOMAIN, f"{server_uuid}_{camera_number}")`, `via_device` to hub, `entry_type=SERVICE`, no MAC/`connections`.
- Single exception-mapping seam (AD-6) with a typed library exception hierarchy and no Home Assistant imports in the library.
- Frozen, typed `SecuritySpyData` coordinator container keyed by `int` camera number (AD-15); the coordinator is its sole writer.
- One watermark-merge function reconciling push and poll writes (AD-16).
- Three-layer availability computed once in base entities (AD-17): server down, camera offline, stream down.
- One adapter-owned consecutive-auth-failure counter spanning both planes, escalating to reauth at 3 (AD-18).
- Quality-scale CI gates: hassfest plus the Home Assistant pylint plugin (the `parallel-updates` check moved from hassfest to pylint in HA 2026.6), plus the HACS Action and pytest coverage.
- Stack: Python ≥ 3.14 (HA 2026.3+ floor), minimum HA 2026.3, aiohttp injected session, hatchling build backend, uv tooling, `src/` layout, ruff, mypy, pytest with `pytest-homeassistant-custom-component`.

Protocol constraints from the API reference that materially shape stories:

- Event stream lines are **CR-terminated only** — a standard `readline()` hangs. Named as the single most likely implementation bug.
- `caplist` supports server-side class filtering (`filter=5|6|7`) and persists an `o` classification bitmask per capture; absolute time reconstructs from `f` (folder date) plus `s` (seconds since midnight).
- Settings writes are partial POSTs whose body must begin with the literal sentinel `formData`, with `cameraNum` in the body, booleans written as `1`/`0` while JSON reads return `true`/`false`. Partial writes are verified non-destructive.
- Arming writes use `ssSetSchedule` with `mode` as a concatenated letter string (`C`/`M`/`A`) and a 16-value `override` parameter.
- The per-camera `permissions` field decodes via `PERM_*` bits and gates entity creation.
- Per-class trigger bits (7–16) only fire when the corresponding `mcTriggerMotionH/V/A` settings are enabled, which are off on a default install.
- The `t` field is overloaded: `caplist.t` (1=movie, 2=image) means something different from `clip.movieType` (0=motion, 1=continuous). Do not share an enum.

Two spike gates carried from the PRD:

- **Blocking Phase 2:** does `caplist`'s `o` field populate at capture close or later? Determines how fresh the Observation Record can honestly be.
- **Gating FR-35:** the Custom Model event payload shape. Auto-defers FR-35 to v2 if the spike cannot run.

### UX Design Requirements

Not applicable. This project has no custom user interface. Every user-facing surface is rendered by Home Assistant from the integration's entity, device, config-flow, and blueprint definitions, so visual identity, layout, and interaction patterns are inherited from Home Assistant rather than designed here. The equivalent design discipline is expressed as entity-model requirements (FR-19…FR-24) and as the standing blueprint design test (§5.10): if a canonical blueprint is awkward to write, the entity model is wrong.

### FR Coverage Map

Every FR maps to exactly one owning epic. Where another epic also realizes part of a requirement, that is noted.

| FR | Epic | Coverage |
| --- | --- | --- |
| FR-1 | Epic 4 | Per-class last-seen timestamps from the capture history |
| FR-2 | Epic 4 | Restart correctness via startup hydration from the poll plane |
| FR-3 | Epic 4 | Self-healing reconciliation (consumes Epic 3's reconnect signal) |
| FR-4 | Epic 4 | Bounded lookback window on capture-history queries |
| FR-5 | Epic 5 | Per-class presence binary sensors |
| FR-6 | Epic 5 | One Classification Event per episode with Peak Confidence |
| FR-7 | Epic 5 | Motion presence with independent inactivity timeout |
| FR-8 | Epic 5 | Detection Threshold and Debounce, global plus per-camera override |
| FR-9 | Epic 4 | Latest Capture served as a Home Assistant image |
| FR-10 | Epic 4 | Capture timestamp as image state, usable as a trigger |
| FR-11 | Epic 4 | Object Class set readable alongside the image |
| FR-12 | Epic 6 | Three independent arm-mode switches |
| FR-13 | Epic 6 | Override-only writes, never schedule mutation |
| FR-14 | Epic 6 | Bidirectional state for every writable control |
| FR-15 | Epic 6 | Read-only Arm Schedule visibility |
| FR-16 | Epic 6 | Camera enable control |
| FR-17 | Epic 6 | Per-class Detection Trigger controls |
| FR-18 | Epic 6 | Per-class sensitivity controls |
| FR-19 | Epic 2 | Hub and Camera Device hierarchy |
| FR-20 | Epic 2 | Correct naming with no manual intervention |
| FR-21 | Epic 2 | Stable identity from server UUID and camera number |
| FR-22 | Epic 2 | Camera entities present but disabled by default |
| FR-23 | Epic 2 | Server and per-camera diagnostic sensors |
| FR-24 | Epic 2 | Server update-available signal |
| FR-25 | Epic 2 | UI configuration flow |
| FR-26 | Epic 2 | HTTPS with optional certificate verification |
| FR-27 | Epic 2 | Reauthentication after bounded consecutive failures |
| FR-28 | Epic 2 | Permission-aware entity creation |
| FR-29 | Epic 2 | Reconfiguration without losing history |
| FR-30 | Epic 3 | Unavailability rather than staleness, three-layer |
| FR-31 | Epic 3 | Automatic recovery with backoff and reconciliation |
| FR-32 | Epic 3 | Disciplined once-only logging |
| FR-33 | Epic 3 | Clean teardown and reload |
| FR-34 | Epic 1 | Open classification vocabulary in library models and parsing (realized again in Epic 5's event schema) |
| FR-35 | Epic 5 | Entities for Custom Model classes *(spike-gated; auto-defers to v2)* |
| FR-36 | Epic 7 | HACS custom-repository installation |
| FR-37 | Epic 7 | Canonical blueprints packaged and importable (first drafted in Epic 5 as the entity-model design test) |
| FR-38 | Epic 7 | Full Bronze rule set verified in CI (CI scaffolding established in Epics 1 and 2) |
| FR-39 | Epic 7 | Silver gates public announcement |
| FR-40 | Epic 1 | Standalone published PyPI library |
| FR-41 | Epic 1 | Async, typed, injectable-session library |
| FR-42 | Epic 1 | Credential-safe diagnostics and anonymizer |
| FR-43 | Epic 5 | Trigger events with decoded reasons |
| FR-44 | Epic 4 | Download-latest-recording service |
| FR-45 | Epic 6 | Default-install trap detection |

## Epic List

Seven epics. Ordering follows the architecture's hard sequencing constraint (the library cannot be retrofitted without blocking Bronze) and then the PRD's release shape. Each epic delivers complete functionality for its own domain and does not require a later epic to function.

### Epic 1: The SecuritySpy API Library

A Python developer can talk to a SecuritySpy server from an ordinary script — query its cameras and capture history, consume its live event stream without the client hanging, and decode what SecuritySpy actually means — with Home Assistant nowhere in sight. This epic exists first because retrofitting a library after writing protocol parsing inside an integration is the large, thankless refactor that blocks Bronze, and because a maintained SecuritySpy library is the project's durable contribution: nobody else has one.

**FRs covered:** FR-40, FR-41, FR-42, FR-34

**Implementation notes:** Greenfield scaffold with no starter template — `src/` layout, hatchling, uv, ruff, mypy `--strict`, GitHub Actions with PyPI trusted-publisher OIDC. Owns CR-only stream framing (the single most likely implementation bug), `caplist` field decoding, permission and trigger bitmask decoding, the schedule model, the settings read/write asymmetry, the pure episode reducer, and the diagnostics anonymizer. Destructive and remote-execution endpoints are excluded from the public surface entirely. Validated by SM-9: installable from PyPI and usable in a script with no Home Assistant present.

Stories 1.8–1.10 were added after 1.1–1.7 landed, when auditing the built library against Epics 2, 4 and 6 showed the health fields, the cheap `camStatus` poll, the capture media endpoints, `schedule-list`, and the camera-enable write had never been assigned to any story — story 1.2's "at minimum the server UUID, version, camera count, and the camera list" was implemented literally and nothing downstream claimed the rest. Because the architecture forbids the integration from knowing any wire format or endpoint URL, those absences are hard blockers rather than inconveniences: they gate Stories 2.4, 2.5, 4.5, 4.7, 6.3 and 6.4, and each must land before its consumer is dispatched.

### Epic 2: Connect and Model

A user adds their SecuritySpy server through the Home Assistant UI — over HTTPS, with a verification toggle for the LAN-IP certificate mismatch — and their cameras appear as correctly-named devices beneath one server hub, with no manual renaming and no entity named after an IP address. Only controls their SecuritySpy account can actually use are created. This is the epic where nothing user-facing exists before it and where the identity decisions are made that can never be changed without orphaning every customization a user has built.

**FRs covered:** FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, FR-27, FR-28, FR-29

**Implementation notes:** Establishes the integration repository scaffold, the single coordinator, the typed data container, the permanent identity scheme, and the exception-mapping seam. Camera (live video) entities ship disabled by default so an existing ONVIF setup is undisturbed. Gold `dynamic-devices` and `stale-devices` patterns are honored here because they are cheap now and expensive to retrofit. Validated by SM-4 (eleven cameras, zero manual renaming) and SM-8 (ONVIF untouched).

### Epic 3: Resilience

The Mac reboots at three in the morning and nobody has to do anything. SecuritySpy goes away, entities report unavailable rather than lying with stale values, the integration retries with backoff without filling the log, and when the server returns it reconnects and recovers on its own — no Home Assistant restart, no reload, no re-authentication. This is the epic that separates an integration people keep from one they uninstall, and it is what the predecessor's users lost.

**FRs covered:** FR-30, FR-31, FR-32, FR-33

**Implementation notes:** Implements three-layer availability once in the base entities (server unreachable, single camera offline, stream lost) so no platform invents its own definition. Heartbeat-based stream-loss detection, indefinite backoff, and the reconnect signal that Epic 4's self-healing consumes. Log discipline is a hard requirement, not a nicety: a multi-hour outage must not produce a proportional volume of log entries. Validated by SM-7.

### Epic 4: The Observation Record

Jensen sits on the sofa and asks whether a delivery came while he was out, and Home Assistant answers — last human, last vehicle, last animal seen, per camera, as relative timestamps he can read at a glance and write automations against. He taps through to the latest capture image to confirm it was the courier. The values are correct twenty minutes after a Home Assistant restart, because they come from what SecuritySpy already wrote to disk rather than from events Home Assistant happened to be awake for. This is the headline deliverable and the reason the project exists.

**FRs covered:** FR-1, FR-2, FR-3, FR-4, FR-9, FR-10, FR-11, FR-44

**Implementation notes:** Entirely poll-plane. Batched class-filtered capture-history queries — one request per class across all cameras, never cameras × classes. Setup must not block on hydration. **Carries the Phase-2 spike gate:** confirm whether SecuritySpy writes classification at capture close or later before committing, since it determines how fresh this can honestly be. The Latest Capture is not a sub-second signal (~96 s post-roll), and nothing here may imply otherwise. Validated by SM-1.

### Epic 5: Live Detection

The driveway narrates itself. A person walks up, SecuritySpy classifies a human, and within a few seconds Home Assistant has both a presence sensor a user can trigger a light on and an event carrying peak confidence that an automation can hand to a vision model. One event per detection, not one per frame — the raw stream emits roughly 190 classification signals for a single person crossing the view.

**FRs covered:** FR-5, FR-6, FR-7, FR-8, FR-43, FR-35

**Implementation notes:** Consumes the library's episode reducer; raw signals never reach the Home Assistant state machine, and per-signal writes are a defect rather than an inefficiency. Motion clearing uses an independent inactivity timeout because SecuritySpy's motion-end signal never fires at all on some cameras. Trigger reasons are decoded, never raw bitmasks. **Includes the first blueprint draft as the entity-model design test** — an awkward blueprint here means the entity model is wrong while it is still cheap to fix. **FR-35 carries its own spike gate** on the undocumented Custom Model payload and auto-defers to v2 if the spike cannot run, with no decision meeting required. Validated by SM-2.

### Epic 6: Control SecuritySpy

A user arms and disarms each capture mode independently per camera, enables and disables cameras, and tunes which object classes actually cause SecuritySpy to record and how sensitively — all from Home Assistant, and all without Home Assistant ever destroying the schedules they built in SecuritySpy. A user whose per-class triggers are off by default is told so, rather than left staring at an empty Observation Record wondering what broke.

**FRs covered:** FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-45

**Implementation notes:** Arming and detection tuning are one epic because they are the same component end-to-end — both are write paths using the same verified partial-POST mechanism, and both touch the same platform files. Writes target the transient override only; schedules are read-only, surfaced through a dynamic select populated from the server, never a hardcoded list. Override transience (bounded at six hours or the next scheduled event) must be visible rather than implied to be permanent. FR-45 closes the loop on the Observation Record: these controls are what let a user turn it on.

### Epic 7: Ship It

Priya finds the integration on the Ben Software forum, adds it as a HACS custom repository, sets it up without asking anyone for help, and imports a working notification blueprint from a one-click link in under a minute. The Bronze rule set passes in the project's own CI before that release exists, and no public announcement happens until Silver does too.

**FRs covered:** FR-36, FR-37, FR-38, FR-39

**Implementation notes:** CI scaffolding is established in Epics 1 and 2; what lands here is the full Bronze rule set passing as a release gate, the HACS packaging, and the two canonical blueprints finished and linked. Quality-scale verification runs hassfest plus the Home Assistant pylint plugin, since the `parallel-updates` check moved from hassfest to pylint in HA 2026.6. The claim is "meets the rule set as verified by our own tooling in CI," never "certified." Silver gates the forum announcement rather than the release itself, deliberately: the predecessor died of maintainer fatigue, and a quiet release at Bronze beats a perfect one that never ships. Validated by SM-3, SM-5, SM-6.

---

## Epic 1: The SecuritySpy API Library

A Python developer can talk to a SecuritySpy server from an ordinary script — query its cameras and capture history, consume its live event stream without the client hanging, and decode what SecuritySpy actually means — with Home Assistant nowhere in sight.

### Story 1.1: Publishable library skeleton

As a maintainer,
I want a published, installable `aiosecurityspy` package with typing and CI in place from the first commit,
So that the integration can depend on it as an ordinary versioned dependency and Bronze `dependency-transparency` is satisfied by construction rather than by retrofit. *(FR-40, FR-41)*

**Acceptance Criteria:**

**Given** a clean checkout of the library repository
**When** a developer runs `uv sync` and the test suite
**Then** the project builds with hatchling from a `src/` layout using only `pyproject.toml`
**And** `requires-python` is `>=3.14`, matching Home Assistant's floor
**And** ruff and `mypy --strict` both pass with zero findings on an empty-but-typed package
**And** a `py.typed` marker is present so type information ships to consumers

**Given** a tagged release is published on GitHub
**When** the publish workflow runs
**Then** the package is uploaded to PyPI via trusted-publisher OIDC with no API token stored in the repository
**And** the published version matches the git tag exactly
**And** the package is OSI-licensed with the license declared in metadata

**Given** the package is installed from PyPI into a bare virtual environment
**When** it is imported
**Then** it imports successfully with no Home Assistant present anywhere on the system

### Story 1.2: Authenticated client with injected session

As a Python developer,
I want to connect to a SecuritySpy server and read its server and camera configuration,
So that I can identify the server and enumerate its cameras before doing anything else. *(FR-40, FR-41, FR-42)*

**Acceptance Criteria:**

**Given** a reachable SecuritySpy server and valid credentials
**When** a `SecuritySpyClient` is constructed with a caller-provided `aiohttp` session and asked for server information
**Then** it returns a frozen, fully-typed model carrying at minimum the server UUID, version, camera count, and the camera list
**And** the client never creates an `aiohttp` session of its own
**And** every camera model exposes its camera number as an `int`

**Given** a server reachable over HTTPS with a certificate that does not match the address used
**When** the client is constructed with certificate verification disabled
**Then** the connection succeeds
**And** when constructed with verification enabled against that same address, it fails with a connection error rather than hanging

**Given** an unreachable host, bad credentials, or a SecuritySpy older than the supported minimum
**When** any client call is made
**Then** the client raises `SecuritySpyConnectError`, `SecuritySpyAuthError`, or `SecuritySpyUnsupportedVersionError` respectively
**And** no raw `aiohttp` exception escapes the library
**And** no exception message, string representation, or traceback contains the username or password

### Story 1.3: Event stream client with CR framing and heartbeat

As a Python developer,
I want to consume SecuritySpy's live event stream as typed events without my client hanging,
So that I can react to what the server is seeing in real time. *(FR-34, FR-41)*

**Acceptance Criteria:**

**Given** a recorded event-stream fixture whose lines are terminated by CR (0x0D) only, with zero LF bytes
**When** the stream client reads it
**Then** every event is parsed and delivered, and the reader never blocks waiting for a newline that will not arrive
**And** each event is delivered as a typed object carrying timestamp, camera number, event type, and decoded payload
**And** an event whose camera field is `X` is delivered as not camera-specific rather than being dropped or misattributed

**Given** a `CLASSIFY` event carrying an Object Class the library has never seen, emitted by a Custom Model
**When** it is parsed
**Then** the class is carried through as an ordinary string with its confidence
**And** handling of the built-in human, vehicle, and animal classes is unaffected
**And** no enumeration, literal type, or validation anywhere rejects the unknown class *(FR-34)*

**Given** an open stream connection
**When** the server's ten-second heartbeat stops arriving
**Then** loss is declared after three missed heartbeats and a `disconnected` callback fires exactly once
**And** reconnection is attempted with exponential backoff, indefinitely
**And** on success a `reconnected` callback fires, distinct from `connected`

**Given** the server rejects the stream connection with an authentication failure
**When** the stream client handles it
**Then** an `auth_failed` callback fires and reconnection is paused rather than retried in a loop
**And** calling `disconnect()` twice is safe and leaves no task, timer, or socket running

### Story 1.4: Capture history decoding

As a Python developer,
I want to query completed recordings filtered by object class and read when each occurred,
So that I can answer "when was a human last seen on this camera" in a single request. *(FR-41)*

**Acceptance Criteria:**

**Given** a SecuritySpy server with recorded captures
**When** the capture history is queried for a set of cameras and a date range with a class filter
**Then** one request is issued covering all requested cameras rather than one request per camera
**And** results are returned as frozen typed models
**And** the server-side class filter is used, rather than fetching everything and filtering locally

**Given** a capture record from the server
**When** it is decoded
**Then** its absolute start time is reconstructed correctly from the folder date and seconds-since-midnight fields, as a timezone-aware datetime
**And** its Object Class set is decoded from the classification bitmask into a set of class strings
**And** an empty classification yields an empty set rather than `None` or an error
**And** the capture type field is decoded without sharing an enumeration with the clip endpoint's differently-meaning field of the same name

**Given** a camera with no captures of the requested class in the queried window
**When** the query runs
**Then** an empty result is returned rather than an error or a fabricated entry

### Story 1.5: Detection episode reducer

As a Python developer,
I want noisy per-frame classification signals reduced into meaningful detection episodes,
So that one person walking past produces one detection rather than roughly a hundred and ninety. *(FR-34, FR-41)*

**Acceptance Criteria:**

**Given** the reference capture of 191 classification signals for a single subject crossing one camera in 95 seconds
**When** they are fed through the reducer with a confidence threshold and a consecutive-signal debounce
**Then** exactly one episode opens and one closes
**And** the episode reports the maximum confidence observed across its whole span, not the value at the moment the threshold was crossed
**And** the reduction ratio is on the order of 190:1

**Given** a stream of signals that never sustains confidence above the threshold for the debounce count
**When** they are reduced
**Then** no episode opens, however frequent the signals

**Given** the reducer
**When** it is constructed
**Then** threshold and debounce are injected per camera and per Object Class rather than being module constants
**And** the reducer is a pure component with no I/O, no timers of its own, and no Home Assistant or network imports
**And** it operates over arbitrary Object Class strings, not a fixed set of three

### Story 1.6: Settings, arming, and permission decoding

As a Python developer,
I want to read and write SecuritySpy's per-camera settings and arming state safely,
So that a client can change one setting without disturbing the roughly 120 others on the page. *(FR-41)*

**Acceptance Criteria:**

**Given** a camera with known settings
**When** the client writes a single setting
**Then** the request is a form-urlencoded POST whose body begins with the required sentinel and carries the camera number in the body rather than the query string
**And** every other setting on that page retains its prior value, verified by reading back before and after
**And** boolean values are written in the server's write encoding while being read in its differing read encoding, with the asymmetry handled inside the library and never at a call site

**Given** an arming instruction for a camera
**When** the client applies it
**Then** the three capture modes are expressed as independent booleans, and all eight combinations are expressible
**And** the write targets the transient override, and no library method exists that mutates a schedule assignment
**And** the available override values, including their bounded durations, are exposed as typed data

**Given** a camera's permission field and trigger reason bitmask
**When** they are decoded
**Then** each is returned as a typed structure of named capabilities and reasons rather than a raw integer
**And** a reason bit the server can emit but that is disabled in SecuritySpy simply does not appear, and its absence is not an error

**Given** the library's public API surface
**When** it is enumerated
**Then** no method exists for deleting captures or executing shell commands or shortcuts on the server *(AD-2)*

### Story 1.7: Credential-safe diagnostics

As a maintainer,
I want a single anonymizer that strips secrets out of anything the library can emit,
So that a user posting a diagnostics dump to a public forum does not publish their camera passwords. *(FR-42)*

**Acceptance Criteria:**

**Given** a settings payload from SecuritySpy containing per-camera device credentials in plaintext
**When** it is passed through the anonymizer
**Then** usernames, passwords, and authentication tokens are redacted
**And** the structure remains readable enough to diagnose a problem

**Given** the library running at debug log level during a full session
**When** the log output is inspected
**Then** no settings payload appears at any level
**And** no credential appears in any log line, exception message, or stack trace
**And** any URL that carried credentials appears only in redacted form

**Given** the anonymizer
**When** a new credential-shaped key is returned by a future SecuritySpy version
**Then** redaction is driven by a single declared key set that can be extended in one place

### Story 1.8: Server and camera health decoding

As a Python developer,
I want the server's health figures and each camera's live health counters as typed model fields, plus the cheap status poll,
So that a consumer can report health without parsing a 27 KB payload on every cycle. *(FR-41; enables FR-23, FR-24)*

**Acceptance Criteria:**

**Given** a `++systemInfo` body
**When** it is decoded
**Then** `ServerInfo` additionally carries CPU usage, memory pressure, certificate expiry, and the offered update version, each typed and each `None` when the server omits it
**And** the offered update version is distinct from the installed version and is absent rather than empty when no update is offered

**Given** the same body
**When** a camera is decoded
**Then** `Camera` additionally carries current frame rate, data rate, and the last error with its description, each typed and each `None` when absent
**And** no existing field of `ServerInfo` or `Camera` changes name, type, or meaning

**Given** a server whose health fields are missing, malformed, or negative where only a non-negative value is meaningful
**When** they are decoded
**Then** each falls back to `None` and the surrounding decode still succeeds, matching how the existing decoders already tolerate partial payloads

**Given** the `++camStatus` endpoint, which returns roughly 794 bytes against `++systemInfo`'s 27 KB
**When** the client is asked for camera status
**Then** it returns a typed per-camera result carrying the number, enabled, online, open, and error fields that endpoint provides
**And** `enabled`, `online`, and `open` are preserved as three distinct states rather than collapsed into one
**And** the endpoint URL and its response shape are known only inside the library

### Story 1.9: Capture media fetch

As a Python developer,
I want to fetch a capture's preview image and download its underlying file,
So that a consumer can serve an image and save a recording without constructing a SecuritySpy URL itself. *(FR-41; enables FR-9, FR-10, FR-44)*

**Acceptance Criteria:**

**Given** a `Capture`
**When** its preview image is requested
**Then** the client returns the JPEG bytes together with their content type
**And** the caller supplies only the `Capture`, never a path, folder date, or query parameter

**Given** a `Capture` for a recorded movie
**When** its file is requested
**Then** the client streams the bytes so a large recording is never held in memory in full
**And** the bandwidth variant and the archive flag are selectable through typed arguments rather than raw query strings
**And** nothing on the SecuritySpy server is deleted or modified by either call

**Given** an account without file permission, or a capture the server no longer holds
**When** either call is made
**Then** it raises the library's own typed permission or connection error
**And** no raw `aiohttp` exception escapes, and no credential appears in the message

### Story 1.10: Schedule names and the camera enable write

As a Python developer,
I want schedules resolvable to their names and a camera's enabled state writable,
So that a consumer can show which schedule governs a camera and take one out of service. *(FR-41; enables FR-15, FR-16)*

**Acceptance Criteria:**

**Given** a `++systemInfo` body carrying `schedule-list`
**When** it is decoded
**Then** the server's schedules are exposed as an id-to-name mapping, including both the built-in defaults and any the user defined
**And** a camera's existing per-mode schedule ids resolve through it to names, with an unknown id resolving to `None` rather than raising

**Given** a camera and a desired enabled state
**When** the client is asked to write it
**Then** only the enabled state is sent, and no unrelated camera setting is disturbed
**And** the write uses the same verified partial-write mechanism as the existing settings path

**Given** an account without the permission that write requires
**When** it is attempted
**Then** it raises the library's typed permission error rather than failing silently or reporting success

---

## Epic 2: Connect and Model

A user adds their SecuritySpy server through the Home Assistant UI and their cameras appear as correctly-named devices beneath one server hub, with no manual renaming and no entity named after an IP address.

### Story 2.1: Add a SecuritySpy server through the UI

As a Home Assistant user,
I want to add my SecuritySpy server by entering its address and my credentials in the UI,
So that I can set the integration up without touching YAML. *(FR-25)*

**Acceptance Criteria:**

**Given** a fresh Home Assistant with the integration installed
**When** the user opens Add Integration and selects SecuritySpy
**Then** a form requests host, port, username, and password
**And** no YAML is required at any point

**Given** the user submits the form
**When** the flow validates
**Then** the credentials are tested against the server before any config entry is created
**And** on success a config entry is created whose unique ID is the server UUID, titled with the server's name

**Given** the user submits a host that is unreachable, credentials that are wrong, or a SecuritySpy older than the supported minimum
**When** validation runs
**Then** a distinct, actionable, translated message is shown for each case
**And** the form is redisplayed with the entered values preserved rather than the flow aborting

**Given** a SecuritySpy server that is already configured
**When** the user tries to add the same server again, by any address that resolves to it
**Then** the flow aborts as already configured and no second entry is created

**Given** the config flow module
**When** test coverage is measured
**Then** it is at 100%, including every abort and error path

### Story 2.2: Connect over HTTPS with a verification toggle

As a Home Assistant user running SecuritySpy over HTTPS,
I want to connect by LAN IP even though my certificate was issued for a dynamic-DNS hostname,
So that I am not blocked by a certificate mismatch I cannot fix. *(FR-26)*

**Acceptance Criteria:**

**Given** the setup form
**When** the user views it
**Then** both HTTP and HTTPS are selectable, and a certificate-verification toggle is present and on by default
**And** the toggle's description states the consequence of disabling it

**Given** a server whose certificate is issued for a dynamic-DNS hostname
**When** the user connects by LAN IP with verification enabled
**Then** setup fails with a message that names the certificate mismatch specifically, rather than a generic connection error
**And** when the user disables verification and retries, setup succeeds

**Given** a completed config entry
**When** the verification setting is inspected
**Then** it is persisted with the entry and applied to every subsequent connection, including the event stream

### Story 2.3: Cameras appear as devices under one server hub

As a Home Assistant user,
I want my cameras to appear as correctly-named devices beneath a single server device,
So that eleven cameras are legible instead of being eleven anonymous entities. *(FR-19, FR-20, FR-21)*

**Acceptance Criteria:**

**Given** a configured SecuritySpy server with eleven cameras
**When** setup completes
**Then** exactly one hub device is created, typed as a service rather than a physical device
**And** one camera device is created per camera, each related to the hub as its parent
**And** each camera device carries its name from SecuritySpy, with zero manual renaming required
**And** no device is named after an IP address and none reports manufacturer "Generic"

**Given** the created devices and entities
**When** their identifiers are inspected
**Then** the hub is identified by the server UUID and each camera by the server UUID combined with its camera number
**And** no identifier derives from hostname, IP address, camera name, or a fabricated MAC address
**And** every entity has a unique ID that is stable across restarts

**Given** a camera renamed in SecuritySpy
**When** the integration next reconciles
**Then** the device name updates in Home Assistant
**And** no entity ID changes, no unique ID changes, and no user customization is orphaned

**Given** the server's hostname, IP, or port changes
**When** the integration reconnects
**Then** no duplicate devices are created and no entities are orphaned

**Given** a camera added to or removed from the SecuritySpy server after setup
**When** the integration next reconciles
**Then** the corresponding device is added or removed without requiring a reload

### Story 2.4: See server and camera health

As a Home Assistant user,
I want to see how my SecuritySpy server and cameras are doing,
So that I can notice a problem before it costs me a recording. *(FR-23)*

**Acceptance Criteria:**

**Given** a configured server
**When** the hub device is viewed
**Then** it exposes server health values including CPU usage, memory pressure, camera count, and certificate expiry
**And** every one of them is categorized as diagnostic and does not appear among the device's primary controls

**Given** a configured camera
**When** its device is viewed
**Then** it exposes per-camera health including current frame rate, data rate, and last error, all categorized as diagnostic

**Given** the health polling cycle
**When** its requests are measured
**Then** it uses the server's light status endpoint rather than the heavy one, except for values only the heavy endpoint provides

### Story 2.5: Know when a SecuritySpy update is available

As a Home Assistant user,
I want to be told when a SecuritySpy update is available,
So that I find out from Home Assistant rather than by chance. *(FR-24)*

**Acceptance Criteria:**

**Given** a server reporting an available update
**When** the hub device is viewed
**Then** an update entity reports that an update is available and names the offered version
**And** the currently installed version is also shown

**Given** the update entity
**When** a user attempts to install from Home Assistant
**Then** no install action is offered, because installing updates is out of scope for v1

### Story 2.6: Live video exists but stays out of the way

As a Home Assistant user already streaming these cameras over ONVIF,
I want SecuritySpy's camera entities to exist but not appear unless I ask for them,
So that installing this integration does not disturb my working video setup. *(FR-22)*

**Acceptance Criteria:**

**Given** a fresh installation on a system with an existing ONVIF setup
**When** setup completes
**Then** each camera device has a live video entity that is disabled by default
**And** no enabled camera entity is added, and the existing ONVIF entities are untouched and still working

**Given** a disabled camera entity
**When** the user enables it and reloads
**Then** it produces working live video

### Story 2.7: Only create entities the user is permitted to use

As a Home Assistant user with a restricted SecuritySpy account,
I want the integration to leave out anything my account cannot use and tell me why,
So that I am not left with entities that fail permanently. *(FR-28)*

**Acceptance Criteria:**

**Given** a configured server
**When** setup completes
**Then** each camera's permissions are decoded into named capabilities and made available on the coordinator data, evaluated per camera
**And** a single shared gating helper exists that every platform consults before creating an entity, so no platform invents its own rule

**Given** an account lacking live-video permission on a camera
**When** setup completes
**Then** that camera's live video entity is not created at all, rather than created and permanently unavailable
**And** cameras the account *can* view are unaffected, proving the per-camera evaluation

**Given** an account lacking a capability that some camera's entity depends on
**When** setup completes
**Then** a repair issue is raised naming the specific missing permission and the cameras affected
**And** the issue text tells the user where in SecuritySpy to grant it

**Given** the user grants the missing permission in SecuritySpy and reloads the entry
**When** setup runs again
**Then** the previously omitted entities are created and the repair issue is cleared

**Given** platforms added by later epics — arming, capture images, the download action
**When** they are built
**Then** they consult this same gating helper, and this story's rule binds them
*(Later epics apply this rule to their own entities; this story owns the mechanism and proves it on the entities that exist now.)*

### Story 2.8: Re-enter credentials when they stop working

As a Home Assistant user whose SecuritySpy password changed,
I want to be prompted to re-enter my credentials,
So that the integration does not just fail silently. *(FR-27)*

**Acceptance Criteria:**

**Given** a configured entry whose credentials have become invalid
**When** three consecutive authentication failures occur, counted across both the polling and streaming paths together
**Then** a reauthentication flow is started and surfaced to the user

**Given** a single transient authentication failure, or two
**When** a subsequent request succeeds
**Then** no reauthentication flow is started and the failure counter resets

**Given** an active reauthentication flow
**When** the user submits working credentials
**Then** normal operation resumes without the config entry being removed
**And** devices, entities, and their recorded history are preserved
**And** submitting credentials for a different SecuritySpy server is rejected rather than silently repointing the entry

### Story 2.9: Change connection details without losing history

As a Home Assistant user who moved SecuritySpy to a new address,
I want to update the connection details in place,
So that I keep all my history and customizations. *(FR-29)*

**Acceptance Criteria:**

**Given** a configured entry
**When** the user opens reconfigure
**Then** host, port, and credentials can be changed and are validated before being saved

**Given** valid new connection details pointing at the same server
**When** the user submits them
**Then** the entry is updated and reloaded
**And** all devices, entities, and their recorded history are preserved

**Given** new connection details pointing at a *different* SecuritySpy server
**When** the user submits them
**Then** the flow aborts with a message explaining the mismatch, rather than orphaning every entity on the entry

---

## Epic 3: Resilience

The Mac reboots at three in the morning and nobody has to do anything.

### Story 3.1: Report unavailable rather than stale

As a Home Assistant user,
I want entities to say they do not know rather than showing me a value that is no longer true,
So that I never build an automation on a number that quietly stopped updating. *(FR-30)*

**Acceptance Criteria:**

**Given** a configured entry
**When** the SecuritySpy server becomes unreachable
**Then** all of that entry's entities report unavailable rather than retaining their last-known values

**Given** a reachable server
**When** a single camera goes offline
**Then** only that camera device's entities become unavailable
**And** the hub's entities and every other camera's entities are unaffected
**And** the offline camera is treated as unavailable rather than as an error requiring user action

**Given** a reachable server whose event stream has dropped
**When** availability is evaluated
**Then** poll-derived entities remain available, because the poll plane still holds truth
**And** the coordinator exposes a stream-health flag, and the base entity offers a push-derived variant that reports unavailable when that flag is down
**And** the variant's behavior is proven by test against a representative entity
*(Epic 5's presence entities declare themselves push-derived and inherit this; this story owns the mechanism.)*

**Given** the entity classes across every platform
**When** their availability logic is inspected
**Then** it is implemented once in the shared base entities and no platform overrides it

### Story 3.2: Recover from connection loss without being asked

As a Home Assistant user asleep at three in the morning,
I want the integration to notice the server went away and come back on its own,
So that a Mac reboot is not something I have to wake up and fix. *(FR-31)*

**Acceptance Criteria:**

**Given** an established connection
**When** the server's periodic heartbeat stops
**Then** the loss is detected within three missed heartbeats, a bounded and documented interval

**Given** a detected disconnection
**When** the integration responds
**Then** reconnection is attempted with exponential backoff, indefinitely, with no attempt limit

**Given** the server returns after an outage
**When** the integration reconnects
**Then** a full reconciliation cycle is triggered from the reconnect signal, refreshing all poll-derived state rather than resuming with whatever was last known
**And** recovery requires no Home Assistant restart, no config entry reload, and no re-authentication
*(Epic 4 hangs observation-value recovery off this same signal; this story owns the trigger.)*

**Given** each of a SecuritySpy restart, a Mac reboot, a network drop, and a Home Assistant upgrade
**When** they occur unattended
**Then** the integration is fully working afterwards with no manual intervention

### Story 3.3: Log problems once, not continuously

As a Home Assistant user,
I want an outage to produce a few log lines rather than thousands,
So that my log stays usable and I can still find real problems in it. *(FR-32)*

**Acceptance Criteria:**

**Given** a connection that is lost
**When** the loss occurs
**Then** it is logged exactly once at error level, naming the server

**Given** an ongoing outage with repeated reconnection attempts
**When** the log is inspected
**Then** retry attempts appear only at debug level
**And** a multi-hour outage produces a small, bounded number of non-debug log entries rather than a volume proportional to its length

**Given** the connection recovers
**When** recovery occurs
**Then** it is logged exactly once
**And** a subsequent loss-and-recovery cycle logs once each again, so the once-only behavior resets correctly

### Story 3.4: Unload and reload cleanly

As a Home Assistant user,
I want to remove or reload the integration without leaving anything behind,
So that reloading actually fixes things instead of compounding them. *(FR-33)*

**Acceptance Criteria:**

**Given** a loaded config entry
**When** it is unloaded
**Then** the event stream connection is closed and all scheduled polling is cancelled
**And** no task, connection, timer, or listener created by the integration survives

**Given** an unloaded config entry
**When** the user reloads it
**Then** it loads successfully without a Home Assistant restart
**And** repeated unload-reload cycles leave no accumulating tasks or connections

**Given** a config entry being removed entirely
**When** removal completes
**Then** its devices and entities are removed and nothing is left in the registries

---

## Epic 4: The Observation Record

Jensen asks whether a delivery came while he was out, and Home Assistant answers — last human, last vehicle, last animal seen, per camera, still correct after a restart.

### Story 4.1: Spike — when does SecuritySpy write classification to a capture?

As a builder,
I want to know whether SecuritySpy records an object classification at the moment a capture closes or some time afterwards,
So that the Observation Record's freshness claim is honest rather than guessed. *(Blocking gate for this epic; PRD Open Question 3)*

**Acceptance Criteria:**

**Given** the live reference server and a camera that can be triggered on demand
**When** a recording is provoked and the capture history is polled repeatedly from the moment the recording ends
**Then** the elapsed time between the capture appearing and its classification being populated is measured and recorded

**Given** the measurement
**When** it is written up
**Then** it states whether classification is present at capture close or lags, and by how long
**And** it states the consequence for restart correctness and for whether the capture's class set can lag the image by one poll
**And** the finding is recorded in the architecture memlog and the lookback and polling assumptions are confirmed or corrected

**Given** the spike concludes
**When** the result is unfavourable — classification lags substantially
**Then** the epic proceeds regardless, with the honest latency documented, because reconciliation remains correct even when it is not immediate

### Story 4.2: Per-class last-seen timestamps

As a Home Assistant user,
I want to see when a human, a vehicle, and an animal were each last seen on each camera,
So that I can answer "has anyone been in the driveway today" without opening SecuritySpy. *(FR-1, FR-4)*

**Acceptance Criteria:**

**Given** a configured server with capture history
**When** the integration has refreshed
**Then** each camera device exposes exactly three observation values, one per built-in object class
**And** each is typed as a timestamp, so Home Assistant renders it as a relative time and it works in automation conditions and templates

**Given** a camera with no capture of a given class within the lookback window
**When** its value is read
**Then** it is absent — not zero, not the epoch, not the current time

**Given** eleven cameras and three classes
**When** one refresh cycle runs
**Then** it issues at most three capture-history requests in total, batched across all cameras, rather than thirty-three
**And** the lookback window is finite, documented, and applied to every query

**Given** any observation value
**When** its provenance is traced
**Then** it derives from the capture history, and no code path lets a live event alone establish it

### Story 4.3: Correct immediately after a restart

As a Home Assistant user who just restarted Home Assistant,
I want the observation values to already be right,
So that I do not have to wait for the next detection to learn what happened this morning. *(FR-2)*

**Acceptance Criteria:**

**Given** a Home Assistant restart with SecuritySpy reachable
**When** the integration completes its first data refresh
**Then** all observation values are populated without waiting for any new detection

**Given** the same restart
**When** setup is timed
**Then** setup itself is not blocked waiting for hydration to finish

**Given** observation values recorded before a restart, with no new capture occurring in between
**When** they are read after the restart
**Then** they match what they were before

**Given** a Home Assistant restart that happens in the middle of an active detection
**When** the integration comes back
**Then** the observation values are neither corrupted nor blanked

### Story 4.4: Recover detections missed while disconnected

As a Home Assistant user whose server was unreachable for an hour,
I want the detections that happened during that hour to appear once it comes back,
So that a gap in connectivity is not a permanent gap in what I know. *(FR-3)*

**Acceptance Criteria:**

**Given** an event stream disconnection spanning one or more detections that SecuritySpy did record
**When** the connection is restored and reconciliation runs
**Then** the observation values reflect those detections
**And** no Home Assistant restart and no config entry reload is required

**Given** a reconciliation that finds a newer capture than the value currently held
**When** the merge runs
**Then** the value advances

**Given** a reconciliation that finds the authoritative history no longer contains a capture the current value was based on, because it was deleted on the server
**When** the merge runs
**Then** the poll result wins and the value is corrected, even though that moves it backwards

**Given** detections that SecuritySpy itself never recorded, because the camera's triggers did not allow it
**When** reconciliation runs
**Then** they are legitimately absent, and this is documented rather than treated as a defect

### Story 4.5: Latest capture as a fetchable image

As a Home Assistant automation author,
I want the most recent capture available at a stable Home Assistant URL,
So that I can hand it to a vision service and get back a sentence worth reading. *(FR-9, FR-10)*

**Acceptance Criteria:**

**Given** a camera with captures
**When** its device is viewed
**Then** it exposes a latest-capture image entity whose state is the timestamp of the capture it holds

**Given** the image entity
**When** an automation fetches it
**Then** the image is served by Home Assistant, requiring no direct reachability to the SecuritySpy server from the consumer
**And** the URL remains valid across image updates and across Home Assistant restarts
**And** the fetch returns the most recent capture known at fetch time

**Given** a new capture superseding the previous one
**When** the entity updates
**Then** its state changes to the new timestamp and is usable as a state trigger

**Given** a Home Assistant restart
**When** the entity initializes
**Then** its state reflects the newest existing capture, not an empty value and not the restart time

### Story 4.6: Read the object classes on the latest capture

As a Home Assistant automation author,
I want to know what SecuritySpy classified in the latest capture,
So that I can branch on it without re-analysing the image myself. *(FR-11)*

**Acceptance Criteria:**

**Given** a latest capture with a recorded classification
**When** the image entity is inspected
**Then** the set of object classes for that capture is readable alongside the image

**Given** a latest capture that SecuritySpy recorded no classification for
**When** the class set is read
**Then** it is empty rather than absent or erroneous

**Given** a capture classified with an object class outside the three built-ins
**When** the class set is read
**Then** that class appears as an ordinary string without error

### Story 4.7: Save the most recent recording to a file

As a Home Assistant automation author,
I want to save a camera's most recent recording to disk,
So that I can keep or forward the footage around an incident. *(FR-44)*

**Acceptance Criteria:**

**Given** a camera with a completed recording
**When** the service is called with that camera and a destination path
**Then** the most recent completed recording is written to that destination
**And** nothing on the SecuritySpy server is deleted or modified

**Given** a destination outside Home Assistant's permitted write paths
**When** the service is called
**Then** it fails with a validation error naming the problem, rather than a generic failure

**Given** a camera with no recording available, or an account without file permission
**When** the service is called
**Then** each produces a distinct, actionable, translated error
**And** user-input errors and operational failures are raised as distinct exception types

---

## Epic 5: Live Detection

The driveway narrates itself — presence to trigger on, and an event carrying confidence to reason about.

### Story 5.1: Per-class presence

As a Home Assistant user,
I want to trigger automations on whether a human, vehicle, or animal is present on a camera right now,
So that I can turn a light on when someone walks up the driveway. *(FR-5)*

**Acceptance Criteria:**

**Given** a configured camera
**When** its device is viewed
**Then** it exposes per-class presence for human, vehicle, and animal
**And** each is discoverable as an ordinary device trigger in the UI automation editor, requiring no attribute-name knowledge

**Given** a detection episode opening on a camera for a class
**When** presence is evaluated
**Then** that class's presence turns on, and it turns off when the episode closes

**Given** a stream of classification signals below the detection threshold, however frequent
**When** presence is evaluated
**Then** it does not turn on

**Given** isolated qualifying signals that do not meet the debounce count
**When** presence is evaluated
**Then** it does not flicker on

**Given** the reference volume of classification signals
**When** the Home Assistant state machine and recorder are observed
**Then** they receive writes per episode transition, not per signal

### Story 5.2: Classification event with peak confidence

As a Home Assistant automation author,
I want one event per detection carrying its class and confidence,
So that I can send the image and the confidence to a vision model and still degrade gracefully if that service is down. *(FR-6)*

**Acceptance Criteria:**

**Given** a detection episode for one class on one camera
**When** it completes
**Then** exactly one classification event fires for it — not one per classification signal

**Given** a fired event
**When** its payload is read
**Then** it carries the object class, the peak confidence for the episode, the camera, and where a capture resulted, a reference to the captured file

**Given** an episode whose confidence varied across its span
**When** the event's confidence is read
**Then** it is the maximum observed across the whole episode, not the value at the moment the threshold was crossed

**Given** the reference measurement of 191 classification signals on one camera in 95 seconds
**When** the resulting events are counted
**Then** they are on the order of one per episode

**Given** an object class outside the three built-ins
**When** an event fires for it
**Then** the payload carries it without any schema change

### Story 5.3: Motion presence that clears itself

As a Home Assistant user,
I want motion detection that turns off on its own,
So that a camera which never reports motion ending does not leave me permanently in motion. *(FR-7)*

**Acceptance Criteria:**

**Given** a configured camera
**When** its device is viewed
**Then** it exposes motion presence, typed as motion for Home Assistant, independent of any classification

**Given** motion signals that stop arriving
**When** the inactivity timeout elapses
**Then** motion presence clears without any dependence on the server signalling motion end

**Given** the reference camera that produced 467 motion signals and zero motion-end signals in 95 seconds
**When** motion stops
**Then** motion presence still clears

**Given** the inactivity timeout
**When** a user changes it
**Then** it has a documented default and takes effect without a Home Assistant restart

### Story 5.4: Tune detection globally and per camera

As a Home Assistant user with both indoor and outdoor cameras,
I want to set detection sensitivity once and override it for individual cameras,
So that a busy kitchen does not force me to mistune my driveway. *(FR-8)*

**Acceptance Criteria:**

**Given** a configured entry
**When** the user opens its options
**Then** detection threshold and detection debounce are both settable, without removing and re-adding the entry

**Given** a per-camera override is set
**When** detection runs for that camera
**Then** the override applies to it and the global value applies to every camera without one

**Given** any of these values is changed
**When** the change is saved
**Then** it takes effect without a Home Assistant restart and without reloading the entry

**Given** a fresh installation on the reference system
**When** no tuning is performed at all
**Then** the shipped defaults produce working presence

### Story 5.5: Trigger events with decoded reasons

As a Home Assistant automation author,
I want to know when SecuritySpy decided to record and why,
So that I can act on the reason without decoding a bitmask myself. *(FR-43)*

**Acceptance Criteria:**

**Given** a camera on which SecuritySpy triggers a recording
**When** the trigger occurs
**Then** a trigger event fires on that camera device

**Given** a fired trigger event
**When** its payload is read
**Then** the reason is a decoded, human-meaningful value — motion, audio, per-class movement, arrival, departure, manual, and the other reasons the server encodes — and never a raw bitmask

**Given** a trigger reason the server can emit but which is disabled in SecuritySpy
**When** the integration runs
**Then** that reason simply never fires, and its absence is not logged as an error

### Story 5.6: Draft the blueprints against the real entity surface

As a builder,
I want to write both canonical blueprints now, against the entities that actually exist,
So that an awkward blueprint tells me the entity model is wrong while it is still cheap to change. *(Design test for FR-37; PRD §12)*

**Acceptance Criteria:**

**Given** the entity surface produced by this epic and Epic 4
**When** both blueprints are drafted — notify with a picture when a person is seen, and capture an image when a person is detected
**Then** each is written using typed entity selectors filtered to this integration, with no hardcoded entity IDs

**Given** the drafts
**When** they are reviewed
**Then** neither requires the author to know an attribute name or read integration source code
**And** any place where a blueprint had to work around the entity model is recorded as an entity-model defect with a proposed fix, not worked around silently

**Given** a defect is found
**When** it is assessed
**Then** it is fixed in this epic if it changes entity structure, since such changes are effectively permanent once released

### Story 5.7: Spike — Custom Model event payload shape

As a builder,
I want to know what a user-supplied CoreML model actually emits on the event stream,
So that the decision to create entities for custom classes rests on evidence rather than hope. *(Gate for FR-35; PRD Open Question 1)*

**Acceptance Criteria:**

**Given** a camera configured with a custom model
**When** its event stream output is captured
**Then** the payload shape for custom-model classifications is recorded, including how class labels and confidences appear

**Given** the reference system has no camera running a custom model
**When** that precondition cannot be met
**Then** the spike is recorded as unrunnable and Story 5.8 defers to v2 automatically, with no decision meeting required
**And** the open classification vocabulary already shipped still lets custom-model users write automations against the raw event

**Given** the payload proves unusable for reliable entity creation
**When** that is concluded
**Then** Story 5.8 defers to v2 on the same terms

### Story 5.8: Entities for Custom Model classes

As a Home Assistant user running a custom CoreML model,
I want presence entities for the classes my model emits,
So that my custom classes are as usable as the built-in ones. *(FR-35 — conditional on Story 5.7)*

**Acceptance Criteria:**

**Given** Story 5.7 confirmed a usable payload shape
**When** a custom model emits a class the integration has not seen before
**Then** that class is discovered at runtime and a presence entity is created for it on that camera

**Given** a discovered custom class
**When** its presence is evaluated
**Then** it follows the same detection threshold and debounce rules as the built-in classes

**Given** a class that stops being emitted during a session
**When** the session continues
**Then** its entity is not removed automatically

**Given** a user with no custom model
**When** they use the integration
**Then** they see no additional entities

**Given** a custom class whose normalized key would collide with an existing entity key
**When** it is discovered
**Then** it is skipped with a single warning rather than silently merged into the existing entity

---

## Epic 6: Control SecuritySpy

Arm, enable, and tune cameras from Home Assistant — without ever destroying the configuration built in SecuritySpy.

### Story 6.1: Arm and disarm each mode independently

As a Home Assistant user,
I want to arm and disarm continuous capture, motion capture, and actions separately per camera,
So that I can express what I actually want rather than a single lossy armed-or-not state. *(FR-12, FR-13)*

**Acceptance Criteria:**

**Given** a camera whose account has arming permission
**When** its device is viewed
**Then** it exposes three independent arming controls, one per mode, each categorized as configuration rather than a primary control

**Given** any one of the three controls
**When** it is toggled
**Then** the other two are unchanged
**And** all eight combinations of the three modes are reachable

**Given** an arming change made from Home Assistant
**When** the resulting server state is inspected
**Then** the camera's schedule assignment in SecuritySpy is unchanged
**And** no Home Assistant action exists that can create, edit, or delete a schedule

**Given** the arming controls
**When** their behavior and documentation are reviewed
**Then** the override's bounded transience — at most six hours, or until the next scheduled event, after which the schedule resumes — is stated rather than implied to be permanent

### Story 6.2: Control state follows the server

As a Home Assistant user who sometimes changes things in the SecuritySpy app directly,
I want Home Assistant to reflect what the server actually says,
So that my dashboard never lies to me about the state of a camera. *(FR-14)*

**Acceptance Criteria:**

**Given** an arm mode changed in the SecuritySpy application
**When** the next reconciliation cycle runs
**Then** Home Assistant reflects the change, without a restart or a reload

**Given** an arm mode changed from Home Assistant
**When** SecuritySpy is inspected
**Then** the change is present there

**Given** a control whose optimistic local state disagrees with what the server subsequently reports
**When** reconciliation runs
**Then** the server's value wins
**And** Home Assistant does not indefinitely report a control state that contradicts the server

**Given** another client such as the vendor's app changes a setting concurrently
**When** reconciliation runs
**Then** that change is picked up, because the integration does not assume it is the only client

### Story 6.3: See which schedule governs a camera

As a Home Assistant user,
I want to see which schedule is governing each arm mode,
So that I understand why a camera is armed without being able to break my schedule configuration. *(FR-15)*

**Acceptance Criteria:**

**Given** a configured camera
**When** its device is viewed
**Then** the active schedule for each arm mode is readable

**Given** a user who has defined their own schedules in SecuritySpy
**When** the schedule values are read
**Then** they reflect the user's own schedules, populated dynamically from the server, not a fixed built-in list

**Given** any Home Assistant surface
**When** a user attempts to change the schedule
**Then** no control permits it

### Story 6.4: Enable and disable a camera

As a Home Assistant user,
I want to enable and disable a camera in SecuritySpy from Home Assistant,
So that I can take a camera out of service without opening the Mac app. *(FR-16)*

**Acceptance Criteria:**

**Given** a configured camera
**When** its device is viewed
**Then** it exposes an enable control reflecting SecuritySpy's enabled state, categorized as configuration

**Given** the control is turned off
**When** SecuritySpy is inspected
**Then** the camera is disabled there

**Given** a disabled camera
**When** its other entities are viewed
**Then** they report unavailable rather than stale values

**Given** the control is toggled
**When** the write is inspected
**Then** no unrelated camera setting is disturbed

### Story 6.5: Choose which classes cause recording

As a Home Assistant user,
I want to control which object classes make SecuritySpy record, per camera,
So that my observation record reflects the driveway rather than kitchen movement. *(FR-17)*

**Acceptance Criteria:**

**Given** a configured camera
**When** its device is viewed
**Then** it exposes a detection-trigger control for human, vehicle, and animal, each categorized as configuration

**Given** a trigger control is toggled
**When** SecuritySpy is inspected and then restarted
**Then** the change is present and survives the restart

**Given** one trigger control is written
**When** the camera's other settings are compared before and after
**Then** none of them changed

### Story 6.6: Adjust per-class sensitivity

As a Home Assistant user,
I want to tune how sensitive SecuritySpy's own detection is for each class per camera,
So that I can reduce noise at its source rather than filtering it downstream. *(FR-18)*

**Acceptance Criteria:**

**Given** a configured camera
**When** its device is viewed
**Then** sensitivity is adjustable for human, vehicle, and animal, each categorized as configuration

**Given** a sensitivity value
**When** the user sets it
**Then** it is constrained to the range SecuritySpy accepts, and out-of-range values are rejected before being sent

**Given** a sensitivity change
**When** SecuritySpy is inspected and then restarted
**Then** the change is present and survives the restart

**Given** these controls and the integration's own detection threshold
**When** their names and documentation are reviewed
**Then** the two are clearly distinguished, because one governs what SecuritySpy records and the other what Home Assistant counts as a detection

### Story 6.7: Tell the user when per-class triggering is off

As a Home Assistant user on a default SecuritySpy install,
I want to be told that my observation record is empty because per-class triggering is switched off,
So that I do not conclude the integration is broken. *(FR-45)*

**Acceptance Criteria:**

**Given** a SecuritySpy install where every configured camera has all per-class detection triggers disabled
**When** the integration evaluates this
**Then** it detects the condition and surfaces guidance naming the setting and where to change it, in SecuritySpy or through this integration's own controls

**Given** the guidance is shown
**When** the user dismisses it
**Then** it stays dismissed

**Given** any per-class detection trigger is subsequently enabled on any camera
**When** the integration re-evaluates
**Then** the guidance does not recur

**Given** the detected condition
**When** the integration responds
**Then** it never enables a detection trigger on the user's behalf

---

## Epic 7: Ship It

A stranger installs it from HACS, sets it up unaided, and imports a working blueprint in under a minute.

### Story 7.1: Install from HACS as a custom repository

As a prospective user who found this on a forum,
I want to install it through HACS by pasting a URL,
So that I do not have to copy files into my configuration directory by hand. *(FR-36)*

**Acceptance Criteria:**

**Given** the repository
**When** a user adds it to HACS as a custom repository
**Then** it installs without any manual file copying

**Given** the installation completes and Home Assistant restarts
**When** the user opens Add Integration
**Then** SecuritySpy appears in the list

**Given** the repository
**When** its structure is validated
**Then** it satisfies the HACS custom-repository requirements, including a single integration under `custom_components/`, the required manifest keys, and brand assets
**And** a minimum supported Home Assistant version is declared and enforced
**And** the HACS validation action passes in CI

### Story 7.2: Import a working automation in one click

As a new user,
I want to import a working notification automation from a link in the README,
So that I get value in my first minute rather than after an hour of YAML. *(FR-37)*

**Acceptance Criteria:**

**Given** the repository
**When** its blueprints are inspected
**Then** two ship — notify with a picture when a person is seen, and capture an image when a person is detected
**And** each carries a canonical source URL so Home Assistant can re-import updates
**And** each uses typed entity selectors filtered to this integration, with no hardcoded entity IDs

**Given** the README
**When** a user views it
**Then** each blueprint has a working one-click import link, verified against a clean Home Assistant instance

**Given** a user imports either blueprint
**When** they fill in the inputs and save
**Then** they get working behavior without editing YAML, reading source, or knowing any attribute name

**Given** the blueprint documentation
**When** it describes timing
**Then** it does not imply the latest capture is available sub-second, since a recording completes only after its post-roll

### Story 7.3: Verify Bronze in CI and cut the release

As a maintainer,
I want the full Bronze rule set enforced automatically on every change,
So that quality does not depend on me remembering, and the release gate is objective. *(FR-38)*

**Acceptance Criteria:**

**Given** the integration repository
**When** CI runs on any change
**Then** hassfest and the Home Assistant pylint plugin both run, together covering every machine-checkable Bronze rule including the parallel-updates check that moved out of hassfest
**And** the HACS validation action runs
**And** a scheduled run executes independently of pushes, so upstream Home Assistant changes surface before a user finds them

**Given** the quality scale declaration in the repository
**When** it is reviewed
**Then** every Bronze rule is marked satisfied or explicitly exempted with a stated reason

**Given** the config flow module
**When** coverage is measured in CI
**Then** it is 100%, including every error and abort path, and CI fails below that

**Given** the documentation
**When** it is reviewed
**Then** it covers the high-level description, installation, removal, provided actions, and configuration parameters

**Given** all of the above passing
**When** the release is cut
**Then** a tagged GitHub release is published as the HACS custom-repository release, with no public forum announcement accompanying it

### Story 7.4: Reach Silver, then announce

As a maintainer,
I want to announce publicly only once the integration is genuinely stable,
So that the first wave of real users does not become the beta test that burns me out. *(FR-39)*

**Acceptance Criteria:**

**Given** the repository after the Bronze release
**When** the Silver rule set is evaluated
**Then** every Silver rule is satisfied or explicitly exempted with a stated reason, declared in the repository

**Given** the test suite
**When** coverage is measured across all integration modules
**Then** it exceeds the Silver threshold, and CI enforces it

**Given** the Silver behavioral rules
**When** they are checked against the implementation
**Then** unavailability logging, entity unavailability, and reauthentication each satisfy their corresponding rule, as already built in earlier epics

**Given** all Silver rules pass
**When** the announcement is made
**Then** it goes to the Ben Software forum and the Home Assistant community forum
**And** the claim is phrased as meeting the rule set as verified by the project's own tooling in CI, never as certified
