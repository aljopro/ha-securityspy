---
title: 'Recover from connection loss without being asked'
type: 'feature'
created: '2026-09-15'
status: 'done'
baseline_revision: '9453397ee374a0bd8900eff45aad4be2138bc945'
final_revision: '6c731a0'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
---

<intent-contract>

## Intent

**Problem:** The integration has no push connection wired up at all (Epic 3's `stream_connected` flag exists on the coordinator but nothing ever sets it), so a SecuritySpy restart, Mac reboot, or network drop is invisible until the user notices stale data and reloads the entry by hand.

**Approach:** `aiosecurityspy` 0.4.0 already ships a fully self-managing `SecuritySpyEventStream` (CR framing, heartbeat watchdog at 3 missed heartbeats, indefinite exponential backoff, four lifecycle callbacks) per AD-11 and AD-19 -- the integration only has to build one from the setup-time client/server, wire its four lifecycle callbacks into the coordinator, and trigger a full poll-plane reconciliation on `reconnected` (FR-31, AD-10).

## Boundaries & Constraints

**Always:** Leave heartbeat/backoff tuning at the library's own defaults (AD-11) -- they already match the documented 3-missed-heartbeats / indefinite-backoff policy, so restating them locally is a second place for the two to drift. The stream is the single implementation of the wire protocol (AD-19); the integration never reimplements framing, heartbeat, or backoff itself. Auth failures from the stream feed the existing single `auth_failures` counter via `coordinator.record_auth_failure` (AD-18) -- no second counter.

**Block If:** N/A -- no decision in this story requires human input; `aiosecurityspy` already publishes everything the ACs need.

**Never:** Do not have this story consume `StreamEvent` payloads for observation state (Epic 4/5's job -- this story owns only the connection lifecycle, not what a decoded event means). Do not duplicate the "logged exactly once" discipline story 3.3 owns; minimal connection-lifecycle logging only.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First connect | Entry sets up, stream connects for the first time | `stream_connected` becomes `True`; no extra reconciliation (setup already synced) | N/A |
| Heartbeat loss | Server goes silent past 3 missed heartbeats | Library declares the connection lost; `on_disconnected` fires | `stream_connected` becomes `False`; push-derived entities go unavailable |
| Reconnect after outage | Server returns; library reconnects with backoff | `on_reconnected` fires: `stream_connected` set `True`, both heavy and light polls re-fetch | No HA restart, reload, or reauth required |
| Auth rejected on the stream | Server answers 401/403 | `on_auth_failed` fires | `coordinator.record_auth_failure()` is called, feeding the shared AD-18 counter; library pauses its own reconnection |
| Server publishes no UTC offset | `ServerInfo.utc_offset is None` | Stream is built with `server_timezone=UTC` | No error; matches the library's own documented fallback |
| Unload | Config entry is unloaded | `stream.disconnect()` is awaited; no task/connection survives | N/A |

</intent-contract>

## Code Map

- `custom_components/securityspy/__init__.py` -- builds the Event Stream (`_async_start_stream`) alongside the RTSP relay, wires its four lifecycle callbacks to the coordinator, registers `stream.disconnect` on unload, stores it on `SecuritySpyRuntimeData`
- `custom_components/securityspy/coordinator.py` -- adds `async_handle_stream_connected` / `async_handle_stream_disconnected` / `async_handle_stream_reconnected`, the last of which triggers a full `_async_reconcile` + `_async_poll_light_status` pass (FR-31); `record_auth_failure` is reused directly as `on_auth_failed`
- `tests/conftest.py` -- `mock_event_stream` fixture and default awaitable `connect`/`disconnect` on every test's mocked client
- `tests/test_init.py` -- setup/unload wiring, UTC-offset handling, lifecycle-callback identity, reconnect-triggers-reconciliation
- `tests/test_coordinator.py` -- unit coverage of the three new handler methods

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/__init__.py` -- add `_async_start_stream` + `_async_handle_stream_event`, wire into `async_setup_entry`, add `stream` field to `SecuritySpyRuntimeData` -- gives the integration an actual push connection
- [x] `custom_components/securityspy/coordinator.py` -- add the three stream lifecycle handler methods -- FR-31's reconcile-on-reconnect requirement lives on the coordinator, not in setup
- [x] `tests/conftest.py` -- `mock_event_stream` fixture -- lets tests assert on the stream without touching real sockets
- [x] `tests/test_init.py` -- wiring, UTC-offset fallback, and reconnect-triggers-reconciliation tests
- [x] `tests/test_coordinator.py` -- unit tests for the three handler methods

**Acceptance Criteria:**
- Given an established connection, when the server's heartbeat stops, then the library declares the loss within 3 missed heartbeats (its own documented default) and `on_disconnected` clears `stream_connected`
- Given a detected disconnection, when the integration responds, then the library retries with indefinite exponential backoff (its own default) with no attempt limit imposed by the integration
- Given the server returns after an outage, when `on_reconnected` fires, then `async_handle_stream_reconnected` re-fetches both poll planes and requires no HA restart, entry reload, or reauth
- Given the entity classes, when availability is inspected, then only the shared base (`entity.py`, already done in 3.1) reads `stream_connected` -- no platform overrides it

## Design Notes

The library (`aiosecurityspy` 0.4.0) already fully implements AD-11: `SecuritySpyEventStream.connect()` schedules its reader and returns immediately (non-blocking, AD-10), retries indefinitely with jittered exponential backoff, and declares loss after `heartbeat_interval * heartbeat_misses` (10s * 3 = 30s) of socket silence -- matching this project's own "within 3 missed heartbeats" requirement exactly. `on_auth_failed` pauses the library's own reconnection loop until an explicit `resume()`; this story does not call `resume()` because the only path back from an auth failure is Home Assistant's reauth flow, which reloads the entry and builds a fresh, unpaused stream.

## Spec Change Log

## Review Triage Log

### 2026-09-15 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 3 (high 0, medium 1, low 2)
- defer: 2 (high 0, medium 2, low 0)
- reject: 9
- addressed_findings:
  - `[medium]` `[patch]` Stream was created and `connect()`ed before `coordinator.async_start()` ran, so `async_handle_stream_connected`'s "registry already synced" claim held only by scheduling accident, not by anything the code established. Reordered `async_setup_entry` so `coordinator.async_start()` completes before `_async_start_stream` is called.
  - `[low]` `[patch]` No test exercised the stream's `on_auth_failed` path end-to-end (only bound-method identity was checked). Added `test_stream_auth_failed_counts_towards_the_shared_threshold`, invoking the wired callback three times and asserting the shared AD-18 counter and reauth flow.
  - `[low]` `[patch]` `test_stream_reconnect_triggers_a_full_reconciliation` set `coordinator.stream_connected` via direct attribute assignment (dead/misleading — it was already `False`) instead of the API the story's contract runs through, and never asserted listeners were notified. Removed the dead assignment and added a listener-notification assertion.

Findings deferred to `deferred-work.md` (not this story's problem to fix, surfaced incidentally):
- A permission denial scoped to `++eventStream` alone pauses the stream permanently with no diagnostic trail (the library's own `on_auth_failed` pause design, AD-11/AD-18, has no `resume()` caller here).
- `_async_reconcile`/`_async_poll_light_status` have no guard against two concurrent invocations; this story adds a third caller into an already-existing pre-3.2 race window.

Rejected (reasoning, not restated per-finding): several findings asked for defensive exception handling around library calls (`event_stream()`, `connect()`, `timezone(utc_offset)`) that the library's own contract (AD-11's "no exception escapes this module"; `ServerInfo.utc_offset`'s decode-time range clamp) already rules out for any `ServerInfo` obtained through `client.async_get_server_info()`; adding guards for states the library guarantees cannot occur would violate AD-19 (never compensate in the adapter for something that belongs upstream) and this project's own "don't guard against scenarios that can't happen" convention. Two findings (event-discard observability, UTC-offset-ambiguity logging) restated deliberate, already-documented scope boundaries (Epic 4/5 owns event consumption; the library already logs a rejected offset at its own decode site). One (relay/stream unload ordering) and one (relay failure blocking stream startitup) described pre-existing, untested-but-harmless coupling with the relay, unrelated to this story's own correctness.

## Verification

**Commands:**
- `python -m pytest` -- 186 passed
- `ruff check custom_components/securityspy tests` -- all checks passed
- `mypy custom_components/securityspy` -- no issues found in 9 source files

## Auto Run Result

Status: done

**Summary:** Wired `aiosecurityspy`'s already-shipped `SecuritySpyEventStream` into the integration. Setup now builds and connects the stream alongside the RTSP relay; its four lifecycle callbacks feed the coordinator's existing `stream_connected` flag and shared AD-18 auth-failure counter, and reconnecting triggers a full heavy+light poll-plane reconciliation (FR-31). Heartbeat loss detection (3 missed heartbeats) and indefinite exponential backoff are the library's own defaults, unmodified.

**Files changed:**
- `custom_components/securityspy/__init__.py` -- `_async_start_stream` builds/connects the stream and registers its unload; `SecuritySpyRuntimeData` gains a `stream` field
- `custom_components/securityspy/coordinator.py` -- three new lifecycle handler methods; `record_auth_failure` reused directly as `on_auth_failed`
- `tests/conftest.py` -- `mock_event_stream` fixture, default awaitable `connect`/`disconnect`
- `tests/test_init.py`, `tests/test_coordinator.py` -- wiring, UTC-offset fallback, reconnect-reconciliation, and auth-failure coverage

**Review findings:** 3 patched (reorder `coordinator.async_start()` before stream connect so the "registry already synced" claim is actually true rather than scheduling luck; added an end-to-end auth-failure test; cleaned up a test that bypassed the flag-change API it was meant to exercise), 2 deferred to `deferred-work.md` (a permission denial scoped to `++eventStream` alone pauses the stream with no diagnostic trail; a pre-existing, now slightly more reachable race between concurrent `_async_reconcile`/`_async_poll_light_status` callers), 9 rejected (mostly requests to guard against states the library's own documented contract already rules out, which AD-19 forbids compensating for in the adapter).

**Verification:** `python -m pytest` (186 passed), `ruff check` (clean), `mypy` (clean).

**Residual risk:** The two deferred findings above. Neither blocks this story's acceptance criteria, which are about ordinary network-outage recovery, not permission-scoped stream denial or high-frequency reconcile overlap.

Commits: `6c731a0` (feat), `a2963a7` (docs).
