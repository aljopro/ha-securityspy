---
title: Home Assistant Integration for SecuritySpy
status: final
created: 2026-08-09
updated: 2026-08-29
---

# PRD: Home Assistant Integration for SecuritySpy

## 0. Document Purpose

This PRD is for the builder, for downstream BMad workflows (architecture, epics and stories), and for any future maintainer deciding whether this project is worth inheriting. It builds on the [product brief](../../briefs/brief-ha-securityspy-2026-08-09/brief.md) and its addendum, and on two research artifacts — the [SecuritySpy API reference](../../research/securityspy-api-reference.md) and [architecture-implications.md](../../research/architecture-implications.md). Those documents establish *what SecuritySpy can do*; this one establishes *what the integration must do*.

Structure: vocabulary is fixed in the Glossary (§4) and used verbatim everywhere else. Features are grouped in §5 with Functional Requirements nested and numbered globally (FR-1…FR-45) so downstream artifacts have stable references. Cross-cutting quality requirements live in §11. Inferences are tagged `[ASSUMPTION]` inline and indexed in §14.

Technical mechanism — transport, parsing, library design, endpoint specifics — is deliberately **not** here. It lives in the research artifacts and in `addendum.md` alongside this file. Where a product requirement is constrained by a verified technical fact, the constraint is stated and the fact is cited, but the implementation is left to the architecture phase.

---

## 1. Vision

SecuritySpy is a mature macOS NVR that classifies humans, vehicles, and animals in real time, streams those classifications over a push event stream, and stores the result against every recording it makes. Home Assistant sees none of it. The information exists, streams live, and is already written to disk — and none of it arrives.

The result is a surveillance system that records everything and tells you nothing. Eleven cameras on the reference system appear in Home Assistant as `generic` camera entities pointed at an IP address, contributing **zero non-camera entities** between them. There is nothing to write an automation against. There is no way to ask *has anyone been in the driveway today*, because nothing in Home Assistant has ever been told.

This project builds the integration that should exist: a SecuritySpy server as a Hub Device, each camera as a Camera Device beneath it, and — as the headline deliverable — an **Observation Record**: what has been seen, where, and when, per camera, correct after a restart. Live events keep it current; the capture history SecuritySpy already maintains makes it true. Video is deliberately not the point; that already works over ONVIF and stays. The value is the data, and the bar is that in three years this still works and someone else is relying on it.

## 2. Why Now

Three things converged in the last eighteen months, and together they define the window.

**The incumbent stopped.** `briis/securityspy` was archived in September 2024 with the author stating plainly he no longer has the resources to maintain it. Its backing library, `pysecspy`, has not shipped since August 2022. Because HACS automatically removes archived repositories from its default store, the integration silently disappeared for users around HA 2025.1 — a removal nobody announced and users discovered by breakage.

**SecuritySpy 6 changed what is possible.** The version-6 client uses a JSON API the published specification does not describe. A HAR capture of that client revealed `++caplist`, which persists an object-classification bitmask against every recording, and supports server-side filtering by object class. This is what makes the Observation Record cheap and restart-correct rather than fragile in-memory reconstruction — and it did not exist as a known capability when the previous integration was designed.

**Nobody is maintaining a reusable SecuritySpy library.** `pysecspy` is dead, and the one surviving descendant of the original integration abandoned it too, parsing XML inline instead. Home Assistant's Bronze quality scale requires an integration's API client to be a transparently-built, versioned, OSI-licensed PyPI package. That ground is unoccupied, and occupying it is what makes both this integration and any future one durable.

## 3. Target User

### 3.1 Jobs To Be Done

- **Know what has been seen, after the fact.** Not "were you notified at the time" — *has anyone been in the driveway today*, asked whenever the question occurs, answered from Home Assistant alone.
- **Be told what is happening, not that something happened.** "There's a package at the door" rather than "motion detected." The reference user has a Nest doorbell that clears this bar and a surveillance system that does not.
- **Automate against cameras like any other Home Assistant device** — in the UI automation editor, without attribute-name lore or reading source code.
- **Keep the working video setup untouched.** ONVIF handles video well; adding knowledge must not cost the user their existing transport.
- **Stop tending the integration.** The predecessor's failure mode was maintainer fatigue. Success includes not having to think about it.
- **For the builder specifically:** produce something durable enough that inheriting it is attractive, and that a core submission remains possible without being committed to.

### 3.2 Non-Users (v1)

- Users wanting SecuritySpy as their **primary video transport** into Home Assistant. Camera entities ship disabled by default; ONVIF coexistence is the expected topology.
- Users on **multiple SecuritySpy servers**. Out for v1; the identity scheme leaves room.
- Users wanting **SecuritySpy configuration management** from Home Assistant beyond arming and detection tuning.
- Users expecting **package detection, face recognition, or scene description**. SecuritySpy does not do these; the integration exposes the image and the user points whatever they like at it.

### 3.3 Key User Journeys

- **UJ-1. Jensen asks the house what it saw.**
  Jensen, eleven cameras across a home, primarily concerned with the outdoor ones. He is on the sofa and wonders whether a delivery came while he was out. Already authenticated — this is his own Home Assistant. He opens a dashboard card listing each outdoor camera with *last human seen*, *last vehicle seen*, and *last animal seen* as relative timestamps. Driveway: human 40 minutes ago, vehicle 41 minutes ago. **Climax:** the question is answered without opening SecuritySpy, scrubbing footage, or having been notified at the time. **Resolution:** he taps through to the latest capture image for the driveway to confirm it was the courier. **Edge case:** Home Assistant restarted twenty minutes ago. The values are still correct, because they are derived from SecuritySpy's stored capture history rather than from events observed while Home Assistant happened to be running.

- **UJ-2. The driveway narrates itself.**
  Jensen, same house, out for the evening. A person walks up the driveway. SecuritySpy classifies a human; the integration's detection debounce confirms it is not a single noisy frame and fires a Classification Event carrying peak confidence and the camera. Jensen's own automation picks it up, fetches the Latest Capture image from its Home Assistant URL, sends it to a vision model, and pushes the reply to his phone. **Climax:** the notification reads *"Someone in a delivery uniform is leaving a box by the front step"* — a sentence he would actually want to read — within a few seconds of SecuritySpy seeing it. **Resolution:** he does nothing, because now he knows. **Edge case:** the vision service is down. The automation still has class, confidence, timestamp, and a working image URL, so a degraded notification ("Human detected, driveway, 94%") still goes out.

- **UJ-3. Priya installs it without asking anyone for help.**
  Priya runs SecuritySpy over HTTPS on a Mac mini and found this integration on the Ben Software forum. She adds it as a HACS custom repository, restarts, and clicks Add Integration. She enters host, port, username, password. The config flow validates the credentials, warns her that her certificate will not verify against a LAN IP and offers the verification toggle, and completes. **Climax:** her cameras appear as correctly-named devices under one server hub, with no manual renaming and no `192_168_0_2_4` entity IDs. **Resolution:** she imports the notification blueprint from the README's one-click link and has a working alert in under a minute. **Edge case:** her SecuritySpy user lacks arming permission. Rather than presenting arm switches that will permanently fail, the integration omits them and raises a repair issue naming the missing permission.

- **UJ-4. The Mac reboots at 3am and nobody notices.**
  Unattended. SecuritySpy goes away mid-night for a software update. The event stream heartbeat lapses; the integration logs the loss once, marks entities unavailable rather than leaving them stale, and retries with backoff, logging retries at debug rather than filling the log. SecuritySpy returns. **Climax:** the integration reconnects, reconciles against the capture history to recover anything missed while disconnected, and logs recovery once. **Resolution:** Jensen finds out only because the Observation Record shows a gap — no Home Assistant restart, no re-authentication, no broken entities.

---

## 4. Glossary

Downstream workflows must use these terms exactly. Introducing a synonym anywhere is a discipline violation.

- **SecuritySpy Server** — one installation of the SecuritySpy macOS application. Identified by a stable server UUID. Exactly one per Config Entry in v1.
- **Hub Device** — the Home Assistant device representing a SecuritySpy Server. Parent of all Camera Devices from that server. One per Config Entry.
- **Camera Device** — the Home Assistant device representing one camera known to a SecuritySpy Server. Child of exactly one Hub Device. Identified by server UUID plus SecuritySpy camera number, never by name.
- **Config Entry** — the Home Assistant configuration entry created by the config flow for one SecuritySpy Server.
- **Event Stream** — SecuritySpy's live push channel. Sub-second, lossy, no replay. Drives latency-sensitive state.
- **Capture History** — SecuritySpy's stored record of completed recordings, including a persisted object classification per recording. Authoritative, survives restarts, self-heals. Drives the Observation Record.
- **Capture** — one completed recording (movie or image) in the Capture History, with a timestamp, camera, and Object Class set.
- **Object Class** — a category SecuritySpy assigns to a detection. The three built-in classes are *human*, *vehicle*, and *animal*. A Custom Model may emit additional Object Classes. Object Class is open data, never a fixed enumeration.
- **Custom Model** — a user-supplied CoreML classification model that SecuritySpy runs per camera, emitting Object Classes beyond the three built-in ones.
- **Classification Signal** — one instantaneous per-frame inference from the Event Stream, carrying a confidence percentage per Object Class. High-frequency and noisy; not a detection in itself.
- **Detection Episode** — a contiguous period during which Classification Signals for one Object Class on one Camera Device sustain confidence above the Detection Threshold for at least the Detection Debounce. The unit of meaning; the thing a user calls "a person was there."
- **Detection Threshold** — the minimum confidence percentage a Classification Signal must carry to count toward a Detection Episode. Configurable globally with a per-Camera-Device override.
- **Detection Debounce** — the minimum number of consecutive qualifying Classification Signals required to open a Detection Episode. Configurable globally with a per-Camera-Device override.
- **Peak Confidence** — the highest confidence observed across a Detection Episode. Reported once per episode, not per Classification Signal.
- **Observation Record** — the per-Camera-Device set of *last seen* timestamps, one per built-in Object Class, derived from the Capture History. The headline deliverable.
- **Latest Capture** — the most recent Capture for a Camera Device, exposed as an image whose state is that capture's timestamp.
- **Arm Mode** — one of SecuritySpy's three independently-settable per-camera modes: *continuous capture*, *motion capture*, *actions*. Independent booleans, not a single state machine.
- **Arm Schedule** — a user-defined SecuritySpy schedule governing an Arm Mode. Read-only from Home Assistant.
- **Arm Override** — a transient SecuritySpy instruction that supersedes an Arm Schedule for a bounded period. The only arming dimension this integration writes.
- **Detection Trigger** — a per-Camera-Device SecuritySpy setting controlling whether a given Object Class causes a recording. Writable.
- **API Library** — the standalone, typed, async Python package on PyPI that owns all SecuritySpy protocol knowledge. Distinct from the integration.

---

## 5. Features

### 5.1 The Observation Record

**Description.** The headline deliverable and the reason this project exists. For each Camera Device, three timestamps — when a human, a vehicle, and an animal were each last seen — derived from the Capture History rather than accumulated from live events. Because SecuritySpy persists an Object Class against every Capture and supports filtering the Capture History by class server-side, each value is one cheap query, and it is correct immediately on startup rather than empty until the next detection. Realizes UJ-1.

This is what distinguishes the integration from every prior attempt. `briis` exposed classification as an attribute on a motion sensor, which vanished on restart. The Observation Record is state that outlives the process observing it.

**Functional Requirements:**

#### FR-1: Per-class last-seen timestamps

A Home Assistant user can read, per Camera Device, the time a human, a vehicle, and an animal was each last seen. Realizes UJ-1.

**Consequences (testable):**
- Each Camera Device exposes exactly three Observation Record values, one per built-in Object Class.
- Each is a timestamp, typed such that Home Assistant renders it as a relative time and it is usable in automation conditions and templates.
- A value is absent (not zero, not epoch) when no Capture of that Object Class exists in the queried window.
- Values are derived from the Capture History, not from Event Stream accumulation.

#### FR-2: Restart correctness

The Observation Record is correct immediately after a Home Assistant restart, without waiting for a new detection. Realizes UJ-1.

**Consequences (testable):**
- After a Home Assistant restart with SecuritySpy reachable, Observation Record values are populated on the integration's first data refresh, without waiting for a new detection. Setup itself is not blocked on this hydration.
- Values after restart match values before restart, where no new Capture occurred in between.
- Restarting Home Assistant during a Detection Episode does not corrupt or blank the Observation Record.

#### FR-3: Self-healing after disconnection

The Observation Record recovers detections that occurred while Home Assistant was disconnected from SecuritySpy. Realizes UJ-4.

**Consequences (testable):**
- After an Event Stream disconnection spanning one or more detections that SecuritySpy recorded, the Observation Record reflects those detections on the next reconciliation without operator action.
- Recovery does not require a Home Assistant restart or a Config Entry reload.

**Out of Scope:**
- Detections SecuritySpy itself never recorded — self-healing recovers what the Capture History holds, and the Capture History holds only what the camera's Detection Triggers allowed (see FR-45).

#### FR-4: Bounded lookback

The Observation Record queries a bounded window of Capture History rather than unbounded history.

**Consequences (testable):**
- The lookback window is finite and documented.
- When no Capture of an Object Class exists within the window, FR-1's absent-value behavior applies rather than an unbounded scan.

**Notes:** `[NOTE FOR PM]` The lookback window length is unset. Too short and "last human seen" reads empty on a quiet camera; too long and startup cost grows. Research does not settle it. Flagged in §13.

`[NOTE FOR PM]` Whether SecuritySpy writes classification at capture close or later (Open Question 3) gates how fresh FR-2 and FR-3 can be. This is **blocking for Phase 2** and carries a spike gate in §12 — it is a short probe against a live server, not a research project.

---

### 5.2 Live Detection

**Description.** What keeps the Observation Record current and what makes real-time automation possible. SecuritySpy's Event Stream emits Classification Signals per frame — measured at 191 signals on one camera in 95 seconds, with confidence swinging from 4 to 100 for a single person crossing the view. Treating each signal as a detection would fire roughly 190 Home Assistant events per person. So the integration reduces signals into Detection Episodes using a Detection Threshold and Detection Debounce, and exposes each episode two ways: as presence (*is a human there now*) and as an event (*a human was detected, with this confidence*). Realizes UJ-2.

Both surfaces exist because they answer different questions, which is the same reason UniFi Protect ships both for vehicles. Presence is what a user triggers a light on; the event is what carries confidence to a vision model.

**Functional Requirements:**

#### FR-5: Per-class presence

A Home Assistant user can trigger automations on whether a given Object Class is currently present on a Camera Device. Realizes UJ-2.

**Consequences (testable):**
- Each Camera Device exposes per-class presence for human, vehicle, and animal, discoverable as ordinary device triggers in the UI automation editor.
- Presence turns on when a Detection Episode opens and off when it closes.
- Presence does not turn on for Classification Signals below the Detection Threshold, however frequent.
- Presence does not flicker on isolated qualifying signals below the Detection Debounce.

#### FR-6: Classification Event with confidence

A Home Assistant automation can react to a completed detection and read its Object Class and Peak Confidence. Realizes UJ-2.

**Consequences (testable):**
- Exactly one Classification Event fires per Detection Episode per Object Class — not one per Classification Signal.
- The event payload carries Object Class, Peak Confidence for the episode, the Camera Device, and — where a Capture resulted — a reference to the captured file.
- Signal volume does not multiply events: the reference measurement of 191 Classification Signals on one camera in 95 seconds produces on the order of one event per Detection Episode, never one per signal.
- Peak Confidence is the maximum observed across the episode, not the value at threshold crossing.

#### FR-7: Motion presence

A Home Assistant user can trigger automations on motion per Camera Device, independent of classification.

**Consequences (testable):**
- Each Camera Device exposes motion presence, typed as motion for Home Assistant.
- Motion presence clears on its own after a period of inactivity, without depending on SecuritySpy signalling motion end.
- Motion presence clears even on cameras that never signal motion end — verified behavior on at least one reference camera that produced 467 motion signals and zero end signals in 95 seconds.
- The inactivity timeout has a documented default and is adjustable without a restart.

#### FR-8: Configurable detection tuning

A Home Assistant user can adjust the Detection Threshold and Detection Debounce globally and per Camera Device.

**Consequences (testable):**
- Both are settable after setup without removing and re-adding the Config Entry.
- A per-Camera-Device value overrides the global value for that camera; absent an override, the global applies.
- Changes take effect without a Home Assistant restart.
- Shipped defaults produce working presence on the reference system without tuning.

#### FR-43: Trigger events

A Home Assistant automation can react to SecuritySpy deciding to record, and read why.

**Consequences (testable):**
- Each Camera Device exposes a trigger event that fires when SecuritySpy triggers a recording.
- The event carries the decoded trigger reason (motion, audio, per-class movement, arrival/departure, manual, and the other reasons SecuritySpy encodes) — never a raw bitmask.
- Reasons the server can emit but that are disabled in SecuritySpy simply do not fire; their absence is not an error.

**Feature-specific NFRs:**
- Reducing Classification Signals to Detection Episodes must not put per-signal load on the Home Assistant state machine or recorder. The ~190:1 reduction is the requirement, not an optimization.

**Notes:** `[ASSUMPTION: The default Detection Threshold is 70% and the default Detection Debounce is a small number of consecutive signals. Research floats ~70 as a starting point but explicitly states correct values are camera- and scene-dependent and must be tuned against real footage. Treated as provisional.]`

---

### 5.3 Latest Capture Image

**Description.** The bridge between detection and meaning. Each Camera Device exposes its most recent Capture as an image with a stable Home Assistant URL, whose state is the capture's timestamp. That URL is what makes downstream vision analysis possible: an automation fetches it, hands it to whatever service the user chooses, and gets back a sentence worth reading. SecuritySpy renders capture thumbnails itself, so no frame extraction is required. Realizes UJ-2.

The integration's job ends at making the image easy to reach. It does not interpret images, and it makes no promise about SecuritySpy being reachable from anywhere other than Home Assistant.

**Functional Requirements:**

#### FR-9: Latest Capture as a fetchable image

A Home Assistant automation can fetch the most recent Capture for a Camera Device from a stable Home Assistant URL. Realizes UJ-2.

**Consequences (testable):**
- Each Camera Device exposes a Latest Capture image.
- The image is served by Home Assistant. The integration makes no requirement that the consumer can reach the SecuritySpy Server directly.
- The URL remains valid across image updates and Home Assistant restarts.
- Fetching returns the most recent Capture known at fetch time.

#### FR-10: Timestamp state as automation trigger

A Home Assistant user can trigger an automation on a new Capture appearing.

**Consequences (testable):**
- The Latest Capture image's state is the timestamp of the capture it holds.
- The state changes when a new Capture supersedes it, and is usable as a state trigger.
- On startup the state reflects the newest existing Capture, not an empty or restart-time value.

#### FR-11: Object Class alongside the image

A Home Assistant automation can read which Object Classes were detected in the Latest Capture.

**Consequences (testable):**
- The Object Class set for the capture is readable alongside the image.
- Where SecuritySpy recorded no classification, the set is empty rather than absent or erroneous.

#### FR-44: Download latest recording

A Home Assistant automation can save the most recent recording for a Camera Device to a file.

**Consequences (testable):**
- A service accepts a Camera Device and a destination and writes the most recent completed recording there.
- Failure modes — no recording available, destination unwritable, insufficient SecuritySpy permission — produce distinct, actionable errors.
- The service does not delete or modify anything on the SecuritySpy Server.

**Feature-specific NFRs:**
- SecuritySpy completes a recording only after its post-roll — measured at roughly 96 seconds after an episode ends on the reference system. The Latest Capture is therefore not a sub-second signal, and SM-2's "within a few seconds" applies to detection (FR-6), not to capture availability. Blueprints and documentation must not imply otherwise.

**Notes:** `[NOTE FOR PM]` Whether classification is written at capture close or later is unresolved (§13, blocking). If later, FR-11 may lag FR-9 by one poll on the newest capture.

---

### 5.4 Arming Control

**Description.** SecuritySpy's three Arm Modes are independent booleans, not a single state machine — which is why they are three separate controls rather than one alarm panel, an encoding that would lose information. Home Assistant writes only the Arm Override, never the Arm Schedule: overriding is transient and reversible, whereas writing a schedule would destroy configuration the user built in SecuritySpy. The active Arm Schedule is shown read-only so users can see what is governing a camera without Home Assistant being able to clobber it.

**Functional Requirements:**

#### FR-12: Per-mode transient arming control

A Home Assistant user can apply a transient Arm Override to each Arm Mode independently per Camera Device.

> **Split 2026-08-29.** FR-12 originally read "arm and disarm each Arm Mode independently" and carried *both* jobs — the transient one and the persistent one — in a single requirement. SecuritySpy expresses them through two different operations, so this is now FR-12 (transient, override) and FR-12a (persistent, schedule assignment). See AD-7's split.

**Consequences (testable):**
- Each Camera Device exposes three independent arming controls, one per Arm Mode.
- Setting one Arm Mode does not alter the other two.
- All eight combinations of the three modes are expressible as a write target.
- Controls are categorized as configuration rather than primary controls.
- The control's transience is visible, not buried: a user can tell from Home Assistant that the state reverts and, where the server reports it, when.

#### FR-12a: Persistent arming via explicit schedule assignment

A Home Assistant user can assign an existing SecuritySpy Arm Schedule — including the built-in "Disarmed 24/7" — to each Arm Mode per Camera Device, through an explicitly invoked action.

**Consequences (testable):**
- The operation is invoked deliberately (a documented action), never by toggling an entity.
- Its description states that it changes SecuritySpy's own configuration and persists until changed again.
- Only schedules SecuritySpy already defines can be assigned; the option list is read from the server, never hardcoded.
- No Home Assistant surface creates, edits, deletes, or reorders a schedule *definition*.
- Home Assistant does not record a prior assignment in order to restore it silently: reversal is the same explicit operation, using the assignment the user can read from FR-15.

#### FR-13: Switches write the override; only the explicit action writes a schedule

Arming from a Home Assistant control writes the Arm Override. Only FR-12a's explicitly invoked action assigns an Arm Schedule, and nothing in Home Assistant alters a schedule's definition.

**Consequences (testable):**
- After using the arming controls in Home Assistant, the Camera Device's Arm Schedule assignment in SecuritySpy is unchanged.
- No Home Assistant action can create, edit, or delete a SecuritySpy Arm Schedule.
- A schedule assignment reaches SecuritySpy only from FR-12a's action — never from an entity state change, and never as a side effect of an override write.
- The transience is stated, not hidden: SecuritySpy's Arm Override is bounded — at most six hours, or until the next scheduled event — after which the Arm Schedule resumes. Documentation and the arming controls' behavior must reflect this rather than implying an indefinite HA-set state.

#### FR-14: Bidirectional state for all writable controls

State changed in SecuritySpy is reflected in Home Assistant, and vice versa — for every control this integration writes.

**Consequences (testable):**
- An Arm Mode changed in the SecuritySpy application is reflected in Home Assistant without a restart or reload.
- An Arm Mode changed from Home Assistant is observable in SecuritySpy.
- The same holds for camera enablement (FR-16), Detection Triggers (FR-17), and sensitivities (FR-18): a change made in SecuritySpy is reflected in Home Assistant within one reconciliation cycle, without a restart.
- Home Assistant does not indefinitely report a control state that contradicts the server's.

#### FR-15: Read-only Arm Schedule visibility

A Home Assistant user can see which Arm Schedule governs each Arm Mode on a Camera Device.

**Consequences (testable):**
- The active Arm Schedule per Arm Mode is readable per Camera Device.
- The value reflects schedules as the user defined them, not a fixed built-in list.
- No Home Assistant *entity* permits changing it; the only surface that reassigns one is FR-12a's explicit action, and a schedule's definition stays unchangeable from Home Assistant entirely.
- The readable assignment is what makes FR-12a reversible without Home Assistant storing hidden state.

#### FR-16: Camera enable control

A Home Assistant user can enable and disable a camera in SecuritySpy.

**Consequences (testable):**
- Each Camera Device exposes an enable control reflecting SecuritySpy's enabled state.
- Disabling in Home Assistant disables the camera in SecuritySpy.
- A disabled camera's entities behave per FR-30 rather than reporting stale values.

---

### 5.5 Detection Tuning in SecuritySpy

**Description.** Per-camera control over which Object Classes cause SecuritySpy to record, plus per-class sensitivity. This matters for a reason independent of privacy: on the reference system, indoor cameras generate the large majority of classification traffic, and an Observation Record dominated by kitchen movement is not useful to someone watching a driveway. These are controls no prior integration surfaced.

These controls also gate the Observation Record's completeness: SecuritySpy's per-class trigger settings are **off on a default install**, so exposing them is what lets a user turn the Observation Record on (see FR-45).

**Functional Requirements:**

#### FR-17: Per-class Detection Trigger control

A Home Assistant user can control, per Camera Device, whether each Object Class causes SecuritySpy to record.

**Consequences (testable):**
- Each Camera Device exposes a Detection Trigger control for human, vehicle, and animal.
- Toggling writes to SecuritySpy and survives a SecuritySpy restart.
- Controls are categorized as configuration.
- Writing one Detection Trigger does not disturb unrelated SecuritySpy camera settings.

#### FR-18: Per-class sensitivity control

A Home Assistant user can adjust per-Object-Class detection sensitivity per Camera Device.

**Consequences (testable):**
- Sensitivity is adjustable for human, vehicle, and animal per Camera Device.
- Values are constrained to the range SecuritySpy accepts.
- Changes are reflected in SecuritySpy and survive a restart.

#### FR-45: Detect the default-install trap

A user whose SecuritySpy has per-class triggering disabled is told so, rather than left with an empty Observation Record.

**Consequences (testable):**
- SecuritySpy's per-class Detection Triggers are off on a default install; the Observation Record is empty until they are enabled. The integration detects this condition.
- When every configured camera has all per-class Detection Triggers disabled, the integration surfaces guidance naming the setting and where to change it — in SecuritySpy or via FR-17.
- The guidance is dismissible and does not recur once any per-class Detection Trigger is enabled.
- The integration does not silently enable Detection Triggers on the user's behalf.

**Notes:** These are SecuritySpy's own sensitivities, distinct from the integration's Detection Threshold and Detection Debounce (FR-8). The Glossary distinction is load-bearing — one governs what SecuritySpy records, the other what Home Assistant considers a Detection Episode.

---

### 5.6 Device and Entity Model

**Description.** What makes eleven cameras legible instead of eleven `192_168_0_2_4` entities with manufacturer "Generic." One Hub Device per SecuritySpy Server, one Camera Device per camera beneath it, correctly named from SecuritySpy, related in the device registry. Identity is derived from the server UUID and camera number — never hostname, IP, or camera name — because identity decisions are effectively permanent and changing them orphans every customization a user has made. Realizes UJ-3.

**Functional Requirements:**

#### FR-19: Hub and camera device hierarchy

Cameras appear as devices beneath a single server device.

**Consequences (testable):**
- One Hub Device is created per Config Entry.
- One Camera Device is created per camera known to the SecuritySpy Server, each related to the Hub Device as its parent.
- The Hub Device is typed as a service rather than a physical device.

#### FR-20: Correct naming without manual intervention

Devices and entities are correctly named on creation. Realizes UJ-3.

**Consequences (testable):**
- Camera Devices carry the camera name from SecuritySpy.
- No device is named after an IP address, and none reports manufacturer "Generic."
- A camera renamed in SecuritySpy is renamed in Home Assistant without breaking entity IDs or user customizations.
- Entity names derive from device name plus entity function, with no hardcoded names.

#### FR-21: Stable identity

Entity and device identity survives renames, address changes, and reconfiguration.

**Consequences (testable):**
- Identity derives from the SecuritySpy Server UUID and camera number.
- Changing the server's hostname, IP, or port does not create duplicate devices or orphan entities.
- Renaming a camera in SecuritySpy does not change any unique identifier.
- Every entity has a unique identifier stable across restarts.

#### FR-22: Camera entities disabled by default

Live video entities exist but do not appear unless the user enables them.

**Consequences (testable):**
- Each Camera Device exposes a live video entity, disabled by default.
- A fresh install adds no enabled camera entities and does not disturb an existing ONVIF setup.
- Enabling one produces working live video.

#### FR-23: Diagnostic sensors

A Home Assistant user can see server and camera health.

**Consequences (testable):**
- The Hub Device exposes server health values including CPU usage, memory pressure, camera count, and certificate expiry, categorized as diagnostic.
- Each Camera Device exposes per-camera health including current frame rate, data rate, and last error, categorized as diagnostic.
- Diagnostic entities do not appear among a device's primary controls.

#### FR-24: Server update availability

A Home Assistant user is informed when a SecuritySpy update is available.

**Consequences (testable):**
- The Hub Device reports whether a SecuritySpy update is available and the version offered.
- The integration does not install updates in v1.

---

### 5.7 Setup and Connection

**Description.** Everything happens in the UI: host, port, credentials, done. HTTPS is supported from day one — the reference server runs it with plain HTTP redirecting — and because SecuritySpy certificates are issued for dynamic-DNS hostnames, users connecting by LAN IP need a verification toggle rather than a failure. The integration also checks what the configured SecuritySpy user is actually permitted to do, and does not create controls that would permanently fail. Realizes UJ-3.

**Functional Requirements:**

#### FR-25: UI configuration flow

A Home Assistant user can add a SecuritySpy Server entirely through the UI. Realizes UJ-3.

**Consequences (testable):**
- Setup requires no YAML.
- The flow accepts host, port, username, and password.
- Credentials are validated against the server before the Config Entry is created.
- Distinct, actionable errors are shown for unreachable host, bad credentials, and insufficient permissions.
- A SecuritySpy Server already configured cannot be added twice.

#### FR-26: HTTPS with optional verification

A user can connect over HTTPS, including where the certificate does not match the address used. Realizes UJ-3.

**Consequences (testable):**
- Both HTTP and HTTPS are supported.
- Certificate verification is toggleable, and the consequence of disabling it is stated in the UI.
- Connecting by LAN IP to a server whose certificate is issued for a dynamic-DNS hostname succeeds with verification disabled and fails with a clear message when enabled.

#### FR-27: Reauthentication

A user is prompted to re-enter credentials when they stop working, rather than the integration failing silently.

**Consequences (testable):**
- Persistent authentication failure starts a reauthentication flow.
- A single transient failure does not — reauthentication triggers only after a documented number of consecutive failures. `[ASSUMPTION: three consecutive authentication failures; the precise count is an architecture decision, but it is bounded and documented, not "eventually."]`
- Completing reauthentication restores operation without removing the Config Entry.

#### FR-28: Permission-aware entity creation

The integration creates only controls the configured SecuritySpy user can actually use. Realizes UJ-3.

**Consequences (testable):**
- Permissions are checked before entity creation.
- Arming controls are omitted when the user lacks arming permission; capture-dependent entities are omitted when the user lacks file access.
- When a capability is omitted for lack of permission, a repair issue names the missing permission.
- No entity is created that is permanently unavailable due to permissions.

#### FR-29: Reconfiguration

A user can change connection details without losing history.

**Consequences (testable):**
- Host, port, and credentials are changeable after setup.
- Reconfiguring preserves devices, entities, and their recorded history.

---

### 5.8 Resilience

**Description.** The requirement that separates an integration people keep from one they uninstall. SecuritySpy will restart, the Mac will reboot, the network will drop, and Home Assistant will be upgraded — and none of these may require human intervention. The Event Stream is lossy and has no replay, so recovery means reconciling against the Capture History rather than hoping nothing was missed. Realizes UJ-4.

**Functional Requirements:**

#### FR-30: Unavailability, not staleness

Entities report unavailable when their data cannot be trusted. Realizes UJ-4.

**Consequences (testable):**
- When the SecuritySpy Server is unreachable, its entities report unavailable rather than retaining last-known values.
- When a single camera goes offline while the server remains reachable, only that Camera Device's entities become unavailable.
- Camera offline is treated as unavailability, not as an error condition requiring user action.

#### FR-31: Automatic recovery

The integration recovers from connection loss without user action. Realizes UJ-4.

**Consequences (testable):**
- Event Stream loss is detected via the absence of the server's periodic heartbeat, within a bounded and documented time. `[ASSUMPTION: detection within three missed heartbeats — roughly thirty seconds, given the measured ten-second cadence.]`
- Reconnection is attempted with backoff, indefinitely.
- On reconnection, state is reconciled against the Capture History (FR-3).
- Recovery requires no Home Assistant restart, no Config Entry reload, and no re-authentication.
- The integration survives a SecuritySpy restart, a Mac reboot, a network drop, and a Home Assistant upgrade.

#### FR-32: Disciplined logging

Connection problems are logged once, not continuously. Realizes UJ-4.

**Consequences (testable):**
- Loss of connection is logged once when it occurs.
- Subsequent retry attempts log at debug level.
- Recovery is logged once.
- A multi-hour outage does not produce a proportional volume of log entries.

#### FR-33: Clean teardown

A Config Entry can be unloaded and removed cleanly.

**Consequences (testable):**
- Unloading closes the Event Stream connection and cancels all polling.
- No task, connection, or timer survives unload.
- The Config Entry can be reloaded after unload without a restart.

---

### 5.9 Custom Model Support

**Description.** SecuritySpy can run a user-supplied CoreML model per camera and emit its outputs over the same Event Stream. No other Home Assistant camera integration surfaces user-supplied models at all. The integration treats Object Class as open data from day one — an integration that hardcodes three class names locks these users out permanently, and correcting it later means changing the event schema and breaking every automation built against it.

Two requirements here differ in confidence, deliberately. FR-34 is unconditional and cheap: never assume the vocabulary is three. FR-35 creates entities for discovered classes, and it depends on a payload shape that is undocumented — the published specification omits the feature entirely and the web client contains no reference to it. It is specified here as the intended behavior, gated on an empirical discovery spike.

**Functional Requirements:**

#### FR-34: Open classification vocabulary

The integration carries arbitrary Object Classes without modification.

**Consequences (testable):**
- Object Class is represented as open data throughout, never a three-value enumeration.
- An Object Class outside the three built-ins is parsed and carried without error, and does not disrupt built-in class handling.
- Adding support for a new Object Class requires no change to the event schema.

#### FR-35: Entities for Custom Model classes

A Custom Model user gets presence entities for the classes their model emits.

**Consequences (testable):**
- Object Classes emitted by a Custom Model are discovered from the Event Stream at runtime.
- A presence entity is created per discovered Object Class per Camera Device, following the same Detection Threshold and Detection Debounce as built-in classes.
- Entities for classes no longer emitted are not removed automatically during a session.
- Users without a Custom Model see no additional entities.

**Notes:** `[NOTE FOR PM]` FR-35 is **conditional on a discovery spike** confirming the Custom Model event payload shape. The spike must run before this FR is committed to an epic, and its own precondition is unverified: it requires a camera running a Custom Model, which the reference system does not currently have. **If the spike cannot run, or the payload proves unusable, FR-35 defers to v2 automatically — no decision meeting required** — and FR-34 alone ships, which still leaves Custom Model users able to write automations against the raw event. Flagged in §13.

---

### 5.10 Distribution and Adoption

**Description.** The integration installs from HACS as a custom repository, ships with two canonical blueprints, and is built to Home Assistant's published quality scale. The blueprints are v1 deliverables, not documentation afterthoughts: they are the automations most users want on day one, and they are executable proof of the entity design — if a blueprint is awkward to write, the entity model is wrong. Realizes UJ-3.

One constraint shapes this: HACS has no blueprint category, so blueprints cannot be HACS-managed or auto-updated. They ship in the repository with one-click import links.

**Functional Requirements:**

#### FR-36: HACS custom repository installation

A user can install the integration through HACS. Realizes UJ-3.

**Consequences (testable):**
- The repository satisfies HACS custom-repository requirements and installs without manual file copying.
- The integration appears in Home Assistant's Add Integration list after installation and restart.
- A minimum supported Home Assistant version is declared and enforced.

#### FR-37: Canonical blueprints

A user can import working automations without writing YAML. Realizes UJ-3.

**Consequences (testable):**
- Two blueprints ship: notify with a picture when a person is seen, and capture an image when a person is detected.
- Each is importable via a one-click link in the README.
- Each uses entity selectors filtered to this integration, never hardcoded entity IDs.
- Each carries a canonical source URL so users can re-import updates.
- Both are writable against the shipped entity model without attribute-name lore.

**Out of Scope:**
- Automatic blueprint updates. HACS does not manage blueprints; users re-import to update.

#### FR-38: Bronze quality scale compliance

The integration meets Home Assistant's Bronze quality scale rule set in full.

**Consequences (testable):**
- Every Bronze rule is satisfied or explicitly exempted with a stated reason, declared in the repository.
- Compliance is verified by Home Assistant's own tooling running in the project's CI, on every change.
- Config flow test coverage is complete, including every error and abort path.
- Documentation covers high-level description, installation, and removal.

#### FR-39: Silver gates announcement, not release

The integration releases at Bronze and announces publicly at Silver.

**Consequences (testable):**
- The HACS custom-repository release ships when Bronze is verified in CI (FR-38). Early adopters get it then; no forum announcement accompanies it.
- Public announcement — the Ben Software forum, the Home Assistant community forum — happens only when every Silver rule is satisfied or explicitly exempted, declared in the repository.
- At announcement, test coverage exceeds the Silver threshold across all integration modules, and unavailability logging (FR-32), entity unavailability (FR-30), and reauthentication (FR-27) satisfy their corresponding Silver rules.
- The behavioral Silver rules are FRs in this document regardless of tier timing; what Silver adds at announcement is chiefly the coverage bar.

**Notes:** The quality scale is formally a core-integration mechanism; no external body certifies a custom integration. The claim is "meets the Bronze and Silver rule sets, verified by our own tooling in CI" — not "is certified."

---

### 5.11 The API Library

**Description.** All SecuritySpy protocol knowledge lives in a standalone Python package on PyPI, separate from the integration. This is required by the quality scale, but it is also the durable contribution: as §2 establishes, nobody maintains a reusable SecuritySpy library, and that is the unoccupied ground.

It is also a sequencing constraint. Retrofitting a library after writing protocol parsing inside an integration is a large, thankless refactor that blocks Bronze — so the library comes first.

**Functional Requirements:**

#### FR-40: Standalone published library

The SecuritySpy API client is a separately published package.

**Consequences (testable):**
- The library is published on PyPI under an OSI-approved license, from a public repository, built in CI from source.
- Published versions correspond to tagged releases.
- The integration depends on it as an ordinary versioned dependency and contains no SecuritySpy protocol parsing of its own.
- The library is usable independently of Home Assistant, with no Home Assistant imports.

#### FR-41: Async, typed, injectable

The library is built to the constraints that keep the highest quality tiers reachable.

**Consequences (testable):**
- The library is fully async.
- It accepts an HTTP session provided by the caller rather than creating its own.
- It ships type information and passes strict type checking.

#### FR-42: Credential-safe diagnostics

Neither the library nor the integration exposes credentials in diagnostics or logs.

**Consequences (testable):**
- Diagnostic output redacts usernames, passwords, and authentication tokens, including per-camera device credentials returned by SecuritySpy's settings endpoints.
- Settings payloads are never logged, including at debug level.
- Credentials do not appear in error messages or stack traces.

**Notes:** FR-42 is not hypothetical. SecuritySpy's settings endpoint returns per-camera device credentials in plaintext to any authenticated web-server user, and research observed a full URL including a password echoed into logs by an external tool. See §11.2.

---

## 6. Non-Goals (Explicit)

- **Not a video transport.** ONVIF works; this integration is not a replacement for it. Camera entities exist, disabled by default.
- **Not an image interpreter.** No scene description, package detection, or face recognition. SecuritySpy classifies into three buckets; richer meaning comes from whatever the user points at the Latest Capture image.
- **Not the downstream pipeline.** The webhook, the vision agent, and the notification are the user's to compose in ordinary automations.
- **Not a SecuritySpy configuration manager.** Arming and detection tuning only. Not storage, schedules, users, network, or recording configuration.
- **Not a privacy policy.** Per-Camera-Device controls are exposed; policy is the user's to compose. Indoor cameras get no special treatment.
- **Not a multi-server manager.** One SecuritySpy Server per Config Entry in v1.
- **Not a competitor to HomeHelper.** HomeHelper is a vendor bridge, not a rival; users may run both, and this integration must not assume it is the only client.
- **Not committed to Home Assistant core.** Building to the quality scale keeps a core submission possible; nothing here commits to one.

## 7. MVP Scope

### 7.1 In Scope

- Observation Record: per-class last-seen timestamps, restart-correct and self-healing (FR-1…FR-4)
- Live detection: per-class presence, Classification Events with Peak Confidence and captured-file reference, trigger events with decoded reasons, motion with independent timeout, configurable tuning (FR-5…FR-8, FR-43)
- Latest Capture image with timestamp state and Object Class; download-latest-recording service (FR-9…FR-11, FR-44)
- Arming: three independent modes, transient override writes from the controls plus an explicit schedule-assignment action, bidirectional state for all writable controls, read-only schedule visibility, camera enable (FR-12…FR-16)
- Detection Trigger and sensitivity controls per Object Class per camera; default-install trap detection (FR-17, FR-18, FR-45)
- Hub and Camera Device model with stable identity, correct naming, diagnostics, update signal (FR-19…FR-24)
- UI config flow with HTTPS, verification toggle, reauthentication, permission-aware entity creation, reconfiguration (FR-25…FR-29)
- Resilience: unavailability, automatic recovery, disciplined logging, clean teardown (FR-30…FR-33)
- Open classification vocabulary (FR-34); Custom Model entities gated on a spike (FR-35)
- HACS custom repository, two blueprints, Bronze in full at release, Silver gating public announcement (FR-36…FR-39)
- Standalone async typed API library on PyPI with credential-safe diagnostics (FR-40…FR-42)

### 7.2 Out of Scope for MVP

- **Capture archive browsing** via Home Assistant's media browser. Wanted, and more tractable than expected. Deferred to v2 because v1 delivers value without it. `[NOTE FOR PM]` Emotionally load-bearing — revisit if the schedule allows.
- **Arbitrary-window clip extraction.** A genuine differentiator no other Home Assistant camera integration offers. Deferred: it carries a disk-fill hazard, since generated clips persist on the server until deleted, and v1's priority is reaching Bronze and shipping. `[NOTE FOR PM]` Strongest v2 candidate.
- **Audio.** SecuritySpy documents AAC on its stream endpoint and demonstrably serves AAC elsewhere, but no audio track was negotiated in testing and every reference camera sources G.711. Unresolved rather than impossible — do not promise it, do not rule it out.
- **PTZ control and manual trigger.** Services, not entities. Deferred.
- **Latest clip as an entity**, discovery, repair issues beyond permissions and the default-install trap (FR-45), full translations, capture tagging.
- **Multi-server support.** The identity scheme leaves room; the feature is not built.
- **Gold and Platinum quality tiers.** Platinum's requirements are cheap if treated as library design constraints from the start (FR-41), so the tier stays reachable without being committed.
- **HACS default store listing.** Requires a merged brands PR and a review the HACS documentation warns can take months. Post-launch milestone, not a launch gate.
- **Destructive and remote-execution endpoints.** SecuritySpy exposes capture deletion and shell/shortcut execution. Explicitly out.

## 8. Success Metrics

**Primary**

- **SM-1: The question is answerable.** "Has anyone been in the driveway today?" is answered from Home Assistant alone, per camera, per Object Class, and remains correct after a Home Assistant restart. Validates FR-1, FR-2, FR-3.
- **SM-2: An end-to-end narrated alert runs in production.** At least one automation runs continuously on the reference system: detection → Latest Capture image → downstream analysis → a notification a human would want to read. Validates FR-6, FR-9, FR-10.
- **SM-3: Both blueprints work unmodified.** A user imports each canonical blueprint and gets working behavior without editing YAML, reading source, or knowing attribute names. Validates FR-37, and serves as the falsifiable test of the entity design.
- **SM-4: Eleven cameras, zero manual renaming.** All cameras on the reference system appear as correctly-named Camera Devices under one Hub Device on first setup. Validates FR-19, FR-20.

**Secondary**

- **SM-5: Someone else installs it successfully without help.** At least one user other than the builder completes installation and setup without asking a question. Validates FR-25, FR-36.
- **SM-6: Quality scale verified in CI.** Bronze rules pass in continuous integration before release; Silver before public announcement. Validates FR-38, FR-39.
- **SM-7: Survives the four disruptions unattended.** A SecuritySpy restart, a Mac reboot, a network drop, and a Home Assistant upgrade each occur without requiring a Home Assistant restart or manual recovery. Validates FR-30, FR-31.
- **SM-8: ONVIF untouched.** The existing ONVIF video setup continues working unchanged after installation. Validates FR-22.
- **SM-9: The library is independently usable.** The API Library is installable from PyPI and usable in a script with no Home Assistant present. Validates FR-40, FR-41.

**Counter-metrics (do not optimize)**

- **SM-C1: Entity count per camera.** More entities is not better. Every entity must answer a question a user actually asks; diagnostics stay categorized and video stays disabled by default. Counterbalances SM-4 and the breadth of §5.6.
- **SM-C2: Detection sensitivity.** Do not tune the Detection Threshold down to maximize detections. A presence sensor that fires on noise is worse than one that misses a marginal detection, because the Observation Record corrects misses on the next reconciliation and cannot correct false positives a user has already been notified about. Counterbalances SM-2.
- **SM-C3: Feature count at v1.** Do not expand scope to differentiate. The predecessor died of maintainer fatigue; shipping a smaller surface that reaches Bronze beats a larger one that never releases. Counterbalances SM-6 and §7.2's deferrals.
- **SM-C4: Adoption.** Do not optimize for install count. The engaged population is small — on the order of one to two hundred — and chasing growth would trade durability for reach in a community that has already been burned by an integration disappearing. Counterbalances SM-5.

---

## 9. Competitive Position

Three things occupy adjacent ground, and none occupies this one.

**`briis/securityspy`** — the original, archived September 2024 (§2). Exposed classification as an attribute on a motion sensor, which made it awkward to automate against and meant nothing survived a restart. It proved demand and died of maintainer fatigue.

**`JoshADC/securityspy`** — an active fork, releasing as recently as April 2026, with a small user base. It added real things: schedule presets, camera enable/disable, and detection score sensors. But it is a continuation of 2020-era code — it dropped the shared library entirely and parses XML inline, it is not in the HACS default store, it carries no quality-scale commitment, and it has no Observation Record. The honest framing is not that nobody else exists; it is that what exists is a single-maintainer fork with the same structural fragility that killed its parent.

**HomeHelper** — the vendor's own Mac application, free, actively maintained, bridging SecuritySpy to both HomeKit and Home Assistant. Its limitation is architectural rather than incidental: the rules live in HomeHelper, not in Home Assistant. Users get side effects, not entities — nothing to build dashboards, history, templates, or their own automations against — and it requires a Mac application running continuously. It is a bridge, not a rival, and users may run both.

**The unoccupied ground** is a native entity model plus a maintained library. No prior effort offers an Observation Record, and none has left behind a reusable SecuritySpy Python package. There is no technical moat — the API is public, if substantially undocumented — so the differentiator is execution: mapping the undocumented surface, building to the quality scale from the start, and still being here in three years.

## 10. Constraints and Guardrails

### 10.1 Safety and Privacy

- The integration holds **no privacy opinion**. Per-Camera-Device arming and Detection Trigger controls are exposed; policy is the user's to compose. Indoor cameras receive no special treatment.
- Credentials must never reach logs, diagnostics, or error messages (FR-42). This is a live hazard, not a precaution — see the FR-42 note on SecuritySpy's plaintext settings payloads.
- Documentation must describe configuring a least-privileged SecuritySpy user for the integration.
- Destructive capabilities SecuritySpy exposes — capture deletion, shell and shortcut execution — are out of scope entirely.

### 10.2 Cost and Sustainability

- **Maintainer fatigue is the primary risk to this product**, evidenced by the predecessor. Scope discipline (SM-C3), quality-scale automation in CI (FR-38), and the library split (FR-40) are the mitigations. None eliminates it.
- Adoption creates obligation. SM-C4 exists because growth is not the goal.
- **Polling cost must scale sanely with camera count.** The reference system has eleven cameras and three Object Classes; a naive implementation issues thirty-three requests per cycle. The Observation Record must not impose load proportional to that product.

### 10.3 Coexistence

- Running alongside ONVIF is the **expected topology, not a failure mode**. Home Assistant cannot merge devices across integrations, so a user running both sees two devices per physical camera. Camera entities disabled by default (FR-22) make the duplication mostly invisible.
- The integration must not assume it is SecuritySpy's only client. HomeHelper, the vendor's iOS app, and the web client may all be connected concurrently.

## 11. Cross-Cutting NFRs

### 11.1 Performance

- Detection latency from SecuritySpy classifying to Home Assistant firing a Classification Event: within a few seconds, dominated by Detection Debounce rather than transport.
- Classification Signal reduction: approximately 190:1 in the measured reference case (FR-6). Per-signal state machine writes are a defect.
- Observation Record polling must not scale as cameras × classes in request count (§10.2).
- Health reconciliation must prefer cheap endpoints; the difference between the light and heavy status endpoints on the reference server is roughly 794 bytes versus 27 KB.

### 11.2 Security

- Credential redaction in all diagnostics and anonymized output (FR-42).
- Settings payloads never logged at any level.
- Certificate verification on by default, disabling it an explicit user choice with stated consequence (FR-26).
- Least-privileged SecuritySpy user documented.

### 11.3 Reliability

- No user-visible failure mode requires a Home Assistant restart (FR-31).
- Persistent state derives from the Capture History, never from Event Stream accumulation alone. The stream is lossy with no replay; it is a latency optimization, not a source of truth.
- Motion clearing must not depend on SecuritySpy signalling motion end (FR-7) — measured as unreliable to the point of never firing on some cameras.

### 11.4 Observability

- Connection loss and recovery logged once each; retries at debug (FR-32).
- Diagnostics downloadable from the Config Entry, credential-redacted.
- Errors distinguish transient failure, authentication failure, and permanent incompatibility, so Home Assistant retries what is retryable and stops on what is not.

### 11.5 Compatibility

- A minimum supported SecuritySpy version is declared and enforced at setup, failing with a clear message rather than misbehaving. `[ASSUMPTION: The minimum is SecuritySpy 6.x, since the Observation Record depends on the version-6 JSON API. The reference server runs 6.20; the earliest 6.x release carrying the required endpoints has not been verified.]`
- A minimum supported Home Assistant version is declared (FR-36).
- Identity and naming schemes are treated as permanent; changing them orphans user customizations (FR-21).

---

## 12. Release Shape

Sequencing, not dates. The ordering constraints are real; the grouping is a starting point for epic planning.

**Phase 0 — Library first.** The API Library (FR-40, FR-41, FR-42) before integration code, for the sequencing reason stated in §5.11: retrofitting it later is a large refactor that blocks Bronze. The library owns stream parsing, capture-list decoding, permission decoding, and the diagnostics anonymizer.

**Phase 1 — Connect and model.** Config flow, HTTPS, permission-aware setup, device hierarchy, naming, stable identity, availability (FR-19…FR-31). Nothing user-facing works before this, and identity decisions made here are permanent.

**Phase 2 — The headline.** Observation Record, Latest Capture image, download service (FR-1…FR-4, FR-9…FR-11, FR-44). This is the product; everything before it is scaffolding. **Spike gate, before Phase 2 commits:** confirm when SecuritySpy writes classification against a Capture (Open Question 3) — a short probe against the live reference server that determines how fresh FR-2 and FR-3 can honestly be.

**Phase 3 — Live detection.** Presence, Classification Events, trigger events, motion timeout, tuning (FR-5…FR-8, FR-43). Depends on Phase 2 for reconciliation to correct against.

**Phase 4 — Control.** Arming, camera enable, Detection Triggers, sensitivities, default-install trap detection (FR-12…FR-18, FR-45).

**Phase 5 — Ship.** Blueprints, HACS packaging, Bronze verification in CI, then Silver (FR-36…FR-39). Blueprints are also the design test: awkward blueprint, wrong entity model — so an early draft against the Phase 3 entity surface is worth more than a polished one at the end.

**Spike, before Phase 3 commits:** the Custom Model payload shape, gating FR-35 (which auto-defers to v2 if the spike cannot run).

## 13. Open Questions

1. **Custom Model event payload shape.** Undocumented; the published specification omits the feature and the web client has no reference to it. Gates FR-35. Requires an empirical spike against a camera running a Custom Model. *Blocking for FR-35 only.*
2. **Observation Record lookback window.** How far back to query (FR-4). Trades startup cost against empty values on quiet cameras.
3. **Is classification written at capture close or later?** Determines whether the Observation Record can serve near-real-time needs or only reconciliation, and whether FR-11 lags FR-9 by a poll. *Blocking for Phase 2 — carries a spike gate in §12. A short probe against the live reference server, runnable now.*
4. **Observation Record polling strategy.** Naive polling is cameras × classes requests per cycle (§10.2). Batching, or polling only after a recording completes, are candidates. Architecture decision.
5. **Default Detection Threshold and Detection Debounce.** Provisionally 70% and a small consecutive-frame count; needs tuning against real footage before release. Stakes are reduced by the Observation Record correcting a mistuned live threshold on the next reconciliation.
6. **Do per-class and arrival/departure triggers fire once enabled?** SecuritySpy's per-class trigger settings are off by default; whether enabling them produces the corresponding trigger signals is testable now and determines whether arrival/departure detection is viable later.
7. **Why was ONVIF abandoned on the reference system?** The closest prior art in the builder's own environment; the failure mode is a requirement. SecuritySpy itself speaks ONVIF to these cameras, so whatever failed was in Home Assistant's ONVIF integration or in double-consuming streams.
8. **Minimum supported SecuritySpy version.** Assumed 6.x (§11.5); the earliest release carrying the required endpoints is unverified.
9. **Should the builder contact the active fork's maintainer?** Not a product requirement, but competing head-on with the only active maintainer in a community of roughly a hundred people is worth a deliberate decision rather than a default.
10. **Media browser and clip extraction — v2, or pulled forward?** Both deferred (§7.2), both wanted, both flagged as emotionally load-bearing.
11. **Resource-scoped auth tokens.** SecuritySpy supports tokens that grant access to a single resource without revealing credentials — the designed answer to credentials leaking through stream URLs into logs. But token generation appears to be GUI-only and the format is unverified. v1 uses username/password with FR-42's redaction discipline; token support is worth investigating for the camera-entity path, where credential-bearing URLs are handed to external processes.

## 14. Assumptions Index

Every `[ASSUMPTION]` in this document, surfaced for confirmation:

1. **§5.2 (FR-8)** — Default Detection Threshold is 70% and Detection Debounce is a small consecutive-signal count. Research floats ~70 explicitly as provisional and states correct values are scene-dependent. Open Question 5.
2. **§5.7 (FR-27)** — Reauthentication triggers after three consecutive authentication failures; the count is an architecture decision, but bounded and documented.
3. **§5.8 (FR-31)** — Event Stream loss is detected within three missed heartbeats (~30 seconds at the measured 10-second cadence).
4. **§11.5** — Minimum supported SecuritySpy version is 6.x, based on the Observation Record's dependency on the version-6 JSON API. The reference server runs 6.20; the earliest sufficient 6.x release is unverified. Open Question 8.

Two further inferences worth naming, drawn from research rather than assumed outright:

5. **§8 (SM-C4)** — The engaged user population is on the order of one to two hundred. This is extrapolated from repository stars, forks, and forum thread participation, not measured; no per-repository install statistics are obtainable for non-default HACS repositories. The PRD deliberately cites no larger figure.
6. **§5.10 (FR-37)** — Blueprints cannot be HACS-managed, since HACS has no blueprint category. One-click import via Home Assistant's import redirect is the mechanism, and auto-update is explicitly not promised.
