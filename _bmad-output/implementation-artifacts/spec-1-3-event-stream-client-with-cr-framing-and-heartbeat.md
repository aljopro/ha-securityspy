---
title: 'Story 1.3: Event stream client with CR framing and heartbeat'
type: 'feature'
created: '2026-08-10'
status: 'done'
baseline_revision: '160d53ca95f7fafd6cd227be9a99aa5457062047'
final_revision: '05a4df8'
review_loop_iteration: 0
followup_review_recommended: true  # 13 patches, 2 high; sticky pause and the widened constructor change public behaviour
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/research/securityspy-api-reference.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `aiosecurityspy` can authenticate and read `++systemInfo`, but nothing consumes SecuritySpy's live event stream. Story 1.5's reducer needs typed classification signals, Epic 3 needs the stream lifecycle callbacks, and Epic 4 needs `FILE` events to debounce reconciliation (FR-34, FR-41).

**Approach:** Add a stream client that reads `++eventStream?version=3` incrementally with CR-only framing, decodes each record into a frozen typed event with a per-type payload, and owns its own lifecycle: heartbeat watchdog, indefinite exponential backoff, and explicit `connected` / `disconnected` / `reconnected` / `auth_failed` callbacks (AD-11). The transport parameters already validated by `SecuritySpyClient` are factored into a shared internal connection object so the stream never re-implements host validation, auth, TLS or URL construction.

## Boundaries & Constraints

**Always:**
- Framing is CR (`0x0D`) only — the single most likely bug in any SecuritySpy client (research §3.1). Never call `readline()`, never split on `\n` alone. A record split across chunk boundaries must reassemble; a trailing `\n` or a `\r\n` pair must not produce an empty or corrupted record.
- Records decode to a frozen, fully-typed event carrying timestamp, event number, camera number, event type, and a decoded payload. Raw dicts and raw lines never cross the public boundary (AD-15). The unparsed line is preserved on the event for diagnosis.
- Camera field `X` (or any non-numeric value) means **not camera-specific** — `camera is None`, delivered, never dropped and never misattributed (research §3.2).
- The classification vocabulary is open (AD-9): a `CLASSIFY` label the library has never seen carries through as an ordinary `str` with its confidence. No enum, `Literal`, or validation rejects it. `class_slug()` is the only normalizer, and only where a permanent key is needed.
- Heartbeat: `NULL` arrives every 10 s on camera `X`. Loss is declared after three missed heartbeats (30 s of silence on the socket), `disconnected` fires **exactly once** per loss, then reconnection retries with exponential backoff **indefinitely**; a successful reconnect fires `reconnected`, which is distinct from the first-ever `connected` (AD-11).
- On 401/403 the stream fires `auth_failed`, **pauses** reconnection instead of looping, and stays paused until the consumer calls `resume()` (AD-11 + AD-18: the library never counts auth failures and never re-authenticates itself).
- `connect()` and `disconnect()` are idempotent; `disconnect()` twice is safe and leaves no task, timer, socket, or pending response behind (FR-33).
- No exception escapes the stream: transport failures become backoff, and a consumer callback that raises is logged and swallowed so one bad handler cannot kill the stream. No credential appears in any log line, message, or `repr` (AD-13).
- The injected session is never created, reconfigured, or closed by the library. The stream request carries no total timeout (it is long-lived by design) but must carry a bounded connect timeout.
- Zero Home Assistant imports; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict src tests` and `uv run pytest -q` stay clean, with no gate disabled and no blanket ignore.

**Block If:**
- The library's own gates cannot pass without disabling a gate or adding a blanket ignore.
- Refactoring the shared connection seam out of `client.py` would change any observable `SecuritySpyClient` behaviour asserted by the existing 181 tests.

**Never:**
- Do not implement capture history (1.4), the episode reducer (1.5) — the stream emits per-signal events and reduces nothing — settings/arming writes (1.6), or the anonymizer (1.7).
- Do not add a `MOTION_END`-based inactivity model: `MOTION_END` is unreliable (research §3.5) and the timeout belongs to the reducer, not here.
- Do not treat `event number` as a persistent ID — it is a per-connection counter that restarts at 0 on every reconnect.
- Do not expose `deleteclip`, `doShell`, `doShortcut`, add `custom_components/` files, or touch `sprint-status.yaml`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CR-only framing | Recorded fixture whose bytes contain `0x0D` separators and zero `0x0A` bytes | Every record is parsed and delivered in order; the reader never waits for an LF | No error expected |
| Split across chunks | One record delivered as two TCP chunks, the split falling mid-field | One event, correctly assembled | No error expected |
| Trailing/absent terminator | Final chunk ends without a CR; stream then ends | The buffered partial record is discarded, not emitted half-decoded | Debug log, no payload contents |
| `MOTION` | `20260809175335 0 7 MOTION 10 20 30 40` | Event with `camera=7`, `MotionPayload(x=10, y=20, width=30, height=40)` (origin top-left) | Unparseable box → payload `None`, event still delivered |
| `CLASSIFY` built-in | `... 7 CLASSIFY HUMAN 88 VEHICLE 3` | `ClassificationPayload` with `{"HUMAN": 88.0, "VEHICLE": 3.0}` keyed by the raw label | — |
| `CLASSIFY` unknown class | `... 7 CLASSIFY DELIVERY_VAN 61` from a Custom Model | `{"DELIVERY_VAN": 61.0}` carried through unchanged; built-in handling unaffected | Nothing rejects the label |
| `TRIGGER_M` | `... 7 TRIGGER_M 129` | `TriggerPayload(mask=129, reasons=frozenset({"video_motion", "human_movement"}))` | Non-numeric mask → payload `None` |
| `FILE` | `... 7 FILE /Volumes/Cam/2026-08-09/x.m4v` | `FilePayload(path=...)` with the full remainder, spaces preserved | — |
| Not camera-specific | `20260809175335 3 X NULL` | Event with `camera=None`, `event_type="NULL"`, delivered | Never dropped, never attributed to a camera |
| Unknown event type | `... 7 SOMETHING_NEW 1 2` | Event with `event_type="SOMETHING_NEW"`, `payload=None`, `info` preserved verbatim | Debug log once per type |
| Malformed record | Fewer than four fields, or a non-14-char timestamp | Record skipped; the stream continues with the next one | Debug log with no payload contents |
| Over-long record | A record exceeding the line cap with no CR in sight | Buffer is dropped rather than grown without bound; stream continues | Debug log |
| Heartbeat loss | Socket silent for 30 s (3 × 10 s) | `disconnected` fires exactly once; backoff reconnect begins | Connection closed before retry |
| Reconnect | Next connect attempt succeeds after ≥1 failure | `reconnected` fires (not `connected`); `connected` fired only on the first-ever success | Backoff resets on success |
| Auth failure | Stream request answers 401 or 403 | `auth_failed` fires, the retry loop pauses, no further connect attempts occur | `resume()` restarts it |
| Transport failure | `ClientError` / `OSError` / non-2xx on connect | Retry with exponential backoff, indefinitely, with jitter and a capped ceiling | Logged; never raised to the caller |
| Callback raises | A consumer callback raises `ValueError` | The exception is logged and swallowed; subsequent events still deliver | Stream stays connected |
| Double disconnect | `disconnect()` awaited twice, including before any `connect()` | Both return cleanly | No pending task, timer, or response remains |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/connection.py` -- new: `_ConnectionSettings` plus the `validate_host` / `validate_credentials` helpers moved verbatim out of `client.py`; the single place a SecuritySpy URL and `BasicAuth` are built (AD-13).
- `aiosecurityspy/src/aiosecurityspy/client.py` -- exists: constructor validation and URL building move to `connection.py`; add `event_stream(...)` factory. Public behaviour must not change.
- `aiosecurityspy/src/aiosecurityspy/events.py` -- new: frozen `StreamEvent` and per-type payload dataclasses, plus the line parser (pure, no I/O).
- `aiosecurityspy/src/aiosecurityspy/stream.py` -- new: `SecuritySpyEventStream` — CR framing, heartbeat watchdog, backoff, callbacks, idempotent connect/disconnect (AD-11).
- `aiosecurityspy/src/aiosecurityspy/const.py` -- exists: add `ENDPOINT_EVENT_STREAM`, `EVENT_*` type constants, the §3.4 trigger-reason bit table with `decode_trigger_reasons()`, heartbeat/backoff defaults.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- exists: re-export the new public surface.
- `aiosecurityspy/tests/test_client.py`, `tests/test_client_transport.py` -- exist: must keep passing unchanged through the connection refactor.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` -- §3.1 framing, §3.2 record format, §3.3 event types, §3.4 trigger bitmask, §3.5 empirical behaviour, §11 custom models. Authoritative over the published spec.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/connection.py` -- create: move `_validate_host` and `_validate_credentials` from `client.py` unchanged, and add a frozen `_ConnectionSettings` holding session, host, url_host, port, scheme, `BasicAuth`, `verify_ssl` and timeout, with `base_url`, `build_url(path)` and a credential-free `__repr__` -- the stream must not re-derive validated transport state, and credential-bearing URL construction stays in exactly one place (AD-13).
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: build a `_ConnectionSettings` in `__init__` and delegate `base_url`/auth/ssl/timeout to it; add `event_stream(*, on_event, on_connected=None, on_disconnected=None, on_reconnected=None, on_auth_failed=None, ...) -> SecuritySpyEventStream` -- one construction path for consumers, and no duplicated validation.
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `ENDPOINT_EVENT_STREAM`, `EVENT_STREAM_VERSION`, the `EVENT_*` string constants of §3.3, `TRIGGER_REASON_NAMES` transcribed from the §3.4 bit table (bits 0–16, non-contiguous meanings) with a `decode_trigger_reasons()` that degrades like `decode_permissions()`, plus `HEARTBEAT_INTERVAL`, `HEARTBEAT_MISSES_BEFORE_LOSS`, and the backoff bounds -- protocol vocabulary has one home.
- [x] `aiosecurityspy/src/aiosecurityspy/events.py` -- create: frozen `StreamEvent` (`timestamp: datetime | None`, `raw_timestamp: str`, `event_number: int`, `camera: int | None`, `event_type: str`, `info: str`, `payload: EventPayload | None`, `raw: str`) plus frozen `MotionPayload`, `ClassificationPayload` (with a `slugged()` helper), `TriggerPayload`, `FilePayload`, `ErrorPayload`, and `parse_event_line(line, *, server_timezone) -> StreamEvent | None` -- decoding is pure so every matrix row is testable with no socket.
- [x] `aiosecurityspy/src/aiosecurityspy/stream.py` -- create `SecuritySpyEventStream` with `connect()`, `disconnect()`, `resume()`, a `connected` property, a CR-splitting incremental reader with a line cap, a per-read heartbeat deadline, exponential backoff with jitter, and the four callbacks with sync-or-awaitable support and exception isolation -- AD-11 puts the whole lifecycle inside the library.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export `SecuritySpyEventStream`, the event and payload types, the new constants and `decode_trigger_reasons` in `__all__` -- the published API is a contract from first release.
- [x] `aiosecurityspy/tests/fixtures/event_stream.bin` -- create a recorded-shape fixture using only `0x0D` terminators, covering `MOTION`, `MOTION_END`, `CLASSIFY` (built-in and a custom-model label), `TRIGGER_M`, `TRIGGER_A`, `FILE`, `ARM_C`, `ONLINE`, `ERROR`, `CONFIGCHANGE` and `NULL`, with at least one `X` camera and one malformed record -- protocol fixtures are this epic's testing strategy.
- [x] `aiosecurityspy/tests/test_events.py` -- create: assert the fixture contains zero `0x0A` bytes, then cover every decoding row of the I/O matrix from the fixture and synthetic lines, including the unknown class, the `X` camera, trigger-bit decoding, and malformed records -- pure decode coverage.
- [x] `aiosecurityspy/tests/test_stream.py` -- create: drive the lifecycle over a stubbed streaming response — chunk-boundary reassembly, heartbeat loss firing `disconnected` exactly once, backoff reconnect firing `reconnected` not `connected`, auth failure firing `auth_failed` and pausing, `resume()` restarting, double `disconnect()`, no leaked tasks, and a raising callback not killing the stream, with time advanced rather than slept -- the lifecycle constraints are only real if asserted.
- [x] `aiosecurityspy/tests/test_stream_transport.py` -- create: run the stream against a real in-process `aiohttp` server that emits CR-only bytes and a 401 case, following the existing `test_client_transport.py` fixture style -- proves the framing survives real chunking, which a stub cannot.
- [x] `aiosecurityspy/README.md` -- edit: add a runnable event-stream snippet showing the callbacks and `disconnect()` -- the "usable from an ordinary script" success criterion.
- [x] `aiosecurityspy/CHANGELOG.md` -- edit: record the stream client, event models and new constants under Unreleased -- AD-14.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- edit: append the server-timezone assumption below if it is still unresolved at the end of implementation -- an assumption that needs a live server is ledger work, not a guess.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a script with no Home Assistant installed, when it creates its own `aiohttp.ClientSession`, builds a client, calls `event_stream(on_event=...)`, awaits `connect()` and later `disconnect()`, then no other library object is needed and the session is still open afterwards.
- Given a consumer running `mypy --strict` against code importing `SecuritySpyEventStream`, `StreamEvent` and the payload types, then every public name resolves through `__all__` with complete type information and no `Any` in a public signature.
- Given the whole `aiosecurityspy` tree, when it is searched for Home Assistant imports, for `deleteclip`/`doShell`/`doShortcut`, and for `readline`, then there are zero matches.

## Spec Change Log

## Review Triage Log

### 2026-08-10 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 2, medium 5, low 6)
- defer: 0
- reject: 2
- addressed_findings:
  - `[high]` `[patch]` `stream.py:_run` never reset the backoff delay after a successful connection, so a server that dropped the stream every few minutes reached the 300 s ceiling and stayed there — verified by execution (sleeps of ~300 s after ~10 *healthy* reconnects). The delay now resets to `backoff_initial` whenever the attempt actually reached the server, so backoff spaces consecutive failures only.
  - `[high]` `[patch]` `disconnect()` called from inside a consumer callback cancelled and awaited the *current* task; `contextlib.suppress` ate the `CancelledError`, the reader survived, and a later `connect()` ran two concurrent readers — verified by execution. It now detects `task is asyncio.current_task()` and lets the cancellation unwind instead of self-awaiting, leaving `_task` in place so `connect()` still sees an unfinished reader.
  - `[medium]` `[patch]` The auth-failure path set `self._task = None` before awaiting a possibly-slow `on_auth_failed` handler, so a `disconnect()`/`resume()` in that window had nothing to await and could spawn a second reader. The reader no longer mutates `_task` at all; ownership sits entirely with the lifecycle methods.
  - `[medium]` `[patch]` Concurrent `connect()`/`disconnect()`/`resume()` could leave a live reader while `connected` reported `False`. All three now run under an `asyncio.Lock` the reader never takes, so a callback-initiated `disconnect()` cannot deadlock.
  - `[medium]` `[patch]` `_decode_classification` used a bare `float()`, accepting `nan`, `1e999` and `"1_0"` (verified) while its sibling `_parse_int` deliberately rejected exactly those; NaN then won the `slugged()` merge and evicted a real confidence. Added a strict `_parse_float()` and made `slugged()` always prefer a finite value.
  - `[medium]` `[patch]` `_REPORTED_UNKNOWN_TYPES` was an unbounded process-global set shared across every stream. Now bounded at 64 entries and cleared wholesale when full — it is log damping, not a correctness record.
  - `[medium]` `[patch]` `_parse_int` hit CPython's 4300-digit `int()` limit, so one mis-framed record tore down the live connection instead of being skipped. Length-guarded before conversion.
  - `[low]` `[patch]` Tuning validation used a bare `value <= 0`, which NaN passes; `asyncio.timeout(nan)` then raises `TypeError` from the selector. Now requires positive *and* finite, matching `client.py`'s timeout check.
  - `[low]` `[patch]` `_parse_timestamp`'s `astimezone()` could raise `OverflowError` near year 0001/9999 under a non-UTC `server_timezone`, killing the stream; now returns `None`.
  - `[low]` `[patch]` The record cap was checked only after the CR scan while the read chunk was itself 64 KiB, so the buffer could reach ~128 KiB against a documented 64 KiB bound; and clearing it blind resynced on an arbitrary byte. The read size now honours the cap and an over-long drop discards until the next CR.
  - `[low]` `[patch]` `_paused` had two doors through the AD-18 contract: `connect()` cleared it and `disconnect()` discarded it. It is now sticky, and `resume()` is the only way out.
  - `[low]` `[patch]` The suite structurally could not observe the backoff defect: every test pinned `backoff_initial == backoff_max`, and the multiplier and jitter were module constants. Both are now constructor parameters, with tests asserting growth, ceiling, reset-after-success and jitter bounds.
  - `[low]` `[patch]` `CHANGELOG.md` and `README.md` claimed `disconnect()` left no task behind and that no exception escaped — both false on the callback path — and did not mention backoff reset or the sticky pause. Corrected to the fixed behaviour.
- Rejected (recorded for traceability, not acted on): adding a `Content-Type` check on the stream response (SecuritySpy's actual stream content type is unrecorded in the research, so rejecting on it risks dropping real streams); and making `connect()` non-async (it is deliberately a coroutine so the published API can await later without a breaking change).

## Design Notes

**Framing, concretely.** Accumulate bytes and split on `b"\r"`; keep the tail as the partial record. Strip a leading/trailing `b"\n"` from each record defensively (the research says there are none, but a future server build adding CRLF must not produce empty records). Decode each record as UTF-8 with `errors="replace"` — a mangled camera name must not kill the stream.

```
20260809175335 0 7 MOTION_END\r20260809175336 1 X NULL\r
-> StreamEvent(camera=7, event_type="MOTION_END"), StreamEvent(camera=None, event_type="NULL")
```

**Heartbeat = socket silence, not `NULL` counting.** `NULL` is every 10 s exactly, but real traffic (915 `MOTION` events in 100 s) also proves liveness. The watchdog is a 30 s deadline on each read; any bytes reset it. This satisfies "three missed heartbeats" and cannot false-positive on a busy camera.

**`connected` vs `reconnected`.** One boolean: `connected` fires on the first successful connect of the object's life; every later successful connect fires `reconnected`. A `disconnect()`/`connect()` pair by the consumer therefore also yields `reconnected`, which is correct — the adapter must reconcile after any gap (AD-10).

**Timestamps carry no zone.** The 14-char `YYYYMMDDHHMMSS` is server-local wall time and no endpoint in the research exposes the server's timezone. The stream takes `server_timezone: tzinfo = UTC` and converts to tz-aware UTC (AD-15); `raw_timestamp` keeps the original string so a consumer can re-interpret. Mark it `[ASSUMPTION]` in code and add a deferred-work entry.

**`event_number` restarts at 0 per connection** — record it, never key off it.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all tests pass, the 181 pre-existing ones included
- `python3 -c "print(open('aiosecurityspy/tests/fixtures/event_stream.bin','rb').read().count(b'\n'))"` -- expected: `0`
- `grep -rn "readline\|homeassistant\|deleteclip\|doShell\|doShortcut" aiosecurityspy/src` -- expected: no matches
- `grep -rn "://.*:.*@\|auth=" aiosecurityspy/src` -- expected: no credential-bearing URL construction

**Manual checks (if no CLI):**
- `stream.py` splits on `b"\r"` only, passes `timeout` with `total=None` and a bounded `sock_connect`, and never closes the injected session.

## Auto Run Result

**Status:** done

**Change:** Story 1.3 adds the event-stream half of `aiosecurityspy`. `++eventStream?version=3` is read incrementally with CR-only framing (research §3.1 — the named single most likely bug in any SecuritySpy client), each record decodes to a frozen typed `StreamEvent` with a per-type payload, and `SecuritySpyEventStream` owns the whole lifecycle per AD-11: a socket-silence heartbeat watchdog, indefinite jittered exponential backoff, `connected`/`disconnected`/`reconnected`/`auth_failed` callbacks, pause-on-auth-failure with an explicit `resume()`, and an idempotent `disconnect()`. The transport state `SecuritySpyClient` already validated was factored into `connection.py` so the stream re-implements no host validation, auth, TLS or URL construction, and `SecuritySpyClient` behaviour is unchanged — all 181 pre-existing tests still pass untouched.

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/connection.py` — new: `ConnectionSettings` plus the host/credential validators moved out of `client.py`; the one place a URL and `BasicAuth` are built (AD-13).
- `aiosecurityspy/src/aiosecurityspy/events.py` — new: `StreamEvent` and the `Motion`/`Classification`/`Trigger`/`File`/`Error` payloads, plus the pure `parse_event_line()`.
- `aiosecurityspy/src/aiosecurityspy/stream.py` — new: `SecuritySpyEventStream` — framing, watchdog, backoff, callbacks, lifecycle.
- `aiosecurityspy/src/aiosecurityspy/client.py` — delegates transport state to `ConnectionSettings`; adds the `event_stream(...)` factory.
- `aiosecurityspy/src/aiosecurityspy/const.py` — `ENDPOINT_EVENT_STREAM`, `EVENT_*` types, the §3.4 trigger-reason bit table with `decode_trigger_reasons()`, heartbeat/backoff/record-cap defaults.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` — exports the new public surface.
- `aiosecurityspy/tests/fixtures/event_stream.bin` — CR-only fixture, 15 records, zero LF bytes.
- `aiosecurityspy/tests/test_events.py`, `test_stream.py`, `test_stream_transport.py` — 106 new tests, the last against a real in-process `aiohttp` server.
- `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` — runnable stream snippet; release notes.
- `_bmad-output/implementation-artifacts/deferred-work.md` — server-timezone assumption recorded.

**Review findings:** 13 patches applied (2 high, 5 medium, 6 low), 0 deferred, 2 rejected, 0 intent gaps, 0 spec repairs. Both high-severity defects were lifecycle bugs invisible to a 256-test suite that passed: backoff that never reset after a healthy reconnect, and a `disconnect()` from inside a callback that left an orphan reader and could double it. 31 regression tests were added, each verified to fail against the pre-fix code.

**Verification:** `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (17 files formatted), `uv run mypy --strict src tests` (no issues, 15 files), `uv run pytest -q` (**287 passed** — 181 pre-existing plus 106 new — in 0.83 s, stable across repeated runs). `grep` over `src` for `readline`, Home Assistant imports and `deleteclip`/`doShell`/`doShortcut`: zero matches. Fixture LF byte count: 0. Independently of the suite, an ordinary script with no Home Assistant installed was run against a real `aiohttp` server: it created its own session, built the client, opened the stream, received a custom-model `CLASSIFY` and an `X`-camera `NULL`, called `disconnect()` twice, and left the session open with zero leftover tasks; `mypy --strict` on that script passed with no `Any` in any public signature.

**Residual risks:**
- `server_timezone` defaults to UTC because no endpoint in the research exposes the server's zone. A server in another zone reports every event hours off — silently wrong rather than visibly broken. `raw_timestamp` preserves the original string; the ledger holds the open question.
- The `++eventStream` record grammar is transcribed from research §3, itself derived from one 100-second capture. Event types outside that capture are carried through with `payload=None` by design, but an `INFO` shape that differs from §3.3 would decode to `None` rather than raising.
- The heartbeat watchdog treats any traffic as liveness, not `NULL` records specifically. That cannot false-positive on a busy camera, but a server emitting garbage without `NULL`s would be considered alive.
- The stream's reconnect path is exercised only against stubs and an in-process server; no real SecuritySpy server, and no TLS, has been involved (real-TLS coverage remains open in the ledger from 1.2).
- `disconnect()` from inside a callback now returns *before* the reader has fully unwound — the cancellation is requested and unwinds as the callback returns. This is the only way to avoid a self-await, and it is asserted by test, but it is a weaker guarantee than the foreign-task path.
- Two high-severity lifecycle defects were found and fixed in review on behaviour the suite already covered, and the fixes widened the constructor (`backoff_multiplier`, `backoff_jitter`) and made the pause sticky — a behaviour change to a public method. That is why a follow-up review is recommended.
