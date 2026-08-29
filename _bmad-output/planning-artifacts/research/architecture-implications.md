---
title: "Architecture Implications — HA SecuritySpy Integration"
status: draft
created: 2026-08-09
updated: 2026-08-09
inputs:
  - "securityspy-api-reference.md"
  - "briefs/brief-ha-securityspy-2026-08-09/brief.md"
  - "briefs/brief-ha-securityspy-2026-08-09/addendum.md"
---

# Architecture Implications

Design conclusions that follow from the API research. **Not a design document** — input to the architecture workflow. Each item states what the evidence forces, so the architecture phase can argue with it rather than rediscover it.

---

## 1. Data flow: push for latency, poll for truth

**The evidence.** `CLASSIFY` is a per-frame inference stream (191 events / 95 s, confidence swinging 4→100 for one subject). `MOTION_END` is frequently never sent. The event stream is a per-connection counter with no replay. But `caplist` **persists classification per capture** and supports **server-side class filtering**.

**The conclusion.** Two paths, different jobs:

| Path | Drives | Properties |
|---|---|---|
| `eventStream` | motion binary sensors, live detection, event entities | sub-second, lossy, no replay |
| `caplist` / `camStatus` poll | *last seen* sensors, image entity, availability | authoritative, survives restarts, self-heals |

**Never derive persistent state from the stream alone.** On startup, backfill from `caplist`. On reconnect, reconcile.

**HA shape.** `DataUpdateCoordinator` in `coordinator.py` with **no `update_interval`**, fed by `async_set_updated_data()` from both the stream and a periodic poll. (Per `docs/integration_fetching_data.md:180-184`. Note `unifiprotect` hand-rolls this in `data.py` — legacy, do not copy.)

---

## 2. Classification: binary sensors with hysteresis, not event-per-CLASSIFY

**The evidence.** §3.5 of the API reference — the raw signal is noisy per-frame inference.

**The conclusion.**
- Per-class **binary sensors** with a confidence threshold plus debounce/minimum-consecutive-frames.
- **One `event` entity fire per episode**, on threshold crossing, carrying *peak* confidence — not one per `CLASSIFY` (which would be ~190 fires per person).
- Threshold and debounce are **config-flow options**; correct values are scene-dependent.
- Mistuning is recoverable: `caplist`'s `o` bitmask is authoritative and corrects a bad live threshold on the next poll.

**Why per-class binary sensors rather than classification-as-attribute:** attribute triggers are second-class in HA — not discoverable in the UI editor, unusable as device triggers. This is what made `briis`'s `attribute: event_object` awkward.

---

## 3. The label vocabulary must be open

**The evidence.** Custom CoreML models emit arbitrary labels on the same event stream (§11).

**The conclusion.** The parser treats classification labels as **open data**, never an enum. v1 may create entities only for human/vehicle/animal, but the event schema must carry arbitrary labels from day one. Retrofitting means changing the event schema and breaking existing automations.

---

## 4. Arming is three-dimensional

**The evidence.** `ssSetSchedule?cameraNum=&schedule=&override=&mode=CMA` — mode is a concatenated letter string of three independent booleans; schedule is a user-definable weekly block set; override has 16 values.

**The conclusion.**
- **Not `alarm_control_panel`** — that is a single mutually-exclusive state machine and cannot represent three independent modes without a lossy 8→4 encoding.
- Three **`switch`** entities (continuous / motion / actions), `EntityCategory.CONFIG`.
- Schedule as a **dynamic `select`** populated from `schedule-list` — never a hardcoded enum, since users define their own.
- Override: `select`, or a service. Timed overrides ("armed for 2 hours") are genuinely useful in automations.

**Open question for architecture:** does the switch write `schedule=1` (Armed 24/7) / `schedule=0` (Disarmed 24/7), or use `override`? Writing schedules destroys the user's configured schedule; overrides are transient and probably correct for automation-driven arming.

---

## 5. Permissions gate entity creation

**The evidence.** `PERM_*` constants decode the per-camera `permissions` field (§9).

**The conclusion.** Pre-flight per camera; **do not create entities the user cannot use**. A permanently-unavailable PTZ entity is worse than none (precedent: `unifiprotect/alarm_control_panel.py:44-58`).

Map: `PERM_SCHED` → arm switches · `PERM_CAMCONTROL` → PTZ · `PERM_PTZSET` → preset-save · `PERM_FILES` → media/image · `PERM_TRIGGER` → trigger service · `PERM_AUDIORCV`/`SND` → audio.

Raise a **repair issue** naming the missing permission when a user expects a feature they cannot access — actionable, so it passes the repair-issue test.

**⚠ Amended 2026-08-29 — the mask is not static.** Live verification (§5.11) shows a camera that
is offline *loses* the capability bits it cannot currently satisfy — `PERM_AUDIORCV` and
`PERM_AUDIOSND` were observed dropping and returning on reconnect, confirmed by prediction. So
"pre-flight per camera and skip what the mask denies" is unsafe as written: a setup run while a
camera happens to be offline silently omits entities that should exist, and they reappear only
on a reload. Any pre-flight must read the mask **while the camera is online**, or treat an
absent bit on an offline camera as *unknown* rather than *denied*. Never cache the mask as a
property of the account.

---

## 5b. Disabled is a state, not an absence

**The evidence (§5.12).** Disabling a camera in SecuritySpy removes it from `++systemInfo`
entirely — `camera-list` shrinks and `server.camera-count` drops to match — while `++camStatus`
still reports it as `enabled:false, online:false, open:false, err:0`. An *unreachable* camera
reads differently: `enabled:true, online:false, err:64 "Host is down"`.

**The conclusion.** `++camStatus` is the **inventory of record**, because it is the only surface
that distinguishes the three cases the user cares about:

| user's situation | `++camStatus` | `++systemInfo` | what HA should say |
|---|---|---|---|
| camera working | `enabled:true, online:true` | present | normal state |
| camera unplugged or faulted | `enabled:true, online:false, err≠0` | present | `unavailable` — genuinely unknown |
| camera **disabled by the user** | `enabled:false, err:0` | **absent** | a deliberate off state, *not* `unavailable` |

Reporting a disabled camera as `unavailable` is misleading: `unavailable` means "cannot reach,
do not know", and a switched-off camera is a known, intentional state that the user chose. It
reads as a fault the user then goes looking for. Keep the device and its entities, and surface
"disabled" distinctly — `enabled` is exactly the signal needed, and story 1.10 already
implements the write that flips it, so the state is actionable and not merely informational.

Building the inventory from `++systemInfo` instead makes a disabled camera's device and
entities **disappear**, orphaning history and breaking automations that reference them — the
failure story 3.1 exists to prevent.

**`[ASSUMPTION]` — not verified.** A camera *deleted* from SecuritySpy is expected to vanish
from `++camStatus` too, which would make "absent from `camStatus`" the discriminator between
deleted and disabled. Testing it means deleting a real camera, which was not worth doing.
Until it is verified, do not build removal logic that depends on it.

Affects stories **2.3**, **2.7**, **3.1**, and **6.4**.

---

## 6. The observation record is the headline

**The evidence.** The stated requirement is *"know what people have been seen."* `caplist?filter=5|6|7` answers it in one request per class.

**The conclusion.** Per camera:

```
sensor.<cam>_last_human_seen      device_class: timestamp
sensor.<cam>_last_vehicle_seen    device_class: timestamp
sensor.<cam>_last_animal_seen     device_class: timestamp
```

Poll-derived, correct after restart. Reconstruct absolute time from `f` (folder date) + `s` (seconds since midnight).

**These are the primary deliverable**, not a by-product of motion sensing.

---

## 7. Entity inventory (v1 candidate)

Per camera, gated on permissions and capability:

| Platform | Entity | Source | Notes |
|---|---|---|---|
| `sensor` | last human / vehicle / animal seen | `caplist` poll | ⭐ headline; `device_class: timestamp` |
| `image` | latest capture | `getpreview` + newest `caplist` | state = capture timestamp |
| `binary_sensor` | motion | event stream + timeout | `device_class: motion` |
| `binary_sensor` | human / vehicle / animal detected | stream + threshold/debounce | |
| `event` | detection | stream, once per episode | peak confidence + file ref; **open labels** |
| `switch` | arm continuous / motion / actions | `ssSetSchedule` | `EntityCategory.CONFIG` |
| `switch` | trigger on human / vehicle / animal | `settings-cameras` `mcTriggerMotionH/V/A` | ⭐ no prior integration had this |
| `select` | schedule | `schedule-list` | dynamic options |
| `number` | motion / human / vehicle / animal sensitivity | `settings-cameras` | `EntityCategory.CONFIG` |
| `sensor` | last error, fps, data rate | `systemInfo` | diagnostic |
| `camera` | live stream | `++stream` RTSP | **disabled by default** — ONVIF coexistence |

Server/hub device: `update` (`new-version`), `sensor` cpu-usage / memory-pressure / camera-count / cert-expiry-days, `binary_sensor` archive-status.

**Deferred:** `media_source` browser (`caplist` + `getpreview` + `getfile`), `button` PTZ presets, download service, `setTags`.

---

## 7b. Media: the clip API is a differentiator

`++clip` generates an MP4 for an arbitrary time window (epoch start/end), and `getfile` honours HTTP Range. Together these make two things tractable that looked expensive:

**`media_source` browser** — `caplist` for listing (server-side class filtering), `getpreview` for thumbnails, `getfile` with Range for playback. Genuinely reachable; strong v2 candidate, possibly v1.

**`securityspy.get_clip(camera, start, end)` service** — produces a shareable MP4 of any incident window. Pairs directly with the detection events: "give me the 30 seconds around that human detection." **No other HA camera integration offers arbitrary-window extraction.** Worth v1 consideration purely as a differentiator.

Caveat: generated clips persist server-side until deleted. A service that generates clips should either clean up after itself or expose deletion, or it will silently fill the user's disk.

---

## 8. Identity and naming — decide once

- **Hub `identifiers`:** `(DOMAIN, systemInfo.server.uuid)`. Never hostname or IP.
- **Camera `identifiers`:** `(DOMAIN, f"{uuid}_{camera_number}")`. Never the name (user-editable). Do **not** fabricate MACs — SecuritySpy cameras may have none, so `connections` is unusable (a divergence from `unifiprotect`, which uses MAC-only `connections`).
- **`via_device`** on cameras → hub identifiers tuple.
- **Hub `entry_type`:** likely `DeviceEntryType.SERVICE` — SecuritySpy is software on a Mac, not an appliance.
- `_attr_has_entity_name = True`; `translation_key` on every description; icons in `icons.json`.

Unique-ID scheme and `has_entity_name` are effectively permanent — changing either orphans user customizations.

---

## 9. Connection handling

- **CR-only framing.** Split on `\r`. This is the likeliest single bug.
- **10 s heartbeat.** Absence → reconnect with backoff.
- **Log discipline:** first failure `ERROR`, subsequent `DEBUG`, recovery once `WARNING` (Silver `log-when-unavailable`).
- **Motion timeout** independent of `MOTION_END`.
- **On reconnect, reconcile via `caplist`** — the stream has no replay.
- `ConfigEntryNotReady` (transient) / `ConfigEntryAuthFailed` (after N failures, not the first 401) / `ConfigEntryError` (permanent, e.g. version too old), all with translation keys.

---

## 10. Security requirements

1. **Redact `username` / `password`** in diagnostics and the library anonymizer — `settings-cameras?format=json` leaks camera credentials.
2. **Never log settings payloads**, including at debug.
3. **HTTPS support in v1**, with a "verify SSL certificate" toggle — certs are issued for DDNS hostnames, so LAN-IP access fails verification.
4. Document the **least-privileged** SecuritySpy user for setup.

---

## 11. Library split

Bronze `dependency-transparency` requires the API client on PyPI, OSI-licensed, built in public CI, versions matching tagged releases. Platinum adds async and injected `aiohttp` session.

**Build the library first.** Retrofitting after writing protocol parsing inside the integration is a large, thankless refactor that blocks Bronze.

The library owns: CR-framed stream parsing, `caplist` field decoding, permission/PTZ/trigger bitmask decoding, the schedule model, and the diagnostics anonymizer.

---

## 11b. Settings writes are cheap and safe

Verified: a partial POST (`formData&cameraNum=N&<one key>=<value>`) does not disturb other fields. So `switch` and `number` entities backed by settings can write directly on state change — no read-modify-write, no lost-update race, no need to cache the whole page.

The library must handle the read/write asymmetry: JSON reads return `true`/`false`; writes require `1`/`0`. Encode this once in the client, not at each call site.

## 11c. Competitive position (for the PRD)

Two prior paths exist. Neither provides a native Home Assistant entity model.

| Capability | `briis/securityspy` | HomeHelper (vendor) | This integration |
|---|---|---|---|
| Status | Abandoned (2022 lib, dropped from HACS) | Maintained, free, v1.2 | — |
| Architecture | HA custom component | Separate Mac GUI app, pushes into HA | HA custom component |
| Motion | ✅ | ✅ | ✅ |
| AI classification | attribute only | ❌ | ✅ per-class entities |
| Observation record | ❌ | ❌ | ✅ |
| Camera stream | ✅ | ❌ | ✅ (optional) |
| Arm / disarm | ✅ switches | ❌ | ✅ three modes |
| AI trigger config | ❌ | ❌ | ✅ |
| Clip extraction | ❌ | ❌ | ✅ possible |
| Extra software | none | always-visible Mac app | none |

**Positioning:** not "replacing an abandoned integration" but "giving Home Assistant a native entity model of SecuritySpy" — which neither path offers.

**Interoperability note:** HomeHelper is a *bridge*, not a competitor, for users who want SecuritySpy to react to HomeKit accessories. The two can coexist; this integration should not assume it is the only client.

---

## 12. Open questions for the architecture phase

1. **Arm switches: write `schedule` or `override`?** (§4) — overrides are transient and probably right for automation.
2. **Default confidence threshold and debounce window.** Needs tuning against real footage.
3. **Poll interval for `caplist`** — per camera per class is 3 requests × N cameras. Batch via `cams=0,1,2,…`? Only poll after a `FILE` event?
4. **Does `o` populate at capture close or later?** Determines whether poll can serve low-latency needs.
5. **`i` and `z` fields** in `caplist` remain unconfirmed.
6. **Do AI-class and arrival/departure trigger bits fire** once `mcTriggerMotionH` is enabled? Testable now.
7. **Multi-server** — out for v1, but `uuid` makes it cheap to leave room.
8. **Media source** — v1 or v2? `caplist` + `getpreview` make it more tractable than expected.
9. **Custom-model entities** — dynamic creation, or a generic event entity only?
