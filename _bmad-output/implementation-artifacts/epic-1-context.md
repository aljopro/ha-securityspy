# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Build `aiosecurityspy`: a standalone, published Python library through which a developer can talk to a SecuritySpy server from an ordinary script — query server and camera configuration, read capture history, consume the live event stream without hanging, decode what SecuritySpy actually means, and write settings safely — with Home Assistant nowhere in sight. This epic comes first because retrofitting a library after protocol parsing has been written inside an integration is a large, thankless refactor that blocks the Bronze quality tier, and because a maintained SecuritySpy library is the project's durable contribution: nobody else has one. Everything downstream depends on the library owning every wire format and endpoint URL in the system.

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

## Requirements & Constraints

- The library is published on PyPI from a public repository under an OSI-approved license, built in CI from source, with published versions corresponding to tagged releases. Consumers depend on it as an ordinary versioned dependency.
- It is fully async, fully typed with type information shipped to consumers, passes strict type checking, and accepts a caller-provided HTTP session rather than creating its own. These constraints exist to keep the highest quality tiers reachable later.
- It must be usable with no Home Assistant present anywhere on the system, and must contain no Home Assistant imports.
- The classification vocabulary is open: unknown Object Classes emitted by Custom Models must parse and carry through as ordinary strings. Nothing may reject a class outside the built-in human/vehicle/animal set.
- Credential safety is a live hazard, not a precaution: the server's settings responses contain per-camera device credentials in plaintext. Settings payloads must never be logged at any level, credentials must never appear in log lines, exception messages, stack traces, or URLs that escape the library, and diagnostics must pass through a single anonymizer.
- Destructive and remote-execution capabilities (capture deletion, shell/shortcut execution) are excluded from the public surface entirely — not wrapped, not private-but-present.
- Success is validated by the library being installable from PyPI and usable in a plain script with no Home Assistant involved.

## Technical Decisions

- **The library is the sole owner of protocol knowledge.** CR-only stream framing, all endpoint URLs, capture-list field decoding (folder date plus seconds-since-midnight into absolute time, classification bitmask into a class set), permission and trigger bitmask decoding, the schedule model, the boolean read/write asymmetry (read one encoding, write another), credential handling, and the anonymizer all live here and nowhere else. Consumers must never need to know a URL or a wire format.
- **Frozen, fully-typed models with `from_api()` constructors.** Raw dicts never cross the library boundary. Camera numbers are `int` everywhere, never stringly-typed. Timestamps are timezone-aware `datetime` (UTC internally); absent means `None`, never epoch or zero.
- **Typed exception hierarchy** (connect, auth, permission, unsupported-version) is the only thing that escapes; no raw HTTP-client exception may leak. The library never counts auth failures, never persists auth state, and never initiates re-authentication — that ownership sits with consumers.
- **Stream lifecycle is owned by the library**: CR framing, heartbeat watch with loss declared after three missed beats, indefinite exponential backoff, and explicit connected / disconnected / reconnected / auth_failed callbacks. On auth failure it pauses reconnection and defers. `disconnect()` is idempotent and cancels every task, timer, and socket.
- **The episode reducer is a pure component** — no I/O, no timers of its own, no network or Home Assistant imports. Threshold and debounce are injected per camera and per class rather than being module constants, and it operates over arbitrary class strings.
- **Writes are direct single-key partial POSTs**, verified non-destructive against the ~120 other settings on the page. No read-modify-write cache. Arming writes the transient override only; no method may mutate a schedule assignment, and schedules are read-only data.
- **Class names entering permanent keys pass through one `class_slug()` normalization** provided by the library (lowercase, `[a-z0-9_]`).
- **Efficiency shapes the API**: capture history is one batched request per class across all cameras, using the server-side class filter — never cameras × classes. A light status endpoint (~794 B) exists alongside the heavy system-info payload (~27 KB); expose both so consumers can poll cheaply.
- **Stack:** Python ≥ 3.14, `src/` layout with hatchling, `pyproject.toml` only, uv, ruff, mypy `--strict`, aiohttp `>=3.12,<4` as an injected session, GitHub Actions with PyPI trusted-publisher OIDC (no stored tokens). Tests use recorded protocol fixtures and must not import Home Assistant.
- **Backward compatibility within the epic:** later stories extend models additively; no existing field may change name, type, or meaning. Health and optional fields degrade to `None` on missing, malformed, or nonsensical values rather than failing the surrounding decode.

## Cross-Story Dependencies

- Story 1.1 (skeleton, typing, CI, publishing) precedes everything else.
- Story 1.2 (client, session injection, exception hierarchy, models) is the base that 1.4, 1.6, 1.8, 1.9 and 1.10 extend.
- Story 1.3 (stream client, typed events, open class handling) feeds 1.5's reducer, which consumes classification signals.
- Story 1.7's anonymizer must cover the settings payloads surfaced by 1.6.
- Stories 1.8–1.10 were added after 1.1–1.7 landed, on discovering that health fields, the cheap status poll, capture media endpoints, schedule names, and the camera-enable write had never been assigned to any story. They are hard blockers for downstream epics, not conveniences: 1.8 gates the server/camera health and status work in Epic 2; 1.9 gates the Latest Capture image and recording download in Epic 4; 1.10 gates the schedule select and camera-enable control in Epic 6. Each must land before its consumer story is dispatched.
