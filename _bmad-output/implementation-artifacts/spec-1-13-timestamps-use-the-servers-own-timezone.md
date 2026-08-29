---
title: "Story 1.13: Timestamps use the server's own timezone"
type: 'bugfix'
created: '2026-08-29'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** Event-stream records and capture entries carry the server's **local** wall clock as a bare `YYYYMMDDHHMMSS` string with no offset. Four public entry points default `server_timezone` to `UTC`, and `events.py:367` justifies it with *"No SecuritySpy endpoint in the protocol research exposes the server's timezone"* -- which is false: `systemInfo.server` publishes `seconds-from-gmt` (`-18000` live), `current-local-time` with a full offset, and `current-absolute-time`, none decoded anywhere. The live heartbeat `20260829062049` therefore decodes as `06:20:49Z` when the truth is `11:20:49Z`. Nothing in the library or integration consults a local clock, so detection logic is unaffected -- but Home Assistant renders a `timestamp` sensor relatively, so "last human seen" reads *"5 hours ago"* for someone who just walked past.

**Approach:** Decode the offset the server already publishes and expose it on `ServerInfo`. Then remove the `UTC` default from every decode entry point so the zone must be stated, matching `Capture.from_api`, which already requires it. A naive wall clock cannot be interpreted without a zone; making that explicit turns a silent five-hour error into a `mypy --strict` failure at every call site.

## Boundaries & Constraints

**Always:** `ServerInfo` exposes the server's UTC offset decoded from `seconds-from-gmt`, and it is `None` when the field is absent, non-integral, or outside the range a real offset can take -- never silently zero, which is indistinguishable from UTC. Timestamps stay timezone-aware and normalised to UTC exactly as today; `StreamEvent.raw_timestamp` keeps preserving the original string, so a consumer can always re-interpret. The conversion itself is unchanged: `naive.replace(tzinfo=tz).astimezone(UTC)` is already correct for both a fixed offset and a full `ZoneInfo`. An explicitly passed zone always wins. Every docstring stating that the server does not expose its timezone is corrected in the same change.

**Block If:** none identified -- the field, its live value, and the conversion behaviour are all verified (verification doc §5.7).

**Never:** No client-side caching of a timezone learned from an earlier call, and no implicit `++systemInfo` fetch to serve a decode. That would reintroduce hidden state and an ordering dependency, and it contradicts the rule `require_permission` already sets: the client does not acquire data behind the caller's back to serve a request. No inference of an IANA zone name from an offset -- an offset does not identify a zone, and SecuritySpy publishes no zone name anywhere. No change to the reducer, the coordinator, or any comparison logic: the skew is internally consistent and nothing compares against a local clock. No re-interpretation of `cert-expiry-time` or `current-local-time`, which already carry their own offsets.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Offset decoded | `server` carries `seconds-from-gmt: -18000` | `ServerInfo` exposes a UTC-5 offset | No error expected |
| Positive offset | `seconds-from-gmt: 34200` (UTC+9:30) | Exposed as UTC+9:30; non-hour offsets are ordinary | No error expected |
| Offset absent | The key is missing | The offset is `None`; the rest of `systemInfo` decodes | No error expected |
| Offset unusable | Non-numeric, or beyond ±24 h | `None`, with a debug log; never coerced to zero | No error expected |
| Zero offset | `seconds-from-gmt: 0` | A real UTC offset, distinct from "unknown" | No error expected |
| Event decoded with the server's offset | `20260829062049` with UTC-5 | `2026-08-29T11:20:49+00:00` | No error expected |
| Event decoded with a real zone | Same record, `ZoneInfo("America/Chicago")` | Same instant; the caller's zone wins | No error expected |
| Historical record across a DST change | `20260115062049` with a fixed UTC-5 vs `ZoneInfo` | The two differ by an hour; the fixed-offset limitation is documented, not silently absorbed | No error expected |
| Caller states no zone | Any decode entry point called without one | A type error at check time, not a wrong instant at runtime | Refuses to guess |
| Unparseable wall clock | 14 digits that are not a real instant | `None` timestamp, `raw_timestamp` preserved, stream continues | Never raises |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: `ServerInfo` (~line 810-850) gains a UTC-offset field decoded in `from_api` (~line 897, beside `cpu_usage`/`memory_pressure`) from `server.get("seconds-from-gmt")`. Validate the range and reject a non-integral value; `_as_int` already exists for this.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- read: `Capture.from_api` (line 984) is already `*, server_timezone: tzinfo` with **no default**. It is the precedent the outer layers should match, not something to change.
- `aiosecurityspy/src/aiosecurityspy/events.py` -- edit: `parse_event_line` (line 363) drops `= UTC`, making `server_timezone` required; correct the `[ASSUMPTION]` docstring (line 367) that claims no endpoint exposes the timezone. `_parse_timestamp` (line 273) is already correct for both a fixed offset and a `ZoneInfo` -- do not touch the conversion.
- `aiosecurityspy/src/aiosecurityspy/stream.py` -- edit: `SecuritySpyEventStream.__init__` (line 110) drops `= UTC`; the value is already stored (line 177) and threaded to `parse_event_line`.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: `create_event_stream` (line 475) and `async_get_captures` (line 600) drop `= UTC`. Both already forward the value; only the defaults change.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export any new public name in sorted (RUF022) order.
- `aiosecurityspy/tests/` -- every existing call site of the four entry points now has to pass a zone; that churn is the point, and is what proves no path silently assumed UTC.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- already documents `seconds-from-gmt` and the local-wall-clock warning on `++eventStream` (AD-19 requires it stay in step).
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §5.7 -- the live evidence, including the fixed-offset-versus-zone comparison.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- decode and expose the server's UTC offset on `ServerInfo` -- the library cannot offer a correct default for a value it never reads.
- [ ] `aiosecurityspy/src/aiosecurityspy/events.py` -- require `server_timezone` on `parse_event_line` and correct the false assumption in its docstring -- the docstring is why the defect went unquestioned.
- [ ] `aiosecurityspy/src/aiosecurityspy/stream.py`, `client.py` -- require `server_timezone` on the stream constructor, `create_event_stream` and `async_get_captures` -- these three defaults are the actual bug surface.
- [ ] `aiosecurityspy/tests/` -- cover every I/O-matrix row, including a positive and a non-hour offset, the absent and unusable forms, zero-as-a-real-offset, and the DST-boundary comparison showing a fixed offset differing from a real zone.
- [ ] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document the breaking signature change, how to obtain the offset, and that a caller who knows the server's IANA zone should pass it instead.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings.
- Given any decode entry point called without a timezone, when `mypy --strict` runs, then it fails -- the wrong answer is unreachable rather than merely discouraged.
- Given the captured live heartbeat `20260829062049` and the server's published offset, when it is decoded, then the result is `2026-08-29T11:20:49+00:00`.

## Spec Change Log

## Review Triage Log

## Design Notes

**Why required rather than a better default.** Three defaults were considered. `UTC` is today's silent five-hour error. The server's own offset as an implicit default would need the client to fetch or cache `++systemInfo` behind the caller's back -- hidden state, an ordering dependency, and a direct contradiction of the rule `require_permission` already sets. Requiring the argument is the only option where a wrong instant cannot be produced at all, and it costs one keyword at each call site. `Capture.from_api` has required it from the start; this makes the outer layers agree with the layer they wrap.

**An offset is not a timezone, and the difference is reachable.** `seconds-from-gmt` is the offset in force when the reading was taken. Verified: `20260829062049` decodes identically under a fixed UTC-5 and under `ZoneInfo("America/Chicago")`, but `20260115062049` differs by an hour, because January is CST. `++caplist` routinely spans a month and can span a transition. SecuritySpy publishes no zone name anywhere, so the library cannot be fully DST-correct on its own -- which is exactly why the README must tell a caller who knows the real zone to pass it. Home Assistant is such a caller: `hass.config.time_zone` is an IANA zone, and passing it is a configuration decision, not wire knowledge, so it sits inside AD-2 and AD-19.

**What is deliberately not changed.** The conversion is already right; `naive.replace(tzinfo=tz).astimezone(UTC)` resolves a `ZoneInfo` per timestamp. Aware-and-normalised-to-UTC output is already right. `raw_timestamp` preservation is already right. This story changes only where the zone comes from.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues, and no call site left relying on a default
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass
