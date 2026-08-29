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
| Probes | `GET` only, via the repo's gitignored `.env` probe credentials |
| Probe account | A **least-privileged** web user — `permissions` = `839` on all 11 cameras |
| Not done | No `POST`, no write of any kind |

The probe account being unprivileged is not a limitation to work around — it is what exposed
the permission behaviour in §5, which is the most consequential finding here.

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
`models.py:257`), so capture history is shifted identically. That propagates into the
Observation Record — "last human seen" — which is the integration's headline feature.

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
