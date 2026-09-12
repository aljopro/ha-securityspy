# AGENTS.md

This file provides guidance to AI coding agents (Claude Code and others) when working with code in this repository.

## What this repo is

- `custom_components/securityspy/` — a Home Assistant custom integration (HACS-distributed, not on PyPI).
- Its SecuritySpy protocol client, `aiosecurityspy`, is **not** in this repo. It lives entirely in the standalone `aljopro/aiosecurityspy` repo, published to PyPI, and this repo always consumes the published package (AD-14) — see "Working with `aiosecurityspy`" below.

**All SecuritySpy protocol knowledge lives in the library, never in the integration** (AD-2). The integration contains zero wire-format knowledge; destructive SecuritySpy endpoints are absent from the library's public surface entirely.

## Commands

```bash
# Integration tests
uv run pytest -q
uv run pytest tests/test_config_flow.py -q          # single file
uv run pytest tests/test_config_flow.py::test_name -q  # single test

# Lint / format / types
uv run ruff check .
uv run ruff format --check .
uv run mypy custom_components tests

# The manifest's aiosecurityspy pin must exist on PyPI
uv run --no-project python scripts/check_library_pin.py
```

## Working with `aiosecurityspy`

`aiosecurityspy` is developed in its own repo, at `/Users/jensen/projects/aiosecurityspy` locally (`aljopro/aiosecurityspy` on GitHub) — never here. This repository's `pyproject.toml` dev dependency and `custom_components/securityspy/manifest.json`'s `requirements` pin the **exact same** published version; bump both together, never one without the other (`scripts/check_library_pin.py` enforces the manifest half exists on PyPI).

**To change the library:** make the change in the standalone repo, run its own gates there (ruff, ruff format, mypy --strict, pytest), bump its `pyproject.toml` version, and cut a release the same way as any other (`git tag vX.Y.Z`, push, then a GitHub Release — its `publish.yml` runs the gates again and publishes via PyPI trusted-publisher OIDC). Then bump the pin here to match and re-run this repo's tests.

**To test an unreleased library change against this integration**, without waiting for a stable release: publish it from the standalone repo as a PyPI **pre-release** (e.g. `0.2.1a1` — `pip`/`uv` never resolve a pre-release unless pinned to that exact version, so this cannot leak to a real user). Point this repo's `manifest.json` requirement and `pyproject.toml` dev dependency at that exact pre-release version, `uv sync`, and run the tests here. Once the real release ships, bump both pins to the stable version and never leave a pre-release pin in place on `main`.

**Never** hand-copy library source into this repo, and never re-add a local editable path source (`[tool.uv.sources]`) for it — that was the previous arrangement (an in-tree subtree) and it drifted from the standalone repo by 1,620 lines with nothing going red before it was replaced by the always-published-package model above.

## Documentation map — read before writing code

Don't guess at protocol or architecture decisions; they're written down and a story should not re-litigate them. Start at [docs/index.md](docs/index.md), which routes to the right document. The essentials:

- **[docs/ha-integration-reference.md](docs/ha-integration-reference.md)** — HA integration patterns written the way *this* project's architecture requires (file structure, `runtime_data`, push-fed coordinator, config/reauth/reconfigure flows, exception taxonomy, quality-scale rules). Read before touching `custom_components/`.
- **`_bmad-output/planning-artifacts/research/securityspy-api-reference.md`** — the reverse-engineered SecuritySpy 6.x API (endpoints, event framing, bitmask decoding, arming model). This supersedes the vendor's own docs where they disagree. Read before touching anything that consumes `aiosecurityspy`, or before changing the library itself in its own repo.
- **`_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md`** — binding architecture decisions AD-1…AD-20. If a story needs a decision not here, it's either in the spine's Deferred section or it's a hole to surface, not invent.
- **`aiosecurityspy/docs/securityspy-openapi.yaml`** in the standalone repo — machine-readable OpenAPI 3.1 description of the wire API, with `x-verification` markers (`live-6.21` / `client-source` / `research-only`) per operation, validated by that repo's own CI.

## Non-negotiable architecture decisions

1. **SecuritySpy owns creation; this integration interacts** (AD-20). This is not a second SecuritySpy UI. SecuritySpy defines and creates its objects — cameras, schedules, everything it exposes; Home Assistant discovers them, reads them, and acts on them. Before adding any surface, ask whether it *creates a SecuritySpy object or acts on one that exists* — creation is out by default and takes an AD-20 amendment, never a story-level call.
2. **The event stream is never the source of persistent truth** (AD-1). Persistent state derives only from the capture-history poll plane; push may only advance state, never originate it.
3. **All protocol knowledge lives in `aiosecurityspy`** (AD-2), never in `custom_components/`.
4. **Identity is server UUID + camera number** (AD-5) and is permanent — never key off address or name.
5. **Object Class is an open string, never a fixed enum** (AD-9) — labels come from user-trained CoreML models.
6. **Credentials never reach logs or diagnostics** (AD-13) — SecuritySpy's settings endpoint returns camera passwords in plaintext, so this is a live hazard, not a precaution.
7. **`hass.data[DOMAIN]` is forbidden** — use `entry.runtime_data` with a typed `ConfigEntry[...]` alias (Bronze `runtime-data` rule, machine-checked by hassfest).
8. **The coordinator is push-fed with no polling interval** (AD-4) — call `async_set_updated_data()` when the event stream delivers, don't pass `update_interval`.
9. **`aiosecurityspy` never owns an aiohttp session** — the caller (Home Assistant, or a script) creates and injects it; the library has no `close()`.

## Vocabulary

Use these terms verbatim in code, comments, docs, and translation strings — introducing a synonym is a discipline violation (the PRD Glossary, §4, is authoritative): *SecuritySpy Server, Hub Device, Camera Device, Config Entry, Event Stream, Capture History, Capture, Object Class, Custom Model, Classification Signal, Detection Episode, Detection Threshold, Detection Debounce, Peak Confidence, Observation Record, Latest Capture, Arm Mode, Arm Schedule, Arm Override, Detection Trigger, API Library.*

## Protocol gotchas (aiosecurityspy)

These have each caused real bugs and are easy to reintroduce:

- **Event-stream lines are CR-terminated only** — a standard `readline()` hangs forever. This is the single most likely bug in any SecuritySpy client.
- **Settings write bodies must begin with the literal sentinel `formData`** (not a `key=value` pair), and use `1`/`0` where JSON reads return `true`/`false`.
- **The `t` field means different things in `caplist` vs. `clip`** — their enums must not be shared.
- **A 401 from the media endpoint can mean permission-denied, not bad credentials** — don't collapse that into `SecuritySpyAuthError`.
- **Event-stream timestamps are bare local wall-clock with no UTC offset** — the library refuses to guess; callers must decode the server's own published offset and pass `server_timezone` explicitly.
- **`event.camera is None`** means the record wasn't camera-specific (wire sends `X`), not that it's invalid.
- **`event.event_number` restarts at 0 on every reconnect** — never key off it, only record it.
- **On 401/403 the event stream pauses rather than retrying** — `on_auth_failed` fires once and nothing resumes it until `stream.resume()` is called explicitly.

## Code architecture

### `aiosecurityspy` (the published package this repo depends on, developed in its own repo)
- `client.py` — `SecuritySpyClient`, the HTTP surface (session-injected, never creates/closes one).
- `connection.py` — low-level HTTP transport/auth handling shared by client and stream.
- `stream.py` — the event-stream reader: CR framing, heartbeat watchdog, exponential backoff, lifecycle callbacks (`on_connected`/`on_disconnected`/`on_reconnected`/`on_auth_failed`).
- `events.py` — event/payload types decoded off the stream (e.g. `StreamEvent`, `ClassificationPayload`).
- `episodes.py` — the detection-episode reducer (turns a run of classification events into a bounded episode with peak confidence).
- `models.py` — data models (`ServerInfo`, camera info, etc.).
- `diagnostics.py` — credential-safe diagnostics/redaction helpers (AD-13).
- `exceptions.py` — the typed error hierarchy (`SecuritySpyAuthError`, `SecuritySpyPermissionError`, `SecuritySpyConnectError`, `SecuritySpyCertificateError`, `SecuritySpyUnsupportedVersionError`, `SecuritySpyError`) that the integration maps to HA config-entry exceptions in exactly one place.
- `const.py` — protocol constants (e.g. `DEFAULT_PORT`), re-exported by the integration's `const.py` rather than restated.

### `custom_components/securityspy/`
- `__init__.py` — `async_setup_entry`/`async_unload_entry`; the one seam that maps library exceptions to `ConfigEntryAuthFailed` / `ConfigEntryError` / `ConfigEntryNotReady` (AD-6). Currently `PLATFORMS: list[Platform] = []` — no coordinator or entity platforms exist yet (deferred to a later story per the file's own docstring); don't assume `sensor.py`, `coordinator.py`, etc. exist without checking.
- `config_flow.py` — UI-only config flow, no YAML/discovery; validates against the live server before creating an entry, keys the entry on server UUID (AD-5) so a re-add by different address aborts instead of duplicating.
- `const.py` — `DOMAIN` plus protocol constants re-exported from `aiosecurityspy`.

The target end-state file structure (coordinator, entity base, platforms) is documented in ha-integration-reference.md §1 — treat it as where this is going, not what exists today.

## Testing conventions

- `tests/conftest.py` patches `SecuritySpyClient` at **both** its import sites (`config_flow.py` and `__init__.py`) with one shared `MagicMock`, so a `side_effect` set once stays in force across a flow that ends by setting the entry up. Follow this pattern for any new module that imports the client.
- `enable_custom_integrations` is autoused — required for HA test tooling to load anything from `custom_components/`.
- The library's test suite has `filterwarnings = ["error"]` — a bare deprecation warning fails the run.

## BMAD / bmad-loop workflow

This repo uses BMAD skills (see `.claude/skills/bmad-*`) for spec-driven development, and `.bmad-loop/` runs an autonomous dev loop against `_bmad-output/planning-artifacts/epics.md` and per-story specs in `_bmad-output/implementation-artifacts/spec-*.md`. A spend-limit hitting mid-loop looks identical to a dev timeout at first glance — see the `bmad-loop-spend-limit-failure-mode` memory before assuming a stalled run is a bug. Story completion is tracked in `_bmad-output/implementation-artifacts/sprint-status.yaml` and marked done via commits like `docs(spec): mark story N.N done`.
