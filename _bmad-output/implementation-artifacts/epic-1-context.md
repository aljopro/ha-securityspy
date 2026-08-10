# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Build `aiosecurityspy`: a standalone, async, fully-typed Python library that owns everything that knows SecuritySpy exists — transport, stream framing, field and bitmask decoding, the signal-to-episode reducer, and credential anonymization — usable from an ordinary script with Home Assistant nowhere present. It comes first because protocol parsing written inside an integration cannot be retrofitted into a library without the large refactor that blocks the Home Assistant Bronze quality tier, and because a maintained SecuritySpy library is the project's durable contribution: none exists today.

## Stories

- Story 1.1: Publishable library skeleton
- Story 1.2: Authenticated client with injected session
- Story 1.3: Event stream client with CR framing and heartbeat
- Story 1.4: Capture history decoding
- Story 1.5: Detection episode reducer
- Story 1.6: Settings, arming, and permission decoding
- Story 1.7: Credential-safe diagnostics

## Requirements & Constraints

- The library is a separately published, OSI-licensed PyPI package built in public CI, so the integration can depend on it as an ordinary versioned dependency.
- Fully async; the caller provides the HTTP session — the library never creates one. Type information ships to consumers and passes strict type checking.
- The classification vocabulary is open: arbitrary object classes carry through unchanged, with no enumeration, literal type, or validation rejecting an unknown class.
- No credential ever appears in a log line, exception message, string representation, traceback, or diagnostics dump. Settings payloads are never logged at any level, including debug.
- Errors must distinguish transient failure, authentication failure, and permanent incompatibility so callers can decide what is retryable.
- Signal reduction of roughly 190:1 is a correctness requirement, not an optimization.
- Capture-history queries must not scale as cameras x classes; one request must cover many cameras.
- Success is proven by installing from PyPI into a bare virtual environment and using the library in a script with no Home Assistant present.

## Technical Decisions

- **Layer boundary (AD-2):** all protocol knowledge lives here and only here — endpoint URLs, stream framing, capture-field decoding, permission and trigger bitmasks, the schedule model, the settings read/write asymmetry, credential handling, the anonymizer. Zero Home Assistant imports anywhere.
- **Excluded surface (AD-2):** destructive and remote-execution endpoints (capture deletion, shell execution, shortcut execution) are absent from the public API entirely — not wrapped, not private-but-present.
- **Exception hierarchy (AD-6):** a typed hierarchy (connect / auth / permission / unsupported-version) that no raw transport exception escapes. The library never counts auth failures, never persists auth state, never initiates reauthentication — that is the consumer's job.
- **Stream lifecycle (AD-11):** the library owns framing, heartbeat watching (loss after three missed ~10 s heartbeats), indefinite exponential backoff, and explicit `connected` / `disconnected` / `reconnected` / `auth_failed` callbacks. On auth failure it pauses reconnection rather than looping. `disconnect()` is idempotent and cancels everything.
- **Reducer (AD-3):** a pure component — no I/O, no timers, no network — taking classification signals to episodes with threshold and debounce injected per camera per class. Episodes report peak confidence across the whole span, not the value at threshold crossing.
- **Data models (AD-15):** frozen, fully-typed dataclasses with `from_api()` constructors; raw dicts never cross the library boundary. Camera number is `int` everywhere, never stringly-typed. Timestamps are timezone-aware UTC; absent means `None`, never epoch or zero.
- **Object class (AD-9):** `str` end-to-end; built-in classes are constants, not a closed type. A single `class_slug()` normalizer (lowercase, `[a-z0-9_]`) is the only path a class name takes into any permanent key.
- **Anonymizer (AD-13):** one redaction path driven by a single declared key set extensible in one place; credential-bearing URLs are constructed only inside the library.
- **Protocol traps to design against:** stream lines are CR-terminated only, so a standard readline hangs — named the single most likely implementation bug. A stream event whose camera field is non-numeric means "not camera-specific" rather than invalid. Capture history supports server-side class filtering and stores a classification bitmask; absolute time reconstructs from a folder date plus seconds-since-midnight. Settings writes are partial form-encoded POSTs whose body must open with a literal sentinel and carry the camera number in the body, with booleans written as 1/0 but read back as JSON true/false — the asymmetry is handled inside the library, never at a call site. Arming writes target a bounded transient override via a concatenated mode-letter string; no schedule-mutating method may exist. Two same-named type fields on different endpoints mean different things and must not share an enumeration.
- **Stack and packaging (AD-14):** greenfield, no starter template. `src/` layout, hatchling, `pyproject.toml` only, `requires-python >= 3.14`, uv for environments, ruff and mypy `--strict` as gates, `py.typed` marker, aiohttp declared as a dependency but session-injected. Release from semver tags via GitHub Actions with PyPI trusted-publisher OIDC and no stored token.
- **Testing:** protocol fixtures from recorded frames and anonymized real captures; no Home Assistant test tooling in this repository.

## Cross-Story Dependencies

- Story 1.1 gates everything else: the package skeleton, typing gates, and CI must exist before any protocol code lands.
- Stories 1.2, 1.3, 1.4, and 1.6 all depend on the shared typed models, constants, and exception hierarchy introduced with the client in 1.2.
- Story 1.5 consumes the typed classification events produced by 1.3 but stays pure — it must remain testable from synthetic signals alone.
- Story 1.7's anonymizer covers payloads produced across 1.2, 1.4, and 1.6, so it lands after those payload shapes are known.
- Every later epic depends on this one. Epic 2 consumes the client, models, exception hierarchy, and permission decoding; Epic 3 consumes the stream lifecycle callbacks and backoff; Epic 4 consumes batched class-filtered capture-history queries; Epic 5 consumes the episode reducer and open class vocabulary; Epic 6 consumes the settings, arming, and trigger-decoding surface. The integration pins this library as a versioned dependency, so its published API is effectively a contract from first release.
