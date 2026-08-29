# AGENTS.md

This file provides guidance to AI coding agents (Claude Code and others) when working with code in this repository.

## What this repo is

Two things in one repo, deliberately separate:

- `custom_components/securityspy/` — a Home Assistant custom integration (HACS-distributed, not on PyPI).
- `aiosecurityspy/` — an async, fully-typed Python client library for Ben Software's SecuritySpy HTTP/event API, also mirrored as a standalone GitHub repo (`aljopro/aiosecurityspy`, published to PyPI). See [aiosecurityspy-repo-split memory] for how commits get ported between the subtree and the standalone repo.

**All SecuritySpy protocol knowledge lives in the library, never in the integration** (AD-2). The integration contains zero wire-format knowledge; destructive SecuritySpy endpoints are absent from the library's public surface entirely.

## Commands

There are **two independent `pyproject.toml`/test suites with incompatible pytest configs** (root uses `asyncio_mode = "auto"` for `pytest-homeassistant-custom-component`; the library uses `asyncio_mode = "strict"` with `filterwarnings = ["error"]`). Running the wrong one against the wrong tests fails at collection/setup, not with a normal test failure — always scope explicitly:

```bash
# Integration tests (from repo root)
uv run pytest -q
uv run pytest tests/test_config_flow.py -q          # single file
uv run pytest tests/test_config_flow.py::test_name -q  # single test

# Library tests — MUST run from inside aiosecurityspy/, never `pytest aiosecurityspy/tests` from root
uv run --directory aiosecurityspy pytest -q
# or: cd aiosecurityspy && uv run pytest -q

# Lint / format / types (run in both the root and aiosecurityspy/ as needed)
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict custom_components tests        # root
uv run mypy --strict src tests                      # inside aiosecurityspy/

# Library-only: validate the OpenAPI description, build distributions
uv run --directory aiosecurityspy python -c "from openapi_spec_validator import validate; from openapi_spec_validator.readers import read_from_filename; validate(read_from_filename('docs/securityspy-openapi.yaml')[0])"
uv run --directory aiosecurityspy uv build
```

Tests import the in-repo library via an editable path source (`aiosecurityspy = { path = "aiosecurityspy", editable = true }` in the root `pyproject.toml`), so a library change is verified against the integration in the same commit — never bump `manifest.json`'s pinned `aiosecurityspy==` version without a matching change here.

## Documentation map — read before writing code

Don't guess at protocol or architecture decisions; they're written down and a story should not re-litigate them. Start at [docs/index.md](docs/index.md), which routes to the right document. The essentials:

- **[docs/ha-integration-reference.md](docs/ha-integration-reference.md)** — HA integration patterns written the way *this* project's architecture requires (file structure, `runtime_data`, push-fed coordinator, config/reauth/reconfigure flows, exception taxonomy, quality-scale rules). Read before touching `custom_components/`.
- **`_bmad-output/planning-artifacts/research/securityspy-api-reference.md`** — the reverse-engineered SecuritySpy 6.x API (endpoints, event framing, bitmask decoding, arming model). This supersedes the vendor's own docs where they disagree. Read before touching `aiosecurityspy/`.
- **`_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md`** — binding architecture decisions AD-1…AD-18. If a story needs a decision not here, it's either in the spine's Deferred section or it's a hole to surface, not invent.
- **[aiosecurityspy/docs/securityspy-openapi.yaml](aiosecurityspy/docs/securityspy-openapi.yaml)** — machine-readable OpenAPI 3.1 description of the wire API, with `x-verification` markers (`live-6.21` / `client-source` / `research-only`) per operation; CI fails if one is missing.

## Non-negotiable architecture decisions

1. **The event stream is never the source of persistent truth** (AD-1). Persistent state derives only from the capture-history poll plane; push may only advance state, never originate it.
2. **All protocol knowledge lives in `aiosecurityspy`** (AD-2), never in `custom_components/`.
3. **Identity is server UUID + camera number** (AD-5) and is permanent — never key off address or name.
4. **Object Class is an open string, never a fixed enum** (AD-9) — labels come from user-trained CoreML models.
5. **Credentials never reach logs or diagnostics** (AD-13) — SecuritySpy's settings endpoint returns camera passwords in plaintext, so this is a live hazard, not a precaution.
6. **`hass.data[DOMAIN]` is forbidden** — use `entry.runtime_data` with a typed `ConfigEntry[...]` alias (Bronze `runtime-data` rule, machine-checked by hassfest).
7. **The coordinator is push-fed with no polling interval** (AD-4) — call `async_set_updated_data()` when the event stream delivers, don't pass `update_interval`.
8. **`aiosecurityspy` never owns an aiohttp session** — the caller (Home Assistant, or a script) creates and injects it; the library has no `close()`.

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

### `aiosecurityspy/src/aiosecurityspy/`
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
