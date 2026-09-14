---
title: 'Story 2.6 — Live video without exposing credentials'
type: 'feature'
created: '2026-09-13'
status: 'done'
baseline_revision: '21a93924'
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '39d2a6e8'
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** No `camera` platform exists, so SecuritySpy cameras can't be watched in Home Assistant. The only ways to get video today put the SecuritySpy password in an RTSP URL.

**Approach:** Give each camera device a `camera` entity. Its stream source is a credential-free address from the library's `RtspRelay` (`aiosecurityspy` 0.4.0, story 1.19). Its still image comes from `client.async_get_camera_image` (story 1.20). A new options flow toggles `create_camera_entities` (default on); changing it reloads the entry.

## Boundaries & Constraints

**Always:**
- `CONF_CREATE_CAMERA_ENTITIES = "create_camera_entities"` in `const.py`, read as `entry.options.get(..., True)`.
- The relay is created in `async_setup_entry` after the server fetch, and only while the option is on and `server.rtsp_port is not None`.
  - Create it with `client.create_rtsp_relay(server)` (loopback bind, library defaults), then `await relay.async_start()`, then `entry.async_on_unload(relay.async_stop)`.
  - It is stored as `SecuritySpyRuntimeData.relay: RtspRelay | None`.
  - An `OSError` from `async_start` logs one warning without its detail, and `relay` becomes `None`. Setup still succeeds.
- `SecuritySpyCamera(SecuritySpyCameraEntity, Camera)` in `camera.py`:
  - One per camera in `coordinator.data.server.cameras`. The inventory is already limited to cameras the account may view live (DW-5).
  - Entity key `camera`, so the unique ID is `{uuid}_{number}_camera`. `_attr_name = None`, so the entity takes the device name. Enabled by default.
  - Call `Camera.__init__` explicitly, since `Camera` needs its own init.
- `supported_features` is `CameraEntityFeature.STREAM` when `relay` is not `None`, otherwise `0`.
- `stream_source()` returns `relay.stream_url(camera_number)`. It returns `None` when there is no relay, or when `stream_url` raises `SecuritySpyPermissionError` or `ValueError` (e.g. a camera added after the relay was built).
- `async_camera_image(width, height)` returns `(await client.async_get_camera_image(coordinator.data.server, camera_number, width=width)).data`. On any `SecuritySpyError` it returns `None`, with at most a debug log containing only the exception's class name.
- When the option is off, `camera.async_setup_entry` adds no entities and removes this entry's `camera`-domain registry entries. Turning the option back on recreates them with the same unique IDs.
- Opening the relay's listener sends nothing to SecuritySpy. The entity never calls `stream_source` or the image method on its own (no polling, no preload).
- `Platform.CAMERA` is added to `PLATFORMS`. `camera.py` sets `PARALLEL_UPDATES = 0`.

**Block If:**
- Meeting an AC appears to need a credential in a URL or log, a library change, or a runtime dependency beyond `aiosecurityspy==0.4.0`.

**Never:**
- `unsecured_stream_url`, `auth=` URLs, or any URL built in the integration.
- Frame extraction from the stream for stills, go2rtc/WebRTC-specific code, a diagnostics platform, or a dynamic-camera listener. The last is a pre-existing deferred gap: new cameras need a reload.
- Changes to other integrations' entities, or to existing sensor and update behaviour.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Fresh setup | 2 cameras, `rtsp_port=8000`, default options | 2 enabled camera entities with STREAM; relay started once; no image or stream call made | None |
| Stream requested | Entity asked for `stream_source()` | Relay URL `rtsp://127.0.0.1:<port>/<id>` | None |
| Still image | `async_camera_image(width=320)` | Library called with `width=320`; returns bytes | None |
| Image failure | Library raises `SecuritySpyConnectError` / `SecuritySpyAuthError` | `None` | No password or base64 in logs |
| No RTSP | `rtsp_port=None` | Entities exist, features `0`, `stream_source` is `None`; no relay | None |
| Relay bind fails | `async_start` raises `OSError` | Setup succeeds, features `0`, one warning | Warning without detail |
| Unknown camera | `stream_url` raises `SecuritySpyPermissionError` | `stream_source` is `None` | None |
| Option off | Options flow sets `create_camera_entities=False` | Entry reloads; camera entities removed; no relay created | None |
| Option back on | Set to `True` | Entities return with the original unique IDs | None |
| Unload | Entry unloaded | `relay.async_stop` awaited | None |

</intent-contract>

## Code Map

- `custom_components/securityspy/__init__.py` -- `PLATFORMS`, `SecuritySpyRuntimeData`, `async_setup_entry` (relay creation goes after the coordinator is created, before forwarding), `async_unload_entry`.
- `custom_components/securityspy/const.py` -- add the option constant.
- `custom_components/securityspy/config_flow.py` -- `SecuritySpyConfigFlow` (user step only). Add `async_get_options_flow` and the options flow, using `OptionsFlowWithReload` if the installed HA provides it, otherwise an update listener that reloads.
- `custom_components/securityspy/entity.py` -- `SecuritySpyCameraEntity(coordinator, camera_number, key)`, reused as-is.
- `custom_components/securityspy/camera.py` -- **new** platform.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- `options.step.init` with the `create_camera_entities` label ("Create live video entities") and description. No new entity name is needed (`_attr_name = None`).
- `tests/conftest.py` -- `mock_client_class` (autospec). Add a relay mock: `create_rtsp_relay` returns a `MagicMock` with `async_start`/`async_stop` as `AsyncMock`, and `stream_url` returns a fixed `rtsp://127.0.0.1:…` URL. `make_server_info*` gets an `rtsp_port: int | None = 8000` kwarg.
- `tests/test_camera.py`, `tests/test_config_flow.py`, `tests/test_init.py` -- new and extended tests.

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/const.py` -- add `CONF_CREATE_CAMERA_ENTITIES`.
- [x] `custom_components/securityspy/__init__.py` -- relay lifecycle, the `relay` runtime field, `Platform.CAMERA`.
- [x] `custom_components/securityspy/camera.py` -- entity and setup, including registry cleanup when the option is off.
- [x] `custom_components/securityspy/config_flow.py` -- options flow with a reload on change.
- [x] `custom_components/securityspy/strings.json`, `translations/en.json` -- options strings, kept identical.
- [x] `tests/conftest.py` -- relay mock and the `rtsp_port` kwarg.
- [x] `tests/test_camera.py` -- one test per matrix row. Also a caplog sweep at DEBUG over setup, image failure, auth failure, and an unreachable server, asserting `MOCK_USER_INPUT`'s password and its base64 `user:pass` form never appear.
- [x] `tests/test_config_flow.py` -- options flow shows the default, saves the value, and reloads the entry.
- [x] `tests/test_init.py` -- relay started on setup, stopped on unload, skipped when the option is off or `rtsp_port` is `None`, and bind failure tolerated.

**Acceptance Criteria:**
- Given a fresh installation, when setup completes, then each camera has an enabled camera entity on its camera device, and no `stream_url` or image call has been made.
- Given an entity, when HA asks for its stream and still image, then the stream is the relay URL and the image comes from `async_get_camera_image`.
- Given the full suite, when the verification commands run, then all pass with 100% coverage.

## Spec Change Log

## Review Triage Log

### 2026-09-13 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 0
- reject: 16: (high 0, medium 3, low 13)
- addressed_findings:
  - `[medium]` `[patch]` `stream_source` let `RuntimeError` escape when HA asked for a stream after the relay stopped (during an unload or reload). It now returns `None`. Test: `test_unknown_camera[stopped]`.
  - `[low]` `[patch]` `async_camera_image` let the library's `ValueError` for a width below 1 escape, and the image proxy accepts `width=0` from its query string. It now returns `None`. Test: `test_image_failure[bad-width]`.

## Design Notes

**Why reload rather than toggle live.** Relay tokens can't be revoked individually; they die only when the relay stops. Reloading the entry stops the old relay through `async_on_unload`. Setup then creates a relay only while the option is on, so "stops issuing their addresses" holds by construction.

**Why still images don't need the relay.** HA's `Camera` calls `async_camera_image` for thumbnails independently of streaming. `++image` uses header auth over the existing session, so a still works even without RTSP.

**Diagnostics AC.** No diagnostics platform exists yet, and none is added here. The credential AC is carried by the log sweep, plus the fact that the runtime data never stores a credential-bearing URL.

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` -- expected: all pass, 100%.
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `uv run mypy custom_components tests` -- expected: clean.

## Auto Run Result

Status: done

**Summary.** SecuritySpy cameras now play live video in Home Assistant, and the password never reaches a URL or log. Each camera device gets an enabled `camera` entity, `SecuritySpyCamera`, named after the device, with unique ID `{uuid}_{number}_camera`.
- **Stream:** `stream_source()` returns the library `RtspRelay`'s loopback address. The relay is created and started in setup, and its `async_stop` is registered for unload.
- **Still image:** `async_camera_image` comes from `client.async_get_camera_image`.
- **No relay:** when the server serves no RTSP, or the relay cannot bind (one warning, no detail), entities remain with stills only and no STREAM feature.
- **Option:** a new options flow (`OptionsFlowWithReload`) toggles `create_camera_entities`, default on. Turning it off reloads the entry, removes the camera entities and builds no relay, so no relay address is issued. Turning it back on restores the same unique IDs.
- **Commit:** `39d2a6e8`.

**Files changed**
- `custom_components/securityspy/camera.py` -- new camera platform.
- `custom_components/securityspy/__init__.py` -- `Platform.CAMERA`, the `relay` runtime field, relay start and stop.
- `custom_components/securityspy/config_flow.py` -- options flow.
- `custom_components/securityspy/const.py` -- `CONF_CREATE_CAMERA_ENTITIES`.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- options strings.
- `pyproject.toml`, `uv.lock` -- dev-only `pyturbojpeg==1.8.3`, which HA's `camera` component imports and tests need. It is not a runtime requirement, so `manifest.json` is unchanged.
- `tests/conftest.py`, `tests/test_camera.py` (new), `tests/test_init.py`, `tests/test_config_flow.py`, `tests/test_translations.py` -- relay mock, `rtsp_port` builder kwarg, one test per matrix row, a DEBUG log sweep for the password and its base64 form, and options-flow and relay-lifecycle tests.

**Review findings:** 2 patched (medium 1, low 1), 0 deferred, 16 rejected. Rejected findings include cameras added after setup needing a reload (already deferred from story 2.4), relay cleanup after a failed setup (confirmed handled by `async_on_unload`), PEP 758 `except` syntax (the project targets Python 3.14), and registry removal when the option is off (exactly what the AC requires).

**Follow-up review recommended: no.** Both fixes are one-line exception widenings, each with a test.

**Verification**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100`: 116 passed, 100.00% coverage.
- `uv run ruff check .`, `uv run ruff format --check .`: clean.
- `uv run mypy custom_components tests`: clean.

**Residual risks**
- Not yet exercised in a running Home Assistant against the reference server. Playback through HA's `stream` component and the relay is proven only by the library's live ffprobe test (story 1.19) and this story's unit tests.
- A camera added on the server after setup gets a device but no camera entity, and its stream stays unavailable, until the entry reloads (pre-existing deferred gap).
- The relay's address is a bearer token on loopback: any process on the HA host that learns it can play that camera.
- No diagnostics platform exists yet, so the diagnostics half of the credential AC holds vacuously.

