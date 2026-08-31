---
title: Detection-episode tuning — first live evidence
date: 2026-08-30
method: "Live `++eventStream` captures against the homelab 6.21 server, reduced through the shipped `EpisodeReducer`"
server: "SecuritySpy 6.21 on homelab, 11 cameras"
bears_on: "PRD Open Q5 (provisional detection defaults); story 1.5 residual risks"
supersedes_partially: securityspy-api-reference.md
---

# Detection-Episode Tuning — First Live Evidence

The `DEFAULT_DETECTION_THRESHOLD` / `DEBOUNCE` / `GAP` constants shipped as
**[ASSUMPTION]** values (PRD Open Q5): chosen to be defensible, never measured. This is
the first capture of real `CLASSIFY` traffic reduced through the actual
`EpisodeReducer`, so the numbers below are the shipped behaviour, not a model of it.

**Reproduce with:**

```bash
DURATION=300 ./scripts/capture_eventstream.sh ~/eventstream.log
cd aiosecurityspy && uv run python ../scripts/analyze_eventstream.py ~/eventstream.log --sweep
```

Cameras are identified by number only. The raw captures are deliberately **not**
committed: `FILE` records carry absolute capture paths that include camera names, and the
names describe the interior of a private home.

## 1. Method and scope

| | |
|---|---|
| Capture | 90 s, single connection, 924 records, **0 unparseable** |
| Classification traffic | 230 `CLASSIFY` records → 690 signals (each record carries all three classes) |
| Subject | One person walking through two interior rooms, cameras 7 then 10 |
| Reduction | Through `EpisodeReducer` via `feed()`, defaults `70 / 3 / 30s` |

Camera 10 is the same camera research §3.5 measured (191 signals in 95 s).

## 2. The reduction requirement holds

| camera | signals | episodes | span | peak |
|---|---|---|---|---|
| 7 | 117 | 1 | 87 s | 100 |
| 10 | 113 | 1 | 77 s | 100 |

690 signals reduced to **2 episodes: a 172.5:1 ratio**, against PRD §11.1's ~190:1
requirement. Two independent episodes correctly keyed per camera, `HUMAN` slugging to
`human`, peak confidence carried across the whole span. **The core claim of story 1.5 is
confirmed against real traffic.**

## 3. `gap` is the only parameter that matters — and 30 s is marginal

A sweep over threshold (50-90), debounce (1-5) and gap (10/30/60 s) moves **only** with
gap. Every debounce value and every threshold from 70 to 80 produced identical output.

| gap | episodes | |
|---|---|---|
| 10 s | 4 | each presence split in two |
| 30 s | 2 | correct |
| 60 s | 2 | correct |

The reason is the silence *inside* a single presence:

| camera | qualifying signals | presence | largest intra-presence silence |
|---|---|---|---|
| 7 | 113 over 87 s | one | **24.0 s** |
| 10 | 103 over 70 s | one | **22.0 s** |

Both silences fall inside one continuous presence. Against a 30 s gap that is **6 seconds
of margin**. This is exactly story 1.5's recorded residual risk — "if a real subject can
be silent longer than the configured gap mid-crossing, one presence becomes two episodes"
— now quantified rather than hypothesised. A subject who stands still, turns away, or
steps briefly out of frame crosses it.

**Recommendation as first written — SUPERSEDED by §8, kept so the reasoning stays auditable:** raise `DEFAULT_DETECTION_GAP` to **45-60 s**. On this capture gap=60
produces results identical to gap=30, so the change costs nothing here; its only real
cost is latency in declaring a subject gone. Still an `[ASSUMPTION]`, but a better-founded
one than 30 s.

**This did not survive a larger sample.** A 3 h capture the same night put the 24 s
silence in a 0.9 % tail rather than making it representative, and found no boundary in the
gap distribution to move the default to. **Keep 30 s** — see §8.

## 4. Threshold is inert for humans; vehicles look different

| class | n | median | max | ≥70 |
|---|---|---|---|---|
| HUMAN | 230 | **98** | 100 | **216** |
| VEHICLE | 230 | 6 | 41 | 0 |
| ANIMAL | 230 | 6 | 33 | 0 |

Humans sit at a median of 98, so any threshold between 70 and 80 behaves identically and
there is no evidence for moving it.

Vehicles are the open question. `VEHICLE` never exceeded **41** here, and a separate
observation on camera 3 (an exterior approach view, a real vehicle present) peaked at **44** — also well under
70. Two independent observations both far below the human range suggests vehicle
inference is systematically less confident, and that a global 70 may make vehicles
undetectable. This is what FR-8's per-class overrides — `(None, "vehicle")` — exist for.
**Not yet conclusive:** two samples, and no capture yet contains a vehicle crossing that
*should* have opened an episode.

## 5. Debounce did nothing, and the signal was far cleaner than §3.5

Research §3.5 describes confidence "swinging 4→100 for a single subject", and debounce
exists to absorb that. This capture shows nothing of the kind: 216 of 230 human signals
were at or above threshold, median 98. Debounce 1 and debounce 5 gave identical results.

Whether the model improved since §3.5, or interior cameras at close range simply produce
steadier inference than whatever §3.5 measured, is unresolved. **Debounce should be kept**
— it is insurance against the noisy case, which is documented and may well reappear on
distant outdoor cameras.

**Corrected by §8:** "currently unexercised" held only for this 90 s sample. Over 3 h
debounce does substantial work, and the value 3 over 1 is justified.

## 6. Wire facts confirmed in passing

- **`EVENT NUMBER` restarts at 0 on every connection.** Observed across every capture
  (1/1, 2/2). Confirms §3.2's "monotonic per-connection counter; not a persistent ID".
- **A reconnect replays nothing.** Connection 2's last record was `…201535 8 7 MOTION_END`;
  connection 3 opened at `…201539 0 …` and re-sent none of it. This closes the story-1.5
  review question about replayed frames advancing a debounce run: the scenario does not
  occur. See that spec's Review Findings.
- **Timestamps collide heavily.** Wire resolution is one second (`%Y%m%d%H%M%S`) while the
  signal rate reaches several per second — one capture had **8 distinct records sharing
  `20260830201540`**. Any logic keyed on timestamp uniqueness is unsound; this is why
  de-duplicating by timestamp equality was rejected.
- **`MOTION_END` is camera-dependent, not uniformly absent.** §3.5 recorded zero ends
  against 467 motion signals on camera 10; camera 7 emitted **9 ends in 5 minutes** here.
  It cannot anchor closure — a rule that fires on one camera and never on another is worse
  than one ignoring the signal — but "unusable" overstated it, and the wording was
  corrected in `episodes.py` and the README.
- **`++caplist` requires `cams`.** Without it the endpoint returns `[]` even given a valid
  date range — success with silent zero results. The OpenAPI description documents the
  missing-date-range case but not this one.

## 7. Limitations

Ninety seconds, one subject, two interior cameras, good lighting, one server, one model.
Enough to establish that the 30 s gap has little margin and that the reduction works on
real traffic. **Not** enough to retune defaults globally. Outdoor cameras at distance —
the likely source of §3.5's violent confidence swings — are unrepresented, and no vehicle
or animal crossing has yet been captured at a confidence that should open an episode.
A longer capture spanning exterior cameras is the next input.

## 8. Second capture: 3 hours, 4,469 CLASSIFY records

A 3 h capture (19,759 records across 3 connections, **0 unparseable**) taken the same
night, after classification was enabled on further cameras. It supersedes two conclusions
drawn from the 90 s sample above.

### 8.1 Debounce is not inert — correction to §5

Over 3 h all three parameters move the outcome, where at 90 s only `gap` did. At
threshold 70 / gap 30 s, debounce 1 → 5 takes 97 episodes to 64. The peak-confidence
column shows what it removes: at `debounce=1` episodes enter at 70, 71, 73, while at
`debounce=5` the weakest is 93. Debounce is filtering exactly the stray high-confidence
frames it was designed for. The 90 s sample was too clean to exercise it, and
`DEFAULT_DETECTION_DEBOUNCE = 3` is justified in a way it previously was not.

### 8.2 There is no natural gap boundary — correction to §3

The reason to expect one: gaps *within* a presence should cluster short, gaps *between*
presences should cluster long, and the valley between them is where the default belongs.
Across 3,712 gaps between consecutive qualifying signals there is no valley — the tail
decays smoothly, with nothing to anchor a threshold to:

| gap band | count | share |
|---|---|---|
| 0-2 s | 3297 | 88.8 % |
| 2-5 s | 145 | 3.9 % |
| 5-10 s | 72 | 1.9 % |
| 10-20 s | 77 | 2.1 % |
| 20-30 s | 33 | 0.9 % |
| 30-45 s | 25 | 0.7 % |
| 45-60 s | 14 | 0.4 % |
| 60-120 s | 19 | 0.5 % |
| > 120 s | 30 | 0.8 % |

Coverage: **30 s covers 97.68 %** of gaps, 45 s covers 98.30 %, 60 s covers 98.71 %.
Moving 30 → 60 s absorbs **38 gaps out of 3,712** (~1 %), and an unknown fraction of those
38 are genuinely separate visits that *should* stay separate.

**Conclusion: keep `DEFAULT_DETECTION_GAP` at 30 s.** The §3 recommendation to raise it
was inferred from one 90 s capture of one subject in two rooms; the 24 s silence it rested
on is real but sits in a 0.9 % tail. No measurement identifies a better value, because the
distribution contains no boundary to find. The choice is a product trade-off — split one
presence, or merge two — not a discoverable optimum.

That is tolerable because **the value is already injected per camera per object class**
(AD-3, FR-8): `ReducerConfig(gap=...)` as the default, with `(camera, None)` and
`(None, class)` overrides resolved ahead of it. A site whose cameras behave differently
overrides it rather than living with the default. What is *not* yet built is exposing it
through the Home Assistant options flow — Epic 5, deliberately out of scope for story 1.5.

### 8.3 Reading the sweep table

The ratio column is **not** a quality score. A higher ratio only means fewer episodes, and
enlarging the gap always produces fewer: the table's best ratio (223:1 at 90/5/60 s) comes
from finding just 30 episodes in 3 hours. With no ground truth for how many presences
actually occurred, the sweep demonstrates *sensitivity*, not correctness. Nothing here
identifies a correct tuning; it bounds how much the tuning matters.

### 8.4 Still open

`VEHICLE` remains unresolved. No capture yet contains a vehicle crossing at a confidence
that should have opened an episode, so §4's observation — vehicle confidence peaking at 41
and 44 against a human median of 98 — is still two data points. An exterior capture during
vehicle traffic is the missing input.
