# Adversarial Review — ARCHITECTURE-SPINE.md (ha-securityspy, 2026-08-09)

**Method:** For each finding, two units one level below the spine are constructed that each obey every AD and convention literally, yet produce incompatible builds. Every pair is a hole; each gets a proposed AD fix.

**Verdict:** The spine's layer boundaries and wire-protocol containment are strong, but the *shared data shapes and merge semantics between layers are almost entirely unspecified* — the coordinator's data contract, the push/poll merge rule, availability semantics, and the class→key slug rule are all places where two compliant teams will collide.

---

## F1 (CRITICAL) — The coordinator data contract does not exist

**Pair:** library team vs coordinator team vs any two platform teams.

AD-4 mandates one coordinator fed by `async_set_updated_data()`, but nothing anywhere defines *what object* the coordinator holds. The library team, obeying "frozen dataclasses, raw dicts never cross the boundary," ships immutable `Camera`/`Capture` models. The coordinator team must merge push-plane episodes with poll-plane captures into something mutable-ish and camera-addressable, so it invents a shape — say `dict[str, CameraState]`. Meanwhile `sensor.py`'s author reads the spine, sees "thin declarative projections of coordinator data," and writes `value_fn=lambda data: data.cameras[num].last_seen[cls]`, while `binary_sensor.py`'s author writes `data[num].episodes[cls].open`. Both are compliant. Neither compiles against the other's assumption, and neither compiles against whatever the coordinator team actually built. Downstream story agents will each hallucinate a different shape.

A sub-collision hides inside: **camera_number's type is never pinned.** The wire uses string numbers (`cams=` list, AD-10), AD-5 interpolates it into f-strings (works for both int and str), and dict keys will be int in one module and str in another. `data["3"]` vs `data[3]` is a silent KeyError factory.

**Fix — new AD-15:** Define a typed `SecuritySpyData` container owned by `coordinator.py` (integration repo): fields, keying (`cameras: dict[int, CameraState]` — camera_number is `int` everywhere in Python, rendered as decimal string only at wire/unique-ID boundaries), and the exact per-camera state fields (per-class last-seen, open episodes, latest capture, control states, health). Entities may read only this container. Library models are inputs to it, never exposed raw to platforms.

## F2 (CRITICAL) — Push and poll both write "last seen"; no merge rule, so two owners of one value

**Pair:** coordinator's stream-callback path vs its reconciliation path (or: episode consumer vs caplist consumer, if split across stories).

AD-1 says the push plane "may only advance state the next poll would confirm." AD-3 delivers episodes (push) that end with a timestamp; AD-10 delivers caplist rows (poll) with timestamps. Both legitimately produce `last_human_seen`. Implementation A: poll unconditionally overwrites (compliant — "poll is the only truth"); result: a just-fired episode's timestamp gets *rewound* by a reconciliation cycle whose caplist row hasn't landed yet (classification-write timing is explicitly an open question, Deferred §3). Implementation B: take `max(push, poll)` (compliant — push "advances"); result: a bogus future-skewed push timestamp can never be corrected by poll, violating AD-1's spirit. Both readings satisfy the letter. The same ambiguity applies to Latest Capture (image.py) advanced by `FILE` events vs caplist.

**Fix — tighten AD-1:** One merge function, in `coordinator.py`, the only writer of persistent fields: poll establishes a baseline watermark; push may set a value only if newer than the current value AND within a sanity horizon of now; on every reconciliation, poll values replace push values whose timestamps are ≤ the poll window's coverage, and push values newer than the window's end survive until the next cycle. Name the function in the AD so stories cite it.

## F3 (HIGH) — Availability has two compliant definitions

**Pair:** any platform module vs any other; also adapter vs HA's coordinator default.

AD-11: "the adapter translates [stream signals] to entity availability." AD-4: standard `DataUpdateCoordinator`, whose built-in `available` semantics key off `last_update_success` — a *poll*-plane notion. Team A implements availability as stream-connected (per AD-11 literally): stream drops → all entities unavailable, even though polls still succeed and AD-1 says poll is the truth. Team B leans on coordinator default: stream drops silently, entities stay available showing stale push-driven state — the predecessor's exact defect. Also unanswered: per-camera availability (SecuritySpy reports per-camera connectivity) vs server-wide, and whether *control* entities (switches — they use the poll/write plane, not the stream) should go unavailable on stream loss at all.

**Fix — new AD-16:** Availability model: server-reachability (poll failures past a threshold) gates *all* entities; stream state gates only push-driven entities (binary_sensor, event), exposed additionally as a hub `binary_sensor` diagnostic; per-camera connected flag from status polls gates that camera's device entities. Implemented once in `entity.py` base classes; platform modules never override `available`.

## F4 (HIGH) — Open-string Object Class (AD-9) meets "class embedded in entity key": no slug rule → unique-ID collisions and churn

**Pair:** library reducer/event emitter vs entity-key generation; or sensor.py vs event.py.

AD-9 makes class an arbitrary string ("Delivery Truck", "ANIMAL", "cat/dog"). Conventions embed it "lowercase" in permanent keys: `last_{class}_seen`. Slugification is unspecified: one module does `.lower()`, another `.lower().replace(" ", "_")`, a third uses HA's `slugify`. Consequences, all while compliant: (a) `f"{uuid}_{n}_last_delivery truck_seen"` — an illegal/unstable unique ID; (b) two custom classes ("My-Cat", "my cat") slug to the same key → **unique-ID collision**; (c) event payloads carry the raw class while entity keys carry the slug, so blueprints (FR-37) matching payload strings against entity keys silently miss. Keys are "permanent once released," so a later fix is a breaking migration.

**Fix — tighten AD-9:** The library exports one canonical `class_slug()` (lowercase, `[a-z0-9_]`, collision behavior defined) used for *every* key/ID; event payloads carry both `object_class` (raw, display) and `object_class_slug`; entity keys use the slug only; hub entity keys are drawn from a reserved namespace so `{uuid}_{key}` can never collide with `{uuid}_{n}_{key}` (e.g. forbid hub keys matching `^\d+_`).

## F5 (HIGH) — "3 consecutive auth failures" has no owner; stream and poll clients each count

**Pair:** `stream.py` vs `client.py` (library), and both vs the adapter.

AD-6 puts the typed exceptions in the library and the mapping in the adapter, but the *counter* is placed nowhere. Compliant build A: library's stream client counts its own 401s across reconnects and surfaces a "hard auth" signal after 3. Compliant build B: adapter counts `SecuritySpyAuthError` from poll calls. Run together: a password change during a stream outage never reaches 3 on either counter (2 stream + 2 poll = 0 reauth), or both reach 3 and the adapter fires reauth while the stream keeps hammering with dead credentials. Also unspecified: what *resets* the counter (any success? per-plane success?).

**Fix — tighten AD-6:** The counter lives exclusively in the adapter (`__init__.py`/coordinator seam); it increments on `SecuritySpyAuthError` from *either* plane, resets on any authenticated success from either plane; the library never counts, never retries an auth failure, and the stream client suspends reconnect attempts on auth failure until the adapter tells it credentials changed (add that pause/resume signal to AD-11's callback contract).

## F6 (MEDIUM) — Options changes vs the injected reducer: reconfiguration semantics undefined

**Pair:** `config_flow.py` (options flow) vs library `episodes.py` / coordinator.

Conventions: options "applied via update listener without reload where possible." AD-3: threshold/debounce are "injected per camera per class" into a pure library reducer. When options change mid-flight, compliant choices diverge: recreate reducers (open episodes vanish → binary_sensors stick ON forever or snap OFF spuriously), mutate injected config live (reducer no longer "pure"/frozen-config), or reload the entry anyway (violates "without reload where possible"?). Additionally, the canonical *option key names* the flow writes and the coordinator reads are never listed — two stories will pick `detection_threshold` vs `threshold_pct`.

**Fix — new AD-17:** Enumerate the canonical options schema (keys, types, per-camera override nesting) in the integration's `const.py` as the single source; define reducer reconfig semantics in the library: `reducer.update_config()` closes any open episode whose class config changed (emitting a normal close) and applies new config to subsequent signals; only connection-data changes reload the entry.

## F7 (MEDIUM) — `capture_ref` is a payload key with no definition; image.py and services.py will disagree

**Pair:** `event.py`/payload producer vs `services.py` (`download_latest_recording`) and `image.py`.

The conventions table declares `capture_ref (nullable)` but nothing defines what it is — a file path? caplist row id? URL? AD-13 forbids credential-bearing URLs outside the library, so if one team makes it a `getfile` URL it violates AD-13 only *arguably* (no credentials embedded — compliant!) while another makes it an opaque token only `client.py` can resolve. The download service and the image platform then can't consume the event producer's ref.

**Fix — tighten conventions + AD-2:** `capture_ref` is a library-defined opaque string (documented format, no credentials, no absolute URL), minted only by the library and resolvable only via `client.download(capture_ref)` / `client.image(capture_ref)`; the integration treats it as a token.

## F8 (MEDIUM) — `trigger_reason` "decoded str" vocabulary is unpinned; blueprints are a second consumer

**Pair:** library bitmask decoder vs blueprint authors (FR-37) and `event.py` `event_types`.

AD-2 puts bitmask decoding in the library; the convention says `trigger_reason` is a "decoded str, never bitmask" — but the string vocabulary ("motion" vs "Motion" vs "MOTION_DETECTED"), multi-bit handling (list? comma-joined?), and the event entity's `event_types` list are all unspecified. Blueprints ship in the integration repo and hard-match these strings; a library rename is then a silent blueprint break with no type checker crossing that boundary.

**Fix:** Add to AD-2/conventions: the library exports the closed set of trigger-reason strings as constants (lowercase snake_case), multi-bit decodes to `list[str]`, and the integration's `event_types` and blueprint trigger strings must be generated/imported from those constants — never retyped.

## F9 (LOW) — "The adapter schedules polls" names two modules

AD-10 says the adapter schedules reconciliation; AD-4 and the seed put scheduling in `coordinator.py`, but `__init__.py` is equally "adapter layer" and owns lifecycle — a stories-split could put startup hydration in `__init__` and debounce/fallback in `coordinator`, yielding two independent schedulers and double caplist fan-out after a reconnect-at-startup race. **Fix:** one sentence in AD-10: all reconciliation triggers funnel through a single scheduler object in `coordinator.py`; `__init__.py` only starts/stops it.

## F10 (LOW) — Camera platform is in the seed but in no AD or capability row

`camera.py` appears in the Structural Seed but no FR/AD governs it — stream proxying would touch credential-bearing URLs (AD-13) and per-camera streams (not the event stream, AD-11). A story agent will invent its transport. **Fix:** either delete it from the seed for v1 or add a capability row binding it to AD-13 (library-minted, credential-free proxy source only).

---

## Summary table

| # | Tier | Hole | Fix |
| --- | --- | --- | --- |
| F1 | Critical | No coordinator data contract; camera_number type unpinned | New AD-15: typed `SecuritySpyData`, `int` camera keys |
| F2 | Critical | Push and poll both own "last seen"/Latest Capture; no merge rule | Tighten AD-1: single watermark-merge function in coordinator |
| F3 | High | Availability definable two compliant ways | New AD-16: layered availability, implemented once in `entity.py` |
| F4 | High | Open class strings in permanent keys, no slug rule → ID collisions | Tighten AD-9: library `class_slug()`, dual payload fields, reserved hub-key namespace |
| F5 | High | Auth-failure counter has no owner across two planes | Tighten AD-6: adapter-owned cross-plane counter; stream pauses on auth failure |
| F6 | Medium | Options keys unnamed; reducer reconfig semantics undefined | New AD-17: canonical options schema + `update_config()` close-and-apply rule |
| F7 | Medium | `capture_ref` undefined; producers/consumers diverge | Library-minted opaque token, resolvable only via client |
| F8 | Medium | `trigger_reason` vocabulary/`event_types` unpinned; blueprints hard-match | Library-exported string constants; blueprints/event_types import, never retype |
| F9 | Low | Two "adapter" modules can both schedule polls | Single scheduler in `coordinator.py` |
| F10 | Low | `camera.py` ungoverned in seed | Bind to AD-13 or cut from v1 seed |
