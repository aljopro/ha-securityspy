# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A Python developer can talk to a SecuritySpy server from an ordinary script — query its cameras and capture history, consume its live event stream without the client hanging, and decode what SecuritySpy actually means — with Home Assistant nowhere in sight. This epic exists first because retrofitting a library after writing protocol parsing inside an integration is the large, thankless refactor that blocks Bronze, and because a maintained SecuritySpy library is the project's durable contribution: nobody else has one. It owns all protocol knowledge (wire formats, endpoint URLs, bitmask decoding) so that no other part of the system needs to know them.

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

## Requirements & Constraints

- The library is a standalone, OSI-licensed, publicly-built PyPI package, fully async, accepting a caller-provided HTTP session, and never creating its own session.
- It ships strict type information (a `py.typed` marker, `mypy --strict` clean) and must import successfully with no Home Assistant present anywhere on the system.
- It carries an open classification vocabulary: arbitrary Object Class strings must pass through unmodified, with no enum or fixed set anywhere rejecting an unknown class.
- Credentials must never appear in exception messages, tracebacks, log output at any level (including debug), or settings payloads. Redaction must be driven by a single, extensible declared key set, and default to redacting unrecognized fields rather than disclosing them.
- Errors must distinguish transient failure, authentication failure, permission denial, and permanent incompatibility — including cases where the server answers `401` for what is actually a permission problem, so callers don't loop on reauth for correct credentials.
- Capture-history queries must use server-side class filtering and cover multiple cameras in one request, never one request per camera.
- Timestamps must reconstruct as timezone-aware datetimes using the server's own UTC offset, not an assumed UTC, with documented behavior when the offset is unavailable or the caller states its own timezone.
- The event stream is CR-terminated only (no LF) — the single most likely implementation bug — and must never block waiting for a newline. Heartbeat loss must be declared after three missed heartbeats, with indefinite exponential-backoff reconnection distinct from auth failure (which pauses rather than loops).
- Settings writes are partial POSTs: body must start with a literal sentinel, carry the camera number in the body, and never disturb unrelated settings. Boolean read/write encoding asymmetry (`1`/`0` on write, `true`/`false` on read) must be handled inside the library only.
- Arming writes target the transient override only; no library method may mutate a schedule assignment, and no arming call may put `schedule=` in the query string.
- The public API surface must exclude destructive and remote-execution endpoints entirely (capture deletion, shell/shortcut execution) — this is a permanent exclusion, not a story-level judgment call.
- Cheap endpoints must be preferred for polling health (`camStatus` at ~794 B) over expensive ones (`systemInfo` at ~27 KB); a camera-list call already holding membership must only re-poll the cheap endpoint.
- Permission-scoped results (camera lists, writes) must reflect exactly what the configured account may see or do — a disabled camera and a permission-withdrawn camera must be indistinguishable by construction.

## Technical Decisions

- Greenfield scaffold, no starter template: `src/` layout, `pyproject.toml` with hatchling as build backend, uv-managed environments, ruff + `mypy --strict`, GitHub Actions CI with PyPI trusted-publisher OIDC (no stored API token). `requires-python >= 3.14`.
- All protocol knowledge (endpoint URLs, wire formats, bitmask layouts) lives exclusively in this library; nothing downstream may know a wire format or URL.
- A typed exception hierarchy maps every failure mode (connect, auth, permission, unsupported-version) — no raw `aiohttp` exception may ever escape the library.
- The signal-to-episode reducer is a pure component: no I/O, no timers, no network or Home Assistant imports; threshold and debounce are injected per camera and per Object Class, not module constants.
- Frozen, typed models throughout (server info, camera, capture, health, permissions, trigger reasons) — decoding must tolerate missing/malformed fields by falling back to `None` rather than failing the whole decode, and must fail loudly (not silently return an empty inventory) when an envelope shape is unrecognized.
- Capture size decodes as a fractional megabyte float, not a truncated integer.
- The RTSP live-video relay is a library component: it rewrites a captured real `DESCRIBE`/`SETUP`/`PLAY` exchange so consumers (go2rtc, ffmpeg, VLC, Frigate) get a stream URL with no userinfo/`auth=` and never see SecuritySpy's real address; UDP `SETUP` and unknown identifiers are refused and logged without the credential-bearing path.
- Live still images are fetched from the library with header (Basic) authentication only — no userinfo or `auth=` in the URL, never extracted from the live stream; only cameras visible to the account are addressable, and optional size/quality arguments are validated before any request.
- Later stories in this epic (1.8–1.10) exist because story 1.2 implemented "at minimum server UUID, version, camera count, camera list" literally, leaving health fields, the cheap `camStatus` poll, capture media, `schedule-list`, and the camera-enable write unassigned — these are hard blockers for Epic 2, 4, and 6 stories and must land before their consumers are dispatched.

## Cross-Story Dependencies

- Story 1.5 (episode reducer) and 1.6 (settings/arming/permission decoding) both depend on 1.2's client and models.
- Stories 1.8, 1.9, 1.10 were retrofitted after 1.1–1.7 to cover gaps found by auditing against Epics 2, 4, and 6; they hard-block Stories 2.4, 2.5, 4.5, 4.7, 6.3, and 6.4 in those later epics.
- Story 1.11 and 1.14 (permission vs. authentication disambiguation) protect FR-27/FR-28, consumed by Epic 2's reauthentication and permission-aware entity creation.
- Story 1.12 (real-server camera inventory decoding) hard-blocks FR-1 and every camera-scoped requirement across all later epics.
- Story 1.13 (server timezone) protects the correctness of FR-1 through FR-8, used throughout Epic 4 and Epic 5.
- Story 1.16 (mode-selecting arming write) is a prerequisite for Epic 6's arming controls (FR-12, FR-13).
- Stories 1.19 (RTSP relay) and 1.20 (live still image) are both consumed by Epic 2's live-video camera entities (Story 2.6, FR-22). Story 1.20 reuses 1.14's media-`401` rule and the 1.18/1.19 visible-cameras-only rule.
- This epic must complete before Epic 2 (Connect and Model), since the architecture forbids the integration from knowing any wire format or endpoint URL — the library is a hard prerequisite for every other epic.
