# Reconciliation: Brief → PRD (2026-08-09)

Source: `briefs/brief-ha-securityspy-2026-08-09/{brief.md, addendum.md}`
Target: `prds/prd-ha-securityspy-2026-08-09/{prd.md, addendum.md}`

Known deliberate changes (JoshADC positioning, CoreML dynamic entities gated on spike, arming override-only + read-only schedule, HA-proxied image access) are excluded per instructions.

---

## Gaps (source content missing from target)

Ranked by importance.

1. **Classification Event drops the captured-file reference.** Brief scope (§Scope, "In, for v1"): "classification events carrying peak confidence **and a captured-file reference**." PRD FR-6's payload is Object Class + Peak Confidence + Camera Device only. The file reference is what links a detection to its recording (and to UJ-2's image fetch); dropping it silently weakens the detection→capture chain the brief made explicit. Either add it to FR-6's consequences or record the drop with a rationale (e.g., the FILE event's 96 s latency per brief addendum §8.9 — but that argues for async attachment, not omission).

2. **`download_latest_motion_recording` service silently dropped.** Brief addendum §8.13 disposition table says **"Keep. Complement with media_source"** — explicitly keep even though media_source is deferred, precisely because with no media browser in v1, download is the only way to get a recording locally. The PRD neither includes it nor lists it in §7.2 Out of Scope. It has vanished without a decision. (Related: `set_arm_mode` "keep a service for scripting" also unaddressed.)

3. **Recording-completed (FILE) event and trigger-reason event entities absent.** Brief addendum §4.2 entity mapping lists "Recording file completed → event entity" and "Trigger events (reason bitmask, arrival/departure) → event entity." The PRD has neither as a capability nor as a scoped-out item. Arrival/departure survives only as Open Question 6; the FILE event surface disappears entirely — yet it is the natural push signal for "poll the Observation Record now" (PRD Open Question 4 lists "polling only after a recording completes" as a candidate without naming the FILE event that enables it).

4. **Blueprint qualitative bar lost.** Brief addendum §8.13 specifies what the flagship notification blueprint must match and beat: presence filter, actionable **silence** button with cooldown, mobile/Telegram targets, and the two concrete incumbent weaknesses our image entity fixes — requires a publicly reachable HTTPS HA instance, and sends the *live* frame rather than the *detection* frame ("the subject may already have left the scene"). FR-37 reduces this to "two blueprints, one-click import, no attribute lore." Nothing obliges the notification blueprint to use the detection frame or to work without a public URL — the exact "demonstrable improvement over the incumbent [to] be called out in release notes."

5. **Additional writable settings from §8.6/§8.14 not covered or scoped out.** `motion-sensitivity`, `audio-sensitivity`, `brightness`, `contrast` are called out as "writable `number` entities," and §8.14 lists Actions-mode trigger variants (`aTriggerMotionH/V/A`). PRD FR-17/18 covers only motion-capture per-class triggers and per-class sensitivities. Deliberate narrowing would be fine (SM-C3), but §7.2 doesn't record it, so it reads as an oversight. FR-17's "each Object Class causes SecuritySpy to record" is also silent on which mode (motion capture vs actions).

6. **Per-camera detection toggle in HA (observation-record inclusion).** Brief §Scope: "Per-camera detection toggles are included too: … an observation record dominated by kitchen traffic is not useful to someone watching a driveway." The PRD maps this need entirely onto SecuritySpy-side Detection Triggers (FR-17) — which changes what SecuritySpy *records*, a heavier side effect than the brief's toggle implies. An HA-side "exclude this camera from detection entities" knob is arguably what was meant; at minimum the reinterpretation is undocumented.

7. **§6a criterion "reachable image within a few seconds of detection" not bound to an FR.** PRD §11.1 covers event latency, and FR-9 covers reachability, but no consequence ties the *image for that detection* to the few-seconds window (the Latest Capture may lag — PRD's own FR-11 note admits classification/capture lag is unresolved). The brief-addendum criterion joins class + confidence + image in one timely event; the PRD splits them across FR-6/FR-9 with no timing link.

## Weakened

1. **Translation/icon discipline (brief addendum §6a Quality: "All entities carry `translation_key`; no hardcoded names or `_attr_icon`").** FR-20 keeps "no hardcoded names" but translation keys and icon handling appear nowhere, and the PRD's "mechanism lives elsewhere" rule doesn't obviously cover an acceptance criterion the brief addendum explicitly said "should feed the PRD."

2. **"Entities go unavailable and recover on their own" per-disruption.** Brief success criteria attach unavailability+recovery to each of the four disruptions; SM-7 keeps the four disruptions but tests only "no restart / no manual recovery," and FR-30/31 test unavailability generally. The specific "Mac reboot ⇒ entities unavailable, then self-recover" pairing survives only narratively in UJ-4.

3. **"Push for latency, poll for truth" as a stated architecture posture.** PRD §11.3 keeps the substance ("stream is a latency optimization, not a source of truth") but the brief's crisp formula — and its corollary "assume no vendor testing on the event stream; let the poll path be authoritative" (§8.12) — is diluted. The vendor-never-uses-the-stream fact is a strong justification worth carrying.

4. **Least-privileged-user guidance demoted.** Brief addendum §8.14 makes it a numbered requirement triple (redact, never log, document least privilege); PRD keeps all three but the documentation item lives only in §10.1/§11.2 prose with no FR consequence, so it can slip through epic decomposition.

## Contradictions

1. **Diagnostics and repair issues: brief defers, PRD requires.** Brief §Scope lists "diagnostics, repair issues" under "Deferred, wanted, not v1," yet the PRD requires downloadable diagnostics (§11.4, FR-42) and permission repair issues (FR-28), and §7.2 excludes only "repair issues beyond permissions." Probably the right call (FR-42's security driver is real), but it reverses the brief's scoping without acknowledgment.

2. **FR-2 "populated before the integration reports itself as set up" vs UJ-4/resilience posture.** The brief requires correctness after restart, not blocking setup on a full Capture History query; making setup wait on the backfill is stricter than the source and mildly conflicts with fast, resilient startup when the server is slow. Worth a conscious choice (backfill-before-setup vs backfill-promptly-after).

3. **Camera-enable control vs permission model.** Minor: FR-16 (enable/disable camera in SecuritySpy) is a settings write the brief's scope line "editing SecuritySpy settings beyond arming" excluded ("Explicitly out for v1"). The brief addendum §8.13 does recommend it as a switch — the two source statements conflict, and the PRD silently sides with the addendum. Record the choice.

## Verbatim-worthy

1. **"If it works, SecuritySpy stops being a system that records and becomes one that *notices*."** (brief, Executive Summary). The single best statement of the product's emotional stake; the PRD's Vision keeps "records everything and tells you nothing" but loses the payoff line.

2. **"The bar is not 'better than the abandoned integration.' The bar is that in three years it still works and someone else is relying on it."** PRD §1 keeps a paraphrase of the second sentence; the first sentence's explicit rejection of the low bar is worth restoring, especially now that the JoshADC fork exists.

3. **"The picture arrives and the knowledge does not."** (brief, The Problem). Sharper than anything in PRD §1/§3.1 for the ONVIF-coexistence framing.

4. **"A notification that is *useful* in a way 'motion detected' never is."** The Nest comparison in PRD §3.1 keeps the fact but not the phrasing.

5. **"If a blueprint is awkward to write, the entity model is wrong."** Present in PRD §5.10 — good; also belongs beside SM-3 where the test is defined.

---

*Prepared 2026-08-09 by input-reconciliation pass; brief and brief addendum read in full against PRD and PRD addendum.*
