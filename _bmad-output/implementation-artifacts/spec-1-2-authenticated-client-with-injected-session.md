---
title: 'Story 1.2: Authenticated client with injected session'
type: 'feature'
created: '2026-08-10'
status: 'done'
baseline_revision: 'aeaedb2c39b795d1c2be73ba273432851085a948'
final_revision: '4ac98c7f601175dec97e184bf5611a85b1a1f3a7'
review_loop_iteration: 0
followup_review_recommended: false  # 2 patches, both high; tightly localized, no public-API behavior change, regression tests added
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/research/securityspy-api-reference.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `aiosecurityspy` is an empty-but-typed skeleton. Nothing can talk to a SecuritySpy server, and stories 1.3, 1.4 and 1.6 all depend on the shared typed models, endpoint constants and exception hierarchy that the client introduces (FR-40, FR-41, FR-42).

**Approach:** Add `SecuritySpyClient` — an async REST client over a caller-injected `aiohttp` session — plus the frozen typed models, endpoint/permission constants and the typed exception hierarchy (AD-6, AD-15). Its first capability is reading `++systemInfo` into a `ServerInfo` carrying server UUID, version, camera count and a `dict[int, Camera]` camera list.

## Boundaries & Constraints

**Always:**
- The caller injects the `aiohttp.ClientSession`; the library never constructs, owns, or closes one, and the client has no `close()`/`__aexit__` that closes the injected session.
- Credentials are held once on the client and sent as `aiohttp.BasicAuth`. No credential ever appears in a URL string, log line, exception message, `repr`, or traceback (AD-13). Models and the client define `__repr__`/`__str__` that cannot leak them.
- Every failure leaving a public method is a `SecuritySpyError` subclass: `SecuritySpyConnectError` (unreachable, timeout, TLS failure, non-auth HTTP status, malformed body), `SecuritySpyAuthError` (401/403), `SecuritySpyUnsupportedVersionError` (server older than the declared minimum, or a payload whose shape cannot be located). No `aiohttp` exception, `asyncio.TimeoutError`, `JSONDecodeError`, `KeyError` or `ValueError` escapes.
- Certificate verification is a constructor flag (`verify_ssl: bool = True`) applied per request (`ssl=False` when disabled), because the session is not the library's to configure. Every request carries an explicit total timeout so a wrong-host TLS handshake fails rather than hangs.
- Models are frozen, fully-typed dataclasses with `from_api()` constructors; raw dicts never cross the public boundary. Camera number is `int` everywhere. Timestamps are timezone-aware UTC; absent is `None`, never epoch (AD-15).
- Object class stays open `str`; `class_slug()` lands in `const.py` as the single normalizer (AD-9).
- Zero Home Assistant imports; `uv run mypy --strict` and `uv run ruff check .` stay clean.

**Block If:**
- The library's own gates (`ruff`, `mypy --strict`, `pytest`) cannot pass without disabling a gate or adding a blanket ignore.

**Never:**
- Do not implement the event stream (1.3), capture history (1.4), the reducer (1.5), settings/arming writes (1.6), or the anonymizer (1.7).
- Do not expose destructive or remote-execution endpoints — `deleteclip`, `doShell`, `doShortcut` must not exist in the tree, not even privately (AD-2).
- Do not count auth failures, persist auth state, retry, or initiate reauthentication — that is the consumer's job (AD-6, AD-18).
- Do not use the `?auth=base64(user:pass)` query form for API calls, and do not build `https://user:pass@host/` URLs.
- Do not add integration (`custom_components/`) files, and do not touch `sprint-status.yaml`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Server info happy path | Fixture `++systemInfo?format=json` body, valid credentials | `ServerInfo` with `uuid`, `version`, `camera_count`, and `cameras: dict[int, Camera]` keyed by `int` camera number; each `Camera` carries name, connected, enabled, permissions bitmask | No error expected |
| Session ownership | Client constructed and used | The injected session is used as-is; it is still open and unclosed after any client call, including failing ones | No error expected |
| Verification disabled | `verify_ssl=False` | Request is issued with `ssl=False`; a mismatched certificate connects successfully | No error expected |
| Verification enabled, bad cert | `verify_ssl=True`, host mismatch (`aiohttp.ClientConnectorCertificateError`) | Raises `SecuritySpyConnectError` promptly, bounded by the request timeout | Error message names the host/port, never the credentials |
| Unreachable host / timeout | `ClientConnectorError` or `asyncio.TimeoutError` | Raises `SecuritySpyConnectError` | Original exception attached via `raise ... from` |
| Bad credentials | HTTP 401 or 403 | Raises `SecuritySpyAuthError` | Message and `repr` contain neither username nor password |
| Old server | Payload version below the minimum (`6.0`) | Raises `SecuritySpyUnsupportedVersionError` naming both the found and required versions | — |
| Unlocatable payload | Body is valid JSON but has no locatable server/camera block, or version is missing/unparseable | Raises `SecuritySpyUnsupportedVersionError` | — |
| Malformed body | Non-JSON body, or HTTP 500 | Raises `SecuritySpyConnectError` | Body content is not echoed into the message |
| Single-camera server | `cameralist.camera` is one dict rather than a list | One-entry `dict[int, Camera]` | — |
| No cameras | Camera list absent or empty | Empty `dict`, not `None` or an error | — |
| Non-numeric camera number | A camera entry whose `number` will not parse as `int` | Entry is skipped; the rest decode | Logged at debug with no payload contents |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- exists: docstring, `__version__`, `__all__`. Re-export the new public surface here.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- new: `SecuritySpyClient` (AD-2 structural seed).
- `aiosecurityspy/src/aiosecurityspy/models.py` -- new: `ServerInfo`, `Camera` (AD-15).
- `aiosecurityspy/src/aiosecurityspy/const.py` -- new: endpoint paths, `PERM_*` bitmask values, built-in class constants, `class_slug()`, minimum version.
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- new: typed hierarchy (AD-6).
- `aiosecurityspy/pyproject.toml` -- exists: aiohttp pin needs aligning to the architecture Stack table.
- `aiosecurityspy/tests/test_package.py` -- exists: skeleton tests; new tests live beside it.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` -- §1 auth/transport, §9 permissions bitmask, §10 `systemInfo` fields; authoritative over the published spec.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- create `SecuritySpyError` base plus `SecuritySpyConnectError`, `SecuritySpyAuthError`, `SecuritySpyPermissionError`, `SecuritySpyUnsupportedVersionError` -- AD-6 requires the full hierarchy to exist now even though only three are raised in this story; the adapter maps against it.
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- create: `DEFAULT_PORT`, endpoint path constants (`++systemInfo` and the `++` prefix rule), `MIN_SERVER_VERSION`, `PERM_*` values from research §9 with a `decode_permissions()` returning `frozenset[str]`, `CLASS_HUMAN/VEHICLE/ANIMAL` string constants, `class_slug()` -- one home for protocol vocabulary; §9 bits are non-contiguous, so they must be transcribed, not computed.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- create frozen `Camera` and `ServerInfo` dataclasses with `from_api()` classmethods and coercion helpers for `int`/`bool`/optional fields -- AD-15; decoding lives in the model, not the client.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- create `SecuritySpyClient(session, host, port=..., *, username, password, verify_ssl=True, timeout=...)` with a private `_request_json()` doing URL build, BasicAuth, ssl flag, timeout, status→exception mapping, and JSON parse; public `async_get_server_info() -> ServerInfo` -- the single mapping seam so no later endpoint re-invents it.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export the client, models, constants and exceptions in `__all__` -- the published API is a contract from first release.
- [x] `aiosecurityspy/pyproject.toml` -- edit: change `aiohttp>=3.10` to `aiohttp>=3.12,<4` -- matches the architecture Stack table now that aiohttp is actually used; re-lock with `uv lock`.
- [x] `aiosecurityspy/tests/fixtures/system_info.json` -- create a representative `systemInfo?format=json` body (multi-camera, real field names from research §10, at least one camera with a distinct permissions bitmask) -- protocol fixtures are the testing strategy for this epic.
- [x] `aiosecurityspy/tests/test_models.py` -- create: cover every decoding row of the I/O matrix (single-camera dict, empty list, non-numeric number, permission decode, `class_slug()`) from fixture and synthetic dicts, no network -- pure decode coverage.
- [x] `aiosecurityspy/tests/test_client.py` -- create: cover the transport rows of the I/O matrix with a stubbed/`aiohttp`-mocked session — happy path, 401/403, 500, non-JSON, connector error, timeout, TLS error, old version, `ssl=False` passthrough, session-never-closed, and a credential-leak assertion sweeping `str`/`repr`/`traceback` of every raised error -- the credential and exception-containment constraints are only real if asserted.
- [x] `aiosecurityspy/README.md` -- edit: add a runnable usage snippet showing the caller creating the session and a least-privileged SecuritySpy user recommendation -- AD-13 and the "usable from an ordinary script" success criterion.
- [x] `aiosecurityspy/CHANGELOG.md` -- edit: record the client, models, constants and exceptions under Unreleased -- AD-14.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings.
- Given a script with no Home Assistant installed, when it creates its own `aiohttp.ClientSession`, constructs `SecuritySpyClient` with it, and awaits `async_get_server_info()`, then it needs no other library object and the library never creates a session of its own.
- Given a consumer running `mypy --strict` against code importing `SecuritySpyClient`, `ServerInfo`, `Camera` and the exception types, then every public name resolves through `__all__` with complete type information and no `Any` in a public signature.
- Given the whole `aiosecurityspy` tree, when it is searched for Home Assistant imports and for the excluded endpoints (`deleteclip`, `doShell`, `doShortcut`), then there are zero matches.

## Spec Change Log

None. No bad_spec loopback occurred.

## Review Triage Log

### 2026-08-10 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 16: (high 0, medium 7, low 9)
- defer: 3: (high 0, medium 1, low 2)
- reject: 8: (high 0, medium 2, low 6)
- addressed_findings:
  - `[medium]` `[patch]` `UnicodeDecodeError` (a `ValueError`) from `response.text()` escaped as a non-`SecuritySpyError`, breaking the exception-containment constraint. Now mapped to `SecuritySpyConnectError`, with a test.
  - `[medium]` `[patch]` `timeout=0` silently disables the aiohttp timeout, voiding the "fails rather than hangs" guarantee. The constructor now rejects non-positive timeouts, out-of-range ports, and hosts carrying a scheme, slash, space or userinfo (userinfo would have put credentials into the URL).
  - `[medium]` `[patch]` A server reporting a bare major version (`"6"`) was rejected as unsupported, because `(6,)` sorts below `(6, 0)`. Parsed versions are now padded to the floor's length.
  - `[medium]` `[patch]` `frozen=True` was a false guarantee: `ServerInfo.cameras` was a plain mutable `dict`. It is now a `MappingProxyType` typed as `Mapping[int, Camera]`, with a test asserting in-place mutation raises.
  - `[medium]` `[patch]` `Camera.permissions` and `Camera.permission_names` were independently settable and could be constructed out of step. `permission_names` is now a derived property.
  - `[medium]` `[patch]` `ServerInfo.current_time` decoded `current-local-time` as epoch seconds on an unverified assumption, with no test that would catch an inverted sign. The field was removed rather than shipping a guessed decode; it is not required by any acceptance criterion.
  - `[medium]` `[patch]` No test exercised real `aiohttp`, so nothing proved the installed library honours the `params`/`ssl`/`timeout`/`auth`/`allow_redirects` kwargs or that `++systemInfo` survives URL normalization. Added `tests/test_client_transport.py`, driving a real in-process `aiohttp` server (6 tests).
  - `[low]` `[patch]` `decode_permissions(-1)` granted every permission, because Python ints are infinite-width. Negative masks now decode to an empty set and are clamped at `Camera.from_api`.
  - `[low]` `[patch]` `json.loads` accepts `NaN`/`Infinity`, on which `int()` raises. `_as_int` now rejects non-finite floats.
  - `[low]` `[patch]` `PERMISSION_NAMES` was an exported mutable dict any consumer could corrupt process-wide. Now a `MappingProxyType`.
  - `[low]` `[patch]` A duplicate camera number silently last-wins, and `camera_count` could disagree with `len(cameras)` with no signal. Both now log at debug; duplicates keep the first entry.
  - `[low]` `[patch]` Redirect behavior was implicit. `allow_redirects=True` is now explicit with a comment recording why (SecuritySpy 301-redirects HTTP to HTTPS) and that aiohttp drops the `Authorization` header across origins.
  - `[low]` `[patch]` The README modelled `use_https=True, verify_ssl=False` together — the worst pairing — and never advised preferring HTTPS. Rewritten with an explicit "Prefer HTTPS" section; the example now uses HTTPS on 8001.
  - `[low]` `[patch]` CHANGELOG overclaimed: it called a hand-authored fixture "recorded" and asserted no `ValueError` escapes, which was false. Both corrected.
  - `[low]` `[patch]` The `noqa: PLR0913` rationale was factually wrong ("all but host are keyword-only"; `session`, `host` and `port` are positional). Corrected.
  - `[low]` `[patch]` Test hygiene: the two credential/exception sweeps looped inside one test body so the first failure masked nine rows (now parametrized with labelled ids); `class_slug`'s final assertion was tautological (now asserts the actual `[a-z0-9_]`-and-non-empty contract); the fixture was read at import time inside a `parametrize` decorator (now resolved inside the test); and the certificate error was fabricated via `__new__` (now a real `aiohttp.ClientSSLError` subclass).

### 2026-08-10 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 15: (high 3, medium 6, low 6)
- defer: 2: (high 0, medium 2, low 0)
- reject: 6: (high 0, medium 3, low 3)
- addressed_findings:
  - `[high]` `[patch]` A bare `ValueError` escaped `ServerInfo.from_api`, breaking the exception-containment constraint. `"²".isdigit()` is `True` but `int("²")` raises, so a version string carrying a non-ASCII digit crashed the decoder instead of raising `SecuritySpyUnsupportedVersionError`. Version parsing is now ASCII-only, with three tests.
  - `[high]` `[patch]` Host validation was a five-character denylist and did not work. Verified accepted: `"nvr:9999"` → `http://nvr:9999:8001`, `"::1"` → `http://::1:8000` (IPv6 was entirely unsupported — a functional break for an NVR library), plus embedded tabs, newlines and a 300-character host. Replaced with a hostname allowlist plus `ipaddress`-validated IPv4/IPv6, and IPv6 literals are now bracketed in the URL. 12 rejection cases and 5 acceptance cases are parametrized.
  - `[high]` `[patch]` A non-latin-1 password leaked into a traceback. `aiohttp.BasicAuth.encode()` raises `UnicodeEncodeError` at *request* time and that exception's `args` contain the credential itself (`('latin-1', 'u:pa€ss', 4, 5, ...)`) — a direct AD-13 violation. The constructor now rejects unencodable credentials up front, and the test asserts neither username nor password appears in `str`, `repr` or `args`.
  - `[medium]` `[patch]` `if status > _HTTP_OK_MAX` let 1xx and 3xx fall through to the JSON parse as if successful. Now `not 200 <= status <= 299`, with an offline parametrized test and a real-server redirect-loop test.
  - `[medium]` `[patch]` `_as_int` produced aliased camera numbers: `True` → camera 1, `2.9` → camera 2, and `"1_0"` → 10 (Python honours underscore literals), so a bogus entry could collide with a real camera. It is now strict — bools rejected, non-integral floats rejected, ASCII-decimal strings only — with a collision regression test.
  - `[medium]` `[patch]` A response declaring an unknown charset raised `LookupError` out of a public method. Now mapped to `SecuritySpyConnectError`, with a test.
  - `[medium]` `[patch]` The body was read unbounded: the 30 s timeout bounds duration, not bytes, so a misbehaving LAN server could buffer arbitrary memory inside a Home Assistant process. Added an 8 MiB cap enforced by a capped read rather than a trusted `Content-Length` (a chunked response declares none).
  - `[medium]` `[patch]` `test_json_payload_shape_matches_the_offline_fixture` could not fail: it round-tripped a module-level dict through `json` and asserted a constant equalled itself, never opening `tests/fixtures/system_info.json`. Rewritten to read the fixture file and assert the live and offline envelopes actually agree.
  - `[medium]` `[patch]` A username containing `':'` raised aiohttp's own `ValueError` from the constructor, undocumented in `Raises`. Now rejected by the library's own validation with a credential-free message.
  - `[low]` `[patch]` The redirect comment asserted an unverified aiohttp behaviour ("drops the Authorization header across origins") as a credential safeguard. It is also misleading — over plain HTTP the credential is on the wire before any redirect. Comment corrected to state what is actually true.
  - `[low]` `[patch]` `_as_bool` swallowed unrecognised tokens silently while every other decode path in the module logged. A camera silently reported disconnected now logs at debug (type only, never the value).
  - `[low]` `[patch]` `class_slug(None)` raised `AttributeError` out of a public helper documented to always return a slug. Non-strings now degrade to `"unknown"`.
  - `[low]` `[patch]` A server reporting `camera-count: "-3"` produced a negative `camera_count` alongside a non-empty inventory. Negative counts now fall back to the decoded count.
  - `[low]` `[patch]` `from aiohttp.test_utils import TestServer` was collected by pytest as a test class. Aliased.
  - `[low]` `[patch]` `exceptions.py` and the CHANGELOG claimed no `ValueError` escapes a public method, which the constructor's own validation contradicts. Both now scope the guarantee to server- and transport-originated failures and state the constructor exception explicitly.

### 2026-08-10 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 3, medium 2, low 4)
- defer: 0
- reject: 11: (high 0, medium 4, low 7)
- addressed_findings:
  - `[high]` `[patch]` **Every large `++systemInfo` was silently truncated and then blamed on the server.** `_request_json` read the body with a single `response.content.read(_MAX_BODY_BYTES + 1)`, but `aiohttp.StreamReader.read(n)` returns whatever is *currently buffered*, not `n` bytes — it is not `readexactly`. Reproduced against a real in-process aiohttp server: a 966 KB payload (400 cameras, ~1/8th of the 8 MiB "cap") failed with `SecuritySpyConnectError: server response was not valid JSON`, so a large SecuritySpy install would be permanently and inexplicably unreadable. Replaced with an accumulation loop that still enforces the cap by reading one byte past it. The entire stubbed suite was blind to this because `FakeContent.read()` returned the whole body in one call; the stub now fragments at 64 bytes and tracks position, and a real-server regression test asserts a >256 KB body decodes in full.
  - `[high]` `[patch]` **A bare `RuntimeError` escaped the typed hierarchy.** `response.get_encoding()` raises `RuntimeError("Cannot compute fallback encoding of a not yet read body")` whenever the response declares no charset and is not `application/json`, because the client reads through `response.content` and never populates `response._body`. Confirmed by execution against a `text/html` response — precisely the wrong-port / error-page case. This broke the "no exception other than a `SecuritySpyError` leaves a public method" constraint that `exceptions.py` and the CHANGELOG both assert. Now mapped to `SecuritySpyConnectError`, with a real-server test.
  - `[high]` `[patch]` **Following SecuritySpy's HTTP→HTTPS redirect told users their correct password was wrong.** `allow_redirects=True` was justified by a comment saying the redirect must be followed. But SecuritySpy redirects to a different *port*, a different port is a different origin, and aiohttp strips the `Authorization` header across origins — verified: the redirect target received `Authorization: None`. Following the redirect therefore cannot succeed; it converts a wrong-scheme mistake into a 401 that sends the user to reset a credential that was never sent. Now `allow_redirects=False`, with 3xx surfaced as `SecuritySpyConnectError` naming the status and suggesting `use_https=True`. The prior "redirect loop" test was asserting the broken behavior and has been replaced.
  - `[medium]` `[patch]` `timeout=inf` and `timeout=nan` slipped past the `timeout <= 0` guard (both comparisons are `False`), leaving the request effectively unbounded and voiding the "fails rather than hangs" guarantee that the guard exists to protect. Now `math.isfinite` plus the positivity check, with tests for zero, negative, inf and nan.
  - `[medium]` `[patch]` A non-integer `port` was accepted and formatted straight into the URL: confirmed `http://h:8000.5` and `http://h:True` (since `isinstance(True, int)` is `True`). Type annotations do not constrain a runtime caller such as a config flow reading user input, and the constructor already validates host, timeout and credentials at runtime. Now raises `TypeError`, with tests.
  - `[low]` `[patch]` `decode_permissions()` — an exported public helper — raised a bare `TypeError` on a non-int, while its sibling `class_slug()` was hardened to degrade for exactly this reason in an earlier pass. Now returns an empty set, `bool` included (`True` would otherwise decode as mask 1).
  - `[low]` `[patch]` `_validate_host`'s docstring claimed it rejects "any character that is not legal in a hostname". It does not: it is a character allowlist, and `a..b` (empty label) and over-long single labels pass. The allowlist is adequate for its real purpose — keeping userinfo and schemes out of the URL — so the docstring was corrected rather than the regex, which would risk rejecting hosts that resolve fine.
  - `[low]` `[patch]` `assert host not in str(err.value) or not host` could not fail for the case it existed to check: for `host=""` every string contains `""`, so the left side is always `False` and the right side rescues it. Replaced with an exact match on the canned message, which by construction contains nothing caller-supplied.
  - `[low]` `[patch]` CHANGELOG accuracy: the exception-containment list now includes `RuntimeError` and the constructor's `TypeError`, the body-cap entry no longer describes the mechanism that was corrupting legitimate responses, and the new redirect policy is recorded.
- Rejected (recorded for traceability, not acted on): `ServerInfo.uuid` defaulting to `""` and the `MIN_SERVER_VERSION` floor are both already open in the deferred-work ledger; unlocatable-payload → `SecuritySpyUnsupportedVersionError` and the unused `SecuritySpyPermissionError`/`class_slug`/`CLASS_*` surface are both mandated verbatim by the intent contract and the task list; `camera_count` disagreeing with `len(cameras)` is the *correct* report when a camera was skipped by the documented non-numeric-number path; negative camera numbers, `ssl=` passed on plain HTTP, and zero-padded IPv4 octets are speculative with no evidence SecuritySpy emits them, and rejecting them risks dropping real cameras or hosts; non-string JSON object keys cannot come out of `json.loads`; `RecursionError` from `json.loads` did not reproduce at 100,000 nesting levels; and the `LookupError` arm, while unreachable against real aiohttp, is harmless defense-in-depth.

### 2026-09-03 — Review pass (follow-up 3, DW-1)
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 2, medium 0, low 0)
- defer: 1: (high 0, medium 0, low 1)
- reject: 2: (high 0, medium 0, low 2)
- addressed_findings:
  - `[high]` `[patch]` **`UnicodeEncodeError` (a `ValueError`) escaped three public methods, violating the exception-containment invariant.** `urllib.parse.quote(value, safe="")` raises `UnicodeEncodeError` on a lone surrogate, and that exception was neither caught nor remapped at any of three call sites: `async_get_capture_preview` (the `getpreview` URL builder), `_stream_bytes` / `async_get_capture_file` (the media URL builder), and `async_set_camera_settings` (the form-body builder). All three are reachable from caller-supplied input (`Capture.path`, the URL path suffix, and a `CameraSettingsPatch` field). The leaked exception's `args` carry the value verbatim -- a camera name, an overlay string, or a filename -- into any traceback that prints `repr(exception)`, exactly the AD-13 path the read-side settings page warns about. Pass 3 closed the same gap for `UnicodeDecodeError` and `RuntimeError` on the read side; `UnicodeEncodeError` was the matching write-side hole. Each `quote()` call is now wrapped in `try/except UnicodeEncodeError` that maps to `SecuritySpyConnectError` with a credential-free message, mirroring the read-side pattern. Three new tests assert the surrogate case at every call site and that the value does not appear in `str`, `repr`, or `args` of the raised error.
  - `[high]` `[patch]` **`CapturePreview.__repr__` echoed the full `data: bytes` payload, up to the 8 MiB body cap.** `CapturePreview` shipped with no hand-written `__repr__`, so the dataclass auto-repr printed `data=b'<full bytes>'` -- a 95 KB JPEG became a 95 KB repr, and the 8 MiB body cap became an 8 MB repr. Real consumers that log previews (HA logs, Sentry breadcrumbs, diagnostics) and any code path that hits `pytest --showlocals`, `cgitb`, or an IDE debugger would emit the full JPEG bytes per frame. The other models with sensitive payloads (`CameraSettings`, `ServerInfo`, `Capture`, `Camera`, `ArmOverride`, `CameraSettingsPatch`) hand-write minimal `__repr__`s specifically to keep this from happening; `CapturePreview` was the only model that ships a `bytes` payload and skipped the same treatment. `CapturePreview` now has a `__repr__` that prints `content_type` and `len(data)` only. A new test asserts the repr is shorter than 200 bytes regardless of payload size.
- deferred (recorded in `deferred-work.md`):
  - `[low]` `[defer]` `SecuritySpyPermissionError` carries `permission="unknown"` for endpoints whose required permission this library does not model (e.g. `++camStatus`), and the user-visible message names the unknown permission. Documented design (`_PERMISSION_UNKNOWN`'s docstring: "this is the one honest thing to say"), and changing to `SecuritySpyConnectError` would lose semantic information. Defer.
- rejected (recorded for traceability, not acted on): `Camera.__repr__` is verbose because `CameraScheduleAssignment` ships with no hand-written `__repr__`, but the existing rationale ("every field is int|None, so the dataclass's own repr cannot carry a credential" -- CaptureModes' same comment) documents that the policy is intentional, and a hand-written copy would be one more thing to keep in sync for purely cosmetic benefit; `CameraSettingsPatch.form_fields()` silently coerces wrong-typed values with `str()`, but an existing test (`test_form_fields_is_the_only_place_that_knows_one_and_zero`) explicitly asserts the current behavior, and changing it would be a documented behavior change rather than a patch.

## Design Notes

**`systemInfo` envelope is not recorded in the research doc.** Only its field names are (§10). `format=json` mirrors the XML tree, so the expected shape is `{"system": {"server": {...}, "cameralist": {"camera": [...]}}}` — but treat that as an assumption. Decode through one small locator that accepts the wrapped or bare form and accepts `camera` as a list or a single dict, and raise `SecuritySpyUnsupportedVersionError` when no server block is locatable, rather than `KeyError`-ing on a guess. The fixture encodes the assumption in exactly one place, so correcting it later is a fixture edit plus a locator branch.

**Version comparison.** `version` is a dotted string like `6.20`; compare numerically component-by-component (`6.20 > 6.9`), never lexically. `MIN_SERVER_VERSION = (6, 0)` carries an `[ASSUMPTION]` comment pointing at PRD Open Q8 — the architecture has not pinned the earliest sufficient 6.x release.

**Timeout is what makes the bad-certificate criterion true.** "Fails rather than hangs" is a property of the `aiohttp.ClientTimeout` passed on every request, not of the TLS error itself; a default `total` (30 s) belongs on the client and must be exercised by a test that drives the timeout path.

## Verification

**Commands:**
- `cd aiosecurityspy && uv lock && uv sync --locked` -- expected: resolves on 3.14 with the new aiohttp pin, exit 0
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all tests pass, including every I/O matrix row
- `grep -rn "homeassistant\|deleteclip\|doShell\|doShortcut" aiosecurityspy/src` -- expected: no matches
- `grep -rn "://.*:.*@\|auth=" aiosecurityspy/src` -- expected: no credential-bearing URL construction

**Manual checks (if no CLI):**
- `client.py` builds URLs from host/port/path only, and credentials appear solely as an `aiohttp.BasicAuth` argument.


## Auto Run Result

**Status:** done (second follow-up review pass; no code was re-derived — no intent_gap and no bad_spec)

**Change:** Story 1.2 was already implemented and reviewed twice. This run was an independent third review of the same diff (`aeaedb2..HEAD` over `aiosecurityspy/`). Two adversarial reviewers ran in parallel; every reported finding was re-verified by executing the code against a real in-process `aiohttp` server before triage, and several reviewer claims were rejected on that basis. 9 patches were applied, 0 newly deferred, 11 rejected. Three were high severity, and all three were invisible to a 166-test suite that passed: a body-read bug that truncated every large `++systemInfo`, a `RuntimeError` escaping the typed exception hierarchy, and a redirect policy that reported a correct password as wrong.

**Files changed this pass:**
- `aiosecurityspy/src/aiosecurityspy/client.py` — body read replaced with a cap-enforcing accumulation loop; `RuntimeError` from `get_encoding()` mapped to `SecuritySpyConnectError`; `allow_redirects=False` with 3xx surfaced as a `use_https=True` hint; finite-timeout and integer-port validation; corrected host-validation and constructor docstrings.
- `aiosecurityspy/src/aiosecurityspy/const.py` — `decode_permissions()` degrades on a non-int instead of raising `TypeError`.
- `aiosecurityspy/tests/test_client.py` — `FakeContent` now fragments and tracks position (the stub that hid the truncation bug); redirect tests inverted to the new policy; non-integer-port and inf/nan-timeout tests; tautological host assertion replaced.
- `aiosecurityspy/tests/test_client_transport.py` — real-server regression tests for a >256 KB body and a charset-less `text/html` response; redirect test rewritten against the new policy.
- `aiosecurityspy/tests/test_models.py` — non-integer permission-mask test.
- `aiosecurityspy/CHANGELOG.md` — exception-containment list corrected; body-cap wording corrected; redirect policy recorded.

**Verification:** `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (11 files formatted), `uv run mypy --strict src tests` (no issues, 9 files), `uv run pytest -q` (**181 passed**, up from 166). `grep` for Home Assistant imports and for `deleteclip`/`doShell`/`doShortcut` over `src`: zero matches. `grep` for credential-bearing URLs: zero matches. The two high-severity transport defects were each reproduced against a real `aiohttp` server before the fix and re-tested after.

**Residual risks:**
- The redirect policy change is a behavior change to a public method: a deployment that genuinely relied on a same-origin redirect being followed would now get a `SecuritySpyConnectError`. This is judged correct — a cross-origin redirect could never have carried the credential — but it is not merely additive, and it is the main reason a follow-up review is recommended.
- The 8 MiB cap is now enforced correctly, but no test drives a body that actually exceeds it over a real server; the oversize path is covered only by the stub.
- The `++systemInfo` envelope and the permission bit table are still hand-authored from research §9/§10, never captured from a live server. The permission-prose contradiction and the `MIN_SERVER_VERSION` floor remain open in the deferred-work ledger.
- `verify_ssl` still has no real-TLS coverage (deferred), so the HTTPS guidance in the README is exercised only against a stub.
- `ServerInfo.uuid` still defaults to `""` when absent (deferred) — both reviewers independently flagged it this pass, which strengthens the case for the ledger item, but it needs a live capture to resolve.
- `aiohttp.BasicAuth` and the `auth=` kwarg remain deprecated for removal in aiohttp 4.0; the intent contract mandates `BasicAuth`, so the migration stays a spec-level decision (already in the ledger).

---

## Auto Run Result

**Status:** done (third follow-up review pass, DW-1 closure; no code was re-derived — no intent_gap and no bad_spec)

**Change:** Story 1.2 was already implemented and reviewed three times. DW-1 preserved the third pass's recommendation for an independent follow-up after the bmad-loop follow-up-review damping cap was spent. This run is the fourth review pass and acts on the new surface since the third pass (52e5eb54..HEAD on the story-1.2 files, ~8.5k lines added by stories 1.3 follow-up, 1.6, 1.10, 1.11, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18). Two adversarial reviewers ran in parallel; every reported finding was re-verified by executing the code against the actual library before triage. 2 patches applied (both high severity, both invisible to the existing 1,021-test suite), 1 newly deferred, 2 rejected. No intent_gap, no bad_spec; no spec amendment.

**Files changed this pass:**
- `aiosecurityspy/src/aiosecurityspy/client.py` — `quote(value, safe="")` wrapped in `try/except UnicodeEncodeError` at three call sites (preview URL, file URL, settings form body); each maps to `SecuritySpyConnectError` with a credential-free message, mirroring the read-side pattern for `UnicodeDecodeError`/`RuntimeError` closed in pass 3.
- `aiosecurityspy/src/aiosecurityspy/models.py` — `CapturePreview.__repr__` now prints `content_type` and `size` only, suppressing the up-to-8-MiB `data: bytes` payload. Follows the same minimal pattern as `CameraSettings.__repr__` (research §8.3).
- `aiosecurityspy/tests/test_client.py` — three new tests for surrogate paths at the three `quote()` sites, each asserting the value does not appear in `str`, `repr`, or `args` of the raised `SecuritySpyConnectError`.
- `aiosecurityspy/tests/test_settings.py` — one new test for the settings form builder with a surrogate in `CameraSettingsPatch.name`.
- `aiosecurityspy/tests/test_models.py` — one new test asserting `CapturePreview.__repr__` is < 200 bytes regardless of payload size.

**Verification:** from `aiosecurityspy/`: `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (28 files already formatted), `uv run mypy --strict src tests` (no issues, 23 source files), `uv run pytest -q` (**1,012 passed**, up from 1,008, +4 new tests). From the integration repo root: `uv run pytest -q` (54 passed), `uv run ruff check .` (all checks passed), `uv run mypy --strict custom_components tests` (no issues, 8 source files). The two high-severity defects were each reproduced against the actual library before the fix and re-tested after: a `CapturePreview` constructed with an 8 KiB payload now produces a 52-byte repr (was 8,075), and a `CameraSettingsPatch(name='Camera With\ud800 Name')` now raises `SecuritySpyConnectError` whose `str`, `repr`, and `args` do not contain the surrogate.

**Residual risks:**
- The same residual risks from pass 3 still hold (redirect policy, 8 MiB cap over real server, hand-authored `++systemInfo` envelope, no real-TLS coverage, `ServerInfo.uuid=""`, `aiohttp.BasicAuth` deprecation). One new item: the deferred `_PERMISSION_UNKNOWN` message ("account lacks the 'unknown' permission") for endpoints whose permission requirement this library does not model.
- The two high-severity patches were each reproduced by the reviewer before the fix, but neither had been added to the test suite before this pass -- meaning the test suite passed both bug states. Both sites now have regression tests.

**Sync note:** the patches were authored in the standalone mirror at `/Users/jensen/projects/aiosecurityspy/` (per the operator's hint that the library code "should live" there) and mirrored back into the in-tree subtree. The next `git subtree split` from `ha-securityspy/aiosecurityspy/` will pick them up.

