---
title: 'Story 1.5: Detection episode reducer'
type: 'feature'
created: '2026-08-10'
status: 'done'
baseline_revision: '50379c397d8bed3b837c783a91d2fb50a006d58d'
final_revision: '4e1f7cb'
review_loop_iteration: 1
followup_review_recommended: false  # second pass done 2026-08-30: 10 patches applied, 1 decision reopened (replay dedupe has no in-reducer fix)
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/research/securityspy-api-reference.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `CLASSIFY` is a per-frame inference stream, not a detection event: research §3.5 measured 191 of them on one camera in 95 s, 0–2 s apart, with confidence swinging 4→100 for a single subject. Nothing in `aiosecurityspy` turns that into "a human was here, peak confidence 99". AD-3 makes that reduction a library component so no consumer re-derives the semantics, and PRD §11.1 calls the ~190:1 reduction a correctness requirement, not an optimization.

**Approach:** Add a pure `episodes.py`: classification signals in, `DetectionEpisode` open/close emissions out, with threshold, debounce and inactivity gap injected per camera per object class. The consumer drives the clock; the reducer owns no timer, no socket, and no `MOTION_END` dependency.

## Boundaries & Constraints

**Always:**
- Pure component (AD-3): no I/O, no network, no `asyncio`, no timers, no wall-clock read. Every time value arrives from the caller — a signal's own timestamp, or the `now` a caller passes to the tick method. Fully testable from synthetic signals with no stream and no server.
- Threshold, debounce and gap are **injected per camera per object class** (AD-3, FR-8), never module constants baked into the reduction. A default config plus overrides resolved in the order `(camera, class)` → `(camera, None)` → `(None, class)` → default, which is exactly FR-8's "per-camera value overrides the global".
- An episode opens only after `debounce` **consecutive** qualifying signals (confidence `>= threshold`) for that camera and class. Below-threshold signals never open one, however frequent (FR-5).
- An episode closes on **inactivity**: no qualifying signal for longer than the configured gap. Never on `MOTION_END`, never on a run of below-threshold signals — with confidence swinging 8→97 between adjacent frames, a below-threshold run is mid-episode, not the end of one (research §3.5).
- Closing does not require a tick: a signal arriving after the gap has already elapsed closes the stale episode first, then starts a fresh debounce run. Tick and signal arrival must produce the same episode boundaries.
- `peak_confidence` is the maximum across the **whole span**, including the debounce signals that opened it and any below-threshold signal inside it — never the value at threshold crossing (FR-6).
- Exactly one open and one close per episode. An already-open episode absorbs further signals silently; nothing is emitted per signal.
- Open vocabulary (AD-9): arbitrary class strings, no enumeration, no validation rejecting an unknown class. A class name becomes an episode key only through `class_slug()`, and two raw labels that slug the same merge into one episode — the higher confidence wins, exactly as `ClassificationPayload.slugged()` already resolves them.
- Frozen, slotted, fully typed models with no `Any` in a public signature (AD-15); timestamps are the timezone-aware UTC `datetime`s the rest of the library produces.
- Zero Home Assistant imports. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict src tests` and `uv run pytest -q` stay clean with no gate disabled and no blanket ignore, and all 394 pre-existing tests still pass.

**Block If:**
- The library's own gates cannot pass without disabling a gate or adding a blanket ignore.

**Never:**
- Do not implement settings/arming (1.6) or the anonymizer (1.7). Do not add Home Assistant entities, events, or options handling — that is Epic 5.
- Do not implement the motion-presence reducer here: story 1.5's acceptance is classification episodes, and FR-7's inactivity-only motion timeout is 5.3's surface. Record the shared shape in Design Notes instead.
- Do not make the reducer subscribe itself to `SecuritySpyEventStream`, spawn a task, or call `datetime.now()`. Do not change `stream.py`, `client.py`, `events.py`, or `models.py` behaviour.
- Do not treat the provisional 70 % / 3-signal / 30 s defaults as verified: they are the architecture's `[ASSUMPTION]` (PRD Open Q5) and must be marked as such.
- Do not touch `sprint-status.yaml` or add `custom_components/` files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reference reduction | 191 signals for one camera/class over 95 s, 0–2 s apart, confidences cycling research §3.5's `20, 69, 19, 77, 88, 8, 54, 25, 5, 18, 18, 49, 13, 17, 16, 97, 96, 99, 99, 28, 51, 71, 64, 91, 97` | Exactly one open and one close; `peak_confidence == 99`; `signal_count == 191` | — |
| Debounce not met | Qualifying signals arriving isolated, never `debounce` in a row | Nothing emitted, no open episode | — |
| Never above threshold | 500 signals all below threshold | Nothing emitted, however frequent | — |
| Peak before crossing | 95, 20, 95, 96 with threshold 90, debounce 2 | Episode opens on the second consecutive 95+; `peak_confidence == 96`, and the pre-open 95 is inside the span | — |
| Close by tick | Last qualifying signal at `t`, `tick(t + gap + 1s)` | One close, `end == t + gap`; a second tick emits nothing | — |
| Close by arrival | Next signal at `t + gap + 5s` | Stale episode closed with `end == t + gap`, then a new debounce run starts | — |
| Per-camera override | Camera 4 threshold 50, global 70; a 60 % signal run | Opens on camera 4, not on camera 7 | — |
| Per-class override | `(None, "vehicle")` debounce 5, global 3 | Vehicle needs 5, human needs 3, same camera | — |
| Slug collision | `"Delivery Van"` at 80 then `"DELIVERY_VAN"` at 90 | One episode keyed `delivery_van`; peak 90; both raw labels recorded | — |
| Independent keys | Human and vehicle signals interleaved on one camera | Two independent episodes, each with its own debounce and peak | — |
| Feeding stream events | A `StreamEvent` whose payload is a `ClassificationPayload` | Fanned into one signal per class at the event's timestamp | — |
| Unusable stream event | Non-`CLASSIFY` event, `payload=None`, `timestamp=None`, or `camera=None` | Ignored, nothing emitted | No raise; the stream must not die on one record |
| Non-finite confidence | `float("nan")` / `inf` | Signal ignored; it never wins a peak comparison | No raise |
| Out-of-order signal | A signal older than the episode's last qualifying signal | Counted, and it can raise the peak, but `last_signal` never moves backward | — |
| Backwards clock | `tick(now)` earlier than an episode's `last_signal` | Nothing closes | No raise |
| Disconnect | `close_all(now)` with two open episodes | Both emit a close with `end == now`; a following `tick` emits nothing | — |
| Reset | `reset()` with open episodes | State discarded, **nothing emitted** — the caller chose not to claim they ended | — |
| Bad config | threshold outside 0–100 or non-finite, `debounce < 1`, gap `<= 0` | `ValueError` at construction, naming the field | Caller mistake |
| Bad signal | Non-int camera, empty class | `ValueError` at signal construction | Caller mistake |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/episodes.py` -- create: the whole story. `ClassificationSignal`, `ReducerConfig`, `DetectionEpisode`, `EpisodeOpened`/`EpisodeClosed`, `EpisodeReducer`. The architecture's structural seed names this file.
- `aiosecurityspy/src/aiosecurityspy/events.py` -- read only: `StreamEvent`, `ClassificationPayload.slugged()` and `_prefers()`'s non-finite rule are the shapes this consumes. Do not modify.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- read, plus append the three provisional defaults (`DEFAULT_DETECTION_THRESHOLD`, `DEFAULT_DETECTION_DEBOUNCE`, `DEFAULT_DETECTION_GAP`) marked `[ASSUMPTION]`; `class_slug()` and `CLASS_*` already live here.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: re-export the new public surface; the published API is a contract from first release.
- `aiosecurityspy/tests/test_events.py` -- the fixture and naming style the new tests follow.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §3.5 -- the 191-signal measurement and the confidence sequence; `MOTION_END`'s unreliability.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `DEFAULT_DETECTION_THRESHOLD = 70.0`, `DEFAULT_DETECTION_DEBOUNCE = 3`, `DEFAULT_DETECTION_GAP` (30 s) with an `[ASSUMPTION]` comment citing PRD Open Q5 -- tuning vocabulary belongs with the rest of the protocol vocabulary, in one place.
- [x] `aiosecurityspy/src/aiosecurityspy/episodes.py` -- create: frozen `ClassificationSignal(camera, object_class, confidence, timestamp)` validating its own fields; frozen `ReducerConfig(threshold, debounce, gap)` validating in `__post_init__`; frozen `DetectionEpisode(camera, object_class, raw_labels, start, end, last_signal, peak_confidence, signal_count)` with an `is_open` property; frozen `EpisodeOpened`/`EpisodeClosed` and an `EpisodeEvent` union; and `EpisodeReducer(default=..., overrides=...)` exposing `add(signal)`, `feed(stream_event)`, `tick(now)`, `close_all(now)`, `reset()`, `open_episodes` and `config_for(camera, object_class)`, each returning a `tuple[EpisodeEvent, ...]` where it emits -- one reduction path, so `add` and `tick` cannot disagree about a boundary.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export the new names and the three defaults in `__all__` -- the published API is a contract.
- [x] `aiosecurityspy/tests/test_episodes.py` -- create: cover every I/O-matrix row, building the 191-signal reference case programmatically from research §3.5's published confidence sequence and asserting exactly one open, one close, `peak_confidence == 99` and a 191:1 signal-to-episode ratio -- the reduction ratio is a correctness requirement, so it must be asserted, not assumed.
- [x] `aiosecurityspy/README.md` -- edit: add a runnable snippet reducing a live `CLASSIFY` stream into episodes via `feed()` plus a periodic `tick()`, stating that the caller owns the clock -- the "usable from an ordinary script" success criterion, and the tick obligation is the one thing a consumer can silently omit.
- [x] `aiosecurityspy/CHANGELOG.md` -- edit: record the reducer under Unreleased, including that the defaults are provisional -- AD-14.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and all 394 pre-existing tests still pass.
- Given a script with no Home Assistant and no network, when it constructs an `EpisodeReducer` and feeds it synthetic signals, then it receives episodes — the reducer is importable and exercisable with no session, no server and no event loop.
- Given `grep` over `episodes.py`, then there is no import of `asyncio`, `aiohttp`, `homeassistant`, and no call to `datetime.now`/`time.time`/`monotonic`.
- Given a consumer running `mypy --strict` against code importing the reducer, then every public name resolves through `__all__` with complete type information and no `Any` in a public signature.

### Review Findings

<!-- Follow-up review pass, 2026-08-30. Layers: Blind Hunter, Edge Case Hunter,
     Acceptance Auditor (all three completed). Reviewed range 50379c397..4e1f7cb.
     All four Acceptance Criteria re-verified and passing. -->

- [x] [Review][Patch] Document that a successor episode can overlap, and can inherit, its predecessor [episodes.py:719, episodes.py:648, README.md] — **Decision (Jensen, 2026-08-30): keep the behaviour, document it.** A delayed signal stamped inside an already-closed episode is evidence about the *same continuous presence*, so discarding it would drop real data, and a pure reducer cannot retract a close it has already emitted. Overlap is therefore the honest representation. The documentation must state both halves: (a) two episodes for one `(camera, class)` key can overlap in time, so `new.start >= previous.end` is **not** an invariant a consumer may rely on; and (b) the late signal is absorbed into the *successor*, so its `peak_confidence` and `signal_count` can carry a value that belonged to the closed predecessor. Confirmed empirically: A closes at `12:00:32`; B then reports `start=12:00:01`, `peak=99.0` and `signal_count=3`, where the 99.0 was A's signal and B's own signals never exceeded 71. Document on `DetectionEpisode.start`, `DetectionEpisode.peak_confidence` and in the README's episode-semantics section.
- [x] [Review][Patch] Clamp a future-skewed deadline anchor in the tick path [episodes.py:714-737, episodes.py:378, Design Notes] — **Decision (Jensen, 2026-08-30): clamp forward skew (option 1), with the corrected mechanism below.** One signal stamped an hour ahead currently pins the inactivity deadline an hour out: confirmed empirically, `tick(T+10min)` closes nothing after a single `T+1h` signal, and the episode stays open until wall-clock reaches `T+1h+gap`. `tick` was hardened against a clock stepping *backwards*; the forward direction was never guarded.
      **Mechanism:** in the `tick` path only, an anchor (`last_qualifying`, or `last_any` for an unopened track) that lies in the future of `now` is clamped down to `now`, mutating the track; ordinary logic then resumes and the tick past `now + gap` closes the episode. Worst-case latency becomes one `gap` rather than the full skew.
      **Rejected mechanisms, recorded so they are not retried:** capping the anchor at the largest timestamp seen across the reducer does nothing, because the skewed signal itself sets that ceiling; and computing `deadline = min(anchor, now) + gap` inside `_expire` yields `now + gap` on every tick, which is always in the future, so the episode would never close at all.
      **Consequence to document:** the clamp cannot live in the arrival path, because a signal's own timestamp is not authoritative — only the `now` a caller passes to `tick` is. `_expire` therefore stops being perfectly symmetric between arrival and tick, which amends the Design Notes claim that "a boundary computed by a tick and one computed by an arrival are the same instant". They still agree on unskewed input and diverge only where the arrival side is provably wrong; update the Design Notes to say exactly that. Behavioural change — needs a regression test driving a future-stamped signal through `tick`.
- [x] [Review][Closed] Replayed frames advancing debounce — **closed 2026-08-30: the scenario does not occur.** Three deliveries of one frame do satisfy `debounce=3` (confirmed empirically), but the reconnect replay that would deliver them was verified live against SecuritySpy 6.21 and does not happen.
      **Live verification.** Three consecutive `++eventStream` connections were opened and closed. Connection 2's last record was `20260830201535 8 7 MOTION_END`; connection 3 opened at `20260830201539 0 …` and re-sent **none** of connection 2's records. A reconnect resumes from the present; it does not flush a buffer. Event numbers restarted at 0 on every connection (2/2 and 1/1 across later captures), confirming research §3.2's "monotonic **per-connection** counter starting at 0. Not a persistent ID."
      **Both candidate mechanisms are ruled out, recorded so neither is retried.** *Timestamp equality:* wire timestamps are one-second resolution (`_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"`) and a live capture showed **eight distinct records sharing the instant `20260830201540`** and seven sharing `201539`; suppressing on equal timestamps would discard most of a real burst and stop a genuine three-frame, one-second burst from ever opening an episode. *`event_number`:* implemented then reverted — within a connection the counter is monotonic so the check never fires, and it resets on reconnect so a replayed record would return bearing a different number. It cannot catch the case it was written for.
      **Conclusion.** Since no replay is delivered, there is nothing to deduplicate, and the debounce guard is not weakened in practice. Were a replay ever introduced (a proxy, a future server change), the counter reset is the only evidence of it and only `SecuritySpyEventStream` observes it — so the fix would belong there, not in a pure downstream reducer. No code change. Verified with `scripts/capture_eventstream.sh` + `scripts/analyze_eventstream.py`, which parse real stream output through `parse_event_line` with zero unparseable records.

- [x] [Review][Patch] `feed()` can raise on a hand-built stream event, contradicting its own contract [episodes.py:642-666] — confirmed: naive timestamp → `ValueError`, `camera=True` → `ValueError`, `classes` as a list or `None` → `AttributeError`. The method promises "a live stream must not die because one record was..." and the loop below it is *already* hardened against hand-built payloads for labels and confidences; guarding camera, timestamp and `classes` is the same guard, consistently applied. Not reachable via `parse_event_line` (always aware, int-or-`None`, real mapping), hence low.
- [x] [Review][Patch] A non-finite signal skips the inactivity check entirely [episodes.py:529-531] — `add()` returns before `_expire` runs, so a camera emitting only NaN/inf after a gap keeps its stale episode open until a `tick`, while one finite signal would have closed it. Confirmed. Move the `is_usable` guard below the `_expire` call: the timestamp is usable evidence that time passed even when the confidence is not.
- [x] [Review][Patch] `close_all`'s docstring and CHANGELOG name the wrong field [episodes.py:589-592, 604] — prose says the clamp raises `end` to "the episode's own last signal", but the code clamps to `track.last_any` while `DetectionEpisode.last_signal` is `last_qualifying`. The code is right; the prose is not. Untested because the existing test uses `debounce=1`, so `last_any == last_signal` and the distinction never appears — add a case with a trailing below-threshold signal.
- [x] [Review][Patch] "Never on a run of below-threshold signals" is literally false [README.md:365, spec Boundaries] — an open track anchors its deadline on `last_qualifying`, so a *dense* low-confidence run longer than `gap` does close the episode, and a test pins exactly that. The behaviour is correct and matches the other half of the same sentence; the wording overstates it. Reword both to "no *qualifying* signal for longer than the gap".
- [x] [Review][Patch] `config_for(True, ...)` silently resolves camera 1's override [episodes.py:497-502] — `True` hashes equal to `1`. `ClassificationSignal` already rejects a bool camera via `_is_int`; `config_for` is the one public entry point that does not, so the module's own policy is applied inconsistently.
- [x] [Review][Patch] A non-Mapping `overrides` raises `AttributeError`, not the documented `ValueError` [episodes.py:449] — the constructor docstring enumerates its `ValueError` cases; a list of pairs escapes them.
- [x] [Review][Patch] `signal_count`'s docstring sentence is meaningless [episodes.py:648] — "Divide by one to get the reduction ratio" is the identity, and `signal_count` includes below-threshold signals, so it is not the numerator of the ratio the tests measure either.
- [x] [Review][Patch] The reference case never exercises an inactivity interaction [test_episodes.py:153-159] — `reference_signals()` spaces 191 signals uniformly at `95s/190 = 0.5s`, while §3.5 is quoted throughout as "0-2 s apart". Nothing in the reference burst approaches the 30 s gap. Add a jittered variant so the headline case exercises the straggler pattern it is cited for.
- [x] [Review][Patch] `MOTION_END` is camera-dependent, not uniformly absent [episodes.py:406, README.md:305] — the docstring called it "unusable" and the README "far too unreliable to close anything with", generalising from research §3.5's camera 10 (467 motion signals, zero ends). A live capture on 2026-08-30 saw camera 7 emit **9 `MOTION_END` events in 5 minutes**, so the signal is inconsistent across cameras rather than absent. The design decision is unchanged and the reasoning is actually stronger stated accurately: a closure rule that works on one camera and never fires on another is worse than one that ignores the signal outright. Wording corrected in both places.
- [x] [Review][Defer] A leaked live-server transport makes the suite intermittently fail on an unrelated test [tests/test_live_server.py] — deferred, pre-existing. An unclosed aiohttp transport to the real server surfaces as an `ExceptionGroup` during a later test's setup (observed on `test_models.py::test_class_slug`), so the apparent victim varies under `pytest-randomly`. Reproduced with these review patches stashed on unmodified `HEAD`; the reducer opens no socket. Recorded in `deferred-work.md`.


## Spec Change Log

## Review Triage Log

### 2026-08-10 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 18: (high 0, medium 5, low 13)
- defer: 0
- reject: 4
- addressed_findings:
  - `[medium]` `[patch]` `add()` expired **every** track against the incoming signal's timestamp, so one camera whose signals carried a clock skewed an hour ahead closed every other camera's open episode early, with a wrong `end`. The add path now expires only the signal's own `(camera, slug)` key — still exactly the matrix's "close by arrival" row, still the one shared `_expire` helper — while `tick()` keeps sweeping everything. This also removes a sort over all tracks on every signal.
  - `[medium]` `[patch]` `DEFAULT_DETECTION_GAP` was a bare `30.0` while the field it configures is a `timedelta`, so `ReducerConfig(gap=DEFAULT_DETECTION_GAP)` — the obvious use of the public constant — raised. The constant is now a `timedelta`.
  - `[medium]` `[patch]` `track.start` was set once and never re-minimised while `last_any`/`last_qualifying` refused to rewind, so an out-of-order signal earlier than `start` produced an episode whose `start` fell after one of its own signals. `start <= last_signal` is now an enforced and documented invariant.
  - `[medium]` `[patch]` Override resolution is whole-config replacement, not a merge, and nothing said so: the README's `ReducerConfig(debounce=5)` example silently reset threshold and gap to the provisional module defaults even when the caller had passed a custom `default=`. Stated in `config_for`'s docstring and restated field-by-field in the README.
  - `[medium]` `[patch]` The purity test was a substring grep — defeated by `getattr(datetime, "now")()`, and it permanently barred the module from documenting inline its single most consequential decision. Replaced by three AST tests (forbidden import roots, clock attribute access including the `getattr` form, and a positive check that the `MOTION_END` rationale is present), which freed `_Track.deadline` to carry the 467-signals/0-ends measurement that justifies inactivity-based closure.
  - `[low]` `[patch]` Two override keys slugging to the same normalized pair silently collapsed, last one winning by dict order — the only caller key mistake this module did not raise on. Now a `ValueError`.
  - `[low]` `[patch]` Neither `default` nor the override *values* were validated, so a non-`ReducerConfig` died later with an `AttributeError` from inside the reduction — the failure `_require_aware` exists to prevent. Both validated at construction.
  - `[low]` `[patch]` `close_all(now)` stamped `end=now` unconditionally while `tick` was hardened against a backwards clock, so `now < start` emitted an episode ending before it began. Clamped to `max(now, last_any)`.
  - `[low]` `[patch]` `_prefers` was copy-pasted verbatim from `events._prefers` — two implementations of one subtle NaN rule. The original is now imported.
  - `[low]` `[patch]` `_signals_from` claimed parity with `ClassificationPayload.slugged()` while also dropping blank labels and non-finite confidences. Docstring corrected to say it is stricter, and why.
  - `[low]` `[patch]` `math.isfinite()` was called directly on a payload confidence, so a hand-built `ClassificationPayload` carrying a non-number raised `TypeError` out of `feed()` — which must never die on one record. Guarded.
  - `[low]` `[patch]` `_Track.deadline`'s `anchor + gap` could raise `OverflowError` near `datetime.max`. Caught; such a track is treated as not-yet-lapsed rather than letting the exception escape a public method, as `parse_event_line` already does.
  - `[low]` `[patch]` `feed()` promised ordered emissions but iterated a slug-keyed dict, so a multi-class frame emitted in wire order while every other emission path sorted. Now slug-ordered.
  - `[low]` `[patch]` `class_slug` collapses any label with no ASCII alphanumerics to `"unknown"`, so `人`, `车辆` and `🐋` merge into one episode with a shared peak. Acceptable, but undocumented and untested; now both.
  - `[low]` `[patch]` The reduction-ratio assertion divided a value already asserted equal to 191 by one already asserted equal to 1 — it could not fail independently, though PRD §11.1's ratio is the reason the module exists. Now asserts signals-fed to emissions-produced against a floor.
  - `[low]` `[patch]` The expected open index was `SEQUENCE.index(99.0)`, which is right only by coincidence. Now derived from the debounce rule and cross-checked against the transcribed sequence.
  - `[low]` `[patch]` `_Track.deadline` guarded on truthiness four lines from `snapshot`'s `is not None`; two spellings of one guard invite fixing the wrong one. Unified.
  - `[low]` `[patch]` Coverage gaps: no inactivity close was driven through `feed()` (the path the README example depends on), `open_episodes` ordering was asserted across classes but never across cameras, and nothing pinned that a never-opened track is forgotten *silently*. All three added.
- Rejected (recorded for traceability, not acted on): range-validating `ClassificationSignal.confidence` to 0-100 (it is wire data reaching the reducer through `feed()`, so a server reporting 101 must degrade, not raise); `_require_finite`'s discarded `float()` return "storing an int behind a float annotation" (PEP 484 admits `int` where `float` is annotated, and the dataclass is frozen); the per-signal `sorted()` cost as a standing performance defect (it was real, but the fix landed as P14's key-scoped expiry rather than as a redesign of the single inactivity path the contract requires); and bounding `_tracks` growth (tracks are bounded by cameras x classes and are discarded after a gap of silence, so there is nothing to bound).

## Design Notes

**Why closure is an inactivity gap, not a below-threshold run.** Research §3.5's confidence sequence for one subject includes `88, 8, 54` in consecutive frames. Closing on N consecutive below-threshold signals would shatter that single crossing into several episodes, which is the 190:1 requirement failing in the other direction. Only silence reliably means "gone", and `MOTION_END` cannot supply it (467 signals, 0 ends on camera 10).

**Who owns the clock.** A pure reducer cannot notice that nothing has happened, so the consumer must call `tick(now)`. To keep a lazy consumer from holding an episode open forever, `add()` performs the same gap check against the incoming signal's timestamp before processing it — the two paths share one `_expire(now)` helper, so a boundary computed by tick and one computed by arrival are the same instant:

```python
def add(self, signal: ClassificationSignal) -> tuple[EpisodeEvent, ...]:
    emitted = list(self._expire(signal.timestamp))
    emitted.extend(self._absorb(signal))
    return tuple(emitted)
```

**Amended 2026-08-30 (follow-up review).** The two paths are no longer *perfectly* symmetric, in exactly one respect. `tick(now)` pulls any of a track's own instants that lie later than `now` back to `now`, and `add()` does not: a signal's timestamp is the value a forward clock skew corrupts, so it cannot be the authority on whether it is itself in the future, while the `now` a caller passes to `tick` is that authority. Without this, one record stamped an hour ahead pinned the inactivity deadline an hour out and held the episode open for the whole skew. On unskewed input the clamp changes nothing and the two paths still agree instant for instant; they diverge only where the arrival side is provably wrong.

`end` is `last_signal + gap` — the instant the episode actually lapsed — not the `now` that happened to notice it, so a late tick does not stretch the episode.

**Peak, and the non-finite rule.** Peak comparison reuses `events._prefers()` semantics: a NaN compares False against everything and would otherwise win by accident. A non-finite confidence is dropped at signal construction, so it can neither open an episode nor set a peak.

**Motion presence later (5.3).** `EpisodeReducer` deliberately reduces *confidence-bearing* signals. Motion is the degenerate case — threshold 0, debounce 1 — but FR-7's timeout is a different default and a different entity, so 5.3 either reuses this class with that config or gets its own thin wrapper. Nothing here forecloses it; nothing here implements it.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, the 394 pre-existing included
- `grep -rn "asyncio\|aiohttp\|homeassistant\|datetime.now\|time.time\|monotonic" aiosecurityspy/src/aiosecurityspy/episodes.py` -- expected: no matches
- `grep -rn "MOTION_END" aiosecurityspy/src/aiosecurityspy/episodes.py` -- expected: no matches outside a comment explaining why it is not used

**Manual checks (if no CLI):**
- `episodes.py` contains no module-level threshold or debounce used in the reduction itself; every value comes from a `ReducerConfig` resolved per camera and class.

## Auto Run Result

**Status:** done

**Change:** Story 1.5 adds the reduction plane of `aiosecurityspy`. `CLASSIFY` is a per-frame inference stream — research §3.5 measured 191 signals on one camera in 95 s with confidence swinging 8→97 between adjacent frames — and `episodes.py` turns that into one `DetectionEpisode` carrying the peak confidence across the whole span. An episode opens after N consecutive signals at or above the threshold and closes on **inactivity**, never on `MOTION_END` (unusable: 467 motion signals and zero ends on reference camera 10) and never on a run of below-threshold frames, which would shatter a single crossing into several episodes. Threshold, debounce and gap are injected per camera per class with `(camera, class)` → `(camera, None)` → `(None, class)` → default precedence, which is exactly FR-8's global-plus-override shape. The component is pure (AD-3): no I/O, no task, no timer, and no clock read — the consumer calls `tick(now)`, and `add()` runs the same inactivity check against the arriving signal's own timestamp through the same helper, so a boundary computed by a tick and one computed by an arrival are the same instant.

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/episodes.py` — new: `ClassificationSignal`, `ReducerConfig`, `DetectionEpisode`, `EpisodeOpened`/`EpisodeClosed`/`EpisodeEvent`, `OverrideKey`, and `EpisodeReducer` with `add`/`feed`/`tick`/`close_all`/`reset`/`open_episodes`/`config_for`.
- `aiosecurityspy/src/aiosecurityspy/const.py` — `DEFAULT_DETECTION_THRESHOLD` (70.0), `DEFAULT_DETECTION_DEBOUNCE` (3) and `DEFAULT_DETECTION_GAP` (30 s, a `timedelta`), all marked `[ASSUMPTION]` against PRD Open Q5.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` — exports the new public surface.
- `aiosecurityspy/tests/test_episodes.py` — new: 86 tests covering every I/O-matrix row, the 191-signal reference reduction, the review regressions, and three AST-based purity checks.
- `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` — a runnable `feed()`-plus-`tick()` snippet stating that the caller owns the clock, the whole-config-replacement semantics of overrides, and the provisional defaults.

**Review findings:** 18 patches applied (5 medium, 13 low), 0 deferred, 4 rejected, 0 intent gaps, 0 spec repairs. The consequential ones were a cross-camera expiry bug (one camera's skewed-ahead clock closed every other camera's open episode early), a public constant whose type made its own obvious use raise, a `start` that could fall after one of its own episode's signals, an undocumented replacement-not-merge override semantic that the README's example walked straight into, and a substring-grep purity test that both under-fired and barred the module from documenting its central decision.

**Verification:** `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (19 files formatted), `uv run mypy --strict src tests` (no issues, 17 files), `uv run pytest -q` (**480 passed** — 394 pre-existing plus 86 new — in 0.98 s). The purity grep over `episodes.py` returns nothing; `MOTION_END` appears once, inside the docstring explaining why it is not used, which the verification section permits. Every behavioural patch was confirmed by running the suite against a copy with the patches reverted: 11 tests failed, exactly the expected ones, and the AST walkers were confirmed non-vacuous by injecting `import asyncio`, `datetime.now()` and the `getattr` form into a parsed copy.

**Residual risks:**
- The 70 % / 3-signal / 30 s defaults are provisional (PRD Open Q5, architecture Deferred). They are marked `[ASSUMPTION]` and were never tuned against real footage — the reference sequence is the only evidence they have been exercised on, and it is a transcription of 25 published values, not the full 191-signal capture.
- Closure semantics rest on one measurement. If a real subject can be silent longer than the configured gap mid-crossing, one presence becomes two episodes. **Measured 2026-08-30 and no longer hypothetical:** silences of 24.0 s and 22.0 s were observed inside single continuous presences, against the 30 s default — 6 s of margin. See `_bmad-output/planning-artifacts/research/classification-tuning-evidence.md`; raising the default is tracked in `deferred-work.md`. Nothing in the protocol carries a "still the same subject" signal, so no amount of care inside the reducer can distinguish the cases.
- A consumer that never calls `tick()` keeps episodes open indefinitely for any camera that simply stops producing signals. `add()` covers only the key it touches (deliberately, after the clock-skew finding), so the tick obligation is real and is stated in the README rather than enforced.
- Slug collapse is lossy at the edges: labels with no ASCII alphanumerics all key to `"unknown"` and share one episode. Documented and tested, but it is a consequence of `class_slug`'s existing behaviour rather than a decision made here.
- `feed()` merges same-slug labels within a single frame before the debounce sees them, so the losing raw label of that frame is not recorded in `raw_labels` unless it also wins in another frame.
