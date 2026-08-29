---
title: "SecuritySpy 6.x Web API — Reverse-Engineered Reference"
status: living
created: 2026-08-09
updated: 2026-08-09
source_version: "SecuritySpy 6.20"
method: "Shipped web client source + live server probes"
---

# SecuritySpy 6.x Web API — Reverse-Engineered Reference

**Purpose.** The published specification at <https://bensoftware.com/securityspy/web-server-spec.html> is a partial and dated view of SecuritySpy 6.x. This document records what the software actually does, derived from two authoritative sources:

1. **The shipped web client** — `/Applications/SecuritySpy.app/Contents/Resources/Web` on the SecuritySpy host (288 files, 2.7 MB). This is the real interface description.
2. **Live probes** against a production 6.20 server (11 cameras).

**Access note.** On the reference setup, `/Applications/SecuritySpy.app` on the *laptop* is a stub with no `Web` directory. The real install is on the Mac mini, reachable as the `homelab` SSH alias over Tailscale.

**Method note.** Where this document and the published spec disagree, this document is correct — but verify against your own server. Sample-based inference produced three wrong field decodings before the client source corrected them; **read the source, don't guess from responses.**

---

## 1. Conventions

All endpoints are prefixed `++` in external URLs (`/++systemInfo`). The web client omits the prefix because the server adds it for same-origin requests.

**Authentication** — three forms:
- HTTP Basic: `https://user:pass@host:8001/++systemInfo`
- Query parameter: `?auth=<base64("user:pass")>` — survives URL-only contexts (ffmpeg, external consumers)
- **Resource-scoped token** (§1b) — undocumented

### 1b. Auth tokens — undocumented but real

SecuritySpy's **URL Generator** (Window menu in the Mac app) offers an *Authentication* option that emits a token instead of credentials:

> "the authentication token allows access to the specified resource only, without revealing the username/password, and will be invalidated if the account is changed or deleted"

Evidence in the app binary:
```
&auth=!%s%s                    ← the "!" prefix distinguishes a token from base64 credentials
.ss_file_token_database_v2
```

**The published spec documents only `auth=base64(user:pass)` and never mentions tokens.**

**Why it matters:** a resource-scoped token in an RTSP URL means ffmpeg never receives admin credentials, and they stay out of config entries, logs, and diagnostics. Token *generation* appears to be GUI-only — no HTTP endpoint or client-side path was found. **Exact format unverified.**

**Transport** — HTTPS is available and, when enabled, plain HTTP redirects to it (`301`). On the reference server: HTTP 8000 → HTTPS 8001. Certificates are issued for the DDNS hostname (`*.viewcam.me`), so LAN-IP access requires either hostname configuration or disabled verification.

---

## 2. Endpoint Catalogue

### 2.1 Documented in the published spec

| Endpoint | Purpose |
|---|---|
| `systemInfo?format=xml\|json` | Full configuration + camera list |
| `image?cameraNum=N` | Single JPEG snapshot |
| `video?cameraNum=N&vcodec=` | Live stream (see §7 — the client uses WebSocket) |
| `stream?cameraNum=N&vcodec=h264` | **RTSP URL** — the path HA's `stream` component wants |
| `hls`, `hls_mediaplaylist` | HLS variants |
| `multiplex?cameras=0,1,2` | Server-composited HTML grid |
| `audio` (GET/POST) | G.711 μ-law audio in/out |
| `download` | HTML/XML capture listing (superseded by `caplist`) |
| `getfile`, `getfilehb`, `getfilelb` | Download a capture (default/high/low bandwidth) |
| `ptz/controls`, `ptz/command`, `getptzcapabilities` | PTZ |
| `setSchedule`, `setPreset`, `cameramodes` | Arming |
| `settings-general\|display\|storage\|compression\|email\|web\|cameras` | Settings |
| `sounds`, `scripts` | Available sounds/AppleScripts (back the Actions settings) |
| `eventStream?version=3` | Live event stream |
| `triggermd?cameraNum=N` | Manual trigger |

### 2.2 NOT in the spec — used by the 6.x client

These are the interesting ones.

| Endpoint | Returns | Integration relevance |
|---|---|---|
| **`caplist`** | JSON capture list **with classification** | ⭐ The observation record. See §4 |
| **`camStatus`** | `[{num, enabled, online, open, err, errDesc}]` | ⭐ Cheap health poll — 794 B vs 27 KB |
| **`getpreview`** | JPEG thumbnail of a capture | ⭐ Image entity content + media thumbnails |
| `cliplist`, `clip`, `deleteclip` | Clip management | — |
| `setTags` | `POST setTags?tagId=N` | User tags on captures (undocumented feature) |
| `deviceList` | `{onvif, bonjour, local, simulated, screen}` | Discovery |
| `updateStatus`, `updateStart`, `updateCancel` | `{active, err, errDesc, percentDownloaded}` | `update` entity |
| `diskInfo` | Storage stats | Diagnostic sensors |
| `ssSetSchedule`, `ssSetPreset` | Arming writes | ⭐ See §5 |
| `ptzcommand` | PTZ execution (client form) | See §6 |
| `settings-web-access-info` | HTML list of all reachable URLs | Config-flow hinting |
| `refreshLicenseInfo`, `submitLicenseInfo`, `submitLicenseFile`, `store-pay` | Licensing | — |
| `dashImage` | Server-rendered PNG activity chart | Novelty |
| `dirList`, `dirShortcuts`, `dirValidity` | Folder picker | — |
| `testAuth`, `testDdns`, `testEmail`, `testUpload` | Config validation | Possibly useful in config flow |
| `doShell`, `doShortcut` | Execute shell/shortcut | ⚠️ Powerful; not for v1 |
| `addAllServerCams`, `addNVRCams` | Bulk camera add | — |
| `screenControl`, `ftDownload` | Screen capture feature | — |
| `settings-order`, `settings-cameras-multi`, `settings-comp`, `settings-sched`, `settings-uploads`, `settings-license` | Additional settings pages | — |

---

## 3. Event Stream

```
GET /++eventStream?version=3[&format=multipart]
```

A long-lived HTTP response that never terminates. Read incrementally.

### 3.1 Framing — ⚠️ the critical gotcha

**Lines are terminated by CR (0x0D) only. There are zero LF bytes.**

The published spec says *nothing* about line termination. Verified by hexdump over 1,341 events:

```
00000000  32 30 32 36 30 38 30 39  31 37 35 33 33 35 20 30  |20260809175335 0|
00000010  20 37 20 4d 4f 54 49 4f  4e 5f 45 4e 44 0d 32 30  | 7 MOTION_END.20|
```

A standard `readline()` never returns and the integration appears to hang. **This is the single most likely implementation bug in any SecuritySpy client.**

### 3.2 Record format

```
[TIME] [EVENT NUMBER] [CAMERA NUMBER] [EVENT] [INFO]
```

- `TIME` — 14 chars, `YYYYMMDDHHMMSS`
- `EVENT NUMBER` — monotonic **per-connection** counter starting at 0. Not a persistent ID.
- `CAMERA NUMBER` — camera number, or **`X`** when not camera-specific
- `INFO` — event-specific, may be absent

### 3.3 Event types

| Event | INFO payload |
|---|---|
| `MOTION` | `X Y W H` bounding box — **origin top-left** |
| `MOTION_END` | — (⚠️ unreliable, see §3.5) |
| `CLASSIFY` | `HUMAN n VEHICLE n ANIMAL n` — percentages 0–100 |
| `TRIGGER_M` / `TRIGGER_A` | reason bitmask (§3.4) |
| `FILE` | full path of completed recording |
| `ARM_C` / `DISARM_C` | continuous capture mode |
| `ARM_M` / `DISARM_M` | motion capture mode |
| `ARM_A` / `DISARM_A` | actions mode |
| `ONLINE` / `OFFLINE` | camera connectivity |
| `ERROR` | error code + description |
| `CONFIGCHANGE` | settings edited |
| `NULL` | heartbeat, every 10 s exactly, camera `X` |

### 3.4 Trigger reason bitmask

Bit 0 = LSB:

| Bit | Meaning | Bit | Meaning |
|---|---|---|---|
| 0 | Video motion detection | 9 | HomeKit event |
| 1 | Audio detection | 10 | Animal movement |
| 2 | AppleScript | 11 | Human arrival |
| 3 | Camera event | 12 | Human departure |
| 4 | Web server event | 13 | Vehicle arrival |
| 5 | Triggered by another camera | 14 | Vehicle departure |
| 6 | Manual trigger | 15 | Animal arrival |
| 7 | Human movement | 16 | Animal departure |
| 8 | Vehicle movement | | |

⚠️ **Bits 7–16 only fire if the corresponding `mcTriggerMotionH/V/A` settings are enabled** (§8). On a default install only bit 0 appears.

### 3.5 Empirical behaviour — 100 s capture, 1,341 events

| Event | Count |
|---|---|
| `MOTION` | 915 |
| `TRIGGER_M` | 202 |
| `CLASSIFY` | 191 |
| `TRIGGER_A` | 15 |
| `NULL` | 10 |
| `MOTION_END` | 6 |
| `FILE` | 2 |

**`CLASSIFY` is a per-frame inference stream, not a detection event.** 191 events on one camera in 95 s, 0–2 s apart, with confidence swinging violently for a single subject:

```
20, 69, 19, 77, 88, 8, 54, 25, 5, 18, 18, 49, 13, 17, 16, 97, 96, 99, 99, 28, 51, 71, 64, 91, 97
```

**`MOTION_END` is unreliable:**

| Camera | `MOTION` | `MOTION_END` |
|---|---|---|
| 10 | 467 | **0** |
| 7 | 383 | 1 |
| 1 | 56 | 5 |

Clients **must** implement their own inactivity timeout.

**`FILE` lags ~96 s** — it fires on episode completion, after the 30 s post-roll. Not a low-latency trigger.

### 3.6 The vendor's own client never uses the event stream

It polls `caplist` and `camStatus`. The event stream is a third-party-only feature, which explains its thin documentation and why `MOTION_END`'s unreliability went unnoticed. **Assume no vendor testing here.**

---

## 4. `caplist` — the capture list ⭐

```
GET /++caplist?cams=4,&startDate=2026-08-09&endDate=2026-08-09&filter=0
```

Note the **trailing comma** in `cams`. Returns a JSON array.

### 4.1 Fields (decoded from `js/captures.js`)

| Field | Meaning |
|---|---|
| `c` | camera number |
| `t` | capture type: **`1` = movie, `2` = JPG image** |
| `s` | **start time, seconds since midnight** (`63319` → 17:35:19) |
| `d` | duration, seconds |
| `i` | (unconfirmed) |
| `g` | **user tag ID** — settable via `POST setTags?tagId=N`, rendered `img/tag-N.png` |
| `m` | **file size** (client calls `SizeStr(file.m)`) |
| `z` | (unconfirmed, tracks `m`) |
| `f` | folder date `YYYY-MM-DD` |
| `n` | filename — encodes date, time, trigger letter, camera name |
| `a` | archive flag — used in `getpreview`/`getfile` URLs |
| `u` | unread/new flag |
| **`o`** | **object classification bitmask: `1`=human, `2`=vehicle, `4`=animal** |

### 4.2 `filter` is class-aware server-side ⭐

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

**The server filters by object class.** A "last human seen" value is one request — `filter=5`, newest entry — not a full fetch plus client-side bitmask filtering.

**`o` is persisted per capture.** Classification is not only a transient stream signal; it is stored against every recording. This enables poll-derived state that is correct after a restart and self-heals from missed events.

### 4.3 Related URL forms

```
getpreview?/{cam}/{folderDate}/{filename}?archive={a}     # note the double-? construction
getfile…?lowBandwidth={0|1}&forceDownload=1&archive={a}
POST setTags?tagId={N}                                     # form-urlencoded body lists captures
```

`getpreview` returns a JPEG thumbnail — verified 640×360, ~95 KB.

---

## 4b. Media retrieval — files, ranges, and on-demand clips ⭐

### 4b.1 `getfile` — with Range support

```
GET /++getfile/<cam>/<YYYY-MM-DD>/<url-encoded filename>?lowBandwidth=0|1&forceDownload=0|1&archive=0|1
```

**Verified: returns `HTTP 206 Partial Content` and honours `Range` headers.** This is what HA's media browser needs for seeking.

| Variant | Content-Type |
|---|---|
| `getfile` | `video/quicktime` |
| `getfilehb` | `video/quicktime` (high bandwidth) |
| `getfilelb` | **`video/mp4`** (low-bandwidth transcode — more browser-friendly) |

`forceDownload=1` switches the type to `application/force-download`.

Client playback patterns:
```html
<video><source src="getfile/{c}/{f}/{n}?lowBandwidth=0&archive={a}&session-id={random12}"></video>
<img src="getfile/{path}?lowBandwidth=0">   <!-- for t==2 JPG captures -->
```

The server sets a `ss-session-id` cookie even under Basic auth (`sessionLen` in `settings-web`). Not required — Basic auth works standalone.

### 4b.2 `++clip` — on-demand time-range extraction ⭐⭐

**This is not merely a saved-clip list. It generates video for an arbitrary time window.**

```
GET /++clip?cameraNum=N&movieType=0|1&start=<epoch>&end=<epoch>
```

- `movieType`: **`0` = Motion Capture, `1` = Continuous Capture**
- `start` / `end`: **Unix epoch seconds** (from `clips.js`: `Math.floor(jsDate.getTime()/1000)`)
- Returns `206` / `video/mp4`
- **404 means "no footage found for that time period"** — the client probes with `Range: bytes=0-1` first and treats 404 as a user-facing message

**Generating a clip persists it server-side**, appearing in `cliplist`:

```json
[{"c": 3, "t": 1, "s": 1786322489, "e": 1786322529, "z": 0.49}]
```

Remove with `GET ++deleteclip?cameraNum=&movieType=&start=&end=` (same four parameters).

**Integration opportunity:** a `securityspy.get_clip(camera, start, end)` service produces a shareable MP4 of any incident window — "the 30 seconds around that detection." No other HA camera integration offers arbitrary-window extraction.

### 4b.3 ⚠️ `t` is overloaded across endpoints

| Context | `0` | `1` | `2` |
|---|---|---|---|
| `caplist.t` | — | movie | JPG image |
| `clip.movieType` / `cliplist.t` | Motion Capture | Continuous Capture | — |

**Same letter, different meaning.** Do not share an enum between them.

### 4b.4 Deletion

```
POST /++delete?v6=1
Content-Type: application/x-www-form-urlencoded

delete=<c>/<f>/<n>?archive=<a>&delete=<...>
```

Repeated `delete=` entries. The `v6=1` flag implies a legacy v5 format. Destructive — out of scope for v1.

---

## 5. Arming — three-dimensional ⭐

```
GET /++ssSetSchedule?cameraNum=N&schedule=<id>&override=<id>&mode=<letters>
```

### 5.1 `mode` is a concatenated letter string

From `js/script.js`:

```javascript
'&mode=' + (ssCC.checked?'C':'') + (ssMC.checked?'M':'') + (ssA.checked?'A':'')
```

- `C` = Continuous Capture, `M` = Motion Capture, `A` = Actions
- `mode=CMA` sets all three at once; `mode=M` sets only motion capture
- Modes are **independent booleans**, not mutually exclusive — which is why `alarm_control_panel` (a single-state machine) is the wrong HA platform

### 5.2 `override` — 16 values

> ⚠️ **See `securityspy-6.21-verification.md` §4.4.** The wire values are **0–14 (fifteen)**;
> the `-1` "Unchanged" entry is a client-only sentinel.


| id | Meaning | id | Meaning |
|---|---|---|---|
| −1 | Unchanged *(client sentinel)* | 7 | Disarmed For 3 Hours |
| 0 | None | 8 | Armed For 3 Hours |
| 1 | Disarmed Until Next Scheduled Event | 9 | Disarmed For 4 Hours |
| 2 | Armed Until Next Scheduled Event | 10 | Armed For 4 Hours |
| 3 | Disarmed For 1 Hour | 11 | Disarmed For 5 Hours |
| 4 | Armed For 1 Hour | 12 | Armed For 5 Hours |
| 5 | Disarmed For 2 Hours | 13 | Disarmed For 6 Hours |
| 6 | Armed For 2 Hours | 14 | Armed For 6 Hours |

### 5.3 Schedules are user-definable, not a fixed set

The four schedules seen on a default install (`Disarmed 24/7`, `Armed 24/7`, `Armed Sunrise To Sunset`, `Armed Sunset To Sunrise`) are **defaults**. Users define arbitrary weekly schedules.

**Data model** (from `js/SchedulePicker.js`): a schedule is a JSON array of `[start, end]` pairs in **minutes since week start**, range `0..10079` (7 × 1440). `end < start` means the block wraps the week boundary.

```json
[[480, 1020], [2400, 2760]]
```

Saved via `settings-sched` POST as `sched={"name":…,"id":…,"objects":[[s,e],…]}`.

**Integration consequence: schedule must be a dynamic `select` populated from `schedule-list`, never a hardcoded enum.**

---

## 6. PTZ

```
GET /++ptzcommand?cameraNum=N&code=C&speed=S        # client form
GET /++ptz/command?cameraNum=N&command=C&speed=S    # documented form
```

### 6.1 Command codes (`js/PtzPicker.js`)

| Code | Action | Code | Action |
|---|---|---|---|
| 1 | Left | 8 | Up-Left |
| 2 | Right | 9 | Up-Right |
| 3 | Up | 10 | Down-Left |
| 4 | Down | 11 | Down-Right |
| 5 | Zoom In | **12 + N** | **Recall preset N** |
| 6 | Zoom Out | **112 + N** | **Save preset N** |
| 7 | Home | 99 | Stop moving |

`speed` is 0–100; the client sends `speed:100` for preset recalls.

### 6.2 Capability bitmask (`ptz-features`)

`1` pan/tilt · `2` home · `4` zoom · `8` presets · `16` speed · `32` continuous.
`63` = all. Preset names are exposed as `preset-name-1` … `preset-name-10`.

---

## 7. Live video — WebSocket

`js/Player.js` opens:

```
wss://host:port/video?cameraNum=N&vcodec=jpeg|h264|h26x&acodec=ulaw|&fps=&apause=1&sizeFraction=N
```

with a binary opcode protocol: `OP_SIZE=1`, `OP_PLAY_PAUSE=2`, `OP_SCHED=3`, `OP_OVERR=4`, `OP_AUDIO=5`. H.265 is negotiated via `h265Available`.

This is **not** the documented multipart MJPEG path, and explains the `HTTP 101 Upgrade` seen in HAR captures.

**Not relevant to Home Assistant**, which wants RTSP via `++stream`.

See §7b for audio — the earlier "μ-law only" claim in this document was wrong.

---

## 7b. Audio — corrected ⚠️

**An earlier version of this document claimed audio is G.711 μ-law only and that AAC is an unfixable upstream constraint. That was wrong.**

### Documented `++stream` parameters (from the published spec)

```
stream?cameraNum=X[&width=X][&height=X][&fps=X][&vcodec=X][&acodec=X]
```

| Parameter | Values |
|---|---|
| `vcodec` | `h264` (default), `h265`, `h26x` (server chooses) |
| `acodec` | **`aac` (default)**, `ulaw`, `pcm`, `none` |
| `width` / `height` | output pixel dimensions |
| `fps` | target frame rate |

⚠️ **`++stream` is RTSP-only.** Every HTTP `GET` returns 404 — hence the URL Generator emitting `rtsp://host:8000/++stream?...`.

### `++audio` — AAC is real

| Request | Response |
|---|---|
| `++audio?cameraNum=N` | `audio/basic` (G.711) |
| `++audio?cameraNum=N&format=aac` | **`audio/aac`** — verified, real data |
| `++audio?cameraNum=N&sampleRate=16000` | `audio/basic` |
| `POST ++audio?cameraNum=N` | two-way talk |

### But RTSP audio was not observed

`ffprobe` against a live 6.20 server returned **video only** (`Stream #0:0: Video: h264`) for `acodec=aac`, `acodec=ulaw`, and on cameras reporting `has-audio=true`.

**Likely explanation:** all cameras on the reference server report `audio-device=''`, `network-audio=true`, and source `audio-format` of **`u-Law` or `A-Law`**. The cameras deliver G.711; AAC requires SecuritySpy to transcode. It demonstrably *can* (`++audio?format=aac` works), but no audio track appeared on RTSP in testing.

**Status: plausible but unproven.** Do not promise HA stream audio; do not rule it out. Worth a dedicated investigation — SDP inspection, `h265`/`h26x`, explicit `width`/`height`, and a camera whose source is not G.711.

**Note:** source `audio-format` is **`A-Law` on 6 of 11 cameras**, not universally μ-law. Do not assume μ-law on the raw path.

### ⚠️ Credentials in RTSP URLs

`rtsp://user:pass@host/...` **leaks into ffmpeg logs, HA debug logs, diagnostics, and error messages** — observed firsthand when `ffprobe` echoed a full URL including the password.

This is exactly what SecuritySpy's auth token (§1b) is for, and is a strong argument for supporting token auth in any client's configuration.

## 8. Settings

### 8.0 The read/write contract ⭐ (verified by live round-trip)

**READ** — `GET ++settings-<page>?format=json` returns a flat JSON object.

```
GET /++settings-cameras?cameraNum=3&format=json
```

⚠️ `cameraNum` is **required** for the cameras page — omitting it returns **HTTP 500**.

| Page | JSON? | Notes |
|---|---|---|
| `settings-cameras` | ✅ | requires `cameraNum` |
| `settings-general` `-display` `-storage` `-email` `-web` `-uploads` | ✅ | |
| `settings-comp` | ✅ | note: **`comp`**, not `compression` |
| `settings-sched` | ✅ | |
| `settings-cameras-multi` | ❌ | HTML only |
| `settings-license` | ❌ | HTML only |
| `settings-order` | ❌ | 404 on GET |

**WRITE** — `POST` to the bare endpoint, form-urlencoded:

```
POST /++settings-cameras                    ← NO query string (query form returns 404)
Content-Type: application/x-www-form-urlencoded

formData&cameraNum=3&overlayText=Front%20Gate
```

Three rules, all load-bearing:

1. **`cameraNum` goes in the body**, not the query string.
2. **The body must begin with the literal sentinel `formData`.** From `GetFormKeyValueString()` in `js/script.js`: `let str='formData'; for(pair of formData.entries()) str+='&'+k+'='+v`.
3. **Booleans are written as `1`/`0`**, keyed by *element id* — checkboxes are serialised separately from the form data. **Note the asymmetry: JSON reads return `true`/`false`, writes require `1`/`0`.**

Response is `200` with a JSON acknowledgement:
```json
{"camUpdate": {"num": "3", "name": "Driveway"}}
```
May also return `{"reload": true}` when the change requires a client reload.

**Form actions** (from the `settings-*.html` `<form action=…>` attributes): `settings-cameras`, `settings-cameras-multi`, `settings-comp`, `settings-display`, `settings-email`, `settings-general`, `settings-sched`, `settings-storage`, `settings-uploads`, `settings-web`.

#### ⭐ Partial writes are safe — verified

Posting only `formData&cameraNum=3&overlayText=…` left every other field untouched: `mcTriggerMotion`, `mcTriggerMotionH`, `motionSensitivity`, `humanSensitivity`, `mcMoviePre`, `mcMoviePost`, `ccMovie`, `brightness`, `name` all retained their prior values.

**A client can write a single setting without read-modify-write of the whole ~120-key page.** This removes a whole class of race condition and makes per-setting entities straightforward.

### 8.1 `settings-cameras?format=json` — ~120 flat keys

> ⚠️ **Corrections in `securityspy-6.21-verification.md` §4.2 / §5.5.** `mcTriggerCamP`
> does not exist (it is `mcTriggerCamP1` / `mcTriggerCamP2`); the Arrives/Departs trigger
> family is missing; and this list covers only *named* fields, so it omits the 82 id-only
> checkbox keys — including **`enabled`**, the camera enable/disable write.


**AI trigger matrix — readable and writable:**

```
mcTriggerMotion   mcTriggerMotionH   mcTriggerMotionV   mcTriggerMotionA
aTriggerMotion    aTriggerMotionH    aTriggerMotionV    aTriggerMotionA
mcTriggerAudio  mcTriggerCamMd  mcTriggerCamP  mcTriggerCamPir  mcTriggerHome
```

`H`/`V`/`A` = Human/Vehicle/Animal. `mc` = motion capture, `a` = actions.

**Sensitivities:** `motionSensitivity`, `humanSensitivity`, `vehicleSensitivity`, `animalSensitivity`, `audioSensitivity` (plus `*Text` variants).

**Animal sub-classes:** `animalBird`, `animalFish`, `animalQuadruped`.

**Recording:** `ccMovie`, `ccImage`, `ccImageInterval`, `ccRemoveAge`, `mcMoviePre` (5 s), `mcMoviePost` (30 s), `mcMovieFps`, `mcDaily`.

**Image:** `brightness`, `contrast`, `transformation`, `quality`, `fps`, `overlayText`, `overlayPos`.

**Masks:** `privacyMask`, `motionMask`, `presenceRect` (see §8.2).

**Actions:** `aScript`, `aSoundCam`, `aSoundMac`, `aShellCommand`, `aDelay`, `aEmail`.

### 8.2 Mask / ROI wire format

From `js/MaskPicker.js` — rectangle mode serialises as a 4-tuple string:

```
presenceRect = "x,y,w,h"
```

Grid mode (`motionMask`) is a long comma-separated list of `0`/`1` cells.

**`presenceRect` is the ROI used by both presence detection and the custom CoreML model** — meaningful to expose for custom-model users.

### 8.2b Other settings pages

**`settings-sched`** — `{schedules: [], presets: [], sunriseOffset1, sunsetOffset1, sunriseOffset2, sunsetOffset2}`.

Both arrays were **empty** on the reference server, confirming the four schedules in `systemInfo`'s `schedule-list` (ids 0–3) are **built-in defaults**; these arrays hold only *user-defined* additions. Sunrise/sunset offsets tune the "Armed Sunrise To Sunset" schedules.

**`settings-storage`** — `tag-1` … `tag-7` booleans (the tag definitions behind `caplist`'s `g` field and `setTags`), plus retention: `removeByAge`, `removeBySpace`, `removeAgeSys` (10), `removeAgeNonSys` (60), `removeGbSys/NonSys`, `usageWarningGb`, `diskWaitTime`, `globalStorage` (`/Volumes/Surveillance`), `archiveStorage`, `archiveMode`.

**`settings-web`** — `accounts` (where `PERM_*` bits are assigned per user), `portHttp`/`portHttps` + WAN variants, `http`/`https` enable, `ddnsName`/`ddnsStatus`/`wanAddress`, `sessionLen`, `corsDomains`, `geoblockList`/`geoblockType`, `listenIps`, `publicResources`, `iframe`, `legacy`, `videoPassthrough`, `hlsMaxFps`/`hlsMaxRes`, `autoNatHttp`/`autoNatHttps`, `screenControl`, `log`.

`sessionLen` and `corsDomains` may matter for a browser-hosted client; `accounts` is where per-user permissions (§9) are configured.

### 8.3 ⚠️ Security: settings JSON leaks device credentials

`++settings-cameras?format=json` returns the camera's **`username` and `password` in plaintext** to any authenticated web-server user, alongside `permissiveSsl` and `portHttp`.

**Requirements for any client:**
1. Redact `username`, `password`, and credential-shaped keys in diagnostics and anonymizers.
2. Never log settings payloads, including at debug level.
3. Recommend a least-privileged SecuritySpy web user.

---

## 9. Permissions bitmask ⭐

> ⚠️ **Incomplete — see `securityspy-6.21-verification.md` §4.1.** Verified against the
> 6.21 account editor: this table is missing **bit 4 (16) "Set camera settings"**,
> **bit 12 (4096) "Hide download options"** (a *negative* permission) and
> **bit 13 (8192) "Receive push streams"**. Bit 1 (value 2) is set on live cameras and is
> named nowhere. The nine bits listed below are correct.


From `js/script.js` — decodes the per-camera `permissions` field:

| Constant | Bit | Value | Meaning |
|---|---|---|---|
| `PERM_LIVEVIDEO` | 0 | 1 | View live video |
| `PERM_FILES` | 2 | 4 | Access captured files |
| `PERM_FILEDEL` | 3 | 8 | Delete files |
| `PERM_CAMCONTROL` | 6 | 64 | Camera control (incl. PTZ movement) |
| `PERM_SCHED` | 7 | 128 | Arm/disarm, set schedules |
| `PERM_PTZSET` | 8 | 256 | Save PTZ presets |
| `PERM_AUDIORCV` | 9 | 512 | Receive audio |
| `PERM_TRIGGER` | 10 | 1024 | Manually trigger |
| `PERM_AUDIOSND` | 11 | 2048 | Send audio (two-way talk) |

Observed `10207` = `LIVEVIDEO + FILES + FILEDEL + CAMCONTROL + SCHED + AUDIORCV + TRIGGER + AUDIOSND`.

**Integration consequence:** pre-flight capability per camera and **skip creating entities the user is not permitted to use**, rather than creating permanently-unavailable ones. Raise a precise repair issue when permissions are insufficient for a requested feature.

---

## 10. `systemInfo` — 69 per-camera fields

> ⚠️ **See `securityspy-6.21-verification.md` §4.3.** On 6.21 the document has six
> top-level keys (`camera-list`, `schedule-list`, `schedule-override-list`,
> `schedule-preset-list`, `group-list`, `server`) and **72** per-camera fields.


**Server block** (hub device + diagnostics):

```
version 6.20        uuid <stable server id>      bonjour-name <host>.local
camera-count        cpu-usage                    memory-pressure
archive-status      new-version                  cert-expiry-days / cert-expiry-time
http-enabled/port   https-enabled/port           ddns-name  wan-address
ip1  ip2            current-local-time           seconds-from-gmt
```

`uuid` is the **stable hub identifier** — use it for device `identifiers` and unique-ID prefixes, never hostname or IP.
`new-version` backs an `update` entity.

**Per-camera** — 69 fields, notably:

| Field | Use |
|---|---|
| `number` | ⭐ stable key — names are user-editable |
| `connected` | availability |
| `cc-mode` / `mc-mode` / `a-mode` | armed/disarmed per mode |
| `cc-schedule-id` / `mc-schedule-id` / `a-schedule-id` | current schedule |
| `*-schedule-override` | current override |
| `time-since-last-motion` | ⭐ seconds-ago → timestamp sensor; **poll fallback** |
| `since-last-capture`, `time-since-last-frame` | freshness counters |
| `current-fps`, `data-rate` | health sensors |
| `last-error`, `last-error-description` | error surface |
| `ptz-features`, `preset-name-1..10` | PTZ |
| `permissions` | §9 |
| `storage-path` | capture location |
| `video-width/height/format`, `port-rtsp`, `address` | stream construction |
| `has-audio`, `audio-format` | audio capability |
| `custom-model` | §11 |
| `motion-sensitivity` | detection tuning |

**Confirmed absent** — must come from the event stream or `caplist`: any recording-active flag, any classification field, any motion-active boolean.

**Client-side camera object** (`_cams`): `num`, `name`, `perm`, `demo`, `type`, `shortcuts`, `ptz`, `open`, `online`, `err`, `errDesc`, `enabled`, `audior` (receive), `audios` (send), `pnames` (preset names).

Note `online` / `enabled` / `open` are **three distinct states**, exposed by `camStatus`.

---

## 11. Custom CoreML models

SecuritySpy runs **user-supplied Apple CoreML classification models** per camera at a configurable rate, over the `presenceRect` ROI (scaled to model input dimensions), delivering **raw model outputs over the same event stream**.

`systemInfo` exposes a per-camera `custom-model` boolean. The web client contains **no** CoreML references — this is configured in the macOS app.

**The published spec does not mention this feature at all**, so the event payload shape is undocumented and must be discovered empirically.

**Architectural requirement: do not hardcode the classification vocabulary to `HUMAN`/`VEHICLE`/`ANIMAL`.** A custom model emits arbitrary labels on the same stream. Parsers must treat labels as open data, or custom-model users are silently locked out — and correcting it later means changing the event schema.

---

## 12. Web client structure

`/Applications/SecuritySpy.app/Contents/Resources/Web` — 288 files, 2.7 MB.

| Path | Contents |
|---|---|
| `index.html` | SPA shell. **UI control definitions decode API parameters** (e.g. `capFilter` → §4.2) |
| `js/captures.js` | `caplist`, `getpreview`, `setTags`, capture rendering |
| `js/clips.js` | `cliplist`, `clip`, `deleteclip` |
| `js/settings.js` (93 KB) | All settings pages, `camStatus`, `deviceList`, update flow |
| `js/script.js` | ⭐ `PERM_*` constants, `ssSetSchedule`, `ssSetPreset` |
| `js/Player.js` | WebSocket live video |
| `js/PtzPicker.js` | ⭐ `kPtz*` command codes |
| `js/SchedulePicker.js` | ⭐ Weekly schedule data model |
| `js/MaskPicker.js` | Mask / `presenceRect` wire format |
| `js/FolderPicker.js` | `dirList`, `dirShortcuts`, `dirValidity` |
| `settings-*.html` (11) | Settings forms — field names map to settings keys |
| `legacy/` | Older client, excluded from analysis |
| `de/` `fr/` `it/` | Localised copies |

**False lead:** `js/tracking.js` (31 KB) is a browser-**fingerprinting** library, not AI object tracking.

---

## 13. Summary of divergences from the published spec

| Topic | Spec | Reality |
|---|---|---|
| Line termination | **Silent** | CR-only; `readline()` hangs |
| `MOTION_END` | "issued after MOTION" | Frequently never sent |
| `settings-*` | POST only | `GET ?format=json` works, ~120 keys |
| `caplist` etc. | Absent | 25+ endpoints the client uses |
| Classification storage | Not mentioned | Persisted per capture (`o` field) |
| Class-filtered queries | Not mentioned | `filter=5/6/7` |
| `permissions` | Not decoded | `PERM_*` constants in client |
| Schedule model | "0–3" | Arbitrary user-defined weekly blocks |
| Custom CoreML | Absent | Supported; emits arbitrary labels |
| Credential exposure | Not mentioned | Settings JSON leaks camera passwords |

**Conclusion: treat the shipped web client as the authoritative interface description, and verify everything against a live server.**
