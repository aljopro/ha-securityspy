---
title: "Addendum: HA SecuritySpy Integration"
status: draft
created: 2026-08-09
updated: 2026-08-09
---

# Addendum — Technical Depth for Downstream Documents

Material gathered during the brief conversation that belongs in the PRD, architecture, or implementation planning rather than in the brief itself. Everything here is evidenced; sources are cited.

---

## 1. SecuritySpy Web API — Surface Summary

Canonical spec: **https://bensoftware.com/securityspy/web-server-spec.html**

All commands are prefixed `++` in real URLs (e.g. `/++systemInfo`).

### Authentication
Two equivalent forms, no session or token:
1. HTTP Basic — `http://user:pass@host:8000/++systemInfo`
2. Query parameter — `?auth=<base64("user:pass")>`

The `auth=` form matters for stream URLs handed to ffmpeg or an external consumer, since it survives URL-only contexts. Credentials travel in the clear unless HTTPS is enabled (`++settings-web`: `portHttps`, `insecure` flag for legacy TLS).

### Video and images
| Endpoint | Purpose |
|---|---|
| `++image?cameraNum=N&width=&height=&quality=` | single JPEG snapshot |
| `++video?cameraNum=N&vcodec=jpeg\|h264\|h265` | multipart MJPEG / H.26x live stream |
| `++stream?cameraNum=N&vcodec=h264&acodec=...` | **RTSP URL** — the H.264 path HA's `stream` component wants |
| `++hls`, `++hls_mediaplaylist?cameraNum=N&quality=0..2` | HLS |
| `++multiplex?cameras=0,1,2&format=&fps=` | server-composited grid |

### Audio — the hard constraint
- `GET ++audio?cameraNum=N` — G.711 μ-law, 8 kHz mono.
- `POST ++audio?cameraNum=N` — two-way talk, audio bytes in body.

HA/WebRTC want AAC. **This is why no SecuritySpy integration has ever shipped stream audio.** Not fixable client-side without transcoding.

### PTZ
- `++ptz/command?cameraNum=N&command=<code>&speed=1-100` — codes 1–19 movement + preset recall, 99 stop, 112–119 save preset.
- `++getptzcapabilities?cameraNum=N` — bitmask: Pan/Tilt=1, Home=2, Zoom=4, Presets=8, Speed=16, Continuous=32.

### Arming / modes — the control surface
`++setSchedule?cameraNum=N&mode=C|M|A&schedule=0..3&override=0..14`
- `mode`: **C** = continuous capture, **M** = motion capture, **A** = actions
- `schedule`: 0 = unarmed 24/7, 1 = armed 24/7, 2 = sunrise–sunset, 3 = sunset–sunrise
- `override`: none, or timed disarm/arm for 1–6 hours
- `cameraNum=-1` applies to all cameras

Also `++cameramodes?cameraNum=N` returns `C:ARMED/DISARMED M:… A:…`; `++setPreset?id=` applies a global schedule preset.

### Triggering
`++triggermd?cameraNum=N` (or `-1`) — manually trigger motion detection / recording.

### Captured files — backs the media_source ambition
- `++download?cameraNum=&format=xml&ccFilesCheck=&mcFilesCheck=&imageFilesCheck=&ageText=&date1Text=&date2Text=&results=200&continuation=` — paginated, filterable capture listing. **This is the API behind the SecuritySpy web view and iOS app capture lists.**
- `++getfile/<cameraNum>/<YYYY-MM-DD>/<filename>`, plus `++getfilehb` / `++getfilelb` (high/low bandwidth).

### Info and settings
- `++systemInfo?format=xml|json` — the poll-everything endpoint.
- `++settings-cameras`, `-general`, `-display`, `-storage`, `-compression`, `-email`, `-web` — GET to read, POST to write. Per-camera settings include `motionSensitivity` and a full trigger matrix: `mcTriggerMotion`, `mcTriggerMotionA/H/V`, `mcTriggerArrivesA/H/V`, `mcTriggerDepartsA/H/V`, `mcTriggerAudio` (A/H/V = Animal/Human/Vehicle; `a`-prefixed variants for Actions).

---

## 2. The Event Stream — Primary Data Path

`GET /++eventStream?version=3` (optionally `&format=multipart`) — **a long-lived HTTP response that never terminates.** Not polling, not SSE-spec, not WebSocket. Must be read incrementally.

**Two implementation gotchas — note the first is NOT in the spec:**
1. Lines are terminated by **CR (0x0D)**, not LF. **The published spec says nothing whatsoever about line termination.** This is known only from our own hexdump (§8.2). An implementer following the documentation would reasonably use `readline()`, get LF semantics, and hang indefinitely.
2. A `NULL` heartbeat arrives every **10 seconds** (spec-stated, and measured at exactly 10 s). Its absence is the connection-loss signal — though the spec offers no explicit disconnection guidance.

**Line format (spec-verbatim):** `[TIME] [EVENT NUMBER] [CAMERA NUMBER] [EVENT] [INFO]` — timestamp is 14 characters `YYYYMMDDHHMMSS`; camera number is **`X` when the event is not camera-specific**; `[INFO]` may be absent. `MOTION` bounding boxes use a **top-left origin**. Endpoint: `eventStream?version=3[&format=multipart]`.

| Event | Payload |
|---|---|
| `MOTION` | bounding box `X Y W H` |
| `MOTION_END` | — |
| `CLASSIFY` | AI results, e.g. `HUMAN 96 VEHICLE 0 ANIMAL 0` |
| `TRIGGER_M` / `TRIGGER_A` | reason **bitmask** (below) |
| `FILE` | full path of the completed recording |
| `ARM_C`/`DISARM_C`, `ARM_M`/`DISARM_M`, `ARM_A`/`DISARM_A` | mode changes |
| `ONLINE` / `OFFLINE` | camera connectivity |
| `ERROR` | code + description |
| `CONFIGCHANGE` | settings edited |
| `NULL` | 10 s heartbeat |

**Trigger reason bitmask** (bit 0 = LSB): 0 Motion, 1 Audio, 2 AppleScript, 3 Camera event, 4 Web server, 5 Other camera, 6 Manual, 7 Human movement, 8 Vehicle movement, 9 HomeKit, 10 Animal movement, 11–16 Human/Vehicle/Animal arrival & departure.

**Arrival vs departure is a potential differentiator** — Nest does not expose it. But see §8.10: these bits never fired in live capture, so it is conditional on per-camera SecuritySpy trigger configuration, not a given.

---

## 3. What `++systemInfo` Does and Does Not Give You

**Per camera:** `number`, `name`, `connected` (yes/no), `video-width`/`video-height`, `cc-mode`, `mc-mode`, `a-mode`, `has-audio`, `ptz-capabilities` (bitmask), `device-name`, `device-type` (Local/Network), `address`, `port`.

**Server level:** `Name`, `Version`, `UUID`, `EventStreamCount`, `DDNSName`, `WanAddress`, `ServerName`, `BonjourName`, `IP1`, `IP2`.

**Critically absent:** motion-active, last-capture-time, and AI classification are **not** fields in `systemInfo`. They exist only on the event stream. **The integration must maintain that state itself**, including a timeout to clear motion if `MOTION_END` is missed. A per-camera "currently recording" flag also appears absent — *unverified, worth checking against a live dump.*

---

## 4. Home Assistant Conventions — Evidence Base

Read from the local mirror at `~/projects/home-assistant/`. Paths below are relative to `developers.home-assistant/docs/` (**docs/**) or `core/homeassistant/components/unifiprotect/` (**up/**).

### 4.1 The event-vs-binary_sensor discriminator

**This is the key design fork, and it has a documented in-code answer.**

`up/binary_sensor.py:466-467`, where a package binary sensor would have gone:
```python
# Package detection is a momentary smart-detect event, not a sustained state:
# it is the package event entity (event.py), not a binary sensor.
```

Fuller rationale at `up/event.py:366-375` — for object types the backend models as discrete point-in-time detections, the event is recorded *already-ended*, so "a sustained binary sensor can never reflect it."

**The rule is duration shape, not semantic category:**
- Backend gives a **start and a later end** → `binary_sensor`
- Backend gives a **single point-in-time fire** → `event` entity

**unifiprotect ships both for vehicle** (`up/binary_sensor.py:450-457` and `up/event.py:426-433`) — the binary sensor answers "is a vehicle present," the event entity carries confidence and license plate. Not redundancy; different questions. **This is the pattern to copy for SecuritySpy classification.**

**Direction of travel worth heeding** — `up/quality_scale.yaml:60-62` records an intent to *remove* the doorbell occupancy binary sensor in favour of the event entity. Do not model momentary triggers as occupancy sensors.

**Device classes:** `event` has only `BUTTON`, `DOORBELL`, `MOTION` (docs/core/entity/event.md:62-66). No person/vehicle/animal class exists for either platform — unifiprotect uses `translation_key` + `icons.json` instead. Event entities are stateless; HA stores the timestamp of the last fire as state (docs/core/entity/event.md:12-14). Only declared `event_types` may be fired.

### 4.2 Proposed entity mapping

| SecuritySpy signal | Platform | Rationale |
|---|---|---|
| Motion (+ bounding box) | `binary_sensor`, `device_class=MOTION` | sustained; bbox → attributes |
| HUMAN / VEHICLE / ANIMAL | `binary_sensor` **if** classification is held for the motion duration; `event` if one-shot | **must verify empirically** |
| Classification + confidence | `event` entity, confidence in payload | mirrors the vehicle/LPR pattern; a binary sensor cannot carry per-fire confidence |
| Trigger events (reason bitmask, arrival/departure) | `event` entity, `event_types` = decoded reasons | inherently point-in-time |
| Recording file completed | `event` entity | point-in-time by definition |
| **Latest capture** | **`image` entity** | state = timestamp of last update; gives a stable HA URL + free "last seen" value |
| Camera online/offline | *not an entity* — drives `_attr_available` | |
| Errors | repair issue or log | see 4.5 |

### 4.3 Device topology

Hub pattern, `"integration_type": "hub"` in the manifest. Child device (`up/entity.py:394-405`) sets `via_device=(DOMAIN, <hub id>)`; hub (`up/entity.py:415-424`) sets matching `identifiers` and no `via_device`.

**Important divergence:** unifiprotect's child devices set only `connections` (MAC), not `identifiers`. **SecuritySpy cameras may be USB/analog with no MAC** — use `identifiers={(DOMAIN, f"{server_id}_{camera_number}")}` on children instead. Do not fabricate MACs.

**Unique IDs** (`up/entity.py:246-252`): `f"{device_id}_{description.key}"`, with the bare device ID and `_attr_name = None` for the "main feature" entity. **Use the SecuritySpy camera number/UUID, never the name** — names are user-editable, and the unique-ID scheme is effectively permanent.

`rules/devices.md:44` — a hub representing software rather than hardware should set `entry_type=DeviceEntryType.SERVICE`. **SecuritySpy is a Mac app, so this likely applies**, unlike unifiprotect's NVR appliance.

### 4.4 Coordinator and push

`docs/integration_fetching_data.md:180-184` is explicit: for a push API, use `DataUpdateCoordinator` **without** `update_method` and `update_interval`, then call `coordinator.async_set_updated_data(data)` when data arrives.

**unifiprotect does NOT do this** — `ProtectData` (`up/data.py:69`) is a hand-rolled pub/sub predating coordinator push support. It is legacy; a greenfield integration should use a real coordinator in `coordinator.py` (also required by the `common-modules` rule, which unifiprotect violates).

Worth copying from it regardless:
- **Log discipline** (`up/data.py:291-314`): first failure at ERROR, every subsequent at DEBUG, recovery once at WARNING. This is the entire point of the Silver `log-when-unavailable` rule.
- **Change detection** (`up/entity.py:227, 325-350`): `_state_attrs` + precompiled `attrgetter`s, calling `async_write_ha_state()` only when a declared attribute actually changed. Matters a lot with a chatty motion stream.
- **Subscription lifecycle** (`up/event.py:84-91`): subscribe in `async_added_to_hass`, register unsub via `self.async_on_remove(...)`.
- `_attr_should_poll = False` but still implement `async_update` for the generic update service (`up/entity.py:262-267`).
- `PARALLEL_UPDATES = 0` per platform.

### 4.5 Availability and errors

Three-way discipline (`up/__init__.py:80-137`):
- `ConfigEntryNotReady` — transient, HA retries with backoff
- `ConfigEntryAuthFailed` — starts reauth; **only after N failures**, since NVRs return spurious 401s during boot
- `ConfigEntryError` — permanent (e.g. version too old)

All carry `translation_domain`/`translation_key` (Gold `exception-translations`).

**Repairs** — `rules/repair-issues.md:5-12`: only for things *the user can fix themselves*. Camera offline is **not** a repair, it is `_attr_available = False`. Good candidates: web server auth disabled in SecuritySpy prefs, configured user lacking arm/disarm permission, SecuritySpy version too old.

### 4.6 Camera platform

`CameraEntityFeature.STREAM` must be advertised **dynamically**, only when a stream URL actually exists (`up/camera.py:155-156, 213-214`). `stream_source()` returns the RTSP URL; `async_camera_image()` handles snapshots.

**Duplicate devices across integrations: no HA convention exists.** Searched thoroughly; all "duplicate" guidance concerns within-integration config-flow dedup. The device registry is domain-scoped — an ONVIF device and a SecuritySpy device for the same physical camera will always be separate entries. The only cross-integration merge mechanism is identical MAC `connections`, unreliable here. Mitigation option: `entity_registry_enabled_default=False` on the camera entity, or a config-flow toggle (unifiprotect has the inverse in `CONF_DISABLE_RTSP`).

### 4.7 Control entities

- **Three arm modes → three `switch` entities**, `entity_category=EntityCategory.CONFIG`. **Not `alarm_control_panel`** — that is a mutually-exclusive state machine (`DISARMED/ARMING/ARMED_AWAY/TRIGGERED`, `up/alarm_control_panel.py:25-32`) and cannot represent three independent simultaneously-settable booleans without a lossy 8→4 encoding. `select` fails for the same reason. Note unifiprotect's alarm panel exists once on the NVR with a single supported feature.
- **PTZ and manual trigger → services**, not entities (`up/services.py:285-303`). Parameterized actions, not state. A button per preset per camera would explode entity count and cannot express arbitrary coordinates.
- If a single "is this camera armed at all" summary is wanted, that is a `binary_sensor`, not a control.

### 4.8 Library split — mandatory, not optional

`rules/dependency-transparency.md:5-12` (Bronze): the dependency must be OSI-licensed, on PyPI, built and published from a **public CI pipeline**, with the PyPI version corresponding to a **tagged release**. Platinum adds `async-dependency` (asyncio-based) and `inject-websession` (accepts an external `aiohttp` session).

Manifest should declare `"iot_class": "local_push"`, a pinned `==` requirement, and `loggers` naming the library's logger namespace.

**Build the library first.** Retrofitting the split after writing protocol parsing inside the integration is a large thankless refactor that blocks Bronze.

### 4.9 Naming, services, diagnostics

- `_attr_has_entity_name = True`; `translation_key` on every entity description; **never** a hardcoded `name=`. Changing `has_entity_name` later renames every entity.
- Icons belong in `icons.json` (Gold `icon-translations`), never `_attr_icon`.
- `strings.json` top-level keys: `config`, `entity`, `exceptions`, `issues`, `options`, `services`.
- Services register in `async_setup`, not `async_setup_entry` (Bronze `action-setup`), and raise `ServiceValidationError` with translation keys.
- `services.yaml` selectors can narrow the device picker — e.g. `entity: domain: camera` for PTZ targets.
- Diagnostics: put the anonymizer **in the library**, not the integration. Redact host, credentials, camera names.

### 4.10 Quality scale — highest-leverage decisions up front

Expensive-to-retrofit items, in rough priority:
1. `entity-unique-id` scheme — permanent; changing it orphans every user's customizations
2. `has-entity-name` — changing it renames everything
3. Hub topology / `via_device` — retrofitting re-parents every device
4. `runtime-data` typed `ConfigEntry` — threads through every module
5. `common-modules` — `coordinator.py`, `entity.py` naming
6. `entity-event-setup` — correct subscribe/unsubscribe lifecycle
7. Library split (4.8)

Exemption to copy verbatim in spirit (`up/quality_scale.yaml:4-6`):
```yaml
appropriate-polling:
  status: exempt
  comment: Integration is push-based using WebSockets (iot_class local_push).
```

---

## 5. Prior Art and Precedents

### 5.1 `briis/securityspy` — the abandoned incumbent
- Repo: https://github.com/briis/securityspy — library https://github.com/briis/pysecspy
- Entities: `camera`, `binary_sensor` (motion), `switch` (arm/disarm), `sensor`, `button`.
- Requires SecuritySpy ≥ 5.3.4, web server on port 8000, user with Administrator or at least "Get Live Video and Images" + "Arm and Disarm".
- **Abandoned.** Maintainer explicitly stepped back; removed from default HACS store ~HA 2025.1; `pysecspy` last PyPI release **August 2022**; last commit activity ~Dec 2024 (an HA 2024.9 deprecation fix). Still installable as a manual custom repository.
- Documented limitations: no stream audio, no SSL.
- Breakage and abandonment discussion:
  - https://community.home-assistant.io/t/core-2024-1-0-kills-security-spy-custom-integration/666210
  - https://bensoftware.com/forum/discussion/4542/home-assistant-hacs-security-spy-integration-abandoned
  - https://bensoftware.com/forum/discussion/4847/home-assistant-integration
  - https://community.home-assistant.io/t/securityspy/370222

**No maintained fork found.**

### 5.2 Non-HA reference implementations — useful as API ground truth
Both handle the event stream properly:
- Go: https://github.com/golift/securityspy — docs https://pkg.go.dev/golift.io/securityspy
- Node-RED: https://flows.nodered.org/node/@luqman/node-red-security-spy

### 5.3 `bambu_lab` — the shape the author wants
Live inspection of the author's HA: **one device, 60 entities**, including `image.*_cover_image` and `image.*_pick_image` whose **state is a timestamp**. Confirms the `image` platform as the right home for "latest capture," and validates the device-with-many-entities model the author described from the outset.

### 5.4 `unifiprotect` — the architectural precedent
Platinum-rated, present in the local core mirror. **Copy:** the event/binary_sensor discriminator, hub topology, log-once-then-DEBUG, three-way config-entry exceptions, dynamic `STREAM` feature, change-detection before state writes, not creating entities the backend cannot back, entity-description-driven platforms, library-side anonymizer. **Avoid:** `data.py` instead of `coordinator.py`, the doorbell occupancy binary sensor, MAC-only child `connections`, the private/public API bifurcation (migration scar tissue), hand-rolled subscription bookkeeping.

Not yet read, possibly relevant later: `config_flow.py`, `migrate.py`, `media_source.py`, `views.py` (HTTP proxy views for snapshots/thumbnails/video — relevant to the media browser ambition).

---

## 6. Author's Live Environment

- **SecuritySpy host:** `192.168.0.2`
- **Home Assistant core:** local mirror at `2026.8.0.dev0`
- **11 cameras:** Front Yard, Back Yard, Driveway, Front Porch, North Yard, Back Patio, Music Room, Living Room, Ada's Room, Peyton's Room, Kitchen
- **Current transport:** 11 separate `generic` camera config entries → `camera.192_168_0_2[_N]`; device `default_name` `192_168_0_2`, manufacturer "Generic", empty `connections`, no `via_device`, every camera manually renamed via `name_by_user`
- **ONVIF:** 11 config entries exist, all `state: not_loaded`, `disabled_by: user` — tried and abandoned. *Reason never captured; worth asking, as it is the closest prior art in the author's own setup.*
- **Camera numbering:** generic entity suffixes appear to map to SecuritySpy camera numbers (`_4` = Driveway)
- **Also present:** Nest doorbell (`camera.front_porch_doorbell`) at the front porch, alongside the SecuritySpy Front Porch Camera — a useful in-house UX benchmark
- **Downstream consumer:** Hermes (Nous Research agent) at `~/.hermes/hermes-agent/`, with `tools/vision_tools.py` and `tools/homeassistant_tool.py`, delivering to Telegram/Discord/Signal

### Local development assets
| Path | Contents |
|---|---|
| `~/projects/home-assistant/core/` | HA core @ 2026.8.0.dev0, includes `unifiprotect` |
| `~/projects/home-assistant/developers.home-assistant/` | full developer docs source |
| `~/projects/home-assistant/addons/`, `frontend/`, `example-custom-config/` | supporting mirrors |
| `~/projects/docs/home-assistant/` | 6 curated notes: REST API, entities/state, templates/registry, icons, auth/networking, resources |
| `~/projects/integration_blueprint/` | HACS integration scaffold |
| `~/projects/cookiecutter-homeassistant-custom-component/` | component cookiecutter |
| `~/projects/securityspy-sdk/` | **empty stub** — `package.json` only, July 2023. Nothing salvageable. |

---

## 6a. Candidate Acceptance Criteria

Moved here from the brief during editorial condensing — brief-level success criteria were reduced to the falsifiable few; these remain valid and should feed the PRD.

**Functional**
- A human detected on any outdoor camera produces an HA event carrying class, confidence, and a reachable image, within a few seconds of SecuritySpy detecting it.
- The `image` entity's state timestamp updates on each new capture and is usable as an automation trigger.
- Arming a camera's motion-capture mode from HA is reflected in SecuritySpy, and a change made in SecuritySpy is reflected back in HA.
- Camera going offline in SecuritySpy marks the corresponding HA entities unavailable, and recovery restores them without HA restart.

**Resilience**
- Logs a connection loss once at ERROR, subsequent retries at DEBUG, and recovery once at WARNING.
- Reconnects to the event stream after the 10 s heartbeat lapses, with backoff.
- Survives a Home Assistant version upgrade without breaking.
- Motion state self-clears on a timeout if `MOTION_END` is never received.

**Quality**
- Config flow validates credentials and surfaces a clear error for bad host, bad credentials, and insufficient SecuritySpy user permissions.
- Reauth flow triggers on persistent auth failure rather than spamming errors.
- All entities carry `translation_key`; no hardcoded names or `_attr_icon`.

## 8. Live Probe Results — 2026-08-09

Read-only probe against the author's production server (SecuritySpy **6.20**, `192.168.0.2`). Raw artifacts in the session scratchpad: `probe-output/systeminfo.xml`, `probe-output/eventstream.raw`, `probe-output/eventstream.lines`. **This section supersedes inferences drawn from the published spec summary wherever the two disagree.**

### 8.1 THE HEADLINE: classification is continuous and noisy

**100-second capture, 1,341 events.** Event type frequency:

| Event | Count |
|---|---|
| `MOTION` | 915 |
| `TRIGGER_M` | 202 |
| `CLASSIFY` | 191 |
| `TRIGGER_A` | 15 |
| `NULL` (heartbeat) | 10 |
| `MOTION_END` | 6 |
| `FILE` | 2 |

`CLASSIFY` fired **191 times on one camera in 95 seconds**, with 0–2 second gaps. Confidence for a single person walking through frame:

```
20, 69, 19, 77, 88, 8, 54, 25, 5, 18, 18, 49, 13, 17, 16, 97, 96, 99, 99, 28, 51, 71, 64, 91, 97, 97, 98, 97, 98, 96
```

Range 4–100, swinging wildly frame to frame.

**Design consequence — this overturns the earlier plan:**

- **Human / vehicle / animal → `binary_sensor` with a confidence threshold plus debounce/hysteresis.** Not one-shot event entities. Raw `CLASSIFY` is a per-frame inference stream, not a detection event.
- **The `event` entity fires once per *episode*, on threshold crossing** — not once per `CLASSIFY`. Naive mapping produces ~190 HA events per person per 90 seconds, which would hammer the state machine and the recorder.
- A confidence threshold (~70?) plus a minimum-consecutive-frames rule is needed. **Both should be config-flow options** — the right values are camera- and scene-dependent.
- The `event` payload should carry *peak* confidence for the episode, not the instantaneous value at crossing.

### 8.2 CR-only framing — confirmed by hexdump

```
00000000  32 30 32 36 30 38 30 39  31 37 35 33 33 35 20 30  |20260809175335 0|
00000010  20 37 20 4d 4f 54 49 4f  4e 5f 45 4e 44 0d 32 30  | 7 MOTION_END.20|
```

**1,341 CR (0x0D), zero LF (0x0A).** Parsers must split on `\r`. A standard `readline()` returns one unbounded line and appears to hang — the most likely single implementation bug in this whole project, now proven rather than inferred.

Line format confirmed: `YYYYMMDDhhmmss EVENTNUM CAMERANUM EVENT [args]`. Event numbers are a **monotonic per-connection counter starting at 0** (0…1340 here), not persistent IDs. Server-level events use camera number `X`. Heartbeat cadence measured at exactly 10s.

### 8.3 `MOTION_END` is unreliable

| Camera | `MOTION` | `MOTION_END` | Span |
|---|---|---|---|
| 10 Kitchen | 467 | **0** | 95s |
| 7 Living Room | 383 | 1 | 99s |
| 1 Back Patio | 56 | 5 | 91s |
| 3 Driveway | 9 | 0 | 2s |

**The integration must implement its own inactivity timeout** to clear motion binary sensors. Do not wait for `MOTION_END`. Confirms the concern flagged from unifiprotect's `_async_event_with_immediate_end` fallback.

### 8.4 `<server>` block — hub device and diagnostics

```
version 6.20          uuid fUCdlMLDp4tbTmSgcbJZ     bonjour-name Jensens-Mac-mini.local
camera-count 11       cpu-usage 32                  memory-pressure 1
archive-status off    new-version (empty)           cert-expiry-days 44
http-enabled true     http-port 8000                http-port-wan 8000
https-enabled true    https-port 8001               https-port-wan 8001
ddns-name chappell.viewcam.me    ip1 192.168.0.2    ip2 100.90.186.57
current-local-time 2026-08-09T17:52:58-05:00        seconds-from-gmt -18000
```

- **`uuid` is the stable hub identifier** — use it for the hub device's `identifiers` and as the unique-ID prefix. Do not use hostname or IP.
- Diagnostic sensor candidates: `cpu-usage`, `memory-pressure`, `camera-count`, `archive-status`, `cert-expiry-days`.
- **`new-version` is an update-available signal** → an `update` entity is viable.
- `ip2` is a Tailscale address (100.64.0.0/10) — the server is on a tailnet.

### 8.5 HTTPS is enabled — move into v1 scope

`https-enabled: true` on port 8001; plain HTTP on 8000 issues `301` to HTTPS. Cert is for `chappell.viewcam.me` (viewcam.me DDNS), **expiring in 44 days** (2026-09-22) — presumably auto-renewing.

Consequences:
- The config flow must handle both schemes, and connecting by LAN IP against a DDNS-hostname cert requires either hostname config or explicit verify-disable. **A "verify SSL certificate" toggle is needed.**
- The abandoned integration's lack of SSL support would break on this server immediately.

### 8.6 Per-camera fields — 69 of them

Full list from a live camera:

```
a-delay-time  a-mode  a-reset-time  a-schedule-id  a-schedule-override  a-script
a-sound-cam  a-sound-mac  a-trigger-audio  a-trigger-video  address
audio-device-name  audio-format  audio-sensitivity  brightness
cc-image  cc-mode  cc-movie  cc-schedule-id  cc-schedule-override
connected  contrast  current-fps  custom-model  data-rate
device-name  device-type  has-audio  last-error  last-error-description
mc-image  mc-mode  mc-movie  mc-movie-fps  mc-movie-post  mc-movie-pre
mc-schedule-id  mc-schedule-override  mc-trigger-audio  mc-trigger-video
motion-sensitivity  name  network-audio  number  overlay-text  path
permissions  port  port-rtsp  preset-name-1..10  ptz-features
shortcut-list  since-last-capture  storage-path  time-since-last-frame
time-since-last-motion  transformation  video-format  video-height  video-width
```

**Confirmed absent** (must come from the event stream): any recording-active flag, any classification field, any motion-active boolean.

**Valuable and previously unknown:**
- `time-since-last-motion`, `since-last-capture`, `time-since-last-frame` — seconds-ago counters. Convert to absolute timestamps for `device_class: timestamp` sensors. Note these give a **poll-based fallback** for last-motion even without the event stream.
- `current-fps`, `data-rate` — live health/diagnostic sensors.
- `last-error` + `last-error-description` — per-camera error surface.
- `motion-sensitivity`, `audio-sensitivity`, `brightness`, `contrast` — writable `number` entities.
- `mc-movie-pre` (5s) / `mc-movie-post` (30s) — explains `FILE` event latency (§8.9).
- `permissions` bitmask (10207 observed) — likely encodes what the authenticated user may do. **Worth decoding**: could drive graceful degradation and a good repair issue when permissions are insufficient.

### 8.7 Camera inventory

| # | Name | Resolution | RTSP | PTZ |
|---|---|---|---|---|
| 0 | Front Yard | 640×480 | 192.168.0.10:8554 | ✅ 63 |
| 1 | Back Patio | 2304×1296 | 192.168.0.18:0 | — |
| 2 | Front Porch | 640×480 | 192.168.0.13:8554 | ✅ 63 |
| 3 | Driveway | 640×480 | 192.168.0.11:8554 | ✅ 63 |
| 4 | Back Yard | 640×480 | 192.168.0.12:8554 | ✅ 63 |
| 5 | Music Room | 1920×1080 | 192.168.0.16:0 | — |
| 6 | North Yard | 640×480 | 192.168.0.14:8554 | ✅ 63 |
| 7 | Living Room | 1920×1080 | 192.168.0.20:0 | ✅ 63 |
| 8 | Ada's Room | 1920×1080 | 192.168.0.15:0 | — |
| 9 | Peyton's Room | 1920×1080 | 192.168.0.19:0 | — |
| 10 | Kitchen | 2304×1296 | 192.168.0.17:0 | — |

All are `device-name: ONVIF`, `device-type: Network`, H.264, `has-audio: true`, `audio-format: u-Law` — **firsthand confirmation of the AAC incompatibility**. Storage under `/Volumes/Surveillance/<Camera Name>/`.

**PTZ: 6 of 11 report `ptz-features=63`** = pan/tilt + home + zoom + presets + speed + continuous. No presets are currently named. PTZ is testable on real hardware, not a blind-build feature. Note camera numbers are **not contiguous with display order** — always key on `<number>`.

### 8.8 Arming model is richer than a boolean

Schedules (`schedule-list`): `0` Disarmed 24/7, `1` Armed 24/7, `2` Armed Sunrise To Sunset, `3` Armed Sunset To Sunrise.

Overrides (`schedule-override-list`, 15 entries): No Override, Disarmed/Armed Until Schedule Event, Disarmed/Armed For 1–6 Hours.

All 11 cameras are currently `schedule-id=1` on all three modes.

**This reopens the switch-vs-select decision.** Each mode carries a *schedule* (4 options) plus an *override* (15 options), not just on/off. Candidate design: a `switch` for the common armed/disarmed case **plus** a `select` for the schedule, or a `select` per mode with the schedules as options. `mode` + `schedule` + `override` is genuinely three-dimensional. **Defer to the architecture phase.**

### 8.9 `FILE` events and the media path

```
17:54:01 cam 3: /Volumes/Surveillance/Driveway/2026-08-09/08-09-2026 5-52-25 PM M Driveway.mov
17:54:54 cam 1: /Volumes/Surveillance/Back Patio/2026-08-09/08-09-2026 5-53-04 PM M Back Patio.mov
```

Filename encodes date, start time, trigger letter (`M` = motion), and camera name. Directory layout `<Camera>/<YYYY-MM-DD>/` matches the `++getfile/<cam>/<date>/<filename>` shape — **the media_source path is viable.**

**Latency caveat:** `FILE` arrives on episode *completion*. The 17:52:25 recording produced its `FILE` event at 17:54:01 — **96 seconds later**, driven by the 30s post-roll plus episode duration. So `FILE` is **not** a low-latency notification trigger. For the Hermes pipeline, trigger on the classification event and pull a live snapshot (`++image`); use `FILE` only for archival linking.

### 8.10 Trigger bitmask — arrival/departure not observed

Only `mask=1` (bit 0, Motion) appeared, across 202 `TRIGGER_M` and 15 `TRIGGER_A`. The human/vehicle/animal movement bits (7, 8, 10) and arrival/departure bits (11–16) **never fired**.

Most likely because per-camera trigger settings (`mcTriggerMotionH/V/A`, `mcTriggerArrives*`, `mcTriggerDeparts*`) are configured for plain motion rather than AI-class triggers on this server.

**Consequence: downgrade the arrival-vs-departure claim from "confirmed capability" to "conditional on SecuritySpy configuration."** Worth verifying by enabling those triggers on one camera before designing entities around them.

### 8.17 The published spec vs. reality (read directly, 2026-08-09)

Source: https://bensoftware.com/securityspy/web-server-spec.html — read directly rather than via summary.

**Confirmed by the spec, matching our probe:** record format and field order; 14-char timestamp; `X` for non-camera-specific events; 10-second `NULL` heartbeat; the complete 17-bit trigger bitmask (bits 0–16); `CLASSIFY` as percentage predictions for humans/vehicles/animals; `eventStream?version=3[&format=multipart]`.

**New detail from the spec:** `MOTION` bounding box origin is **top-left**.

**Where the spec is silent — and it matters:**

| Topic | Spec | Consequence |
|---|---|---|
| **Line termination** | **Not mentioned at all** | An implementer defaults to LF and hangs. Only our hexdump (§8.2) reveals CR-only. |
| Custom CoreML model | No mention whatsoever | Payload shape must be discovered empirically; reinforces the label-agnostic parser (§8.16) |
| Event-stream authentication | Not covered in that section | Falls back to the general auth-in-URL mechanism |
| `MOTION_END` / `ONLINE` / `OFFLINE` / `CONFIGCHANGE` payloads | Unspecified | Must be probed |

**Where the spec is wrong-in-practice:** it describes `MOTION_END` as "issued after MOTION." §8.3 found 467 `MOTION` and **zero** `MOTION_END` on one camera over 95 seconds. Implementing to the spec produces motion sensors that never clear.

**Endpoints the spec documents that we had not catalogued:** `ptz/controls` (HTML control page), `hls_mediaplaylist` (fixed-quality HLS), `multiplex` (HTML grid), `sounds` and `scripts` (HTML/XML lists — these back the `aSoundCam` / `aScript` settings fields seen in §8.14), `getfilehb` / `getfilelb` (bandwidth variants), `setPreset`, `cameramodes`, `triggermd`.

**Endpoints the spec does NOT document, which the 6.x web client uses** (see §8.12, §8.14): `camStatus`, `caplist`, `cliplist`, `getpreview`, `deviceList`, `updateStatus`, `dashImage`, `refreshLicenseInfo`, `settings-web-access-info`. The spec also describes `settings-*` as **HTTP POST only**, whereas `GET ?format=json` demonstrably returns ~120 flat keys.

**Conclusion: the published specification is a partial and dated view of SecuritySpy 6.x.** Treat the web client as the authoritative interface description, and verify everything against a live server.

### 8.12 UNDOCUMENTED JSON API — from HAR capture of the official web UI

A HAR capture of the SecuritySpy web client (192 entries) revealed a **JSON API that is not in the published web-server spec**. All endpoints verified working against the live server. **This is the API the official client actually uses**, and it is materially better than the documented XML surface.

#### `++camStatus` — cheap health poll

```json
[{"num":0, "enabled":true, "online":true, "open":true, "err":0, "errDesc":""}, ...]
```

**794 bytes for 11 cameras**, versus 27 KB for the `++systemInfo` XML. Ideal for periodic health reconciliation alongside the push stream. Note `enabled` / `online` / `open` are three distinct states — worth modelling separately rather than collapsing into one availability boolean.

#### `++caplist` — the capture list, and **it carries classification**

```
GET ++caplist?cams=4,&startDate=2026-08-09&endDate=2026-08-09&filter=0
```

Returns a JSON array. Fields decoded empirically:

| Field | Meaning | Notes |
|---|---|---|
| `c` | camera number | |
| `t` | capture type | **`1` = movie, `2` = JPG image** (client renders `JPG` vs a duration) |
| `s` | **start time, seconds since midnight** | verified: `63319` → 17:35:19, matches filename |
| `d` | duration, seconds | |
| `i` | (unconfirmed) | |
| **`g`** | **user tag ID** | settable via `POST setTags?tagId=N`; rendered as `img/tag-N.png` |
| **`m`** | **file size** | client calls `SizeStr(file.m)` |
| `z` | (unconfirmed, tracks `m`) | |
| `f` | folder date `YYYY-MM-DD` | matches `getfile`/`getpreview` path segment |
| `n` | filename | encodes date, time, trigger letter, camera name |
| `a` | archive flag | used in `getpreview`/`getfile` URLs |
| `u` | unread/new flag | drives italic styling in the client |
| **`o`** | **object classification bitmask** | **`1`=human, `2`=vehicle, `4`=animal** |

> **Corrected from the shipped client source.** Earlier readings of `t`, `g`, and `m` — inferred from response samples — were wrong. `m` is file size, not a motion score. Read `js/captures.js`, not sample data.

#### `filter` is class-aware server-side — this is the important part

From `index.html`'s `capFilter` control:

| `filter` | Meaning |
|---|---|
| 0 | All Files |
| 1 | All Images |
| 2 | All Movies |
| 3 | Continuous Capture Movies |
| 4 | Motion Capture Movies |
| **5** | **Human Motion Capture Movies** |
| **6** | **Vehicle Motion Capture Movies** |
| **7** | **Animal Motion Capture Movies** |

**The server will filter by object class.** A *last human seen* sensor is therefore one cheap request — `caplist?cams=N,&startDate=…&endDate=…&filter=5`, take the newest entry — rather than fetching everything and filtering on the `o` bitmask client-side. This makes the headline feature both simple and cheap to poll.

#### Exact URL forms (from `js/captures.js`)

```
getpreview?/{cam}/{folderDate}/{filename}?archive={a}      # note the double-? construction
getfile...?lowBandwidth={0|1}&forceDownload=1&archive={a}
POST setTags?tagId={N}                                      # form-urlencoded body lists captures
```

**`o` is the headline.** Observed values `0`, `1`, `4`, `5` (none / human / animal / human+animal). Semantically validated: cameras 10 (Kitchen) and 8 (Ada's Room) — indoor, where people and pets are — carry nearly all nonzero values; outdoor cameras were all `0` today.

**Design consequence — this substantially de-risks §8.1.** Classification is not only a transient event-stream signal; **SecuritySpy persists it against each recording.** Therefore:

- "Last human / vehicle / animal detected" can be a **poll-derived sensor**, not fragile in-memory state reconstructed from a noisy stream.
- **Correct state after an HA restart** — backfill from the API rather than waiting for the next detection.
- The media browser can be **filtered by object type**.
- Missed or dropped events self-heal on the next poll.

The architecture becomes **push for latency, poll for truth**: the event stream drives sub-second binary sensors and events; `++caplist` provides ground truth, reconciliation, and startup backfill. This is the standard robust pattern and it is now cheap to implement.

#### `++getpreview` — capture thumbnails

```
GET ++getpreview/<cameraNum>/<YYYY-MM-DD>/<url-encoded filename>?archive=0
```

Returns a **JPEG thumbnail** — verified 640×360, ~95 KB, HTTP 200. Path-style with URL-encoded filename.

Two uses: the media_source browser thumbnail, and — more importantly — **the `image` entity's content**. No need to extract a frame from the `.mov` ourselves; SecuritySpy renders one.

#### The vendor's own client does not use the event stream

The shipped web client polls `caplist` and `camStatus`; **`eventStream` appears nowhere in it**. The event stream is a pure third-party API feature the vendor UI never exercises.

This explains both its thin documentation and why `MOTION_END`'s unreliability (§8.3) went unnoticed. **Practical consequence: assume no vendor testing on the event stream. Verify empirically and let the poll path be authoritative.**

#### Others

- **`++setTags`** — `POST setTags?tagId=N`. SecuritySpy supports **user tags on captures**, undocumented in the spec. Possible HA surface: tag from an automation, or filter the media browser by tag.
- **`++cliplist`** — companion to `caplist` for clips; returned empty (`2 bytes`) in this capture.
- **`++dashImage?date=&width=&height=&type1=&type2=&item1=&smooth=&dark=1`** — server-rendered PNG activity chart. Novelty; low priority.
- **`++video?cameraNum=N&vcodec=jpeg&acodec=ulaw&apause=1&sizeFraction=1`** returned **HTTP 101 Upgrade** — the web client uses a **WebSocket** video path, distinct from the documented multipart MJPEG.
- **`++image?cameraNum=N&brightness=&contrast=&fisheyeStrength=&fisheyeType=&transformation=&settings=1`** — stills with image-adjustment parameters.
- **`++settings-cameras?cameraNum=N`** returned 84 KB of **HTML**, not the documented XML/JSON variant.

#### Revised recommendation for the `image` entity

Source the latest-capture image from `++getpreview` against the newest `++caplist` entry, rather than reacting only to `FILE` events. This gives correct state on startup, survives missed events, and delivers the classification (`o`) alongside the image in one round trip.

### 8.13 Prior-art automations — what `briis` shipped, and what to change

Source cloned to `scratchpad/briis-ref/`. Both README examples and the blueprint were read in full.

#### Example 1 — "Capture Image when Person is detected"

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.motion_outdoor
    attribute: event_object      # human | vehicle
    to: human
action:
  - service: camera.snapshot
    target: {entity_id: camera.outdoor}
    data: {filename: /config/www/camera_outdoor.jpg}
```

**Problem: it triggers on a state attribute.** Attribute triggers are second-class in HA — no device triggers, no UI automation-editor support, and the user must know the attribute name and its legal values from documentation.

**Our version** — dedicated per-class binary sensors make this a plain state trigger:

```yaml
trigger:
  - platform: state
    entity_id: binary_sensor.driveway_human_detected
    to: "on"
```

Discoverable in the UI, usable as a device trigger. This is a concrete argument for per-class binary sensors over classification-as-attribute, independent of the §8.1 reasoning.

#### Example 2 — "Download Video Recording when motion is complete"

```yaml
trigger: {platform: state, entity_id: binary_sensor.motion_outdoor, from: 'on', to: 'off'}
action:
  - service: securityspy.download_latest_motion_recording
    data: {entity_id: camera.outdoor, filename: /media/outdoor_latest.m4v}
```

**Keep this service** — a local copy is genuinely useful. But note it is partly a workaround for the absence of `media_source`: with captures browsable natively (via `++caplist` + `++getpreview` + `++getfile`), downloading is a choice rather than a prerequisite. Ship both.

Note also this automation depends on `MOTION_END`-driven `off` transitions — see §8.3, where `MOTION_END` proved unreliable. Our inactivity timeout makes this trigger work where a naive implementation would leave it never firing.

#### The blueprint — `securityspy_push_notification_motion_event.yaml`

Genuinely well built, and worth studying rather than reinventing. Features: presence filter, mobile app / HTML5 / Telegram targets, actionable **silence** button with cooldown and timeout, notification tag/channel handling, configurable time format, debug mode via persistent notifications, and camera-entity discovery from the motion entity's device.

**Its weakness, and our opportunity.** Image attachment is:

```yaml
notification_image: "{{ input_base_image_url }}{{ state_attr(camera_entity_id, 'entity_picture') }}"
```

Two consequences, both acknowledged in its own documentation:
1. **Requires a publicly reachable HTTPS Home Assistant instance** — "if you do not have these, the actionable notifications and images will not appear."
2. It sends the **current live frame**, not the frame that triggered the detection. Given notification latency, the subject may already have left the scene.

**Our `image` entity fixes both**: it holds the actual capture that triggered the detection (via `++getpreview`), served from Home Assistant's own local URL. Better content, no public URL requirement, no certificate dependency for local notifications. **This is a demonstrable improvement over the incumbent and should be called out in release notes.**

#### Services in `briis` — disposition

| `briis` service | Our disposition |
|---|---|
| `set_arm_mode(entity, mode, enabled)` | Largely superseded by per-mode switch entities; keep a service for scripting |
| `enable_schedule_preset(preset_id)` | Maps to `++setPreset`. **Untestable here** — `schedule-preset-list` was empty on the reference server |
| `download_latest_motion_recording(entity, filename)` | **Keep.** Complement with `media_source` |
| `enable_disable_camera(entity, enabled)` | Better as a `switch` entity than a service (maps to `camStatus.enabled`) |

#### Blueprint set planned for v1

1. **Detection notification with image** — the flagship; person/vehicle/animal, presence filter, actionable silence, using the detection frame rather than a live snapshot.
2. **Capture image on detection** — the `briis` example, triggered off a first-class binary sensor.

Blueprints double as executable documentation of the entity design: if one is awkward to write, the entity model is wrong.

### 8.14 SecuritySpy 6.x API rework — the published spec is out of date

Verified against the live 6.20 server. **The documented web-server spec materially understates what 6.x exposes.** The web client is the better specification.

#### JSON-first endpoints (none in the published spec)

| Endpoint | Returns | Use |
|---|---|---|
| `++camStatus` | `[{num, enabled, online, open, err, errDesc}]` | cheap health poll (794 B vs 27 KB) |
| `++caplist` | capture array **with classification bitmask** | observation record, media browser |
| `++cliplist` | clip array (empty here) | — |
| `++getpreview/<cam>/<date>/<file>` | JPEG thumbnail | image entity, browser thumbnails |
| `++deviceList` | `{onvif, bonjour, local, simulated, screen}` | discovery of addable devices |
| `++updateStatus` | `{active, err, errDesc, percentDownloaded}` | update entity progress |
| `++refreshLicenseInfo` | `{err, errDesc}` | — |
| `++dashImage` | rendered PNG chart | novelty |
| `++settings-web-access-info` | HTML list of all reachable URLs | config-flow hinting |

`++diskInfo`, `++soundFile`, `++settings-order` are referenced in client JS but returned 404 — likely POST-only or version-gated.

#### `++settings-cameras?format=json` — ~120 flat settings keys

This is the significant one. It returns a flat JSON object, and **the full AI trigger matrix is readable and writable**:

```
mcTriggerMotion   mcTriggerMotionH   mcTriggerMotionV   mcTriggerMotionA
aTriggerMotion    aTriggerMotionH    aTriggerMotionV    aTriggerMotionA
mcTriggerAudio  mcTriggerCamMd  mcTriggerCamP  mcTriggerCamPir  mcTriggerHome
motionSensitivity   vehicleSensitivity   animalSensitivity   audioSensitivity
motionMask   ccMovie   ccImage   mcMoviePre   mcMoviePost   mcMovieFps
brightness   contrast   transformation   overlayText   overlayPos   quality   fps
```

**This resolves the §8.10 mystery.** AI-class and arrival/departure trigger bits never fired because `mcTriggerMotionH/V/A` are all `false` on this server — only plain `mcTriggerMotion` is enabled. Nothing is broken; the capability is switched off.

**New v1 capability, available to no prior integration:**
- `switch.<cam>_trigger_on_human` / `_vehicle` / `_animal` — backed by `mcTriggerMotionH/V/A`, with `aTrigger*` equivalents for Actions mode.
- `number.<cam>_human_sensitivity` / `_vehicle_sensitivity` / `_animal_sensitivity`.

This serves the observation-record goal directly: enabling `mcTriggerMotionH` on the outdoor cameras makes SecuritySpy record and classify human events there, which is what the *last seen* sensors read.

#### ⚠️ Security: settings JSON leaks device credentials

`++settings-cameras?format=json` returns the camera's **`username` and `password` in plaintext** to any authenticated web-server user, alongside `permissiveSsl` and `portHttp`.

**Requirements this imposes:**
1. `diagnostics.py` and the library-side anonymizer **must** redact `username`, `password`, and any `*Ssl` / credential-shaped keys.
2. Settings payloads must **never** be logged, including at debug level.
3. Setup documentation should recommend a least-privileged SecuritySpy web user.

### 8.16 Custom CoreML model plugin — forward-compatibility requirement

SecuritySpy supports **user-supplied Apple CoreML classification models**. The user provides a model; SecuritySpy runs it per-camera at a configurable rate over the **presence rectangle** ROI (from the camera's motion-detection settings, scaled to the model's input dimensions) and delivers **raw model output values to clients in real time over the same `++eventStream`**.

Use cases: custom object detection, scene classification, anomaly scoring, any image-based inference — without modifying SecuritySpy.

**Verified on the 6.20 reference server:** per-camera `custom-model` field exists in `systemInfo`, `false` on all 11 cameras (feature present, not in use). The settings client references `presenceRect`.

Also newly observed in `settings-cameras` JSON: `humanSensitivity`, and animal sub-classification toggles `animalBird` / `animalFish` / `animalQuadruped` alongside `animalQuadruped=true`.

#### The architectural requirement

**Do not hardcode the classification vocabulary to `HUMAN` / `VEHICLE` / `ANIMAL`.**

A custom model emits arbitrary named outputs on the same stream. An integration whose parser recognises only the three built-in labels silently discards everything a custom-model user cares about — and correcting it later means changing the event schema, which breaks existing automations.

**Requirements:**
1. The event-stream parser treats classification labels as **open/dynamic data**, not an enum.
2. The event entity's payload carries the raw label/score set, whatever the labels are.
3. Consider dynamically-created sensors, or a generic per-camera "custom model output" event entity, for non-built-in labels.
4. v1 may scope *entities* to the three built-in classes — but the **parser and event schema must be forward-compatible**.

This is a cheap decision now and an expensive retrofit later.

#### Strategic note

Custom CoreML models are SecuritySpy's native analogue of an external vision pipeline, and the two are complementary rather than competing:

| | Custom CoreML model | External agent (e.g. Hermes) |
|---|---|---|
| Latency | per-frame, on-device | seconds, network round-trip |
| Cost | negligible | per-call inference |
| Output | labelled scores | open-ended natural language |
| Good for | "is this my car" | "a delivery driver left a box and walked back to a van" |

**Surfacing user-supplied models as Home Assistant entities is something no other camera integration offers** — UniFi Protect, Nest, and Ring all ship closed classification vocabularies. Worth naming as a differentiator.

### 8.15 Assessment of third-party research

A Gemini-sourced summary of `briis/securityspy`'s features was evaluated against the cloned source. **Three of four claims do not survive contact with the code.** Recorded because the same summary is likely to resurface.

| Claim | Verdict |
|---|---|
| "Passed AI detections into HA as standard binary sensors" | **False.** Classification was a state *attribute* (`event_object`) on a single motion binary sensor — see §8.13 and the project's own README example. |
| "Disable indoor recording when phone joins Wi-Fi" | **Unsupported.** A generic HA presence automation. The arm switches existed; the use case is invented colour. |
| "Supported RTSP for very low-latency playback" | **Backwards.** `config_flow` offers *disable RTSP stream*, and the README says disabling it "Gives better realtime live streaming." Users turned RTSP **off** for latency. |
| "Easy snapshot capture + rich push notifications" | **Accurate.** Matches the README examples and the shipped blueprint. |

**Method note:** prefer cloned source to generated summaries. The repository is public; the code is the authority.

### 8.18 The shipped web client is the real specification

`/Applications/SecuritySpy.app/Contents/Resources/Web` on the SecuritySpy host — 288 files, 2.7 MB, plus a `legacy/` tree. **This is the authoritative interface description**, and reading it corrected three field decodings that sample-based inference had gotten wrong (§8.12).

**Access note:** the copy at `/Applications/SecuritySpy.app` on the author's laptop is a stub with no `Web` directory. The real install is on the Mac mini, reachable as the `homelab` SSH alias (Tailscale). Read it over SSH.

**Structure:** `index.html` (the SPA shell, and where UI control definitions like `capFilter` decode API parameters), `js/` (28 files — `captures.js`, `clips.js`, `settings.js` at 93 KB, `Player.js`, `PtzPicker.js`, `MaskPicker.js`, `SchedulePicker.js`, `FolderPicker.js`), `settings-*.html` (11 pages), `css/`, `img/`, localised `de/` `fr/` `it/`, and `legacy/`.

**Additional endpoints catalogued from source**, beyond §8.12/§8.14: `dirList`, `dirShortcuts`, `dirValidity` (folder picker), `diskInfo`, `screenControl`, `ftDownload`, `doShell`, `doShortcut`, `addAllServerCams`, `addNVRCams`, `openUrl`, `openHomeHelper`, `userManual`, `testAuth`, `testDdns`, `testEmail`, `testUpload`, `submitLicenseFile`, `submitLicenseInfo`, `refreshLicenseInfo`, `store-pay`, `updateStart`, `updateCancel`, `updateStatus`, `ssSetSchedule`, `ssSetPreset`, `settings-order`, `settings-cameras-multi`, `settings-comp`, `settings-sched`, `clip`, `deleteclip`, `delete`, `setTags`.

**False lead worth recording:** `js/tracking.js` (31 KB) is a browser-fingerprinting library, not AI object tracking.

**Method:** when a decoding matters, read the client source rather than inferring from response samples. Sample-based inference produced three wrong answers here; the source produced unambiguous ones.

### 8.11 Probe scripts

`ss-probe-info.sh` and `ss-probe-eventstream.sh` in the session scratchpad; credentials read from `~/.securityspy.env` (mode 600, outside the repo), never echoed, passed via `curl -u` so they stay out of process listings. Reusable for regression checks against a live server.

---

## 7. Open Questions for the PRD

**Resolved by the 2026-08-09 probe (§8):** `CLASSIFY` shape (continuous, not momentary — binary sensors with threshold + debounce); CR-only framing; no per-camera recording flag; `MOTION_END` unreliable; HTTPS in use.

**Still open:**

1. **Concrete automation scenarios.** None captured despite two asks. Needed as acceptance criteria.
2. **Why was ONVIF abandoned?** Closest prior art in the author's own environment; the failure mode is a requirement. Note SecuritySpy itself talks ONVIF to these cameras (`device-name: ONVIF`), so the cameras support it — whatever failed was in HA's ONVIF integration or the double-consumption of streams.
3. **Children's-bedroom cameras** — does the integration hold any opinion on privacy, or is it purely the user's to compose? Currently assumed the latter.
4. **How does Hermes get triggered, and how does it fetch images** — HA camera proxy, or direct to SecuritySpy? Decides whether images must be exposed to HA only, or network-reachable. Note the server is on a tailnet (`ip2` = 100.90.186.57), which may make direct access simpler than expected.
5. **Multi-server support** — out for v1, but does the config-flow/unique-ID design need to leave room for it? (The `uuid` field makes this cheap to accommodate.)
6. **What confidence threshold and debounce window** should default for classification binary sensors? Needs tuning against real footage; must be user-configurable. Note §8.12 reduces the stakes — `++caplist`'s persisted `o` bitmask gives an authoritative per-capture answer that can correct a mistuned live threshold.
11. **Confirm `++caplist` `filter` semantics** (`0`/`2` = all, `1` = none, `3` = 65-item subset — of what?), and whether `o` can be queried/filtered server-side.
12. **Is `++caplist` `o` populated at capture close, or later?** Determines whether it can serve low-latency needs or only reconciliation.
13. **What is `i`** in `++caplist` (size units), and `g` (always 0)?
14. **Does `++cliplist` matter** — it returned empty; is it for a feature not in use here?
7. **Decode the `permissions` bitmask** (10207 observed). Could drive graceful degradation and a precise repair issue when the configured user lacks arm/disarm rights.
8. **Do AI-class and arrival/departure triggers fire** once enabled per-camera in SecuritySpy (§8.10)? Determines whether arrival/departure entities are viable.
9. **Switch vs select for arming** (§8.8) — the mode/schedule/override model is three-dimensional, not boolean. Architecture decision.
10. **Is `since-last-capture` a usable poll fallback** for the `image` entity's timestamp, or must it be driven purely by `FILE` events?
