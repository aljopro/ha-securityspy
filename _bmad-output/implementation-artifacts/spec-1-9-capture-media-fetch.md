---
title: 'Story 1.9: Capture media fetch'
type: 'feature'
created: '2026-08-28'
status: 'review'
baseline_revision: 'f42960c7f42828a882d441f180efccf8032ccce3'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `Capture` (from `++caplist`) carries enough to identify a recording, but nothing in the library can turn one into bytes -- a consumer needing a preview thumbnail or the recorded file itself would have to build a SecuritySpy URL by hand, breaking the architecture's "the library owns every endpoint URL" rule and re-implementing the `getpreview`/`getfile` quirks (research §4.3, §4b.1) itself.

**Approach:** Add `SecuritySpyClient.async_get_capture_preview(capture)` returning the JPEG thumbnail as bytes + content type, and `SecuritySpyClient.async_get_capture_file(capture, *, bandwidth=..., archive=None)` returning a typed, async-iterable stream object so a large recording is never fully buffered. Both derive their URL from `Capture` fields alone; neither takes a path, folder date, or raw query parameter.

## Boundaries & Constraints

**Always:** Both calls are read-only GETs -- nothing on the server is deleted, modified, or archived by either. `async_get_capture_preview` takes only `capture`; the `archive` query flag is derived from `capture.archived`, never caller-supplied, matching the "only the Capture" AC. `async_get_capture_file` accepts `bandwidth: CaptureFileBandwidth = CaptureFileBandwidth.STANDARD` and `archive: bool | None = None`, where `None` means "use `capture.archived`" -- an explicit `True`/`False` overrides it. The filename component of the URL is percent-encoded with `urllib.parse.quote` (existing precedent in `client.py`), never interpolated raw. Every transport failure funnels through the existing typed hierarchy (`SecuritySpyAuthError` for 401/403, `SecuritySpyConnectError` for every other unexpected status, redirect, TLS, timeout or transport failure) -- no raw `aiohttp` exception, and no credential, escapes either call, including from inside the file stream's chunk-by-chunk iteration. `async_get_capture_file`'s stream never buffers the full body: bytes are read and yielded in bounded chunks, with no `_MAX_BODY_BYTES` cap applied (that cap exists for JSON/text bodies this library parses in full; a movie is neither). `async_get_capture_preview` reuses the existing 8 MiB body cap (a JPEG thumbnail is verified ~95 KB, research §4.3) and returns raw bytes, never text-decoded.

**Block If:** none identified -- both endpoints, their content types, and the `getpreview` double-`?` URL construction are documented with enough specificity (research §4.3, §4b.1, §4b.3) to implement unattended.

**Never:** No `forceDownload` parameter -- the library returns bytes to the caller directly, never asks the server for a browser download disposition. No caller-supplied path, folder date, or filename -- only a `Capture` is accepted. No use of `getfilehb`/`getfilelb` as a query parameter on `getfile` (`lowBandwidth=`) -- `CaptureFileBandwidth` selects one of the three distinct endpoint paths research §4b.1's table documents, not a query flag layered on `getfile`, since the table is the more explicit of the two partly-overlapping pieces of evidence. No change to `Capture`, `caplist` decoding, or any existing endpoint/model.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Preview fetch | A `Capture` with `camera=4`, `folder_date="2026-08-09"`, `filename="M+2026-08-09_17-35-19_C.jpg"`, `archived=False` | `async_get_capture_preview` GETs `++getpreview?/4/2026-08-09/<url-encoded filename>?archive=0` and returns `CapturePreview(data=<jpeg bytes>, content_type="image/jpeg")` | No error expected |
| Archived preview | Same, `archived=True` | The built URL ends `?archive=1` | No error expected |
| Standard-bandwidth file fetch | Same `Capture`, `bandwidth=CaptureFileBandwidth.STANDARD` (default), `archive=None` | GETs `++getfile/4/2026-08-09/<url-encoded filename>?archive=0`; returns a `CaptureFileStream` whose `content_type` is `"video/quicktime"` and whose async iteration yields the body in bounded chunks, never buffering the full response | No error expected |
| Low-bandwidth file fetch | `bandwidth=CaptureFileBandwidth.LOW` | GETs the `++getfilelb` endpoint variant; `content_type` is `"video/mp4"` | No error expected |
| High-bandwidth file fetch | `bandwidth=CaptureFileBandwidth.HIGH` | GETs the `++getfilehb` endpoint variant; `content_type` is `"video/quicktime"` | No error expected |
| Explicit archive override | `capture.archived=False`, caller passes `archive=True` | The built URL uses `archive=1`, not the capture's own flag | No error expected |
| Credentials rejected | Server answers 401/403 to either call | `SecuritySpyAuthError` raised before any body is read | Typed, no raw `aiohttp` exception |
| Capture no longer held / other unexpected status | Server answers e.g. 404 to either call | `SecuritySpyConnectError` raised with a credential-free reason | Typed, no raw `aiohttp` exception |
| Body exceeds the preview cap | `getpreview` response declares or streams more than 8 MiB | `async_get_capture_preview` raises `SecuritySpyConnectError` ("too large"), matching the existing `_request` cap behaviour | Typed |
| Connection drops mid-stream | The file's connection fails or times out after some chunks have already been yielded | The in-progress `async for` raises `SecuritySpyConnectError`, not a bare `aiohttp`/`TimeoutError`/`OSError` | Typed, no raw exception |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `ENDPOINT_GET_PREVIEW = f"{ENDPOINT_PREFIX}getpreview"`, `ENDPOINT_GET_FILE = f"{ENDPOINT_PREFIX}getfile"`, `ENDPOINT_GET_FILE_HIGH_BANDWIDTH = f"{ENDPOINT_PREFIX}getfilehb"`, `ENDPOINT_GET_FILE_LOW_BANDWIDTH = f"{ENDPOINT_PREFIX}getfilelb"` next to the other `ENDPOINT_*` constants (research §4.3, §4b.1), each with a doc comment citing the section; add three int constants `CAPTURE_FILE_BANDWIDTH_STANDARD = 0`, `..._HIGH = 1`, `..._LOW = 2` (client-side selector only -- not a wire value) mapping each to its endpoint + content-type pair; add every new name to `__all__` in sorted (RUF022) order.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: add frozen `CapturePreview` (`data: bytes`, `content_type: str`); add a `CaptureFileBandwidth` value type mirroring the existing `arm_override()`/`ArmOverride` validated-int-sentinel pattern (~line 555-573), with a `capture_file_bandwidth()` constructor validating against the three `CAPTURE_FILE_BANDWIDTH_*` constants and exposing the matching endpoint constant + content type.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: refactor `_request`'s URL-build-and-issue-GET-and-map-status prologue (~lines 820-875) into a shared private async context-manager helper reused by the existing buffered path, a new `_request_bytes(path, params) -> tuple[bytes, str]` (buffered, 8 MiB cap, no text decode) for the preview fetch, and a new `_stream_bytes(path, params) -> CaptureFileStream` (unbounded total via `self._connection.stream_timeout()`, chunked `response.content.read(n)` loop matching the existing accumulation-loop precedent, no `_MAX_BODY_BYTES` cap, wraps `aiohttp.ClientError`/`TimeoutError`/`OSError` raised during iteration into `SecuritySpyConnectError`) for the file fetch. Add `async_get_capture_preview(self, capture: Capture) -> CapturePreview` building the `++getpreview?/{camera}/{folder_date}/{quoted filename}?archive={0|1}` URL exactly as research §4.3's double-`?` form documents (the `archive` flag baked into the path string itself, not passed via `params`, since it is not an ordinary key=value pair the server parses with a standard query splitter -- research §4.3's note). Add `async_get_capture_file(self, capture: Capture, *, bandwidth: CaptureFileBandwidth = ..., archive: bool | None = None) -> CaptureFileStream` building the `++getfile{,hb,lb}/{camera}/{folder_date}/{quoted filename}` path with an ordinary `archive` query param.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export `ENDPOINT_GET_PREVIEW`, `ENDPOINT_GET_FILE`, `ENDPOINT_GET_FILE_HIGH_BANDWIDTH`, `ENDPOINT_GET_FILE_LOW_BANDWIDTH`, `CAPTURE_FILE_BANDWIDTH_STANDARD/_HIGH/_LOW`, `CaptureFileBandwidth`, `capture_file_bandwidth`, `CapturePreview`, `CaptureFileStream` from the `.const`/`.models`/`.client` import blocks and `__all__`, sorted (RUF022).
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §4.3, §4b.1, §4b.3 -- the URL-shape and content-type source for all of the above.
- `aiosecurityspy/tests/test_client.py` -- the `FakeSession`/`FakeResponse`/`FakeContent` harness (~line 40-160) that both new client methods' tests are built on; `FakeContent.read` already fragments reads at 64 bytes, which is what exercises the new streaming accumulation loop.
- `aiosecurityspy/tests/test_models.py` -- the `Capture`-building helpers already present, to construct fixtures for `async_get_capture_preview`/`async_get_capture_file` tests without re-deriving a `Capture` by hand in `test_client.py`.
- `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document both new methods, the streaming contract, and the `archive` default-from-`Capture` rule.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- add the four `ENDPOINT_GET_*` constants and three `CAPTURE_FILE_BANDWIDTH_*` constants, each documented and exported -- the media endpoints and the bandwidth-variant selector need named, protocol-owning constants per the library's existing convention.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add `CapturePreview`, `CaptureFileBandwidth`, `capture_file_bandwidth()` -- the typed value objects the client methods return and accept.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- extract the shared request-issue-and-status-map helper; add `_request_bytes` and `_stream_bytes`; add `async_get_capture_preview` and `async_get_capture_file` -- the accessors this story exists to deliver.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export every new name in sorted order -- keeps the published surface complete and RUF022-clean.
- [x] `aiosecurityspy/tests/test_client.py` -- cover every I/O-matrix row: both endpoints' URL construction (including the `getpreview` double-`?` and the three `getfile*` variants), the archive-derived-from-`Capture` default and its override, the 401/403 → `SecuritySpyAuthError` and unexpected-status → `SecuritySpyConnectError` mappings for both calls, the preview's 8 MiB cap, and a mid-stream transport failure during file iteration mapping to `SecuritySpyConnectError` rather than escaping raw.
- [x] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document the new methods, their return types, and the streaming/archive-default contract.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a `CaptureFileStream` returned by `async_get_capture_file`, when its bytes are consumed via `async for chunk in stream`, then no single call ever holds more than one bounded chunk of the movie body in memory at once.

## Spec Change Log

- **2026-08-28**: Initial implementation of capture media fetch (preview and file streaming)

## Design Notes

**`archive` is derived from `Capture.archived` by default, on both calls -- with an explicit override only on the file fetch.** The preview AC is explicit that the caller supplies only the `Capture`; the file AC is explicit that the archive flag is "selectable through typed arguments." `archive: bool | None = None` on `async_get_capture_file` reconciles both: it works from the `Capture` alone by default (same principle as preview), while still giving a caller who deliberately wants the other storage tier a typed door, rather than none at all.

**`getpreview`'s `archive` flag travels inside the path string, not through `params`.** Research §4.3 flags the URL as `getpreview?/{cam}/{folderDate}/{filename}?archive={a}` -- a literal second `?`, not `&`. A standard query-string parser (aiohttp's `params=` merge included) treats everything after the *first* `?` as one blob split on `&`; feeding `archive` through `params` would produce `.../{filename}&archive=0`, which SecuritySpy's own idiosyncratic parser -- one that evidently splits the query on the *last* `?` -- would not recognize as the `archive` key at all. The path is therefore assembled as one literal string and handed to the transport layer with no separate `params`.

**Bandwidth selects one of three endpoint paths, not a query flag.** Research §4b.1 documents `getfile`/`getfilehb`/`getfilelb` as three distinct paths with three content types in an explicit table; a separate `lowBandwidth=` query parameter also appears in one client-playback example, but only ever paired with the bare `getfile` path and never shown combined with the other two variants. The table is the more explicit and more complete of the two, so `CaptureFileBandwidth` selects the endpoint path.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, every pre-existing test included, new tests covering the I/O matrix above

## Dev Agent Record

**Completion Notes:**
- All 6 tasks completed successfully
- 811 tests pass (790 pre-existing + 21 new)
- ruff check, ruff format, mypy --strict all pass with zero findings
- `CapturePreview` and `CaptureFileBandwidth` added to models.py following the `ArmOverride`/`arm_override()` pattern
- `_request_bytes` (buffered, 8 MiB cap) and `_stream_bytes` (unbounded streaming) added to client.py
- `async_get_capture_preview` builds the double-`?` URL correctly with percent-encoded filename
- `async_get_capture_file` supports all three bandwidth variants and archive override
- `CaptureFileStream` wraps transport errors into `SecuritySpyConnectError` during iteration
- All new names exported from `__init__.py` in sorted order
- README and CHANGELOG updated with documentation

**File List:**
- `aiosecurityspy/src/aiosecurityspy/const.py` -- added endpoint and bandwidth constants
- `aiosecurityspy/src/aiosecurityspy/models.py` -- added CapturePreview, CaptureFileBandwidth, capture_file_bandwidth()
- `aiosecurityspy/src/aiosecurityspy/client.py` -- added CaptureFileStream, _request_bytes, _stream_bytes, async_get_capture_preview, async_get_capture_file
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- exported all new names
- `aiosecurityspy/tests/test_client.py` -- added 21 new tests for capture media fetch
- `aiosecurityspy/tests/test_credential_containment.py` -- updated expected endpoint names
- `aiosecurityspy/README.md` -- documented new methods
- `aiosecurityspy/CHANGELOG.md` -- documented new features
