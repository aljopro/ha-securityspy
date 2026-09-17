# Epic 1 Context: The SecuritySpy API Library

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

A Python developer can talk to a SecuritySpy server from an ordinary script — query its cameras and capture history, consume its live event stream without the client hanging, and decode what SecuritySpy actually means — with Home Assistant nowhere in sight. This library is the project's durable contribution and is a hard prerequisite for the integration: retrofitting protocol parsing out of the integration later would block Bronze.

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

## Requirements & Constraints

- Live video must reach Home Assistant with no SecuritySpy credential ever appearing in a stream source, a log at any level, or diagnostics (FR-22, FR-41, FR-42).
- Destructive and remote-execution SecuritySpy endpoints are excluded from the library's public surface entirely.
- The library owns all wire-format knowledge (CR-only event-stream framing, `caplist` field decoding, permission/trigger bitmasks, the schedule model, the settings read/write asymmetry, the diagnostics anonymizer) — the integration must never know an endpoint URL or wire format.
- A `401` can mean a missing permission rather than bad credentials; exception mapping must distinguish these (Story 1.14, carried into any new auth path).
- Only cameras/resources the authenticated account may actually see are addressable; permission-denied and disabled-camera cases must be indistinguishable by construction (Story 1.18).
- The library must be independently installable from PyPI and usable in a plain script with no Home Assistant present (SM-9).

## Technical Decisions

- **AD-13 (Credential and identity containment):** the concern is egress (diagnostics, logs at every level, issue reports, exception messages), not the LAN. Default is non-disclosure — anything PII, secret, or password-shaped is redacted or encrypted, judged by category rather than a fixed field list. A credential-bearing URL (the `auth=` query parameter, base64 or otherwise) may only be constructed inside the library's RTSP relay, on its own upstream connection to SecuritySpy — never returned from a public API, stored, or logged. Consumers get either a relay address or a credential-free `unsecured_stream_url()`. Any value that can't be withheld must be recorded in a disclosure register (field, artifact, reason, reduced form used).
- **Under review as of 2026-09-16 (ties to PRD Open Q11):** SecuritySpy 6.22b9+ adds per-account API keys (shown as `API_` + 32 base62 characters; used as an HTTP Basic-auth password, or historically proposed as `auth=API_…` though live testing found the raw query form rejected — base64-wrapped works). A key is a secret under AD-13 and must be redacted like a password. Story 1.21 is the spike that determines whether/how the library's auth path changes; **the relay and username/password path are retained regardless**, since servers older than 6.22 have no keys — any key support is additive, not a replacement.
- The library is versioned and released independently (PyPI, semver tags, OIDC trusted publishing) and pinned as a dependency by the integration (AD-14).

## Cross-Story Dependencies

- Story 1.21 depends on Stories 1.19 (RTSP relay) and 1.20 (still-image fetch) as the concrete auth call sites to test against a live server.
- Story 1.21's findings gate any future change to FR-22, Story 1.19, Story 1.20, or Story 2.6 (the integration's live-video entity) — such a change goes back through a sprint-change-proposal, not directly into this spike.
