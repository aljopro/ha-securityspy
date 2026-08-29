# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Build `aiosecurityspy`, a standalone, fully-typed async Python library on PyPI that owns all SecuritySpy protocol knowledge — querying cameras and Capture History, consuming the live Event Stream without hanging, decoding what the server actually means — usable from an ordinary script with Home Assistant nowhere in sight. It comes first because retrofitting protocol parsing out of an integration later is the large refactor that blocks Bronze, and because a maintained SecuritySpy library is the project's durable contribution (FR-40…FR-42, FR-34).

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

- Independently published PyPI package, OSI-licensed, built in public CI from source, released from semver tags with the tag matching the published version exactly; importable with no HA installed (FR-40).
- Fully async; accepts a caller-provided aiohttp session and never creates/closes one; ships type information and passes `mypy --strict` (FR-41). Python `>=3.14`, aiohttp `>=3.12,<4`, hatchling, `src/` layout.
- Credential-safe by construction: no username/password/token/camera-device credential in any log line (including debug), exception message, or diagnostics output; settings payloads never logged at any level (FR-42, AD-13).
- Object Class is open string data — unknown classes parse and carry without error; the three built-ins are constants, never a closed enum (FR-34, AD-9).
- Destructive and remote-execution endpoints (capture deletion, `doShell`, `doShortcut`) are absent from the public surface entirely — not wrapped, not private-but-present (AD-2).
- No Home Assistant imports anywhere in the library; raw aiohttp exceptions never escape (AD-6).
- Wire-shape correctness is verified against captured real-server payloads (live 6.21 fixtures), not fixtures authored to match a guess.

## Technical Decisions

- **AD-2 protocol containment:** CR-only event-stream framing, endpoint URLs, `caplist` decoding (`f`+`s` → absolute time, `o` classification bitmask), permission/trigger bitmask decoding, the schedule model, bool read/write asymmetry (JSON `true/false` read, `1/0` write), and the anonymizer live only here. Settings writes are form-urlencoded POSTs whose body begins with the literal sentinel `formData`, camera number in the body, verified non-destructive.
- **AD-3 episode reducer:** a pure, configurable component — Classification Signals in, Detection Episodes out (open/close + Peak Confidence), with Detection Threshold and Debounce injected per camera per class; no I/O, no timers, no HA imports. The ~190:1 reduction is the requirement, not an optimization.
- **AD-6 exception taxonomy:** typed hierarchy (`SecuritySpyAuthError`, `SecuritySpyConnectError`, `SecuritySpyPermissionError`, `SecuritySpyUnsupportedVersionError`). Verified on 6.21: the server cleanly separates 401 (who you are) from 403 (what you may do) — permission denial must never collapse into auth error; parse numeric status only (reason phrases are unreliable). A 401 from media endpoints can mean permission-denied, not bad credentials.
- **AD-9 open vocabulary:** Object Class is `str` end-to-end; `class_slug()` normalization (lowercase, `[a-z0-9_]`) is the library's single key-sanitizer.
- **AD-11 stream lifecycle:** the library owns CR framing, heartbeat watch (loss declared after 3 missed heartbeats ≈ 30 s), indefinite exponential backoff, and `connected`/`disconnected`/`reconnected`/`auth_failed` callbacks; `auth_failed` pauses reconnection (never retries in a loop) until the caller resumes; `disconnect()` is idempotent and cancels everything.
- **AD-13 anonymizer:** single declared credential-shaped key set, extensible in one place; redaction is by category (PII/secret/password), including `setPass`/`fsPass`/`quitPass`, `wan-address`, `deviceList`, and both `auth=` forms.
- **AD-19 single implementation:** the library is the only thing that speaks SecuritySpy; the integration consumes it as a pinned versioned dependency. Endpoint URLs and response shapes are known only inside the library.
- **Models:** frozen, fully-typed dataclasses with `from_api()` constructors; raw dicts never cross the library boundary; absent fields decode to `None`, never fabricated; timestamp-aware datetimes, never epoch/zero.
- **Verified wire facts (6.21) that shape decoding:** event-stream records and capture times are the server's local wall clock — decode with the server's published offset (`seconds-from-gmt`/`current-local-time`), which is an offset, not a timezone (story 1.13). `++camStatus` (cheap health: `num`/`enabled`/`online`/`open`/`err`/`errDesc`) and `++systemInfo` enumerate different camera sets — a disabled camera vanishes from `systemInfo` but not `camStatus`; `systemInfo` is the inventory of record. Permissions mask varies per camera (rights intersected with camera capability), never collapsed to one account-level set. `caplist`'s `m` is a float in megabytes. `t` means different things in `caplist` vs `clip` — enums must not be shared. Schedule/preset ids are neither small nor sequential (may exceed int32).

## Cross-Story Dependencies

- Library stories gate downstream epic consumers and must land before their consumer is dispatched: 1.8 gates Epic 2 stories 2.4/2.5 (health/update), 1.9 gates Epic 4 stories 4.5/4.7 (image/download), 1.10 gates Epic 6 stories 6.3/6.4 (schedule visibility, camera enable).
- 1.11 protects FR-27 (reauth) and FR-28 (permission-aware entities); 1.12 hard-blocks FR-1 and every camera-scoped requirement; 1.13 protects FR-1…FR-8.
- The in-tree copy (`ha-securityspy/aiosecurityspy/`) and the standalone published repo must stay in sync: a library change is verified against the integration via the editable path dependency in the same commit, while `manifest.json` pins the released PyPI version — the two must agree at release (AD-19).