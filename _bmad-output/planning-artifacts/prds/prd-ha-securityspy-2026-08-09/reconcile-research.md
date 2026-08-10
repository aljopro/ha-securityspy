# Reconciliation: Research → PRD

Input reconciliation of `research/securityspy-api-reference.md` and `research/architecture-implications.md` against `prd.md` + `addendum.md`. Scope: product-relevant constraints and capabilities only; technical mechanism deliberately excluded from the PRD is not reported. Ranked by importance within each section.

## Gaps — research findings the PRD silently drops

### G1. Auth-token support absent from the PRD (security capability, not mechanism)
API ref §1b and §7b document resource-scoped auth tokens ("`!`-prefixed `auth=`") whose entire purpose is keeping admin credentials out of RTSP URLs, ffmpeg logs, and diagnostics — and the research calls token support "a strong argument for supporting token auth in any client's configuration." The PRD's config flow (FR-25) accepts only username/password, and FR-42 promises credential redaction but never the option to avoid credentials in stream URLs at all. Since FR-22 ships live-video entities (RTSP via credentials-in-URL is the known path, and the research observed a password echoed by ffprobe), the PRD should at least: (a) require that enabling a camera entity not place credentials where FR-42 forbids them, or (b) note token auth as a v1/v2 requirement with its "format unverified" caveat. Currently it is silent. This is a *what-the-product-promises* gap: FR-42's consequences ("credentials do not appear in error messages") are arguably unachievable for RTSP camera entities without addressing this.

### G2. Detection Triggers off-by-default undermines FR-1/SM-1 without a stated setup requirement
The PRD acknowledges (§5.5) that per-class triggers are off on a default install, but only as motivation for FR-17. Research §3.4 is stronger: with `mcTriggerMotionH/V/A` disabled, per-class trigger bits never fire and — critically for the Observation Record — captures may not carry class-filtered relevance the way the headline promises. Nothing in FR-1..FR-4, UJ-3, or the config flow requires the integration to *detect* this state and tell the user (e.g., a repair issue or setup hint) that the Observation Record will be empty/degraded until class triggers are enabled. Priya installs successfully (UJ-3) and gets three permanently absent timestamps with no explanation. A "guide the user to enable class triggers" requirement is missing.

### G3. No requirement about CONFIGCHANGE / external configuration changes
Research documents the `CONFIGCHANGE` event and the addendum's own interoperability note ("must not assume it is the only client" — PRD §10.3 keeps the note). But FR-14 promises bidirectionality only for arm state. Settings-backed controls (FR-16 camera enable, FR-17 triggers, FR-18 sensitivities) have no requirement that changes made in SecuritySpy or by another client (HomeHelper, the Mac app) are reflected in HA. The research provides the signal (CONFIGCHANGE) and the coexistence constraint; the PRD drops the resulting product promise: settings controls must not show stale state after external edits.

### G4. Three distinct camera states (enabled / online / open) collapsed
API ref §10 stresses `online` / `enabled` / `open` are three distinct states plus `err`/`errDesc`. FR-16 (enable control) and FR-30 (offline → unavailable) cover two; the "open/error" dimension (camera enabled and online but failing, with an error description) appears only as a diagnostic "last error" sensor (FR-23). Product-level: FR-30's consequence "camera offline is treated as unavailability, not an error condition" conflicts with the reality that SecuritySpy distinguishes disabled (intentional), offline (unavailable), and erroring (actionable) — a camera in persistent error state should surface as such, not be indistinguishable from a network blip.

### G5. Per-user permission changes at runtime
Research §1b notes tokens are "invalidated if the account is changed"; §9 defines permissions per user. FR-28 checks permissions "before entity creation" only. No requirement covers permissions being *reduced* after setup (entities begin failing) or *granted* (entities never appear until…?). The addendum even flags Gold `dynamic-devices`/`stale-devices` as worth honoring. A reconfiguration/reload consequence ("permission changes are picked up on reload/reauth, with entities added/removed accordingly") is missing from FR-28/FR-29.

### G6. `FILE` event ~96 s lag never surfaces as a product caveat
Research §3.5: recording-completion lags ~96 s (post-roll). The Observation Record is capture-derived, so "last human seen" can trail reality by up to ~1.5–2 minutes plus poll interval. UJ-1's dashboard promise and FR-9/FR-10 ("most recent Capture", "state changes when a new Capture supersedes it") make no latency statement. Open Question 3 covers classification-write timing but not this verified completion lag. The PRD should bound or at least document the expected staleness of capture-derived values so SM-1 is testable honestly.

### G7. Least-privilege documentation is promised but the *set* of needed permissions is not required output
Research §9/§10 (security reqs) says "document the least-privileged SecuritySpy user." PRD §11.2/§10.1 repeats "least-privileged SecuritySpy user documented" but no FR consequence requires the documentation to enumerate which `PERM_*`-level capabilities each feature needs (the research gives the exact map). Minor, but it is the difference between a checkbox and actionable docs; fold into FR-28 or docs requirements.

## Weakened — research constraints the PRD states more softly than the evidence supports

### W1. Arm Override durations are bounded to ≤6 hours / until-next-scheduled-event — FR-13's "override-only writes" has an unstated capability cap
Research §5.2: overrides come in exactly 16 fixed values, max 6 hours, or "until next scheduled event." There is no permanent override. FR-12's consequence "all eight combinations of the three modes are expressible" is true only *transiently*: an automation that "disarms the driveway" via override will silently revert on the next schedule boundary or after ≤6 h. The PRD never tells the user (or the blueprint author) that HA-driven arming is inherently temporary. This is a user-visible limitation the override-only decision creates, and the PRD adopts the decision (§5.4, addendum §5) without carrying its cap.

### W2. Persistent classification (`o` field) timing is unverified, but FR-3/FR-2 promise unconditional self-healing
Architecture doc Open Question 4: "Does `o` populate at capture close or later?" — unresolved. PRD Open Question 3 acknowledges this only for FR-11 lag. But FR-3's "the Observation Record reflects those detections on the next reconciliation" also depends on it: if classification is written late, one reconciliation may not suffice. Consequence wording should be "on a subsequent reconciliation once SecuritySpy has persisted classification," or the open question should explicitly gate FR-3's test.

### W3. Verified-vs-unproven audio distinction — PRD §7.2 gets it right in prose but the camera entity promise doesn't inherit it
§7.2 correctly states audio is "unresolved rather than impossible." However FR-22 promises "enabling one produces working live video" with no statement that streams may be video-only. Fine as a v1 boundary, but a consequence like "no audio is promised on the live video entity" would prevent SM-8/FR-22 acceptance disputes. Minor.

### W4. Event stream is vendor-untested — resilience framing understates it
Research §3.6: the vendor's own client never uses the event stream; "assume no vendor testing here." The PRD's Resilience section treats disconnects/reboots as the hazard, but the research implies a stronger requirement: the stream may misbehave in *unknown* ways on future SecuritySpy releases (MOTION_END already does). FR-31/FR-30 cover connection loss; nothing requires that malformed/unexpected stream data degrade gracefully to poll-derived state rather than crash or wedge the integration. One consequence under FR-30/FR-34 would close it ("unparseable Event Stream data never renders the integration unavailable; poll-derived state continues").

## Contradictions — PRD consequences vs. verified research facts

### C1. FR-6 / §5.2: "~190 Classification Signals" for a 95-second single-person episode — number misattributed
Research §3.5: the 191 CLASSIFY events in ~95 s were measured **on one camera across the whole capture window**, described as a per-frame inference stream with events 0–2 s apart — not measured as one continuous single-person Detection Episode producing 191 signals. FR-6's testable consequence "A 95-second single-person episode producing ~190 Classification Signals produces exactly one Classification Event" hardens a stream-rate observation into an episode-shape fact. The once-per-episode requirement is right; the specific test consequence over-claims the measurement. Reword to cite the rate, not a fabricated episode.

### C2. FR-7's "verified behavior… 467 motion signals and zero end signals in 95 seconds" — window conflation
Research §3.5: the capture was described as "100 s capture" / "95 s" in different rows; camera 10 showed 467 MOTION and 0 MOTION_END over that capture. Substantively correct; PRD's use is fine, but note the same capture yielded MOTION_END = 6 total across cameras (not zero everywhere) — FR-7's wording ("cameras that never signal motion end") matches the evidence for camera 10 specifically. No change needed beyond precision; flagged for the record.

### C3. §5.1 "each value is one cheap query" vs. research-flagged polling cost — internally reconciled but worth aligning
API ref §4.2 supports one-request-per-class; architecture doc Open Q3 warns 3 × N cameras per cycle. PRD §10.2/§11.1 carries the scaling constraint correctly. Not a contradiction on inspection — listed to confirm it was checked.

### C4. "Zero non-camera entities" claim (§1 Vision) — consistent with brief, not contradicted by research. Checked; no issue.

## Summary of recommended PRD edits (priority order)
1. Add a requirement (or explicit v1 exclusion with FR-42 impact analysis) for resource-scoped token auth on stream URLs (G1).
2. Add a setup-guidance/repair requirement for class triggers off-by-default (G2).
3. State the Arm Override ≤6 h / until-next-event cap as a user-visible limitation of FR-12/FR-13 (W1).
4. Extend bidirectionality to settings-backed controls or add a staleness bound (G3).
5. Reword FR-6's 190-signal episode consequence to a rate-based claim (C1); soften FR-3 pending Open Q3 resolution (W2).
6. Distinguish camera error state from offline in FR-30/FR-23 (G4); add permission-change handling to FR-28/FR-29 (G5); document capture-derived latency (~96 s FILE lag) for SM-1 honesty (G6); add graceful degradation on malformed stream data (W4).
