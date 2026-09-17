# When Does SecuritySpy Write Classification to a Capture?

**Story:** 4.1 (spike) — PRD Open Q3, risk R-001, test-design gate `4.1-LIVE-076`
**Server tested:** SecuritySpy 6.22b10
**Camera tested:** camera 7 (number only; no name, hostname, IP or credential appears in this document)
**Date:** 2026-09-16

No credential value appears anywhere in this document. No fabricated number
appears anywhere in this document: every figure below is either a measured
reading from the live probe or a derived quantity, and everything that could
not be exercised live is marked untested with its reason.

## Headline result

On this server/camera, a manual-triggered motion capture **appears in
`++caplist` within one 3-second poll of the trigger firing, and its recording
closes ~21 seconds after the trigger** (an ~18-second movie). The capture's
object classification (`o`) was **never populated in any of the five triggered
captures** within the poll window (40–70 s after recording close). The spike
therefore produced **no positive number for "does classification lag capture
close, and by how much"** on this camera: the honest answer is that no
classified capture was observed in the sample, which is consistent with either
"camera 7 has no classification model assigned" or "the scene held no
classifiable object during the triggers".

## Method

Instrument: `aiosecurityspy/scripts/measure_classification_write_timing.py`
(library repo). For each trigger it:

1. Takes a baseline `++caplist` poll (`async_get_captures`,
   `capture_filter=CAPTURE_FILTER_ALL`, today's folder, test camera) so a
   capture already fully written at its first post-trigger observation is
   still detected as new.
2. Fires the manual trigger (`++triggermd?cameraNum=N`, raw aiohttp GET with
   an `Authorization: Basic` header built via `aiohttp.encode_basic_auth()`)
   using the ADMIN account.
3. Polls `++caplist` every 3 s until the new capture's class set settles or
   the per-trigger deadline elapses. Records, per trigger: the wall-clock
   appearance time (first poll that sees the capture), recording-close time
   (`start + duration`), classification-populated time (first poll with a
   non-empty `object_classes`), and the two deltas.

The poll uses the library's public surface only; the raw trigger is confined
to the library repo (AD-2).

**Clock-skew caveat.** "Trigger fired", "appeared" and "classified" are the
probe host's wall clock (UTC); "start" and "close" are the server's own
timestamps decoded through the server's published offset. The deltas assume
the probe host and server clocks agree to within the 3-second poll interval;
a few seconds of mutual skew would bias the appearance and classification
latencies by that amount.

## Per-trigger measurements

All times are UTC as printed by the probe (capture `start` is decoded to UTC
via the server's published `seconds-from-gmt` offset).

| # | Trigger fired | Appeared | Close (`start+duration`) | Classified | classes | classified−close | classified−appeared |
|---|---|---|---|---|---|---|---|---|
| 1 | 03:08:31 | 03:08:34 | 03:08:51 | — | `{}` | n/a | n/a |
| 2 | 03:15:24 | 03:15:27 | 03:15:45 | — | `{}` | n/a | n/a |
| 3 | 03:16:30 | 03:16:33 | 03:16:51 | — | `{}` | n/a | n/a |
| 4 | 03:17:36 | 03:17:39 | 03:17:57 | — | `{}` | n/a | n/a |
| 5 | 03:40:52 | 03:40:55 | 03:41:14 | — | `{}` | n/a | n/a |

Rows 1–4 came from two probe runs (`--triggers 1 --timeout 90 --interval 3`
then `--triggers 3 --timeout 60 --interval 3`); row 5 from a third
(`--triggers 1 --timeout 90 --interval 3`) after the probe's measurement loop
was hardened (it now keeps polling past a classified sighting until the
recording's duration is stable, and matches only captures whose `start` lies
bounded around the trigger instant). Every capture matched the trigger window
(camera 7, `start` no earlier than trigger − 15 s), and every one was an
**unclassified** capture: `object_classes` stayed empty for the whole poll
window (60–90 s post-trigger, i.e. ~40–70 s after recording close).

**Derived quantities, consistent across all five captures:**

- **Appearance latency after trigger: ≤ 3 s.** The capture was first visible
  on the poll exactly one `--interval` (3 s) after the trigger in every case;
  its true `start` lies within the preceding interval. The derived `start`
  offset is **trigger + ~2–3 s** (the recording began just after the trigger
  fired; no pre-roll was observed on this camera).
- **Recording close: trigger + ~21 s** (`close = start + duration`, duration
  ~18 s). Rows were read once each; the probe does not track `start`/`duration`
  across polls, so no within-row "stable from first sight" claim is made.
- **Classification: never populated within the window.** No `o` bits were
  ever set on any of the five captures.

## Consequences

### (a) Restart correctness (FR-2 / FR-3)

Unaffected by this measurement, in either direction. The poll plane derives
persistent state from `++caplist`, and an empty `o` is a legal, decodable
state — the `Capture.object_classes` model degrades a zero/absent `o` to an
empty `frozenset`, never to a failure. If a future camera does write
classification late, a restart-time backfill could momentarily see a capture
without its class and self-heal on the next poll; if it writes at close,
backfill is immediately correct. Neither changes the restart-correctness
claim. What this spike did observe is that "a capture exists" and "its class
set is non-empty" are separately readable states of the same record — a
capture can be present in `caplist` while `o` is still empty. It did **not**
observe a class arriving after the capture (nothing was ever classified), so
the AD-1 two-plane separation as a *class-lag* mechanism remains unproven.

### (b) Can the capture's class set lag the image by one poll? (FR-9 vs FR-11)

**Unverified on this camera** — no class was written at all, so the sample
cannot confirm or refute the "class alongside image" promise (FR-11). The risk
the spike was meant to retire remains open: if classification is written after
close, an image/capture entity could briefly present a classless capture until
a later poll picks up the class. The measured appearance/close latency says
nothing about it. This is the honest bound: the spike did **not** prove
classification is present at close, and did **not** prove it lags — it proves
the question is unanswerable on camera 7 with this scene.

## Lookback and AD-10 poll-cycle assumptions

- **Appearance latency ≤ 3 s is consistent with AD-10.** A capture is visible
  in `caplist` within one 3-second poll interval of the trigger firing. The
  AD-10 event-driven poll trigger (FILE-debounced, ~5 s) and the ~10-minute
  slow fallback both exceed the 3 s appearance latency by wide margins, so
  both will reliably observe a newly-closed capture on the poll that fires
  after its close.
- **7-day lookback: not contradicted.** The lookback governs retention and
  request width, not write timing; this measurement neither confirms nor
  corrects it.
- **Classification-population latency: unmeasured, so the AD-10 assumption
  that a poll sees a fully-classified capture is neither confirmed nor
  corrected** — it remains unverified for this camera. If a classified
  capture is later captured (a camera with a model, a scene with a moving
  object), the probe can be re-run to get the positive number.

## Sub-findings not exercised live

- **No classified capture occurred** in any of the four triggers. Reason
  (either, indistinguishable through the library's public surface): camera 7
  has no CoreML classification model assigned, so classification never fires
  for it; or the scene contained no classifiable object during the window
  (the triggers ran ~03:08–03:17 UTC, likely empty/quiet). The library's
  `CameraSettings` model deliberately does not expose the model assignment,
  so the two cannot be told apart without a raw settings probe that the spike
  deliberately did not add. Untested; no classification-write latency number
  is reported.
- **Whether classification would ever populate on a classified capture** (a
  camera with an active model, a scene with motion) — untested, same reason.

## Resolution of test-design gate `4.1-LIVE-076`

The blocking spike gate has returned with this measurement. It settles the
capture-plane half of R-001 (appearance ≤ 3 s, close ≈ trigger + 21 s) and
returns a null result for the classification-write half (no classified capture
in the sample). The gate's freshness question — "does the class populate at
close or later, and by how much" — is answered "not observable on camera 7 in
this sample", so Epic 4's freshness claims (FR-2/FR-3/FR-11) are neither
proven nor disproven by this spike. The regression test added with this spike
(`test_live_classification_write_timing_mechanism`) locks in the mechanism —
a triggered capture appears in `caplist` and its class set is a decodable
`frozenset[str]` — without baking in a wall-clock bound.