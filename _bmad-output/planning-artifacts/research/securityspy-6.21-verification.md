---
title: SecuritySpy 6.21 — infrastructure and call verification
date: 2026-08-29
method: "Shipped app-bundle source read on the homelab + authenticated read-only probes"
server: "SecuritySpy 6.21 on homelab (macOS 26.6.2), 11 cameras"
supersedes_partially: securityspy-api-reference.md
---

# SecuritySpy 6.21 — Infrastructure and Call Verification

Companion to `securityspy-api-reference.md` (built against **6.20**). This pass read the
shipped web client out of the application bundle on the homelab and confirmed the wire
behaviour with authenticated read-only probes against the live **6.21** server.

**Every claim below is either "confirms the reference doc" or "corrects it", with the
evidence named.** Nothing here is inferred from behaviour alone where source was available.

## 1. Method and scope

| | |
|---|---|
| Source read | `/Applications/SecuritySpy.app/Contents/Resources/Web` (client) and `Contents/MacOS/SecuritySpy` (`strings` only) |
| App version | `CFBundleShortVersionString` = **6.21**; `systemInfo.server.version` = `6.21` |
| Probes | `GET` throughout, plus **one** authorised settings write (§5.8), via the repo's gitignored `.env` credentials |
| Probe account | A **least-privileged** web user — `permissions` = `839` on all 11 cameras |
| Second account | A temporary account cycled **Live → Live+Captures → Administrator** to A/B the permission surface, **since deleted** (confirmed: it now returns `401`) |
| Live state changes | Jensen unplugged one camera and disabled another, on request, to observe the fault and disabled paths (§5.10, §5.12) |
| Not done | The `++ssSetSchedule` write was never performed; it remains the only `client-source` operation in the OpenAPI description |

The probe account being unprivileged is not a limitation to work around — it is what exposed
the permission behaviour in §5, which is the most consequential finding here.

**The pass is complete.** All seven gaps in `verification-gaps.md` are closed, seven defects
were found (five specced as stories 1.11–1.15, two carrying decisions rather than code), and
8 of the 9 operations in `aiosecurityspy/docs/securityspy-openapi.yaml` now carry
`x-verification: live-6.21`. Two findings changed how the *integration* must be built rather
than the library: the inventory-of-record choice in §5.12, and the non-static permission mask
in §5.11.

## 2. Infrastructure

**The web client is a static bundle the server templates on serve.** `Web/index.html`
declares `var _cams; var _isAdmin; var _isAuth; ...` and never assigns them, and
`<select id="ssSchedSelect">` / `<select id="ssCamSelect">` ship **empty** — yet
`script.js:154` reads `ssCamSelect.options.length` during `IndexLoad()`. The server fills
these in before the page reaches the browser. Reading the on-disk HTML therefore shows the
*shape* of the UI but never the data; the data has to come from `++systemInfo`.

**Two path surfaces, and the `++` prefix is load-bearing.** Both forms reach the same
handler when authenticated, but they behave differently when not:

| Request | Authenticated | Unauthenticated |
|---|---|---|
| `GET /++systemInfo?format=json` | `200` | **`401`** (Basic challenge) |
| `GET /systemInfo?format=json` | `200` | **`303`** (redirect to the login page) |

The web client uses **bare** paths throughout (`fetch('camStatus')`, `fetch('ssSetPreset?id=')`)
because it holds a session cookie. A library using Basic auth must always use `++`: a bare
path on an expired credential yields a `303`, which this library maps to *"server redirected;
if the server uses TLS, construct the client with use_https=True"* — a completely misleading
diagnosis of an auth failure.

**Transport surfaces in 6.21:**

1. **HTTP `++` API** — what this library speaks.
2. **WebSocket** at `/video?cameraNum=N&vcodec=…&acodec=…&fps=…&apause=1&sizeFraction=N&auth=<token>`,
   binary opcodes `OP_SIZE=1 OP_PLAY_PAUSE=2 OP_SCHED=3 OP_OVERR=4 OP_AUDIO=5` (`Player.js:13-17,313`).
3. **Form POST** to the bare settings actions, per `GetFormKeyValueString` (§4).

Note the WS URL carries **`&auth=<token>`**, which the reference doc's §7 URL omits — it ties
to the undocumented auth tokens in §1b.

## 3. Confirmed — the reference doc is right

- **§8.0 `GetFormKeyValueString`** is verbatim correct (`script.js:101-107`), including that
  checkboxes are serialised **separately, keyed by element `id`, as `1`/`0`**, appended after
  the named `FormData` entries.
- **§8.0 form actions** — `settings-comp` and `settings-sched` really are the action names
  even though the files are `settings-compression.html` / `settings-scheduling.html`.
- **§7 WebSocket** URL shape and all five opcodes.
- **§9** — every one of the nine bits it lists is correct (`script.js:2-10`).
- **§10 per-camera schedule keys** — the JSON really is `cc-schedule-id`, `mc-schedule-id`,
  `a-schedule-id`, `cc-schedule-override`, … as the library already decodes them. The binary
  also contains `schedule-id-cc` spellings, but those are the **XML** tag forms; the JSON
  keys the library uses are correct. *(Checked specifically because the XML spellings look
  like a decoding bug — they are not.)*
- **§2.2 `camStatus`** — exactly `[{num, enabled, online, open, err, errDesc}]`, a bare
  top-level JSON array.

## 4. Corrections to the reference doc

### 4.1 §9 permissions is missing three bits ⭐

`settings-web.html`'s account editor is authoritative — each permission checkbox has id
`p<bitIndex>` and `AccountPicker.js:90` computes `1 << parseInt(box.id.slice(1))`:

| Bit | Value | Label in the app | In §9? | In the library? |
|---|---|---|---|---|
| 0 | 1 | Get live video and images | ✅ | ✅ |
| 2 | 4 | Get captured footage | ✅ | ✅ |
| 3 | 8 | Delete captured footage | ✅ | ✅ |
| **4** | **16** | **Set camera settings** | ❌ | ❌ |
| 6 | 64 | Camera Control (PTZ) | ✅ | ✅ |
| 7 | 128 | Change schedules | ✅ | ✅ |
| 8 | 256 | Set PTZ preset positions | ✅ | ✅ |
| 9 | 512 | Get live audio | ✅ | ✅ |
| 10 | 1024 | Trigger motion detection | ✅ | ✅ |
| 11 | 2048 | Send live audio (two-way audio) | ✅ | ✅ |
| **12** | **4096** | **Hide download options** | ❌ | ❌ |
| **13** | **8192** | **Receive push streams** | ❌ | ❌ |

`PERM_NODOWNLOAD = (1<<12)` also appears in `script.js:11`. Two things matter about it:
it is a **negative** permission — set means *deny* — so it must never be fed through a
"does this camera grant X" helper that assumes set-means-allow.

**Bit 1 (value 2) remains unexplained.** It is set on all 11 live cameras
(`permissions: 839` = bits 0,1,2,6,8,9) but is named neither in `script.js` nor in the
account editor. Treat as reserved; do not assign it a meaning.

### 4.2 §8.1 trigger key names are wrong in one place, incomplete in another

- `mcTriggerCamP` does not exist. The real ids are **`mcTriggerCamP1`** and
  **`mcTriggerCamP2`** (and likewise `aTriggerCamP1` / `aTriggerCamP2`).
- §8.1 omits an entire trigger family present on the page: `mcTriggerArrives`,
  `mcTriggerDeparts`, `aTriggerArrives`, `aTriggerDeparts`, each with `A`/`H`/`P`/`V`
  variants, plus `triggerPopupA|H|P|V`.

### 4.3 §10 `systemInfo` structure

The doc describes a "server block" and "per-camera" fields. The actual document has
**six top-level keys**:

```
camera-list  schedule-list  schedule-override-list  schedule-preset-list  group-list  server
```

Per-camera field count is **72** on 6.21, not the documented 69.

### 4.4 §5.2 override count

"16 values" is off by one: the wire values are **0–14 (fifteen)**. The `-1` that appears in
`index.html`'s `ssOverrideSelect` is a **client-only "Unchanged" sentinel**, absent from the
server's own `schedule-override-list` and absent from `live-cam.html`'s copy of the select.

Display names also differ by surface — the settings UI says *"Disarmed Until Next Scheduled
Event"* where `systemInfo` says *"Disarmed Until Schedule Event"*. **Prefer the server's
`schedule-override-list` names**; they are the ones a consumer can actually fetch.

### 4.5 §8.0 settings pages

`settings-audio` is a real form action (`settings-audio.html`) and is missing from the doc's
list of ten. `settings-order` is **POST-only** with body `order=4,5,6,…`
(`settings.js:727-733`) — consistent with the doc's "404 on GET", but it is a real endpoint,
not an absence.

## 5. New findings

### 5.1 `SS-UUID` is in every response header ⭐

```
Server: BBVS/6.0/fUCdlMLDp4tbTmSgcbJZ
SS-UUID: fUCdlMLDp4tbTmSgcbJZ
```

This is byte-identical to `systemInfo.server.uuid`, and it is present **even on 401 and 403
responses**. A consumer can identify a server without a successful authenticated parse.

### 5.2 An unprivileged account gets `403`, not `401` ⭐⭐

With **valid** credentials that merely lack bit 4 ("Set camera settings"):

| Endpoint | Result |
|---|---|
| `++systemInfo`, `++camStatus` | `200` |
| `++settings-cameras`, `++settings-sched`, `++settings-general` | **`403`**, body `403 Access Denied` (`text/plain`) |

The server cleanly separates *who you are* (401) from *what you may do* (403). Verified
directly (authorised bad-credential probes; the account was confirmed working afterwards,
no lockout):

| Attempt | Status | Body | `WWW-Authenticate` |
|---|---|---|---|
| Valid user, wrong password | `401` | `401 Unauthorized` | `Basic realm="SecuritySpy"` |
| Nonexistent user | `401` | `401 Unauthorized` | `Basic realm="SecuritySpy"` |
| No credentials | `401` | `401 Unauthorized` | `Basic realm="SecuritySpy"` |
| **Valid credentials, missing bit 4** | **`403`** | `403 Access Denied` | **absent** |

So the two are separable three ways — status, body text, and the presence of the
`WWW-Authenticate` challenge. This library currently maps **both** to
`SecuritySpyAuthError` — see §7.1.

### 5.3 `HEAD` is broken, and reason phrases are unreliable

`HEAD` on any endpoint returns the malformed status line **`HTTP/1.1 400 OK`** — code 400
with reason phrase "OK", `Content-Length: 15`. Never use `HEAD` for a reachability probe.

More generally the **reason phrase cannot be trusted**: the `403` also comes back as
`HTTP/1.1 403 OK`, while the `401` correctly says `Unauthorized`. Parse the numeric status
only — which this library already does.

### 5.4 Schedule data shapes (resolves a story 1.10 unknown)

```jsonc
"schedule-list": [ {"name": "Disarmed 24/7", "id": 0}, {"name": "Armed 24/7", "id": 1},
                   {"name": "Armed Sunrise To Sunset", "id": 2},
                   {"name": "Armed Sunset To Sunrise", "id": 3} ]
"schedule-override-list": [ {"name": "No Override", "id": 0}, … {"name": "Armed For 6 Hours", "id": 14} ]
"schedule-preset-list": []          // empty on this server
```

Both lists are arrays of `{name: str, id: int}` — **not** an object keyed by id. The four
`schedule-list` entries with ids 0–3 are the built-in defaults, confirming §8.2b.

**Update 2026-08-29 (closes gap G2).** Jensen created one throwaway schedule and one
throwaway preset, and the read was repeated:

```jsonc
"schedule-list":        [ …built-ins 0–3…, {"name": "Untitled Schedule", "id": 20189} ]
"schedule-preset-list": [ {"name": "Untitled Preset", "id": 3186401225} ]
```

- A user-defined schedule uses **the same `{name, id}` shape** as a built-in, so
  `_decode_schedules` handles it unchanged. `ServerInfo.from_api` on this live payload
  returns all five schedules. Story 1.10's "and any the user defined" is now verified.
- **Ids are neither small nor sequential**, and a preset's exceeded signed 32-bit range
  (3186401225). Nothing may narrow a schedule or preset id to int32.
- `schedule-preset-list` is genuinely populatable; the library models no presets.
- **The XML form is not a mirror of the JSON form.** Without `format=json` the same read
  returns an empty `<schedulepresetlist>` while the JSON carries the preset. Reason about
  wire shape from the JSON form only — which is what the client requests.

### 5.5 The camera enable control (resolves the other story 1.10 unknown) ⭐

`settings-cameras.html` carries `<input type="checkbox" id="enabled">` — **id only, no
`name` attribute**. That is precisely why it is absent from §8.1's key list, which was
harvested from named fields. Per `GetFormKeyValueString`, the write is:

```
POST /++settings-cameras
Content-Type: application/x-www-form-urlencoded

formData&cameraNum=4&enabled=1
```

The full set of id-only boolean keys on that page (82 of them) includes `enabled`,
`ccMovie`, `ccImage`, `mcTriggerMotion*`, `animalBird|Fish|Quadruped`, `viewOnly`,
`permissiveSsl` and the Arrives/Departs family from §4.2.

`settings-cameras-multi.html` pairs each field with an `x`-prefixed "apply this one" toggle
(`xEnabled` gating `enabled`) — relevant only if bulk writes are ever wanted.

**Not verified by write.** The field name and mechanism are read from the shipped client;
no POST was issued against the live server.

## 5.6 `caplist` verified against 10,476 live captures

Fetched with `cams=…&startDate=…&endDate=…&filter=0` over a month. The envelope is a
**bare top-level array** and the library decodes it correctly — 10,476 of 10,476 entries,
none rejected. All thirteen documented keys (`c t s d i g m f n a u z o`) are present on
every entry. Three corrections:

- **`m` is a float, in megabytes.** `script.js:405` names the parameter `mb` and converts
  upward to GB/TB, downward via `parseInt(mb*1000)+' KB'`. Observed range `0.04` to
  `9129.763`, and **float on every one of 10,476 entries** (only 8 happen to be
  integral-valued). §4.1 calls it "file size" without a unit or type.
- **`z` does not simply "track `m`"** as §4.1 suggests — the two are equal on only 1,046
  of 10,476 entries. Meaning still unconfirmed. `i` is an int of unknown meaning
  (not `m` in KB: entry 0 has `m=0.713` → 713 KB but `i=1349`).
- **The filename format in §4.1's example does not match this server.** The real form is
  `08-29-2026 5-52-31 AM M Living Room.mov` — **every one of the 10,476 filenames contains
  spaces, and none contains `+`**, where the doc's example (`M+2026-08-09_17-35-19_C.jpg`)
  is the reverse. This is why the story 1.9 review's percent-encoding finding was
  load-bearing rather than theoretical: unencoded, every capture on this server would have
  produced a broken `getfile` URL.

### Library consequence: `Capture.file_size` is lost for 99.92% of captures

`models.py:1013` reads `file_size = _as_int(payload.get("m"))` into a field typed
`int | None`. `_as_int` yields `None` for a non-integral float, so file size decodes for
**8 of 10,476** captures. Where it does decode, an `int` in a field named `file_size`
invites a consumer to read megabytes as bytes. Same failure class as §7.2: a wire type
guessed, then pinned by fixtures written to match the guess.

## 5.7 Event stream verified live — framing confirmed, timezone assumption falsified

Captured 45 s of `++eventStream?version=3` from the running server (unbuffered; curl's
default buffering silently yields an empty file on a low-traffic stream).

**Framing — §3.1 is exactly right, on 6.21 too.** Over the capture: **5 CR (0x0D) bytes,
0 LF (0x0A) bytes, 0 CRLF pairs.** CR is a *terminator*, not a separator — every record
including the last ends with CR, so a correct reader finishes with an empty buffer. The
library's `stream.py` (`_RECORD_SEPARATOR = b"\r"`) handles this correctly; feeding the raw
capture through its framing logic emitted 5 records with 0 bytes left buffered.

**Record format — §3.2 confirmed.** `20260829062049 0 X NULL`: 14-char timestamp, a
per-connection counter starting at **0** and incrementing monotonically, `X` for
non-camera-specific, then the event type. `parse_event_line` decoded 5 of 5, with
`camera=None` for `X`.

**Heartbeat — §3.3 confirmed.** `NULL` on camera `X` at 062049 / 062059 / 062109 / 062119 /
062129 — exactly 10 s apart, matching `HEARTBEAT_INTERVAL = 10.0`.

**Response shape.** `200`, `Content-Type: text/plain`, with **no `Content-Length` and no
`Transfer-Encoding: chunked`** — a close-terminated stream. `Keep-Alive: timeout=20, max=100`
is advertised but does not apply to the open stream.

### Library defect: the server's timezone is published, and ignored ⭐

`events.py:367` documents an assumption: *"No SecuritySpy endpoint in the protocol research
exposes the server's timezone, so this defaults to UTC."* **That is false on 6.21.**
`systemInfo.server` carries all of:

| Field | Live value |
|---|---|
| `seconds-from-gmt` | `-18000` (UTC−5) |
| `current-local-time` | `2026-08-29T05:28:00-05:00` — full ISO-8601 *with offset* |
| `current-absolute-time` | `809692080.070819` |
| `time-format` | `12` |

None of the four is decoded anywhere in the library, and the integration never passes
`server_timezone`, so the `UTC` default stands. Event-stream records carry the server's
**local** wall clock, so the live heartbeat `20260829062049` decodes as
`2026-08-29T06:20:49+00:00` when the truth is `2026-08-29T11:20:49+00:00` — **five hours
wrong**, and wrong by whatever the offset happens to be for any other install.

The same `server_timezone` parameter feeds `Capture.start` (`client.py:600`,
`models.py:257`), so capture history is shifted identically.

**Scope of the damage, checked rather than assumed.** `datetime.now()`, `utcnow` and
`time.time()` appear **nowhere** in the library or the integration: the reducer's
`deadline()` measures from an event's own timestamp plus a gap, so every comparison is
event-time against event-time. The skew is therefore *internally consistent* — episode
open/close, debounce runs, inactivity gaps and capture ordering all still behave correctly.

What breaks is absolute correctness, wherever a value meets a real clock. Home Assistant is
that clock: a `device_class: timestamp` sensor renders relatively, so "last human seen" would
read *"5 hours ago"* for someone who just walked past. The fix is confined to the decode
boundary — no reducer or coordinator logic needs to change — but until it lands the
Observation Record's displayed values are wrong by the server's offset.

### An offset is not a timezone

`seconds-from-gmt` is the offset **in force when the reading was taken**, not a zone. It is
correct for live events and wrong by an hour for historical captures across a daylight-saving
boundary — verified:

| Record | Decoded with fixed `-18000` | Decoded with `ZoneInfo("America/Chicago")` |
|---|---|---|
| `20260829062049` (August, CDT) | `2026-08-29T11:20:49Z` | `2026-08-29T11:20:49Z` ✅ agree |
| `20260115062049` (January, CST) | `2026-01-15T11:20:49Z` | `2026-01-15T12:20:49Z` ❌ **1 h out** |

`caplist` routinely spans a month and can span a transition, so this is reachable, not
theoretical. SecuritySpy publishes no zone name anywhere, so the library cannot be fully
DST-correct on its own. The library's existing `naive.replace(tzinfo=tz).astimezone(UTC)`
handles both inputs correctly — a real `ZoneInfo` resolves the offset per timestamp — so the
fix is entirely about *sourcing* the right `tzinfo`, never about the conversion.

Note the structure is already right: `StreamEvent.timestamp` is timezone-aware and normalised
to UTC, and `raw_timestamp` preserves the original string. Nothing is lost; only the assumed
offset is wrong.

## 5.8 Settings pages, verified with an elevated account (G3, G4, G5)

A temporary account (`aielevatedtest`) with the settings permission was created for this pass
and removed afterwards. It closed the largest block of unverified guesses in the reference doc.

### Bit 4 (value 16) confirmed as "Set camera settings" ⭐

A clean A/B: the probe account's per-camera `permissions` is `839` and every `++settings-*`
returns `403`; the elevated account's is `10207`/`12255` and every one returns `200`. The bits
it gained are `9368` = file_delete + **set_camera_settings (16)** + schedule + trigger +
push_streams. Story 1.11's central premise is now live-verified rather than read from the
account editor's checkbox ids.

**The reference doc's own worked example is arithmetically wrong.** §9 states *"Observed 10207
= LIVEVIDEO + FILES + FILEDEL + CAMCONTROL + SCHED + AUDIORCV + TRIGGER + AUDIOSND"* — that
sums to **3789**, not 10207. The real decomposition is
`1+2+4+8+16+64+128+256+512+1024+8192`, which balances **only** if the three undocumented bits
(2, 16, 8192) are included. The doc's own evidence contradicts its own table.

### `++settings-cameras` read

**129 keys**, not the documented "~120": 48 booleans, 62 ints, 19 strings. `username` and
`password` are both present in plaintext, so §8.3 holds on 6.21.

`enabled` **is** present in the JSON read, as a JSON `bool` (`True`) — while it must be
*written* as `1`/`0`. That is the read/write asymmetry §8.0 rule 3 describes, now confirmed
for this specific key.

**Library check.** Of the 23 wire keys `CameraSettings` maps, 22 are present with matching
types and 23 of its 24 fields decode from a live page. Credentials are correctly dropped at
decode — neither value reaches the model. The one exception: **`presenceRect` does not exist**
on any of the 11 cameras, so `CameraSettings.presence_rect` is permanently `None`. Every
camera on this server reports `custom-model: False`, and §8.2 ties `presenceRect` to presence
detection and custom CoreML models, so whether it appears once a custom model is assigned is
**untested**. `motionMask` and `privacyMask` are both present as documented.

### The enable write, performed live (G4)

Toggled `enabled` off and back on for camera 5 (Music Room) with the owner's authorisation:

```
POST /++settings-cameras
formData&cameraNum=5&enabled=0
-> 200 {"camUpdate":{"num":"5","name":"Music Room"}}
```

- `++camStatus` flipped to `enabled: false`, then back to `true` on restore.
- The acknowledgement shape matches research §8.0's documented `{"camUpdate": {...}}`.
- **Partial-write safety, measured across all 129 keys: exactly one changed — `enabled`.**
  After restoring, **zero** of the 129 differ from the original snapshot. §8.0's "partial
  writes are safe — verified" holds on 6.21, and story 1.10's mechanism is confirmed end to
  end rather than read from client source.

### `++settings-sched` (G2 still open)

Shape matches §8.2b exactly: `{schedules: [], presets: [], sunriseOffset1/2, sunsetOffset1/2}`.
Both arrays are **empty**, as on the reference server, so the elevated account did **not**
close G2 — the shape of a *user-defined* schedule remains unverified and still needs someone
to create one.

## 5.9 Media endpoints answer a permission failure with `401` (closes G5) ⭐⭐

`aielevatedtest` was reduced to **Live**-only permission for this test.

| endpoint | full-permission | Live-only |
|---|---|---|
| `++getfile` | `206 video/quicktime` | **`401`** |
| `++getfilehb` | `206 video/quicktime` | **`401`** |
| `++getfilelb` | `206 video/mp4` | **`401`** |
| `++getpreview` | `200 image/jpeg` | **`401`** |
| `++systemInfo`, `++caplist`, `++camStatus` | `200` | `200` |

The credentials are valid — `++systemInfo` returns `200` for the same account in the same
second. So on the media endpoints SecuritySpy expresses *insufficient permission* as `401`,
and §5.2's "an unprivileged account gets `403`, not `401`" is true **only of the settings
pages**. Which code a denial carries is a property of the endpoint, not of the server.

**The permission `401` is byte-identical to a wrong-password `401`.** A deliberately wrong
password on the same URL returns the same status, the same
`WWW-Authenticate: Basic realm="SecuritySpy"`, and the same 16-byte `401 Unauthorized`
body. There is no discriminator in the response.

**Consequence (defect 7).** A Live-only user's capture fetch raises `SecuritySpyAuthError`,
which in Home Assistant means a reauth prompt. The user re-enters *correct* credentials, and
the next fetch fails identically — an unbreakable loop, with the true cause ("this account
may not read captures") never surfaced. This is the same failure story 1.11 exists to
prevent, reached by a path the story did not anticipate.

Any fix has to come from **outside** the single response, since the response carries no
signal: e.g. on a media `401`, re-read a known-permitted endpoint, and if that succeeds treat
the denial as a permission failure rather than an authentication one. That is a library
change under AD-19 and wants its own story — it is not a mapping-seam tweak.

**Also settled here:** `++caplist` accepts `startDate`/`endDate` as **`YYYY-MM-DD` only**. A
full ISO instant (`2026-08-20T00:00:00`) and a compact `20260820000000` both return `[]` —
success with silent zero results, never an error. The library already rejects `datetime`
bounds in `async_get_captures` with a comment predicting exactly this; that prediction is now
confirmed on a live server.

## 5.10 A camera in an error state, and a non-permission bit (G6, G7) ⭐

The Living Room camera (number 7) was unplugged deliberately. Both error surfaces agree:

```jsonc
// ++camStatus
{"num":7,"enabled":true,"online":false,"open":false,"err":64,"errDesc":"Host is down"}
// ++systemInfo camera-list entry
"last-error": 64, "last-error-description": "Host is down", "connected": false
```

- **`err` / `last-error` is an `int` on the wire.** `CameraStatus.error` and
  `Camera.last_error` are typed `str | None`, which reads like a mismatch but is deliberate:
  `_as_error_code` collapses zero and carries any other value through as the server's own
  string. Decoding the live response yields `error='64'`, `error_description='Host is down'`
  for camera 7 and `None`/`None` for the healthy ten **in the same response** — the first time
  the sentinel has been exercised against a mixed inventory. **No defect.**
- **`enabled` remains `true` while the camera is down**, confirming the docstring's claim that
  `enabled`, `online` and `open` are independent rather than nested.
- Code **64 = "Host is down"** is the first real error code seen. It is one value from an
  unknown space; do not enumerate error codes on this evidence.

**Permission bits, A/B'd across three permission types** on one account (camera 7 unplugged
throughout):

| permission type | connected cameras | camera 7 | bits |
|---|---|---|---|
| Live | `513` | `1` | 0, 9 |
| Live, Captures | `519` | `7` | 0, **1**, 2, 9 |
| probe account (has Control) | `839` | `327` | 0, 1, 2, 6, 8, 9 |

- **Bit 1 (2) arrives with "Captures", paired with `PERM_FILES`.** Granting Captures to a
  Live-only account sets bits 1 and 2 together and changes nothing else. Its meaning is still
  unnamed in the web client — narrower than before, but not identified. Leave it unassigned.
- **Bits 8 and 9 are already modelled**: `PERM_PTZSET` (bit 8, appears only with Control) and
  `PERM_AUDIORCV` (bit 9). Bit 9 matches `has-audio` on all 11 cameras. It initially looked
  like camera connectivity because the sole camera missing it is the unplugged one, which
  reports `has-audio: false` and an empty `audio-format` while down.
- **Settled (2026-08-29): the mask varies with camera connection state.** Camera 7 has a
  microphone. Two probes that do not need the camera reachable:
  1. Its `++settings-cameras` page is identical to a working camera's on every audio field —
     `noAudioSend` unchecked, the same `audioDevice` selection. So the missing bits are not a
     configuration.
  2. A stored Living Room recording from 2026-08-08, fetched via `++getfile` and inspected
     with `ffprobe` (stream metadata only), carries **`pcm_alaw`, 8 kHz, mono** alongside its
     H.264 video. The camera not only has a microphone, it is an **A-Law** device — so when
     connected it belongs to the `12255` group and holds *both* audio bits.

  Its mask reads `9695` purely because it is unplugged. **`camera-list[].permissions` is
  therefore not a static property of the account or the hardware: a camera going offline
  visibly loses permission bits.** A consumer must never cache the mask, and must never infer
  "this account may not receive audio from this camera" from a single reading — the camera may
  simply be down. Prediction, falsifiable on replug: camera 7 returns to `12255`.

## 5.11 The full permission bitmask, read under an Administrator account ⭐⭐

With `aielevatedtest` set to **Administrator — full access to everything**, the per-camera
masks are *not* uniform:

| mask | cameras | bits set |
|---|---|---|
| `12255` | 1, 5, 8, 9, 10 | 0,1,2,3,4,6,7,8,9,10,**11**,13 |
| `10207` | 0, 2, 3, 4, 6 | 0,1,2,3,4,6,7,8,9,10,13 |
| `9695` | 7 (unplugged) | 0,1,2,3,4,6,7,8,10,13 |

**The mask is granted rights intersected with what the camera can do.** An Administrator holds
every right, yet five cameras lack `PERM_AUDIOSND` (bit 11) and the unplugged one also lacks
`PERM_AUDIORCV` (bit 9). The five carrying bit 11 are exactly the five reporting `A-Law`
audio; the five without it report `u-Law`. So `has_permission()` reading as "*this camera*
grants X" is the correct framing, and `const.py` naming it a "per-camera permission bitmask"
is right — a consumer must never collapse the eleven masks into one account-level set.

**The masking is observed on the audio bits only.** `CAMCONTROL` (6) and `PTZSET` (8) are set
on all eleven cameras, the unplugged one included, and every camera is ONVIF — so control
rights do not vary here and this evidence does not show them being masked by capability. Only
bits 11 and 9 vary, and bit 11 tracks the audio codec exactly: the five `A-Law` cameras carry
it, the five `u-Law` cameras do not. Read the rule as "a capability the camera lacks does not
appear as a granted right", demonstrated for audio; do not assume the same masking for a bit
no camera in this inventory lacks.

This live-verifies nine of the eleven named bits at once (0, 2, 3, 4, 6, 7, 8, 9, 10, 11, 13).
Two remain unobserved and both are explainable:

- **Bit 12 `PERM_NODOWNLOAD` is clear on every camera**, which is the expected reading of an
  Administrator under §4.1's inverted sense: set means *hide* download options. A grant-shaped
  bit would have been set here. This is the first live evidence for the deny-bit
  interpretation, and it holds.
- **Bit 5 (32) has never been observed set** under any of the four permission types tested.
  Unlike bit 1 it is not merely unnamed — it appears unused. Do not model it.

**Bit 1 (2) is set on every camera even for an Administrator**, consistent with §5.10: it
arrives with Captures and is held by anyone who has them. Still unnamed, still unassigned.

**One privacy finding.** `server.wan-address` differs by account: the Administrator sees the
server's registered remote-access hostname (a personal `*.viewcam.me` name), while the
ordinary account sees only the host it connected to. `is_credential_key("wan-address")` is
`False` and `anonymize()` passes the value through unchanged, so this hostname would appear
verbatim in a Home Assistant diagnostics dump that users routinely attach to public issues. It
is not a credential, so story 1.7 is not violated as written — but it is personally
identifying network information, and HA's own guidance treats that as redactable. See
"Documentation follow-ups".

## 5.12 A disabled camera vanishes from `++systemInfo` but not `++camStatus` ⭐⭐

North Yard (camera 6) was disabled in the SecuritySpy UI. The two inventory endpoints then
**disagree about which cameras exist**:

| endpoint | cameras reported | camera 6 |
|---|---|---|
| `++camStatus` | 11 | present: `{"num":6,"enabled":false,"online":false,"open":false,"err":0,"errDesc":""}` |
| `++systemInfo` | **10** | **absent from `camera-list` entirely** |

`server.camera-count` also reads `10`, so `++systemInfo` is internally consistent — it does not
report a count that disagrees with its own list, and `ServerInfo.from_api` decodes it without
complaint. **There is no library defect here.** What there is, is a behavioural fact with
direct consequences for the integration:

- **A disabled camera is not an errored camera.** `err` is `0` and `errDesc` is empty; only
  `enabled` is `false`. It is distinguishable from the unplugged case (§5.10), where `enabled`
  stayed `true` and `err` was `64`. The three booleans earn their independence here.
- **`++camStatus` is not simply a cheaper `++systemInfo`.** Its docstring calls it "the
  low-cost alternative", and for *health* it is — but the two enumerate **different sets**. A
  consumer that creates entities from `++systemInfo` and polls health from `++camStatus` will
  receive status for a camera it has no entity for.
- **Historical captures survive.** `++caplist` for camera 6 still returns its recordings, so
  disabling stops the camera, not access to what it already recorded.

**Consequence for epic 2 and epic 3, not for the library.** If devices are built from
`++systemInfo`, disabling a camera in SecuritySpy makes its Home Assistant device and entities
*disappear* rather than go unavailable — which is the failure story 3.1 ("report unavailable
rather than stale") exists to prevent, and it would silently orphan history and break
automations. Stories 2.3, 2.7 and 3.1 must decide deliberately whether the inventory of record
is `++camStatus` (11, includes disabled) or `++systemInfo` (10, excludes them). The two are not
interchangeable.

**Also confirmed here:** §5.11's falsifiable prediction. With Living Room reconnected, its mask
read **`12255`** under the Administrator account — exactly as predicted, both audio bits
restored. `camera-list[].permissions` varying with camera connection state is now established
by prediction and confirmation, not by inference from a single reading.

## 5.13 `++ssSetSchedule` also denies with `401` — the `403` case is the exception ⭐⭐

An attempt to exercise the last unverified operation was **blocked**, and the block is the
finding. Using the ordinary probe account (mask `839`), in the same second:

| request | status |
|---|---|
| `++systemInfo?format=json` | `200` — the credentials are valid |
| `++settings-cameras?cameraNum=10` | `403` |
| `++ssSetSchedule?cameraNum=10&mode=CMA&override=0` | **`401`** |

Mask `839` grants `live_video, files, camera_control, ptz_preset_set, audio_receive` and
**not** `PERM_SCHED` (128), which `async_set_camera_arming` names as this endpoint's
requirement. So the `401` is a permission denial, on an endpoint that is not media.

**This overturns the scoping in §5.9.** The `401`-for-permission behaviour is not a property of
media endpoints; it is the *general* case, and `++settings-cameras` returning `403` is the
exception. Which code a denial carries cannot be predicted from an endpoint's kind — only from
having tested that endpoint. Story 1.14 was rewritten accordingly: the disambiguation is keyed
on the `401` status rather than on a list of endpoints, because the list was wrong within a day
of being written.

**The write itself remains unperformed.** `++ssSetSchedule` stays the sole `client-source`
operation in the OpenAPI description, and AD-7's rule that `schedule=` is never sent still
rests on a read of `script.js`. Closing it needs an account holding `PERM_SCHED` — either
granting it to the probe account or another temporary account. The restore point for the
intended test is recorded: **Kitchen (camera 10), all three modes `armed`, all three schedule
ids `1`, all three overrides `0`.**

## 5.14 `++ssSetSchedule` verified by write — `mode` is a TARGET SELECTOR ⭐⭐⭐

Performed with an authorised privileged account against **Kitchen (camera 10)**, every step
read back and restored; final diff against the baseline is empty.

| # | request | result | changed |
|---|---|---|---|
| 1 | `mode=CMA&override=0` | `200`, body `OK` | **nothing** |
| 2 | `mode=CM&override=0` | `200` | **nothing** |
| 3 | `schedule=1&override=0&mode=CM` | `200` | nothing (schedule already `1`) |
| 4 | `schedule=2&override=0&mode=A` | `200` | **`a-schedule-id` 1 → 2** |
| 5 | `override=2&mode=A` (no `schedule`) | `200` | **`a-schedule-override` 0 → 2** |

**`mode` names which of the three capture modes the write applies to. It is not their armed
state.** The shipped client confirms it — `ScheduleSetterPanelApply` builds
`cameraNum, schedule, override, mode` from three checkboxes that select *which* modes the
chosen schedule and override are applied to. `schedule` and `override` are the values;
`mode` is the target set. Either value may be sent alone (step 5 proves `override` works with
no `schedule`), which means **AD-7's rule that arming writes an override and never a schedule
is achievable exactly as written** — the rule is sound, its implementation is not.

**The response is `200 OK`, `text/plain`, body `OK` (2 bytes), in every case above —
including the two writes that changed nothing.** The status does not indicate that anything
was applied. A caller cannot distinguish "applied" from "targeted nothing" without reading
back.

**Consequence: `async_set_camera_arming` does not do what it says (defect 8).** It passes the
three booleans as `mode` and never sends `schedule` or a value for them to apply to, so:

- A call with all three modes true and a real `override` **works by accident** — it targets
  all three modes and applies the override.
- A call with modes all-false sends `mode=` empty, targeting **nothing**. The docstring calls
  this "the legal instruction 'disarm all three'"; it is a silent no-op returning `200 OK`.
- There is **no arm/disarm capability here at all** in the sense the method claims. Arming is
  expressed by assigning a schedule (`0` = Disarmed 24/7, `1` = Armed 24/7) or an override to
  the targeted modes.

**Also found:** `ssSetPreset?id={presetId}` in the same source region — the endpoint that
applies a schedule preset (§5.4's `schedule-preset-list`). Neither modelled nor tested.

## 5.15 A real browser session, captured (HAR, 221 entries) ⭐⭐⭐

Jensen exercised the web app as a privileged user and exported a HAR. This is the first
evidence taken from the *client's own traffic* rather than from reading its source.

### 5.15.1 There are two API surfaces, not one

Every call in the capture uses a **bare path** (`/caplist`, `/camStatus`, `/getpreview`), never
the `++` prefix, and authentication is `POST /login` with `user=` and `pass=` form fields,
answered `303`. A wrong password answers `303` to `login.html?feedback=Login+failed` — **not**
`401`. So §2's "bare paths redirect to login" is the *browser* surface; the `++` prefix with
HTTP Basic is the *programmatic* surface, and `aiosecurityspy` is correctly on the latter.

**No `Set-Cookie` and no `Cookie` header appears anywhere** in an unsanitised DevTools export
that preserved every other header. Combined with the `303` to `.` on success, that points to
SecuritySpy binding the session to the client address after login rather than issuing a
cookie. Stated as the reading of the evidence, not as a verified mechanism — proving it needs
a second client on a different address.

### 5.15.2 `getpreview` is exactly what the library builds ✅

```
/getpreview?/4/2026-08-29/08-29-2026%202-13-02%20PM%20M%20Back%20Yard.mov?archive=0
```

Spaces are `%20`, the `/` separators are **not** encoded, and both `?` are literal. That is
precisely what `_stream_bytes` produces with per-segment `quote(part, safe="")` joined by `/`.
Story 1.9's encoding fix and the `x-raw-url-template` are confirmed against the real client.

### 5.15.3 Live video is a WebSocket with a binary control protocol ⭐⭐⭐

```
wss://…:8001/video?cameraNum={n}&vcodec={v}&acodec={a}&fps={f}&apause=1&sizeFraction={s}&auth={t}
```

`101 Switching Protocols`, with `Upgrade` and `Sec-WebSocket-Key`. Live video is **not** an
HTTP MJPEG pull. The HAR shows a single parameter combination; the permutations come from
`Player.js:307-316` (`startStream`):

| parameter | values | chosen by |
|---|---|---|
| `vcodec` | `jpeg`, `h264`, `h26x` | `jpeg` when MSE is unavailable or JPEG is forced; `h26x` when the browser reports H.265 support, else `h264` |
| `acodec` | `ulaw` or **empty** | `ulaw` only when the camera has audio **and** the account holds `PERM_AUDIORCV`; empty otherwise |
| `fps` | integer or empty | caller-supplied; empty means the server decides |
| `sizeFraction` | `1, 2, 4, 8, 16` | a **divisor**: the largest power of two whose downscale still covers the display area (`Player.js:299`) |
| `apause` | always `1` | constant |
| `auth` | token, empty in this capture | role unknown under Basic auth |

**`acodec` is gated on the permission mask** — `this.cam.perm & PERM_AUDIORCV`. That is the
client consuming bit 9 exactly as §5.11 describes, and it means a camera that is offline (and
so missing the bit) would be asked for a silent stream.

**The socket is bidirectional.** `sendMessageToServer` (`Player.js:430`) sends a 4-byte
binary frame plus optional payload:

```
byte 0: opcode   byte 1: val1   bytes 2-3: val2 (big-endian)   bytes 4+: payload
```

with opcodes `OP_SIZE=1`, `OP_PLAY_PAUSE=2`, **`OP_SCHED=3`**, **`OP_OVERR=4`**, `OP_AUDIO=5`.
So schedule and override can be set **over the video socket**, not only via `++ssSetSchedule`
— a second arming path the project has never seen. `OP_SIZE` also carries an H.265 flag in
`val2`, so quality is renegotiated mid-stream rather than by reconnecting.

**Scope of this finding — corrected.** This is how the *web player* streams, and only that.
It is **not** the only way to get video out of SecuritySpy, and an earlier draft of this
section wrongly generalised it into "live video is not an HTTP MJPEG pull". The player uses a
WebSocket because it wants H.264/H.265 into MediaSource plus a control channel; the HTTP API
offers simpler options that suit Home Assistant better. See §5.16. None of the frame format is
verified by us beyond the `101` and the source read; it stays `client-source`.

### 5.15.4 Four endpoints the project does not model

| endpoint | shape | notes |
|---|---|---|
| `/ptzcommand` | `?cameraNum={n}&code={c}&speed={0-100}` → `200`, body `OK` | Codes observed: 2, 6, 7, 11, 21, **99**. 99 always follows a movement command and carries `speed=0` — it reads as *stop*. Not verified. |
| `/clip` | `?cameraNum={n}&movieType=1&start={ISO}&end={ISO}` → `206 video/mp4`, served with `Range` | **Takes a full ISO instant**, unlike `caplist`'s date-only bounds. A 24-hour range was aborted client-side; a 1-minute range returned `206`. |
| `/cliplist` | no parameters → `200` `[]` | Empty on this server; shape unknown. |
| `/dashImage` | `?formData&type1={n}&item1={n}&type2={n}&smooth={n}&width=&height=&date=&dark={0\|1}&{cachebuster}` → `200 image/png` | Server-rendered dashboard graphs. Note the **`formData` sentinel appearing in a GET query string**, and a bare trailing random integer as a cache-buster. |

### 5.15.5 How the UI actually disarms a camera — and why it collides with AD-7 ⚠

```
/ssSetSchedule?cameraNum=4&schedule=0&override=-1&mode=CMA   → 200 OK
```

This is the disarm control. It assigns **schedule `0` (Disarmed 24/7)** to all three modes,
with `override=-1`. Two things follow:

1. **`override=-1` is confirmed as the "leave as-is" sentinel**, matching
   `ARM_OVERRIDE_UNCHANGED` exactly. Previously read from source; now seen on the wire.
2. **Persistent arming and disarming is expressed by assigning a schedule, not an override.**
   That is the operation AD-7 forbids the library from performing. An override is transient
   and bounded by design, so it cannot express "disarmed until I say otherwise" — which is what
   a Home Assistant switch or alarm-panel entity means.

**This trips story 1.16's `Block If` verbatim** ("the fix would require sending `schedule=` to
express arming"). AD-7 is not wrong about what an override does; it is that the library has no
operation for the thing the UI's disarm button performs. Epic 6's stories 6.1 and 6.4 cannot
be built without resolving it, and it is an architecture decision, not an implementation one.

### 5.15.6 Cadence and absences

`camStatus` was polled 8 times in 22 seconds — roughly every 3 seconds, far more aggressive
than a Home Assistant coordinator should be. Neither `systemInfo` nor `eventStream` appears
anywhere in the capture: the pages exercised here do not use them.

## 5.16 Media delivery: four options, all simpler than the WebSocket ⭐⭐⭐

Prompted by Jensen pointing at SecuritySpy's built-in **URL Generator** ("generates URLs for
standard media streams ... to clients such as VLC or Homebridge"). Verified live except where
noted:

| endpoint | result | notes |
|---|---|---|
| `++image?cameraNum={n}` | `200 image/jpeg` | Single snapshot. Honours `width=` and `quality=` (234 KB → 21 KB at `width=320&quality=50`). |
| `++video?cameraNum={n}` | `200 multipart/x-mixed-replace; boundary=ssBoundary8345` | A plain **MJPEG stream** over HTTP. |
| `hls?cameraNum={n}` (and `++hls`) | `200 application/x-mpegURL` | **Adaptive HLS.** The master playlist offers three variants pointing at `++hls_mediaplaylist?cameraNum={n}&quality={0,1,2}`, at ~218 kbps / 750 kbps / 3.1 Mbps. |
| `rtsp://{host}:8000/stream?cameraNum={n}&vcodec=h26x` | port 8000 confirmed open | From the URL Generator. H.264/H.265. **A different port from the web server** — 8000 vs 8001 here. Not exercised. |
| `++audio?cameraNum={n}&format=aac` | `200 audio/aac` | Audio alone. Also `&sampleRate=16000`. |

`++stream?...` appears in the binary but returns `404` on 6.21; treat it as stale.

**This overturns the conclusion drawn in §5.15.3.** Home Assistant's camera platform wants a
still image and a stream URL, and SecuritySpy publishes both over ordinary HTTP, inside the
transport `aiosecurityspy` already has. **Story 2.6 needs no WebSocket support.** `++image` is
a snapshot; HLS or RTSP is the stream. The WebSocket is the web player's private
implementation, not the API's only door.

### 5.16.1 The `auth` token — verified, scoped, and not mintable over HTTP ⭐⭐

The URL Generator issues a token described as granting "access to the specified resource only,
without revealing the username/password", "invalidated if the account is changed or deleted".
Two tokens were generated for the **same account and same camera**, differing only in the
resource, and both were tested live:

| request (no credentials supplied) | result |
|---|---|
| `GET /video?cameraNum=4` + its own token | **`200 multipart/x-mixed-replace`** |
| `GET /video?cameraNum=4` with no token | `303` to login |
| `GET /video?cameraNum=**5**` with camera 4's token | `303` — denied |
| `GET /++image?cameraNum=4` with the *video* token | `401` — denied |
| `GET /hls?cameraNum=4` with the *video* token | `303` — denied |
| `GET /++systemInfo` with the video token | `401` — denied |
| `rtsp://…:8000/stream?cameraNum=4&vcodec=h26x` + its RTSP token | **works** — `h264` 640x480 + `pcm_mulaw`, via `ffprobe` |
| same RTSP token, `cameraNum=5` | `401 Unauthorized` on `DESCRIBE` |

**The scoping claim is true, and tighter than advertised: the token binds to endpoint *and*
camera**, not merely to a camera. A token for MJPEG on camera 4 opens nothing else at all.
This is the mechanism **AD-13** wants for any URL handed to the Home Assistant frontend.

**Shape.** `!` + 8 hex characters + 40 hex characters. The 8-character prefix was *identical*
across the two tokens (same account); the 40-character remainder differed. 40 hex is SHA-1
length, so this reads as an account identifier followed by a keyed digest over the resource —
consistent with a server-held secret.

**No HTTP endpoint mints one.** The generator is a native window (`URLGeneratorWindow` in the
binary); nothing in the shipped web client or the endpoint surface issues a token, and the
only HMAC strings in the binary are OpenSSL's generic algorithm table, not evidence of this
token's construction. Jensen confirms she does not know how they are generated either.
Treating them as **server-minted and human-copied** is the safe reading.

### There are TWO `auth=` forms, and only one is safe ⚠

SecuritySpy's own documentation describes `auth=` as "the Base64-encoded version of the string
`username:password`". That is a **second, distinct** form from the URL Generator's token, and
both are accepted. Verified live, with no `Authorization` header sent:

| `auth=` value | `++image` | `++systemInfo` | `++caplist` | `video` | scope |
|---|---|---|---|---|---|
| `base64("user:pass")` | `200` | `200` | `200` | `200` | **the whole account** |
| `base64("user:wrong")` | `401` | `401` | — | — | rejected |
| `!{8 hex}{40 hex}` (generator) | `401` | `401` | — | `200` for its own camera only | **one endpoint, one camera** |

The leading **`!`** is the discriminator. Without it the value is parsed as base64 credentials;
with it, as a scoped token.

**The documented form is credentials-in-a-URL.** Base64 is an encoding, not encryption — a
`auth=` query parameter carrying it is the account's username and password in plaintext for
anyone who can read a server log, a proxy log, a browser history, or a Home Assistant frontend
URL. It also grants **everything the account can do**, not just the stream it was pasted into.

**Rule for this project: the library and the integration must never construct the base64
form.** `aiosecurityspy` authenticates with an `Authorization` header, which keeps credentials
out of the request line, and `const.py` already flags `++ssSetSchedule` as an exposure precisely
because it is a GET. The `!`-prefixed token is the only acceptable URL-embedded credential, and
its whole value is that it is *not* the account.

**Consequence for story 2.6 — three options, and the token is not automatically the winner:**

1. **User pastes a token per camera.** Most faithful to AD-13, but manual, and it does not
   scale: eleven cameras means eleven visits to a macOS dialog, repeated whenever the account
   changes, since that invalidates every token.
2. **Home Assistant proxies the stream**, authenticating server-side with the stored
   credentials and never putting them in a frontend URL. This is ordinary practice for HA
   camera integrations and satisfies AD-13's intent without any manual step.
3. **Credentials in the URL.** Rejected outright — this is exactly what AD-13 forbids.

Option 2 looks right for the default path, with option 1 worth offering for users who want a
direct stream URL. **This is a decision for story 2.6, recorded here, not made here.**

### 5.16.2 `getpreview` takes AI-class parameters

The binary carries:

```
getpreview?/{path}?aiTypeHuman={..}&aiTypeVehicle={..}&aiTypeAnimal={..}&auth={..}
```

So the thumbnail endpoint accepts per-class flags the project has never sent and does not
model — plausibly controlling detection overlays on the returned image. Untested.

## 5.17 The rest of the HAR: tagging, deletion, device discovery ⭐⭐

A residual sweep of the capture — the endpoints not covered in §5.15.

### 5.17.1 A `200` can carry a failure

| request | body | response |
|---|---|---|
| `POST /setTags?tagId=3` | `setTag=4%2F2026-08-29%2F…Back%20Yard.mov%3Farchive%3D0` | `200`, body **`OK`** |
| `POST /delete?v6=1` | `delete=4%2F2026-08-29%2F…C%20Back%20Yard.mov%3Farchive%3D0` | `200`, body **`NO`** |

The delete was **refused**, and the only signal is the two-byte body. Both endpoints take the
capture as a URL-encoded `{camera}/{folderDate}/{filename}?archive={0|1}` triple in the POST
body — the same triple the media endpoints take in the path.

**`aiosecurityspy` discards the body of every write.** `async_set_camera_arming` calls
`_request_text` and drops the returned string, so a `NO` would read as success. It is not a
live defect today — `++ssSetSchedule` answers `OK` even to nonsense (below) — but the body is
the only failure channel these endpoints have, and any future write must read it.

**`++ssSetSchedule` validates almost nothing.** With a privileged account:

| request | result |
|---|---|
| `cameraNum=99` (no such camera) | `404 The specified camera…` |
| `mode=Z` (not a mode letter) | **`200 OK`** |
| `override=999` (undefined) | **`200 OK`** |

Only the camera number is checked. This reinforces §5.14: `OK` means "request accepted", never
"anything was applied", and the library's own `arm_override` validation is the *only* thing
stopping an undefined override reaching the wire.

### 5.17.2 `deviceList` — ONVIF discovery

`GET /deviceList` → `200 application/json`:

```jsonc
{"onvif":[{"name":"C210","id":"uuid:3fa1fe68-…","ip":"192.168.0.20","used":true}, …]}
```

Discovered devices with model name, ONVIF UUID, **LAN IP**, and whether SecuritySpy already
uses each. Unmodelled. Potentially useful to a config flow, but it publishes the internal
network layout, so it must never be included in a diagnostics dump unredacted — the same
concern as `wan-address` (§5.11), and `anonymize()` covers neither.

### 5.17.3 Continuous captures have no time in the filename

One preview request was for `08-29-2026 C Back Yard.mov` — no clock time, where every motion
capture reads `08-29-2026 2-13-02 PM M Back Yard.mov`. The `C`/`M` letter is the capture type.
`_parse_capture_start` reconstructs the start from the folder date plus the `s` seconds field
rather than from the filename, so this is not a defect — but any future filename parsing must
not assume a time is present.

### 5.17.4 Small confirmations

- `caplist` was seen with `filter=0` and `filter=2`, both against `cams=4,` — the trailing
  comma is real in the client's own traffic, as §4 records.
- `/clip` was only ever called with `movieType=1`; other values remain unknown.
- **`++settings-cameras` returns `text/html` without `format=json`** and
  `application/json` with it (129 keys, confirming §5.8). The library sends `format=json`, so
  it is correct — but the OpenAPI description should state that the parameter is required, since
  the bare path returns an 85 KB HTML form.

## 5.18 The settings surface, captured (second HAR, 243 entries) ⭐⭐⭐

A second capture covering the settings pages. **Twelve** settings endpoints exist, each a
`GET` to read and a `POST` to write: `-cameras`, `-general`, `-audio`, `-display`, `-sched`,
`-storage`, `-comp`, `-uploads`, `-email`, `-web`, `-license`, `-order`. Also new here:
`/image` (the bare-path twin of `++image`), `/diskInfo`, `/refreshLicenseInfo`.

### 5.18.1 The browser writes the WHOLE form; our partial write is better

`POST /settings-cameras` was sent five times, each a **2,757-byte body carrying every field**,
including the camera's device `username` and `password` in cleartext. The browser does a full
read-modify-write on every save.

This does **not** contradict §5.8's partial-write finding — that was verified directly, one
field changing 1 of 129 keys — it means both approaches work, and the library should keep its
partial write. The reason is **blast radius, not secrecy**: a full-form write re-sends all 129
fields to change one, so a stale read or a single bad field rewrites the camera's entire
configuration. Credentials on the wire are *not* the argument — these cameras speak plain HTTP
on the LAN regardless, so anyone able to observe that traffic already has the device. Worth
stating in `CameraSettingsPatch`, because "the shipped client does a full form" is otherwise a
tempting reason to switch.

### 5.18.2 Body shapes are not uniform

| endpoint | body |
|---|---|
| most `settings-*` | `formData&field=value&…` — the sentinel then named fields |
| `settings-uploads` | **`formData`** alone, 8 bytes — an empty form is valid |
| **`settings-order`** | **`order=4,3,2,0,6,1,5,7,10,9,8`** — no `formData` sentinel at all; a bare comma-separated camera order |

So `formData` is not universal. Anything modelling a settings write must not assume it.

### 5.18.3 Credential-bearing fields the anonymizer does not know ⚠

SecuritySpy's settings carry several real secrets under names `is_credential_key` does not
match:

| field | endpoint | `is_credential_key` | reality |
|---|---|---|---|
| `password` | `-cameras`, `-email` | ✅ `True` | device / SMTP password |
| `username` | several | ✅ `True` | — |
| **`setPass`** | `-general` | ❌ `False` | settings password |
| **`fsPass`** | `-general` | ❌ `False` | full-screen exit password |
| **`quitPass`** | `-general` | ❌ `False` | quit password |
| `videoPassthrough` | `-web` | ❌ `False` | ✅ correct — *not* a secret despite the name |

The function is pleasingly not naive — it does not false-positive on `videoPassthrough` — but
it misses SecuritySpy's `*Pass` convention. Note these are the **SecuritySpy application's own**
passwords (settings, full-screen exit, quit), not camera device credentials.

**The risk here is egress, not the LAN.** On-network traffic is not the concern — the cameras
are plain HTTP anyway. The concern is a Home Assistant **diagnostics dump**, which is
deliberately exported and routinely attached to public issues. That is the one path where this
data leaves the network on purpose, and it is the path `anonymize()` exists to guard.
**Latent, not live:** the library reads none of these pages today. It becomes real the moment a
consumer puts a `settings-general` payload into a dump.

### 5.18.4 Accounts: safe to read, credential-bearing to write

`POST /settings-web` carries `account={…"username":"…","password":"…"…}` in cleartext — the
account editor submitting a password, which is unavoidable when setting one.

**The read side is clean.** `GET ++settings-web?format=json` returns 30 keys including an
`accounts` array of 3 accounts with **no `password` field at all** (verified by structure;
values were never displayed). So enumerating accounts does not expose their passwords, and an
earlier worry on my part was unfounded.

Also confirms §5.11: `wanAddress` and `ddnsName` are configured values, which is why a
privileged account sees the real `*.viewcam.me` name and an ordinary one sees the connected host.

## 6. Endpoints the client calls that §2.2 omits

`openHomeHelper`, `openUrl?url=`, `soundFile?format=m4a&name=`, `userManual?lang=`,
`settings-web-access-info`, `submitLicenseFile`. None are integration-relevant; listed for
completeness of the catalogue.

## 7. Consequences for this project

### 7.1 Library defect: `403` is reported as rejected credentials

`client._map_status` maps `401` and `403` alike to `SecuritySpyAuthError`, whose message is
*"credentials were rejected"*. §5.2 shows `403` means the credentials are **fine** and the
account simply lacks a permission bit. A user running the least-privileged account §8.3
recommends would be told to check a password that is correct.

This is also exactly the behaviour epic story 1.10's third acceptance criterion asks for
("raises the library's typed permission error rather than failing silently"), and
`SecuritySpyPermissionError` already exists. Worth fixing beyond 1.10's scope, since it
affects every settings read today.

### 7.2 Story 1.10 is unblocked

Both unknowns that would have become Block If entries are resolved:

- **Schedule names** — `schedule-list`, top-level, `[{name, id}]` (§5.4).
- **The enable write** — `enabled=1|0` on `++settings-cameras`, through the existing verified
  partial-write path (§5.5).
- **The permission that write requires** — **bit 4, value 16, "Set camera settings"**, which
  the library does not yet define (§4.1). The epic's permission AC cannot be satisfied
  without adding it.

### 7.3 Smaller follow-ups

- `PERMISSION_NAMES` should gain bits 4, 12 and 13, with 12 flagged as negative-sense.
- `CameraStatus.error` is typed `str | None`; the live wire sends `err: 0` as an **int**.
  Worth confirming the decode path does the right thing with a non-string.
- The reference doc should be updated with §4's corrections, or annotated as 6.20-era.
- `Capture.file_size` needs a float type and a documented unit (§5.6).
- The server's timezone must be decoded from `seconds-from-gmt` and used as the default for every wall-clock decode (§5.7).

## 8. Open questions

1. **Bit 1 (value 2)** — set on every camera, named nowhere.
2. **Does the `403` body ever differ per endpoint?** Only `403 Access Denied` was observed
   across `settings-cameras`, `settings-sched` and `settings-general`.
3. **Is `enabled` readable from `++settings-cameras` JSON?** Could not confirm — the probe
   account gets 403. `++camStatus` exposes it regardless, which is the better read path.
4. **`schedule-preset-list`** was empty; its element shape is unverified.
