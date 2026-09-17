# Epic 4 Context: The Observation Record

<!-- Generated from planning artifacts. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Deliver the project's headline feature: per Camera Device, the last time a human, a vehicle, and an animal were each seen, plus the Latest Capture image and a save-latest-recording service. Values derive from what SecuritySpy already wrote to disk (Capture History), never from events Home Assistant happened to be awake for, so they are correct right after a restart and recover detections that occurred while the integration was disconnected. This is the reason the project exists and the state that outlives the process observing it.

## Stories

- Story 4.1: Spike — when does SecuritySpy write classification to a capture?
- Story 4.2: Per-class last-seen timestamps
- Story 4.3: Correct immediately after a restart
- Story 4.4: Recover detections missed while disconnected
- Story 4.5: Latest capture as a fetchable image
- Story 4.6: Read the object classes on the latest capture
- Story 4.7: Save the most recent recording to a file

## Requirements & Constraints

- Each camera exposes exactly three observation timestamps (human, vehicle, animal), typed as timestamps so Home Assistant renders them as relative time and they work in automation conditions and templates.
- A class with no Capture in the queried window is **absent** — never zero, never the epoch, never the current time.
- After a restart with the server reachable, values are populated on the first data refresh without waiting for a new detection, and setup is not blocked on hydration.
- After a disconnection, the next reconciliation reflects any detections SecuritySpy recorded — no restart or Config Entry reload. Detections SecuritySpy never recorded (triggers off) are legitimately absent and documented as such, not treated as defects.
- Lookback is bounded and finite (7-day assumption); absent-value behavior applies when nothing falls in the window rather than scanning unbounded history.
- A refresh cycle issues at most one capture-history request per built-in class, batched across all cameras — never cameras × classes (33 requests is the failure case).
- The Latest Capture is served by Home Assistant at a URL that survives image updates and restarts; its state is the capture timestamp and is usable as a state trigger. On startup it reflects the newest existing capture, not an empty or restart-time value. Consumers need no direct reachability to the server.
- The Object Class set of the Latest Capture is readable alongside the image; empty (not absent/erroneous) when no classification was recorded, and arbitrary classes carry as ordinary strings.
- The save-recording service writes the most recent completed recording to a caller-supplied destination, deletes/modifies nothing on the server, and distinguishes user-input errors from operational failures with distinct, actionable, translated messages.
- The Latest Capture is not a sub-second signal (SecuritySpy completes a recording only after its ~96 s post-roll); nothing here may imply otherwise.

## Technical Decisions

- Entirely poll-plane (AD-1): Observation Record and Latest Capture values must be fully derivable from Capture History alone. Push may only advance state the next poll would confirm, never be its sole source. Hydrate from poll on startup; reconcile from poll on stream reconnect. The integration never assumes it is SecuritySpy's only client.
- One push-fed coordinator per Config Entry with `update_interval=None` (AD-4); all entity data comes from the frozen, typed `SecuritySpyData` container keyed by `int` camera number, and the coordinator is its sole writer (AD-15).
- All push/poll merges go through the single watermark merge function (AD-16): incremental push may only advance a timestamp (monotonic max-wins); a full poll reconciliation is authoritative and overwrites, including regressions such as captures deleted server-side.
- Reconciliation cycles run at startup (non-blocking), on the library's reconnect signal, debounced (~5 s) after a FILE stream event, and on a slow fallback interval (~10 min) (AD-10).
- Zero protocol knowledge in the integration (AD-2, AD-19): class-filtered `caplist` queries, bitmask/absolute-time decoding, and media fetch all live in `aiosecurityspy`; the integration constructs no endpoint URLs.
- Object Class is open string data end-to-end, with a single `class_slug()` normalization wherever a class name enters a permanent key (AD-9); unknown classes parse and carry without error.
- Identity and unique IDs follow AD-5 (server UUID + camera number); entity availability is the three-layer scheme computed once in the base entities from Epic 3, and stream loss alone does not make capture-history entities unavailable.
- Story 4.1 is a blocking spike gate for the epic's freshness claims: it must measure whether SecuritySpy writes classification at capture close or later, which decides how fresh the record can honestly be and whether the class set can lag the image by one poll. The epic proceeds regardless with the honest latency documented.

## UX & Interaction Patterns

No custom UI is authored — Home Assistant renders every surface from entity, device, config-flow, and service definitions. Observations must render as glanceable relative timestamps; the Latest Capture is an image entity whose timestamp state doubles as a trigger; the recording save is a service with per-cause validation errors. The standing design test applies: if a canonical blueprint for these is awkward to write, the entity model is wrong.

## Cross-Story Dependencies

- Story 4.4 consumes Epic 3's reconnect signal (reconciliation triggered on `reconnected`).
- Protocol surface is gated on library stories: 1.4 (class-filtered capture history + bitmask/time decoding), 1.9 (preview image and recording file fetch), 1.13 (server timezone), 1.15 (fractional-megabyte sizes); 4.5 and 4.7 cannot start before 1.9 lands.
- The coordinator, `SecuritySpyData` container, and base entities come from Epics 1–3.
- Epic 6's FR-45 closes the loop: it tells a user whose per-class triggers are off why their Observation Record is empty.