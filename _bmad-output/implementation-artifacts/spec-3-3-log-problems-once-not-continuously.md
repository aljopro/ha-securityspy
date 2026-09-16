---
title: 'Log problems once, not continuously'
type: 'feature'
created: '2026-09-15'
status: 'done'
baseline_revision: '5b3fe55be680f736ff4e6c75e579cd037cdabb7b'
final_revision: 'bcee8681ce32d06c68db29d0352f91adf26af177'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
---

<intent-contract>

## Intent

**Problem:** Story 3.2 wired the Event Stream's `connected`/`disconnected`/`reconnected` callbacks into `SecuritySpyDataUpdateCoordinator.async_handle_stream_*`, but none of them log anything (FR-32). A multi-hour outage with indefinite exponential-backoff retries is currently either silent or, if retry logging is later added carelessly, would flood the log at a volume proportional to outage length.

**Approach:** Add exactly one `LOGGER.error` call naming the server on the loss transition, and exactly one `LOGGER.warning` call on the recovery transition, both inside `async_set_stream_connected` in `coordinator.py` where the existing True/False dedup already guarantees each fires only once per transition. Retry-attempt visibility already exists at DEBUG in the `aiosecurityspy` library's own logger during backoff; no new retry logging is added in the integration.

## Boundaries & Constraints

**Always:** Log the connection-loss transition exactly once at ERROR, naming the server (`self.data.server.name`). Log the recovery transition exactly once at WARNING. Reuse the existing `async_set_stream_connected` True/False dedup (coordinator.py:204-206) as the sole gate — do not add a second "already logged" flag. A subsequent loss-then-recovery cycle must log once each again, since the dedup flag naturally resets by flipping back and forth.

**Block If:** Nothing here requires human judgment; proceed.

**Never:** Do not add any integration-side DEBUG logging for individual retry attempts — that already comes from `aiosecurityspy`'s own logger and duplicating it would violate the "small, bounded number of non-debug entries" requirement by risking accidental promotion above DEBUG later. Do not log payloads or settings bodies at any level (pre-existing project-wide rule). Do not change `async_handle_stream_connected`'s (first-ever connect) behavior — it has no prior "disconnected" state to recover from, so it must not log a spurious WARNING recovery message. `async_handle_stream_reconnected` reuses `async_set_stream_connected(True)` exactly like `async_handle_stream_connected` does today, so it gets the WARNING for free without any per-call special-casing.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First-ever connect | `stream_connected` starts `False`; `async_handle_stream_connected()` fires | `stream_connected` becomes `True`; no log line (no prior loss to recover from) | No error expected |
| Connection lost | `stream_connected` is `True`; `async_handle_stream_disconnected()` fires | Exactly one `LOGGER.error` naming the server; `stream_connected` becomes `False` | No error expected |
| Repeated disconnect calls during one outage | `stream_connected` already `False`; `async_handle_stream_disconnected()` fires again | No-op, no new log line (existing dedup at coordinator.py:204) | No error expected |
| Connection recovers | `stream_connected` is `False`; `async_handle_stream_reconnected()` fires | Exactly one `LOGGER.warning`; `stream_connected` becomes `True`; reconciliation still runs as in 3.2 | No error expected |
| Second loss-then-recovery cycle | A prior cycle already logged once each | New ERROR on the next loss, new WARNING on the next recovery — dedup flag reset by the intervening state flip | No error expected |

</intent-contract>

## Code Map

- `custom_components/securityspy/coordinator.py:193-207` -- `async_set_stream_connected`: add the ERROR/WARNING log calls on the two transition branches; this is the single gate all three handlers already funnel through.
- `custom_components/securityspy/coordinator.py:210-236` -- `async_handle_stream_connected` / `async_handle_stream_disconnected` / `async_handle_stream_reconnected`: unchanged; they already call `async_set_stream_connected`, so no per-handler logging is added.
- `tests/test_coordinator.py:783-870` -- existing stream-handler tests; extend with caplog-based assertions following the pattern already used elsewhere in the file (e.g. lines 298-349, 600-625: `with caplog.at_level(...)`, filter `caplog.records` by `levelname` and `record.name == "custom_components.securityspy"`).

## Tasks & Acceptance

**Execution:**
- [x] `custom_components/securityspy/coordinator.py` -- in `async_handle_stream_disconnected`, log `LOGGER.error("SecuritySpy stream connection to %s lost", self.data.server.name)` guarded by `if self.stream_connected:` (checked before calling `async_set_stream_connected(False)`) -- delivers AC1: exactly one ERROR per loss, naming the server, with no per-attempt repeats since the guard reads the pre-transition flag.
- [x] `custom_components/securityspy/coordinator.py` -- in `async_handle_stream_reconnected`, log `LOGGER.warning("SecuritySpy stream connection to %s recovered", self.data.server.name)` guarded by `if not self.stream_connected:` (checked before calling `async_set_stream_connected(True)`) -- delivers AC3: exactly one WARNING per recovery, and leaves `async_handle_stream_connected` (first-ever connect) untouched and log-free per the Design Notes.
- [x] `tests/test_coordinator.py` -- add tests: first connect logs nothing, disconnect logs exactly one ERROR naming the server, repeated disconnect calls add no further ERROR, reconnect logs exactly one WARNING, a second loss/recovery cycle logs one ERROR and one WARNING again -- covers the full I/O matrix.

**Acceptance Criteria:**
- Given a connected stream, when it disconnects, then exactly one ERROR log line naming the server is emitted, and further disconnect signals during the same outage add no more.
- Given an ongoing outage, when reconnection attempts occur, then no integration-side log line above DEBUG is produced by those attempts (library-level DEBUG retry logging is unaffected and out of scope).
- Given a disconnected stream, when it reconnects, then exactly one WARNING log line is emitted, and a subsequent disconnect/reconnect cycle produces one ERROR and one WARNING again.
- Given the very first stream connect after setup, when it succeeds, then no recovery WARNING is logged (there was no prior loss).

## Spec Change Log

## Review Triage Log

### 2026-09-15 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (low 2)
- defer: 3: (low 2, medium 1)
- reject: 4: (low 4)
- addressed_findings:
  - `[low]` `[patch]` No test exercised repeated `async_handle_stream_reconnected()` signals for WARNING dedup, symmetric to the existing repeated-disconnect coverage — extended `test_stream_reconnect_logs_exactly_one_warning` to call it three times and assert exactly one WARNING.
  - `[low]` `[patch]` Neither new logging test asserted the final `stream_connected` value, so a broken early-return beside the new log guard could pass all logging assertions while silently breaking entity availability — added `assert coordinator.stream_connected is False/True` to the disconnect and reconnect logging tests.

Deferred to `deferred-work.md`: unconditional `_async_reconcile()`/`_async_poll_light_status()` re-run on redundant reconnect signals (pre-existing cost from Story 3.2, unrelated to this story's logging change); `ServerInfo.name` is server-reported and not guaranteed unique across config entries, so two identically-named servers would produce indistinguishable log lines; the recovery WARNING logs before `_async_reconcile()` runs, so a reconcile failure immediately after a logged "recovered" message has no correlating log tying the two together.

Rejected as noise: strict-emptiness assertion in `test_stream_first_connect_logs_nothing` vs. level-scoped assertions elsewhere (stylistic, not a defect); the call-site guard duplicating the boolean check that `async_set_stream_connected` also performs (explicitly sanctioned by this spec's Design Notes); missing comment/heading separating the new logging tests from surrounding tests (cosmetic); the edge-case-hunter's `on_reconnected`-before-`on_connected` scenario, which the library's own connect-before-reconnect callback contract makes unreachable.

## Design Notes

The key design decision, resolved above: logging must live at the call sites that already distinguish "first connect" (`async_handle_stream_connected`) from "reconnected after a loss" (`async_handle_stream_reconnected`), rather than inside the shared `async_set_stream_connected` setter, because the setter's own `stream_connected` boolean cannot distinguish "never connected" from "was connected, now isn't" on the `False → True` edge. Concretely:

```python
@callback
def async_handle_stream_disconnected(self) -> None:
    """Record a lost connection; push-derived entities go unavailable."""
    if self.stream_connected:
        LOGGER.error("SecuritySpy stream connection to %s lost", self.data.server.name)
    self.async_set_stream_connected(False)

async def async_handle_stream_reconnected(self) -> None:
    if not self.stream_connected:
        LOGGER.warning("SecuritySpy stream connection to %s recovered", self.data.server.name)
    self.async_set_stream_connected(True)
    await self._async_reconcile()
    await self._async_poll_light_status()
```

Checking `self.stream_connected` *before* calling the setter (which then dedupes internally) keeps the "only on a real transition" guarantee without adding a second flag, and keeps `async_handle_stream_connected` (first-ever connect) untouched and log-free.

## Verification

**Commands:**
- `pytest tests/test_coordinator.py -k stream -q` -- expected: all stream-handler tests, including the new logging assertions, pass.
- `ruff check custom_components/securityspy/coordinator.py tests/test_coordinator.py` -- expected: no lint violations.

## Auto Run Result

Status: done

**Summary:** Added log-once ERROR/WARNING logging to the Event Stream's disconnect/reconnect handlers in the coordinator, gated on the pre-transition `stream_connected` flag so each fires exactly once per loss/recovery cycle and resets correctly across repeated cycles, per FR-32. A prior session's implementation was logically correct but failed deterministic `ruff format --check` verification because the two new `LOGGER` calls were wrapped onto extra lines; this session reformatted them to the single-line form ruff expects. No behavioral or intent changes were made.

**Files changed:**
- `custom_components/securityspy/coordinator.py` -- `async_handle_stream_disconnected` logs one ERROR naming the server on a real loss transition; `async_handle_stream_reconnected` logs one WARNING on a real recovery transition; `async_handle_stream_connected` (first-ever connect) is untouched and stays log-free. This session's only change: reformatted the two `LOGGER` calls to satisfy `ruff format`.
- `tests/test_coordinator.py` -- four new/extended tests covering first-connect silence, single ERROR on loss (with repeat-call dedup and final-state assertion), single WARNING on recovery (with repeat-call dedup and final-state assertion), and a second loss/recovery cycle logging one ERROR and one WARNING again.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- two entries appended for pre-existing/out-of-scope issues surfaced by review (see below).

**Review findings breakdown:** 2 low-severity patches applied (repeated-reconnect test symmetry; final-state assertions coupling the log to `stream_connected`). 3 items deferred (unconditional reconcile re-run on redundant reconnect signals, pre-existing from 3.2; non-unique `ServerInfo.name` across config entries in log messages; no log correlation between a "recovered" WARNING and an immediately-following reconcile failure). 4 items rejected as noise (test-assertion style preference; the call-site boolean-check duplication that this spec's Design Notes explicitly chose; test file organization; an `on_reconnected`-before-`on_connected` ordering that the library's callback contract makes unreachable).

**Verification performed:** `uv run ruff format --check .` -- 99 files already formatted (previously failed on coordinator.py; fixed by this session). `pytest tests/test_coordinator.py -k stream -q` -- 9 passed. `ruff check custom_components/securityspy/coordinator.py tests/test_coordinator.py` -- all checks passed.

**Residual risks:** None blocking. The three deferred items are pre-existing or out-of-scope for this story's acceptance criteria and are tracked in `deferred-work.md` for future focused attention.

