---
title: 'Story 1.4: Capture history decoding'
type: 'feature'
created: '2026-08-10'
status: 'done'
baseline_revision: '57f50620773a6abf63ba88223de30592a6795a7d'
final_revision: 'eab7bdd'
review_loop_iteration: 0
followup_review_recommended: false  # 10 patches, none high; all localized, each with a regression test
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/research/securityspy-api-reference.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `aiosecurityspy` can authenticate and read the live event stream, but nothing reads SecuritySpy's *persisted* record of what happened. The stream is transient and restarts at zero; AD-1 makes the capture-history poll plane the sole source of persistent truth, and Epic 4 cannot answer "when was a human last seen on this camera" without it (FR-41).

**Approach:** Add `++caplist` support: one batched, server-side class-filtered request covering many cameras, decoded into frozen typed `Capture` models whose absolute start time is reconstructed from the folder date plus seconds-since-midnight and whose object classes come from the persisted `o` bitmask (research §4).

## Boundaries & Constraints

**Always:**
- One request covers all requested cameras. The `cams` parameter is a comma-joined list of camera numbers **with a trailing comma** (research §4) — never one request per camera, and never `len(cameras) x len(classes)` requests.
- Class filtering is done by the **server**, via `filter=` (5=human, 6=vehicle, 7=animal; research §4.2). Never fetch `filter=0` and filter locally on the `o` bitmask.
- Absolute start time is reconstructed from `f` (folder date `YYYY-MM-DD`) plus `s` (seconds since midnight) and returned as a timezone-aware UTC `datetime` (AD-15). Absent or undecodable means `None`, never epoch or zero.
- `o` decodes to a `frozenset[str]` of class names via a `decode_object_classes()` that degrades exactly like `decode_permissions()` (unknown bits ignored, negative/non-int decodes to nothing). Absent or `0` yields an **empty frozenset**, never `None` and never an error.
- `caplist.t` (1=movie, 2=JPG image) gets its own constants and its own decoder. It must not share a name, mapping, or enumeration with `clip.movieType`/`cliplist.t`, where the same letter means Motion vs Continuous Capture (research §4b.3).
- Raw dicts never cross the boundary: the public method returns a `tuple[Capture, ...]`, newest first, deterministic regardless of server ordering. A camera-day with no matching captures returns an empty tuple, not an error and not a fabricated entry.
- The single transport seam is `SecuritySpyClient._request_json`. No new session use, no new URL construction, no new status handling; no raw transport, JSON, or `ValueError` escapes (AD-6).
- No credential in any log line, message, or `repr`. Response bodies are never echoed into an exception.
- Zero Home Assistant imports; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict src tests` and `uv run pytest -q` stay clean, with no gate disabled and no blanket ignore, and all 287 pre-existing tests still pass.

**Block If:**
- The library's own gates cannot pass without disabling a gate or adding a blanket ignore.

**Never:**
- Do not implement the episode reducer (1.5), settings/arming (1.6), or the anonymizer (1.7).
- Do not implement `getfile`, `getpreview`, `++clip`, `cliplist`, or `setTags` — Epic 4 story surface, not this one. Do not expose `deleteclip` or `++delete` in any form (AD-2).
- Do not enforce a lookback window inside the library; the bounded window is the consumer's (FR-4, Epic 4). Do not make the date range optional or unbounded-by-default.
- Do not invent a class-to-`filter` mapping for a class the server has no filter for: the open-vocabulary rule (AD-9) governs labels arriving *from* the server, not a server-side filter that does not exist.
- Do not touch `sprint-status.yaml` or add `custom_components/` files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Batched query | `cameras=[4, 1, 1]`, one date range | Exactly one GET, `cams="1,4,"` (sorted, de-duplicated, trailing comma) | — |
| Server-side class filter | `object_class="human"` | `filter=5` sent; no local bitmask filtering anywhere | — |
| No class filter | `object_class=None` | `filter=0` (all files) | — |
| Unknown class filter | `object_class="delivery_van"` | `ValueError` at the call, naming the three filterable classes | Caller mistake; raised before any request |
| Absolute time | `{"f": "2026-08-09", "s": 63319}`, `server_timezone=UTC` | `start == 2026-08-09T17:35:19+00:00`, tz-aware | — |
| Non-UTC server | same record, `server_timezone=ZoneInfo("America/Chicago")` | Interpreted as server-local, returned converted to UTC | — |
| Bad/absent time fields | `f` missing, unparseable, or `s` non-numeric/negative | `start=None`; the capture is still returned | Debug log, no payload contents |
| Classification bitmask | `o=5` | `{"human", "animal"}` | — |
| Empty classification | `o=0`, `o` absent, `o=null` | `frozenset()` | Never `None`, never an error |
| Unknown class bit | `o=9` (bit 3 unknown) | `{"human"}` — unknown bit ignored | — |
| Capture type | `t=1` / `t=2` / `t=7` | `capture_type=1`/`2`/`7`, `is_movie` True/False/False, `capture_type_name` `"movie"`/`"image"`/`None` | Unknown value carried through, not rejected |
| Empty result | Server returns `[]` | `()` | No error |
| Skippable entry | Entry is not an object, or has no usable `c` | Entry skipped; the rest decode | Debug log, no payload contents |
| Non-list body | Body is `{"captures": [...]}` | Decoded from the embedded list | — |
| Unusable body | Body is a string, number, or a mapping with no list | `SecuritySpyConnectError` | Body never echoed |
| No cameras | `cameras=[]` | `()` with **no request issued** | — |
| Bad arguments | negative/non-int camera, `start_date > end_date`, or both `object_class` and `capture_filter` given | `ValueError` before any request | Caller mistake |
| Auth rejected | Server answers 401/403 | `SecuritySpyAuthError` from the shared seam | Unchanged from 1.2 |
| Ordering | Server returns records in arbitrary order | Newest `start` first; ties by camera then filename; `start=None` last | — |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/const.py` -- exists: add `ENDPOINT_CAPTURE_LIST`, the `CAPTURE_FILTER_*` values of §4.2, the `CAPTURE_TYPE_MOVIE/IMAGE` pair of §4.1, `OBJECT_CLASS_BITS`, `decode_object_classes()`, and `capture_filter_for_class()`. Protocol vocabulary has exactly one home.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- exists: add the frozen `Capture` with `from_api()`; reuses the existing `_as_int`/`_as_str`/`_as_bool` coercers, which are already strict about `bool`, `NaN`, and `"1_0"`.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- exists: add `async_get_captures(...)` over the existing `_request_json` seam.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- exists: re-export the new public surface; the published API is a contract from first release.
- `aiosecurityspy/tests/test_models.py`, `tests/test_client.py` -- exist: decoding and request-shape coverage follow these files' fixture style.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` -- §4 field table and `filter` semantics, §4b.3 the overloaded `t`. Authoritative over the published documentation.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `ENDPOINT_CAPTURE_LIST`, `CAPTURE_FILTER_ALL/IMAGES/MOVIES/CONTINUOUS/MOTION/HUMAN/VEHICLE/ANIMAL`, `CAPTURE_TYPE_MOVIE=1`, `CAPTURE_TYPE_IMAGE=2` with a `CAPTURE_TYPE_NAMES` read-only mapping, `OBJECT_CLASS_BITS` (`1`→human, `2`→vehicle, `4`→animal), `decode_object_classes(mask)` degrading like `decode_permissions`, and `capture_filter_for_class(name)` raising `ValueError` for a class with no server-side filter -- one home for protocol vocabulary, and a comment at `CAPTURE_TYPE_*` stating explicitly that it must never be shared with `clip.movieType` (§4b.3).
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: add frozen, slotted `Capture` (`camera: int`, `start: datetime | None`, `duration: timedelta | None`, `capture_type: int | None`, `object_classes: frozenset[str]`, `filename: str`, `folder_date: str`, `file_size: int | None`, `tag_id: int | None`, `archived: bool`, `unread: bool`, `path: str`) with `from_api(payload, *, server_timezone)`, `is_movie`/`capture_type_name` properties, `has_class()`, and a credential-free `__repr__` -- decoding is pure so every matrix row is testable with no network.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: add `async def async_get_captures(self, cameras: Iterable[int], *, start_date: date, end_date: date, object_class: str | None = None, capture_filter: int | None = None, server_timezone: tzinfo = UTC) -> tuple[Capture, ...]`, validating arguments before issuing anything, building `cams`/`startDate`/`endDate`/`filter`, going through `_request_json`, and sorting the result newest-first -- one batched request, server-side filtering, and no second transport path.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export `Capture`, the new constants, `decode_object_classes` and `capture_filter_for_class` in `__all__` -- the published API is a contract.
- [x] `aiosecurityspy/tests/fixtures/caplist.json` -- create: a recorded-shape `++caplist` array covering a movie and a JPG, `o` values of 0/1/5/9, one entry with a missing `f`, one non-object entry, and one entry with no usable `c` -- protocol fixtures are this epic's testing strategy.
- [x] `aiosecurityspy/tests/test_models.py` -- edit: cover every decoding row of the I/O matrix from the fixture and synthetic payloads, including the `63319` -> `17:35:19` reconstruction under UTC and a non-UTC zone, empty/unknown-bit classification, and the capture-type decode -- pure decode coverage.
- [x] `aiosecurityspy/tests/test_client.py` -- edit: assert the request shape (single call, sorted de-duplicated `cams` with trailing comma, the `filter` value per class, the date strings), the empty-cameras short-circuit issuing no request, argument-validation `ValueError`s, the non-list and unusable body paths, empty-result `()`, and the newest-first ordering -- the batching and server-side-filter constraints are only real if asserted.
- [x] `aiosecurityspy/README.md` -- edit: add a runnable "when was a human last seen" snippet using `async_get_captures` -- the "usable from an ordinary script" success criterion.
- [x] `aiosecurityspy/CHANGELOG.md` -- edit: record the capture-history surface under Unreleased -- AD-14.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- edit: extend the existing server-timezone entry to name `models.Capture` / `async_get_captures` as well, since capture times inherit the same unresolved assumption -- one ledger entry per open question, not one per file.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a script with no Home Assistant installed, when it creates its own `aiohttp.ClientSession`, builds a client and calls `async_get_captures([1, 2, 3], start_date=..., end_date=..., object_class="human")`, then it receives typed `Capture` objects and the session is still open afterwards.
- Given a consumer running `mypy --strict` against code importing `Capture` and the new constants, then every public name resolves through `__all__` with complete type information and no `Any` in a public signature.
- Given the whole `aiosecurityspy` tree, when it is searched for Home Assistant imports and for `deleteclip`/`doShell`/`doShortcut`/`getfile`, then there are zero matches.

## Spec Change Log

## Review Triage Log

### 2026-08-10 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 0, medium 4, low 6)
- defer: 2: (high 0, medium 1, low 1)
- reject: 4
- addressed_findings:
  - `[medium]` `[patch]` `_capture_entries()` returned the *first* list-valued entry of a wrapped body, so `{"error": [...], "captures": [...]}` decoded the error array and reported a real day's captures as `()` — a silent "nothing happened" verified by execution. It now accepts a bare array or a named key (`captures`/`caplist`/`files`/`file`) only; any other envelope is a `SecuritySpyConnectError`, which is the visible failure it always was.
  - `[medium]` `[patch]` `datetime` subclasses `date`, so `start_date=datetime.now(UTC)` passed both `mypy --strict` and the range check and then serialised as `2026-08-09T13:45:00+00:00` into `startDate` — a query the server cannot match against a folder date. Both bounds are now rejected unless they are plain dates, before any request is issued.
  - `[medium]` `[patch]` `capture_filter` accepted any non-negative integer. The server is not documented to validate `filter`, so a value it ignores returns the *whole* history while the call reads as a narrow query. Validated against the new `CAPTURE_FILTERS` set.
  - `[medium]` `[patch]` `Capture.path` was built by concatenation from server-supplied fields, so a filename carrying `/`, `\` or `..` produced a triple that addresses a different file once a consumer puts it in a media URL. Such an entry now gets an empty path (the capture is still returned), and the docstring and README state that the value is not percent-encoded.
  - `[low]` `[patch]` The DST rationale in `_parse_capture_start`'s docstring was factually wrong: it claimed a fall-back day can carry `s >= 86400` and that such a day "lands correctly". `s` is a wall-clock second-of-day, so the real situation is that it carries no fold bit — one local hour per fall-back is ambiguous (`fold=0`, the earlier instant) and the skipped spring-forward hour is non-injective. Corrected and marked `**[ASSUMPTION]**`; three tests now pin the wall-clock semantics and the fold choice. The same wrong sentence in this spec's Design Notes was corrected in place rather than via a `bad_spec` loopback: the implementation is correct as written, so re-derivation would produce identical code.
  - `[low]` `[patch]` `_EPOCH` named the sort sentinel for an epoch it is not (year 0001, not 1970) in a change whose own contract says "never epoch". Renamed `_SORT_FLOOR`.
  - `[low]` `[patch]` The ordering tiebreak was `(camera, filename)`, so two entries agreeing on both fell back to the server's order despite the documented determinism. Extended to every observable field, with a test that forward and reversed bodies produce identical results.
  - `[low]` `[patch]` The `end_date` inclusivity claim was stated as fact; research §4 records only a same-day query. Marked `**[ASSUMPTION]**`, matching how every other unverified protocol claim in this codebase is flagged.
  - `[low]` `[patch]` Nothing documented that the class filters select motion-capture *movies*, so a JPG capture classified human is invisible to `object_class="human"`. Stated in the docstring, README and CHANGELOG.
  - `[low]` `[patch]` Nothing documented that the response is read whole under an 8 MiB cap while the date range is deliberately unbounded, so a wide query fails with "server response body was too large" and no hint that narrowing it is the fix. Stated in the docstring and README.
- Deferred: `Capture.tag_id` has two representations of "no tag" (`0` vs `None`) and choosing needs a server with and without tags; and `server_timezone` is now a per-call argument on both the stream and the poll plane, which lets the two drift apart — a public-API shape decision rather than a patch.
- Rejected (recorded for traceability, not acted on): parenthesising `except OverflowError, ValueError, OSError:` for a pre-3.14 syntax error (`ruff format` re-applies PEP 758 style under this project's target, and `requires-python >= 3.14` means pip never installs it on an older interpreter); a claim that `capture_filter_for_class()` raises `AttributeError` on a non-string (verified false — `class_slug()` already degrades non-strings to `"unknown"`, producing the documented `ValueError`); the fixture used by `test_no_local_bitmask_filtering_happens` being unrealistic for a `filter=5` response (that is the point of the test — it proves the client does no local filtering, which a realistic fixture cannot); and reworking `_parse_capture_start` to absolute-seconds arithmetic (that would be wrong for a wall-clock second-of-day, and is now pinned by a cross-DST test).

## Design Notes

**Time reconstruction, concretely.** `f` is a folder date, `s` is a *wall-clock* second of local midnight. Adding a `timedelta` to an aware `datetime` is wall-clock arithmetic in Python, which is exactly the field's semantics; build it additively rather than with `hour=s//3600` so an out-of-range value a misbehaving server sends rolls into the next day instead of raising. `s` carries no fold bit, so the DST fall-back hour is ambiguous (`fold=0`, the earlier instant) and the skipped spring-forward hour is not injective — an `[ASSUMPTION]`, not a fixable defect:

```python
naive = datetime.combine(folder, time(), tzinfo=server_timezone) + timedelta(seconds=s)
start = naive.astimezone(UTC)
```

A negative or non-integer `s`, or an unparseable `f`, yields `start=None`. `astimezone()` can raise `OverflowError` near year 0001/9999 — catch it and return `None` rather than letting it escape a public method, exactly as `parse_event_line` does.

**Why `filter` is a request parameter and not a post-filter.** `filter=5` is "Human Motion Capture Movies" — a server-side scan. Fetching `filter=0` across eleven cameras and filtering on `o` locally returns the same answers while transferring the whole day's history, which is precisely the cameras x classes cost Epic 1 forbids. `capture_filter` is offered alongside `object_class` for the non-class filters (movies-only, continuous-only); passing both is a `ValueError`.

**`t` is deliberately a bare `int`.** `caplist.t` and `clip.movieType` share a letter and mean different things. Storing the raw integer with a *derived* `capture_type_name` keeps an unknown future value carrying through, and means there is no enum for a later story to reach for by mistake.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all tests pass, the 287 pre-existing ones included
- `grep -rn "homeassistant\|deleteclip\|doShell\|doShortcut\|getfile\|getpreview" aiosecurityspy/src` -- expected: no matches
- `grep -rn "filter=0" aiosecurityspy/src` -- expected: only the `CAPTURE_FILTER_ALL` default path, never a fetch-then-filter fallback

**Manual checks (if no CLI):**
- `client.py` issues exactly one GET per `async_get_captures` call, through `_request_json`, with a trailing comma on `cams`.

## Auto Run Result

**Status:** done

**Change:** Story 1.4 adds the poll plane of `aiosecurityspy`. `++caplist` is queried once for every requested camera — the `cams` parameter is the sorted, de-duplicated camera list with research §4's trailing comma — and object-class filtering happens on the *server* via `filter=`, so the cost is one request rather than one per camera or cameras x classes. Each entry decodes to a frozen `Capture` whose absolute start is reconstructed from the folder date plus the wall-clock seconds-since-midnight field and whose `object_classes` come from the persisted `o` bitmask, which is what makes poll-derived state correct after a restart (AD-1). `caplist.t` deliberately stays a bare `int` with a derived name, because it shares a letter with `clip.movieType` and means something else (research §4b.3).

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/const.py` — `ENDPOINT_CAPTURE_LIST`, the `CAPTURE_FILTER_*` values with a `CAPTURE_FILTERS` validation set, `CAPTURE_TYPE_MOVIE`/`IMAGE` with `CAPTURE_TYPE_NAMES`, `OBJECT_CLASS_BITS`, `decode_object_classes()` and `capture_filter_for_class()`.
- `aiosecurityspy/src/aiosecurityspy/models.py` — frozen `Capture` with `from_api()`, the additive wall-clock time reconstruction, and a path builder that refuses a filename which could escape its directory.
- `aiosecurityspy/src/aiosecurityspy/client.py` — `async_get_captures(...)` over the existing `_request_json` seam, with argument validation before any I/O, the empty-camera short-circuit, named-key envelope handling and deterministic newest-first ordering.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` — exports the new public surface.
- `aiosecurityspy/tests/fixtures/caplist.json` — recorded-shape fixture with the skippable and unclassified entries.
- `aiosecurityspy/tests/test_models.py`, `tests/test_client.py` — 107 new tests covering every I/O-matrix row plus the review regressions.
- `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` — "when was a human last seen" snippet, and the non-obvious protocol caveats.
- `_bmad-output/implementation-artifacts/deferred-work.md` — server-timezone entry extended to the capture path; two new entries from review.

**Review findings:** 10 patches applied (4 medium, 6 low), 2 deferred, 4 rejected, 0 intent gaps, 0 spec repairs. The consequential ones were an envelope-parsing path that could report a real day's captures as "nothing found", a `datetime` slipping through a `date` annotation into a query the server cannot match, an unvalidated `filter` that a server ignoring it would answer with the entire history, and a media path built by concatenation from a server-supplied filename.

**Verification:** `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (17 files formatted), `uv run mypy --strict src tests` (no issues, 15 files), `uv run pytest -q` (**394 passed** — 287 pre-existing plus 107 new — in 0.89 s). `grep` over `src` for Home Assistant imports and for `deleteclip`/`doShell`/`doShortcut`/`getfile`/`getpreview`: zero matches. Every review patch has a regression test, and the DST and path-escape tests were confirmed to fail against the pre-fix code.

**Residual risks:**
- `server_timezone` still defaults to UTC and is now a per-call argument on both the stream and the poll plane, so a consumer can set them inconsistently and make the two planes disagree about when the same thing happened. Both the unknown zone and the API-shape question are in the ledger.
- A wall-clock second-of-day cannot express DST fold. One local hour per fall-back resolves to the earlier instant, and two captures in the skipped spring-forward hour can share a UTC instant. Nothing in `caplist` carries the missing bit.
- The `caplist` field table is transcribed from the web client's `captures.js`, not from a vendor specification: `i` and `z` are unconfirmed and are not decoded, and the `o` bitmask is assumed to be exactly three bits with the rest unknown-but-ignorable.
- The response envelope has been read off one server version. A server wrapping the array under a key outside the accepted set now fails loudly rather than decoding — the safer failure, but a failure.
- No real SecuritySpy server has been involved: `end_date` inclusivity, `filter` validation behaviour, and the trailing-comma requirement are all taken from the research document.
- The whole response is buffered under the client's 8 MiB cap and `caplist` offers no paging, so a sufficiently wide caller-chosen window fails rather than degrading.
