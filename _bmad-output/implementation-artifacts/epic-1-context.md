# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A Python developer can talk to a SecuritySpy server from an ordinary script — query its cameras and capture history, consume its live event stream without the client hanging, and decode what SecuritySpy actually means — with Home Assistant nowhere in sight. This epic exists first because retrofitting a library after writing protocol parsing inside an integration is the large, thankless refactor that blocks Bronze, and because a maintained, standalone SecuritySpy library is the project's durable contribution.

## Stories

- Story 1.1: Publishable library skeleton
- Story 1.2: Authenticated client with injected session
- Story 1.3: Event stream client with CR framing and heartbeat
- Story 1.4: Capture history decoding
- Story 1.5: Detection episode reducer
- Story 1.6: Settings, arming, and permission decoding
- Story 1.7: Credential-safe diagnostics
- Story 1.8: Server and camera health decoding
- Story 1.9: Capture media fetch
- Story 1.10: Schedule names and the camera enable write
- Story 1.11: A permission denial is not an authentication failure
- Story 1.12: Decode the camera inventory a real server actually sends
- Story 1.13: Timestamps use the server's own timezone
- Story 1.14: A 401 can mean permission, not bad credentials
- Story 1.15: Capture size is megabytes, and fractional
- Story 1.16: Mode selects which capture modes a write targets
- Story 1.17: Redact secrets and identifying detail, not just credentials
- Story 1.18: One call for the cameras you may see, in their current state
- Story 1.19: Relay live video without handing out credentials
- Story 1.20: Fetch a camera's live still image
- Story 1.21: Spike — do SecuritySpy API keys replace credentials on every path the library uses?
- Story 1.22: Close Story 1.21's unmet sub-ACs and decide on shape-based key detection

## Requirements & Constraints

Covers FR-40 (standalone published PyPI library), FR-41 (async, typed, injectable-session library), FR-42 (credential-safe diagnostics), and FR-34 (open classification vocabulary — no enum or fixed set anywhere rejects an unrecognized Object Class). Library-side stories also protect downstream requirements they don't own: correct permission-vs-auth error distinction (protects FR-27/FR-28), correct wall-clock decoding (protects FR-1..FR-8), and credential-free live video/still-image access (FR-22).

The library must be installable from PyPI and importable with no Home Assistant present (validated by SM-9). `requires-python >= 3.14`. CI runs ruff and `mypy --strict` with zero findings; releases publish via PyPI trusted-publisher OIDC, no stored API token, OSI-licensed. No method may exist for deleting captures or executing shell commands/shortcuts on the server — those endpoints are excluded from the public surface entirely.

Two spike gates apply within this epic's late stories: whether SecuritySpy's `caplist.o` field populates at capture close or later (gates Epic 4's freshness claim, tracked as a Phase-2 gate elsewhere) and Story 1.21/1.22's own gate on 6.22 API keys — if no 6.22 test server is available, PRD Open Question 11 stays open and the RTSP relay remains the shipped design; no further decision is required until evidence exists.

## Technical Decisions

- All protocol knowledge lives in `aiosecurityspy` (AD-2); `ha-securityspy` consumes it as an ordinary versioned dependency and never copies, vendors, subclasses, or wraps library types to add or correct protocol behavior — a wrong or missing behavior is fixed in the library, never worked around in the adapter.
- Event stream lines are CR-terminated only (0x0D, no LF) — the single most likely implementation bug; a standard `readline()` hangs.
- The `caplist` `o` field is a classification bitmask decoded into a set of class strings (empty classification → empty set, never `None`); absolute time reconstructs from `f` (folder date) + `s` (seconds since midnight), using the server's own UTC offset rather than assumed UTC.
- Settings writes are partial POSTs whose body must begin with the literal sentinel `formData`, carry `cameraNum` in the body (never the query string), and handle the boolean write/read asymmetry (`1`/`0` on write, `true`/`false` on read) inside the library only.
- Arming writes use `++ssSetSchedule` targeting the transient override only, expressed as independent booleans per capture mode; no library method mutates a schedule assignment, and no query string may ever contain `schedule=` (AD-7).
- Per-camera `permissions` and per-class trigger-reason bitmasks decode into typed, named structures, not raw integers; an inverted-sense permission (set = deny) is never reported as granted, and a disabled-but-definable reason bit simply doesn't appear.
- The episode reducer (signal → detection episode) is a pure component: no I/O, no timers, no HA/network imports, injected threshold and debounce per camera and per class, reporting peak (not threshold-crossing) confidence. Target reduction ratio ~190:1.
- A single declared credential-shaped key set drives anonymization (AD-13), extendable in one place; unrecognized fields default to redacted, not disclosed. Settings payloads never appear in logs at any level.
- Credential and identifying-network-detail containment (AD-13, widened) applies to the RTSP relay and still-image fetch: URLs the library hands out never carry userinfo or `auth=`, and no password or its base64 form may appear in any log record at any level.
- Two-repository split (AD-14): `aiosecurityspy` (library, PyPI OIDC release, HACS forbids more than one integration per repo) is fully separate from `ha-securityspy`. Bronze gates release; Silver gates public announcement — decided in Epic 7, not here.
- API keys (SecuritySpy 6.22b9+) are a reopened design question (PRD Open Q11): resource-scoped tokens were previously superseded by the RTSP relay, then reopened when 6.22 added per-account keys. Story 1.21/1.22 exist purely to gather evidence and make one recommendation; no key-authentication path is implemented inside either story.

## Cross-Story Dependencies

- Stories 1.8–1.10 backfill gaps discovered by auditing 1.1–1.7 against Epics 2, 4, and 6: health fields, the cheap `camStatus` poll, capture media endpoints, `schedule-list`, and the camera-enable write were never assigned to a story. These are hard blockers — because the architecture forbids the integration from knowing any wire format or endpoint URL, Stories 2.4, 2.5, 4.5, 4.7, 6.3, and 6.4 cannot be dispatched until their corresponding 1.8–1.10 story lands.
- Story 2.6 (live video entities) depends directly on Stories 1.19 (RTSP relay) and 1.20 (live still image).
- Story 1.22 follows Story 1.21 and exists specifically to close the sub-ACs 1.21 left explicitly open (partial-password-shape lock-out, key regenerate/delete response, cross-permission camera visibility); it makes the one recommendation 1.21 deferred (adopt shape-based key detection now, or keep deferring) but implements neither outcome itself. PRD Open Question 11 stays "reopened" unless 1.22's recommendation is to close it.
- Story 1.11 and 1.14 both refine the same permission-vs-authentication distinction (1.11 for general endpoints, 1.14 specifically for media/scheduling endpoints answering `401`); both protect FR-27/FR-28, consumed later by Epic 2's reauth flow (Story 2.8).
- Story 1.16's mode-scoped arming write is a prerequisite for Epic 6's arming controls (FR-12, FR-13).
- Story 1.18's permission-scoped camera list with stateless health refresh underlies FR-28 (Epic 2, Story 2.7's entity-gating mechanism).
