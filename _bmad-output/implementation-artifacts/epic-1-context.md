# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Build and publish `aiosecurityspy`, a standalone, async, fully-typed Python library that talks to a SecuritySpy server with Home Assistant nowhere in sight: querying cameras and capture history, consuming the live event stream without hanging, and decoding what SecuritySpy actually means (bitmasks, schedules, settings asymmetries, timestamps). This epic ships first because retrofitting protocol parsing out of an integration after the fact is the large refactor that blocks Bronze quality-scale compliance, and because a maintained SecuritySpy library is this project's durable, reusable contribution — nobody else has one. Every later epic depends on this library and must never duplicate or work around its knowledge of the wire protocol.

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

## Requirements & Constraints

- The library is a separately published PyPI package, OSI-licensed, built in CI from a tagged release via trusted-publisher OIDC (no stored API token), importable with no Home Assistant present anywhere on the system.
- Fully async; accepts a caller-provided HTTP session rather than creating its own; ships type information and passes strict type checking; `requires-python >= 3.14`.
- Object Class is open string data end-to-end, never a closed enumeration — an unrecognized class (e.g. from a Custom Model) must parse and carry through without error or disruption to built-in classes, and adding a new class requires no schema change.
- Credentials (usernames, passwords, tokens, per-camera device credentials) must never appear in logs at any level, diagnostics output, exception messages, or stack traces. A single anonymizer, driven by one declared/extensible credential-key set, is the only path diagnostics take out of the library.
- Destructive and remote-execution server capabilities (capture deletion, shell/shortcut execution) are excluded from the public API surface entirely — not wrapped, not private-but-present.
- Authentication failure and permission failure must be distinguishable without parsing a message string, so a least-privileged account is never told to re-enter a correct password.
- Reference scale for the episode reducer: ~191 per-frame classification signals for one 95-second subject crossing must reduce to exactly one episode (~190:1 ratio), reporting peak confidence across the whole span.

## Technical Decisions

- **All protocol knowledge lives in this library and nowhere else** (AD-2, AD-19): CR-framed stream parsing, endpoint URLs, `caplist` field decoding, permission/trigger bitmask decoding, the schedule model, the settings bool read/write asymmetry (JSON `true/false` read, `1/0` write), and credential handling are library-only. The integration must never parse wire formats, copy library code, or compensate for a library gap with a local workaround — a missing capability is a library change, released and pinned, before the consuming feature lands.
- **Exception hierarchy** (AD-6): the library raises its own typed exceptions — `SecuritySpyConnectError`, `SecuritySpyAuthError`, `SecuritySpyPermissionError`, `SecuritySpyUnsupportedVersionError` — and never lets a raw `aiohttp` exception escape or imports Home Assistant.
- **Stream client** (AD-11): owns CR framing, heartbeat watch (loss declared after 3 missed heartbeats, ~30s), indefinite exponential backoff, and emits explicit `connected` / `disconnected` / `reconnected` / `auth_failed` callbacks; `auth_failed` pauses reconnection rather than retrying in a loop; `disconnect()` is idempotent and cancels everything.
- **Settings writes** (AD-8): a single-key partial POST per change, verified non-destructive against the ~120 other settings on the page; body-based (not query-string) camera number; no read-modify-write caching.
- **Arming model**: writes target the transient Arm Override only (bounded duration or next scheduled event); the three capture modes are independent booleans (all eight combinations expressible); no library method mutates a schedule assignment in this epic.
- **Object Class normalization** (AD-9): class strings pass through the library's single `class_slug()` function wherever they enter a permanent key; `HUMAN`/`VEHICLE`/`ANIMAL` are constants, not a closed type.
- **Data models**: frozen, fully-typed dataclasses with `from_api()` constructors; raw dicts never cross the library boundary; timestamps are timezone-aware `datetime`, decoded using the server's own published UTC offset rather than an assumed UTC, with the daylight-saving limitation documented.
- **Camera inventory decoding must be validated against a captured real-server payload**, not only an author-written fixture, and an unrecognized envelope shape must surface as a decode failure rather than a silently empty inventory.
- **Stack**: `src/` layout, hatchling, `pyproject.toml`-only, uv, ruff, `mypy --strict`, GitHub Actions with PyPI trusted-publisher OIDC; aiohttp is caller-injected (`>=3.12,<4`); test fixtures come from recorded protocol frames (HAR / captured streams), not hand-authored ones.

## Cross-Story Dependencies

- Stories 1.8–1.10 were added after 1.1–1.7 landed because auditing the library against Epics 2, 4, and 6 found health fields, the cheap camera-status poll, capture media endpoints, schedule names, and the camera-enable write had never been assigned to a story. These are hard blockers, not conveniences: Story 1.8 gates Epic 2's Stories 2.4/2.5, Story 1.9 gates Epic 4's Stories 4.5/4.7, and Story 1.10 gates Epic 6's Stories 6.3/6.4.
- Story 1.5 (episode reducer) is consumed directly by Epic 5 (Live Detection); raw per-signal data must never reach a consumer's state machine.
- Story 1.4 (capture history) and Story 1.13 (timezone-correct timestamps) together are what makes Epic 4's Observation Record correct immediately after a Home Assistant restart.
- Story 1.7 (diagnostics anonymizer) and Story 1.11 (permission vs. auth distinction) are both consumed by the integration's exception-mapping seam (AD-6) and by Epic 2/3's reauth and error-reporting flows.
- No story in this epic may add Home Assistant imports or depend on anything outside the library; every downstream epic depends on this one, never the reverse.
