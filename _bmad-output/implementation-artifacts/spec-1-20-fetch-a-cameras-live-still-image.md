---
title: 'Fetch a camera''s live still image'
type: 'feature'
created: '2026-09-13'
status: 'done'
baseline_revision: 'dc4b7be' # aiosecurityspy HEAD
review_loop_iteration: 0
followup_review_recommended: false
final_revision: '7afa36e' # aiosecurityspy HEAD
context:
  - '{project-root}/../aiosecurityspy/AGENTS.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** Story 2.6's camera entity needs a current still image fetched with header auth, but `aiosecurityspy` 0.3.0 can only fetch previews of recorded captures, and AD-2 forbids the integration from calling `++image` itself.

**Approach:** Add `SecuritySpyClient.async_get_camera_image(server_info, camera_number, *, width=None, quality=None) -> CameraImage`, which GETs `++image?cameraNum=N[&width=W][&quality=Q]` through the existing `_request_bytes` path (Basic header, 8 MiB cap, 401 disambiguation).

## Boundaries & Constraints

**Always:**
- Validate before any request: the camera number goes through `_validated_camera_number`, and a number not in `server_info.cameras` raises `SecuritySpyPermissionError(PERMISSION_NAMES[PERM_LIVEVIDEO], number)`, mirroring `unsecured_stream_url`. `width` must be an `int` (not `bool`) ≥ 1, and `quality` an `int` (not `bool`) in 0–100, else `ValueError`.
- Call `_request_bytes` with `permission=PERMISSION_NAMES[PERM_LIVEVIDEO]` and `camera_number=number`, so a 401 is resolved by the existing permission-vs-auth probe (story 1.14) and 403 → permission error.
- A 2xx response whose content type doesn't start with `image/` raises `SecuritySpyConnectError(host, port, "server did not return an image")`; the message must not include the body.
- New `ENDPOINT_IMAGE: Final = f"{ENDPOINT_PREFIX}image"` in `const.py`, exported in `__all__` of both `const.py` and the package.
- New frozen, slotted `CameraImage(data: bytes, content_type: str)` in `models.py` with a `__repr__` that hides the bytes, like `CapturePreview`; exported from the package.
- No new log records beyond `_request_bytes`'s existing ones; no credential or `auth=` in any URL.

**Block If:**
- Satisfying an AC appears to require a credential in a URL or log, or a new runtime dependency.

**Never:**
- Reusing or renaming `CapturePreview`; changing `_request_bytes` behaviour for existing callers; streaming MJPEG (`++video`), HLS, or image-adjustment parameters; Home Assistant imports.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | camera 4 visible; server 200 `image/jpeg` | `CameraImage(data=<jpeg>, content_type="image/jpeg")`; URL `…/++image?cameraNum=4`, `Authorization` header, no userinfo | None |
| Sizing | `width=320, quality=50` | URL `…/++image?cameraNum=4&width=320&quality=50` | None |
| Bad args | `width=0`, `width=True`, `quality=101`, `quality=-1`, `camera_number="4"` | No request sent | `ValueError` |
| Not visible | camera 9 absent from `server_info.cameras` | No request sent | `SecuritySpyPermissionError("live_video", 9)` |
| 401, probe succeeds | 401 then `++systemInfo` 200 | — | `SecuritySpyPermissionError("live_video", 4)` |
| 401, probe fails | 401 then probe 401 | — | `SecuritySpyAuthError` |
| Non-image body | 200 `text/html` | — | `SecuritySpyConnectError`, message without body |
| Transport failure | timeout / unreachable | — | `SecuritySpyConnectError` (existing mapping) |

</intent-contract>

## Code Map

Library repo `/Users/jensen/projects/aiosecurityspy` (written `aiosecurityspy/`); run commands from its root.

- `aiosecurityspy/src/aiosecurityspy/client.py` -- `unsecured_stream_url` (~762, refusal pattern), `async_get_capture_preview` (~981, model to copy), `_request_bytes` (~1313, takes a pre-built path; no `params`), `_map_status` (~1122).
- `aiosecurityspy/src/aiosecurityspy/const.py` -- `ENDPOINT_GET_PREVIEW` (~176), `__all__` (~63), `PERM_LIVEVIDEO`/`PERMISSION_NAMES`.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `CapturePreview` (~1362).
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- imports and `__all__`.
- `aiosecurityspy/tests/test_client.py` -- `FakeStreamSession` (~1609), preview tests (~1650).
- `aiosecurityspy/tests/test_credential_containment.py` -- `EXPECTED_ENDPOINT_NAMES` (~87), `FakeServer._respond` (~320), `drive_every_path` (~367).
- `aiosecurityspy/tests/test_live_server.py` -- `_client`, `SECURITYSPY_TEST_CAMERA` fixture, live media test (~329).
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- `getpreview` operation (~252) as template.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- add and export `ENDPOINT_IMAGE`.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add `CameraImage`.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- add `async_get_camera_image` per the contract, building the query with `urlencode`.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export `CameraImage` and `ENDPOINT_IMAGE`.
- [x] `aiosecurityspy/tests/test_client.py` -- one test per matrix row.
- [x] `aiosecurityspy/tests/test_models.py` -- `CameraImage.__repr__` hides bytes.
- [x] `aiosecurityspy/tests/test_credential_containment.py` -- add `ENDPOINT_IMAGE` to `EXPECTED_ENDPOINT_NAMES`, a `++image` branch to `FakeServer`, and a lambda to `drive_every_path`.
- [x] `aiosecurityspy/tests/test_live_server.py` -- `@pytest.mark.live` test fetching the test camera's image; assert `content_type` starts with `image/jpeg` and data starts with `b"\xff\xd8"`; skips without `.env`.
- [x] `aiosecurityspy/docs/securityspy-openapi.yaml` -- add `/++image` with `cameraNum`, `width`, `quality`, `x-verification: live-6.21`.
- [x] `aiosecurityspy/CHANGELOG.md` (`## [Unreleased]` → `### Added`) and `README.md` -- document the method.

**Acceptance Criteria:**
- Given every scenario in the matrix, when caplog at DEBUG and rendered exceptions are inspected, then no `SENTINELS` value or base64 credential appears.
- Given the reference server and a visible camera, when the live test runs, then it receives a decodable JPEG.
- Given the full library suite, when gates run, then all pass with no warnings.

## Spec Change Log

## Review Triage Log

### 2026-09-13 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 1, low 3)
- defer: 0
- reject: 14: (high 0, medium 0, low 14)
- addressed_findings:
  - `[medium]` `[patch]` A 2xx `image/*` response with an empty body was returned as a zero-byte `CameraImage`. An empty body now raises the same `SecuritySpyConnectError`. Test: `test_camera_image_empty_body_is_a_connect_error`.
  - `[low]` `[patch]` The content-type check was case-sensitive. It now lowercases before comparing. Test: `test_camera_image_content_type_is_matched_case_insensitively`.
  - `[low]` `[patch]` Bad-argument coverage lacked `quality=True`, a float width, a string quality, a negative camera and `camera_number=True`. All added as parametrized cases.
  - `[low]` `[patch]` No test for a 403. Added `test_camera_image_403_is_a_permission_error`.

## Design Notes

**Why a new `CameraImage` rather than `CapturePreview`.** Same shape, but `CapturePreview` means "a recorded capture's thumbnail"; the glossary forbids reusing a term for a different concept.

**Why refuse invisible cameras locally.** `++systemInfo` lists only cameras the account may view live (DW-5), so absence is already a permission answer; refusing locally avoids an extra 401 plus disambiguation probe, as stories 1.18/1.19 do.

## Verification

**Commands:**
- `uv run pytest -q` -- expected: all pass; live tests skip without configuration.
- `uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `uv run mypy --strict src tests` -- expected: clean.

## Auto Run Result

Status: done

**Summary.** `aiosecurityspy` now has `SecuritySpyClient.async_get_camera_image(server_info, camera_number, *, width=None, quality=None) -> CameraImage`. It fetches `++image` with an `Authorization: Basic` header and no credential in the URL. Arguments are validated and invisible cameras are refused before any request. A 401 goes through the existing permission-or-auth probe, and an empty or non-image body is a `SecuritySpyConnectError` that doesn't echo the body. Commit: `aiosecurityspy@7afa36e`. Not tagged, released or pushed.

**Files changed**
- `src/aiosecurityspy/client.py` -- `async_get_camera_image`.
- `src/aiosecurityspy/const.py`, `models.py`, `__init__.py` -- `ENDPOINT_IMAGE` and `CameraImage`, exported.
- `tests/test_client.py` -- matrix rows plus review additions (empty body, mixed-case type, 403, more bad arguments).
- `tests/test_models.py` -- `CameraImage` repr hides the bytes.
- `tests/test_credential_containment.py` -- new endpoint and method in the sweep.
- `tests/test_live_server.py` -- live JPEG test.
- `docs/securityspy-openapi.yaml`, `README.md`, `CHANGELOG.md` -- documented under Unreleased.

**Review findings:** 4 patched (medium 1, low 3), 0 deferred, 14 rejected. Rejected items include stale or foreign `server_info` (the documented local-refusal design), SVG or 206 responses, and the helper duplication.

**Follow-up review recommended: no.** The fixes are small and local.

**Verification**
- `uv run pytest -q`: 1099 passed, 16 skipped (live tests without configuration).
- `uv run ruff check .`, `uv run ruff format --check .`: clean.
- `uv run mypy --strict src tests`: clean.

**Residual risks**
- Live, against the reference server (2026-09-13): `uv run pytest -q -m live -k image` passed -- a JPEG was fetched for the configured test camera.
- `width` and `quality` were verified live in research (6.21), not by this story's live test.
