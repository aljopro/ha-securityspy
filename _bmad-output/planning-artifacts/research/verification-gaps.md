---
title: SecuritySpy verification gaps and action items
date: 2026-08-29
status: one-gap-open
companion_to: securityspy-6.21-verification.md
---

# Verification Gaps and Action Items

What could not be verified against the live 6.21 server on 2026-08-29, what each gap
blocked, and what closed it. Ordered by value-per-risk.

**Why this list exists:** the pass found seven defects, and three were the same failure —
a wire shape or type *guessed* from research, then pinned by a fixture written to match the
guess, so no test could ever fail. Everything below was exposed to that same failure mode.

**Status: seven of eight gaps closed.** G8 was opened afterwards, by the question of whether
the two inventory endpoints can ever disagree under per-camera permissions. G1–G6 were settled by live observation. G7 is closed as
far as evidence allows — bits 8 and 9 turned out to be already modelled, and bit 1 is narrowed
to "granted with Captures" but deliberately left unnamed. Access used: an ordinary probe
account, plus a temporary account cycled through Live → Live+Captures → Administrator, **now
deleted** (deletion confirmed: it returns `401`). All probing was read-only except one
authorised settings write (§5.8) recorded there.

**What outlived the gaps** are the two decisions in "Documentation follow-ups" and the two
defects still awaiting implementation, listed below. Those are the live items; the gap
sections are history.

## Access-gated gaps

### G1 — Event stream ✅ CLOSED 2026-08-29
**Verified live.** CR-only framing confirmed (5 CR, 0 LF, 0 CRLF over a 45 s capture);
record format, per-connection counter from 0, `X` for non-camera-specific, and the exact
10 s `NULL` heartbeat all confirmed. The library's framing and `parse_event_line` handled the
raw capture correctly — 5 of 5 records, 0 bytes left buffered.
**It also falsified a documented assumption:** the server publishes its timezone
(`seconds-from-gmt`), which the library ignores. See defect 5 below and
`securityspy-6.21-verification.md` §5.7.
**Note for anyone repeating this:** curl buffers by default and yields an empty file on a
low-traffic stream. Use `-N`.

### G2 — No user-defined schedules exist ✅ CLOSED 2026-08-29
Jensen created one throwaway schedule and one throwaway preset. Re-read of
`++systemInfo?format=json` confirms story 1.10's user-defined case:

- `schedule-list` gained `{"name": "Untitled Schedule", "id": 20189}` — **the same
  `{name, id}` shape as the built-ins**, so `_decode_schedules` needs no change.
  `ServerInfo.from_api` on the live payload returns all five schedules, ids 0–3 plus 20189.
  Story 1.10's AC "including both the built-in defaults and any the user defined" is now
  verified on a real server rather than assumed.
- A user-defined id is **not** small and **not** sequential. The one issued was 20189, and
  the preset's was **3186401225 — larger than a signed 32-bit int**. Python's unbounded `int`
  and `_as_int` handle this, but nothing downstream may narrow a schedule or preset id to
  int32, and no test may pin ids to a small range.
- `schedule-preset-list` holds `[{"name": "Untitled Preset", "id": 3186401225}]`. **The
  library decodes no presets at all** — `preset` appears nowhere in `models.py`. Not a defect
  against any current story (1.10 is about schedule *names*), but the field is real, populated,
  and unmodelled. See "Documentation follow-ups".
- **XML/JSON divergence:** the same read without `format=json` returns
  `<schedulepresetlist></schedulepresetlist>` — empty — while the JSON form carries the preset.
  The client always sends `format=json`, so this does not affect it, but the XML form is not a
  faithful mirror of the JSON one and must not be used to reason about wire shape.

### G3 — Admin-privileged read ✅ CLOSED 2026-08-29
A temporary `aielevatedtest` account with the settings permission closed this. Confirmed:
`++settings-cameras` has **129** keys (not "~120"), `enabled` is present and reads as a JSON
bool, `username`/`password` are plaintext as §8.3 warns, and `CameraSettings` decodes 23 of 24
fields from a live page with no credential leakage. **Bit 4 (16) = "Set camera settings" is
now live-verified** by A/B against the probe account, which also exposed an arithmetic error in
the reference doc's own §9 example. One residue: `presenceRect` exists on **no** camera, so
`CameraSettings.presence_rect` is always `None` — see defect 6.

### G4 — The enable write ✅ CLOSED 2026-08-29
Performed live on camera 5 (Music Room) with the owner's authorisation.
`formData&cameraNum=5&enabled=0` returned `200 {"camUpdate":{...}}`, `++camStatus` flipped, and
the restore returned it exactly. **Partial-write safety measured across all 129 keys: exactly
one changed.** After restore, zero differ from the original. Story 1.10's mechanism is
confirmed end to end.

### G5 — No camera-scoped 403 ✅ CLOSED 2026-08-29 — **the premise was wrong**
`aielevatedtest` was dropped to **Live**-only permission and the media endpoints were fetched
with it. There is no camera-scoped 403 to find, because **media endpoints answer a
permission failure with `401`, not `403`**:

| endpoint | full-permission account | Live-only account |
|---|---|---|
| `++getfile` | `206 video/quicktime` | **`401`** |
| `++getfilehb` | `206 video/quicktime` | **`401`** |
| `++getfilelb` | `206 video/mp4` | **`401`** |
| `++getpreview` | `200 image/jpeg` | **`401`** |
| `++systemInfo` / `++caplist` / `++camStatus` | `200` | `200` |

The same credentials return `200` on `++systemInfo` in the same second, so they are valid.
The `401` is a **permission** verdict wearing an authentication status code, and §5.2's
"an unprivileged account gets 403, not 401" holds only for the settings pages.

**Worse: the response is byte-identical to a wrong password.** Same status, same
`WWW-Authenticate: Basic realm="SecuritySpy"`, same 16-byte `401 Unauthorized` body. Nothing
in the response distinguishes "your password is wrong" from "your account may not read
captures", so no amount of care at the mapping seam can tell them apart from one response.

Story 1.11's matrix row for "the error carries that camera number" is therefore **not
verifiable as written** — that row describes a response shape this server does not produce.
See defect 7.

### G6 — No camera in an error state ✅ CLOSED 2026-08-29
Jensen unplugged the Living Room camera (number 7). Both error surfaces populated, and
**both decode correctly — no defect**:

| surface | wire | decoded |
|---|---|---|
| `++camStatus` | `{"num":7,"enabled":true,"online":false,"open":false,"err":64,"errDesc":"Host is down"}` | `error='64'`, `error_description='Host is down'`, `online=False`, `open=False` |
| `++systemInfo` | `last-error: 64` (int), `last-error-description: "Host is down"`, `connected: false` | `last_error='64'`, `last_error_description='Host is down'` |

Settled facts:
- **`err` is an `int` on the wire** (`64`), and `errDesc` carries the text. `CameraStatus.error`
  is typed `str | None`, which looked like a mismatch — it is not. `_as_error_code` documents
  carrying a non-zero code through "as the server's own string", and it does. The healthy
  cameras still collapse `0` to `None` in the same response, so the sentinel logic is
  exercised against a real mixed inventory for the first time.
- **`enabled` stays `true` while the camera is down.** The three booleans are genuinely
  independent, as the docstring claims: an unplugged camera is enabled, not online, not open.
- Error code **64 = "Host is down"** is the first real code observed. The library does not
  enumerate codes and should not start: 64 is one value from an unknown space.

### G7 — Permission bit 1 (value 2) ✅ CLOSED 2026-08-29 — **it is server-derived, not grantable**
Closed by the account editor's own `POST` body, which Jensen captured from the browser. The
body carries `permissions` as an array of per-camera bitmasks, one value per checkbox state.

**Every checkbox maps to exactly one bit, and value `2` is never transmitted:**

| checkbox | value | bit | constant |
|---|---|---|---|
| Get live video and images | 1 | 0 | `PERM_LIVEVIDEO` |
| Get captured footage | 4 | 2 | `PERM_FILES` |
| Delete captured footage | 8 | 3 | `PERM_FILEDEL` |
| Set camera settings | 16 | 4 | `PERM_SETTINGS` |
| Camera Control (PTZ) | 64 | 6 | `PERM_CAMCONTROL` |
| Change schedules | 128 | 7 | `PERM_SCHED` |
| Set PTZ preset positions | 256 | 8 | `PERM_PTZSET` |
| Get live audio | 512 | 9 | `PERM_AUDIORCV` |
| Trigger motion detection | 1024 | 10 | `PERM_TRIGGER` |
| Send live audio (two-way audio) | 2048 | 11 | `PERM_AUDIOSND` |

Ten checkboxes, ten bits, **none of them bit 1**. The UI cannot set it and the client never
sends it, yet `++systemInfo` reports it — so **bit 1 is computed by the server**. Combined with
the earlier readings (absent under Live-only and on a live-video-only camera; present wherever
`PERM_FILES` is granted), it behaves as a derived companion to captured-file access.

**Action: leave bit 1 out of `PERMISSION_NAMES` permanently, and never treat it as a grant.**
This is now a stronger conclusion than "unnamed": a bit no administrator can set is not a
permission a consumer may reason about. `decode_permissions` ignoring unknown bits is exactly
right. The remaining unknown — *what* the server derives it from — no longer blocks anything.

**Wire-format finding: the `permissions` array is 1-indexed.** Camera *n* is at index *n+1*;
index 0 is unused, and the array is zero-padded well past the camera count. Verified against a
known per-camera configuration: offset-by-one matched **11 of 11** cameras, direct indexing
matched **0 of 11**. Anyone implementing an account write must not index it by camera number.
The library performs no account writes and should not start (AD-13).

### G8 — Do per-camera permissions hide a camera from one endpoint? ✅ CLOSED 2026-08-29 — **yes, and it inverts the earlier conclusion**
With the account granted **only Driveway** (camera 3, mask `1` — live video alone) and every
box unticked on the other ten:

| endpoint | cameras returned |
|---|---|
| `++systemInfo` | **1** — Driveway only |
| `++camStatus` | **11 — every camera**, `enabled:true, online:true, open:true, err:0` on all ten the account may not see |

**`++systemInfo` is permission-scoped. `++camStatus` is not scoped at all.** The earlier entry
here concluded the opposite — that permission is expressed only inside the mask and never by
omitting a camera, so `++camStatus` could serve as the inventory of record. That was based on
account-level permission types and on per-camera configs where every camera still held *some*
right. Both were true as far as they went and both were misleading: a camera with **zero**
permissions is removed from `camera-list` entirely, and only that configuration reveals it.

**Consequences, in order of importance:**

1. **`++camStatus` must never be the membership list.** Using it would create Home Assistant
   entities for cameras the account has no right to see, defeating story 2.7 outright. It
   discloses the existence, count, numbering and live health of every camera on the server to
   any authenticated account, however restricted. That is an information disclosure in the
   product, not in this integration — but the integration must not amplify it.
2. **`++systemInfo` is the inventory of record**, being the only permission-scoped surface.
   `++camStatus` remains the cheap health poll, but its results must be **intersected** with
   the `++systemInfo` set and never unioned with it.
3. **A disabled camera and an unpermitted camera are nearly indistinguishable.** Both are
   present in `++camStatus` and absent from `++systemInfo`. The one discriminator is
   `enabled`: an unpermitted camera reads `enabled:true`, a disabled one `enabled:false`
   (§5.12). It fails when a camera is *both*, and guessing wrong in that direction leaks. So
   **do not** use it to decide entity creation — decide membership from `++systemInfo` alone,
   and never create an entity for a camera absent from it.
4. **This reopens the §5.12 disappearance problem rather than solving it.** Since membership
   must come from the scoped endpoint, a camera that is disabled *or* de-permissioned vanishes
   from it. The answer is not to widen membership but to stop deleting: keep known devices and
   mark them unavailable rather than removing them, which is correct for both causes and leaks
   neither.

**Incidental G7 evidence:** Driveway at live-video-only reads mask `1` — bit 0 alone, **no
bit 1**, and it has no `PERM_FILES`. Consistent with the hypothesis that bit 1 accompanies
captured-footage access. Still not the isolating test.

## Visibility and enablement are two axes (Jensen, 2026-08-29)

The clean model, which resolves the ambiguity G8 records:

1. **Permission answers *can this account see the camera?*** It is a visibility gate and it
   decides whether a camera exists in Home Assistant at all.
2. **`enabled` answers *what state is a visible camera in?*** It is a property of something
   already visible.

The unresolvable cell in the earlier analysis — absent from `++systemInfo` with
`camStatus.enabled:false`, meaning either permitted-and-disabled or unpermitted-and-disabled —
is unresolvable because it is a question that should never be asked. If permission says no,
the camera does not exist for this account and its enabled state is not our concern.

**The defect is in the API's shape, not the model: SecuritySpy collapses the two axes into one
signal.** Disabling a camera withdraws it from `++systemInfo`, so a *state change* is expressed
as a loss of *existence*, on the only permission-scoped surface there is. The integration's job
is to un-collapse them, and **remembered membership** is what does it — permission was
established when the camera was first seen in `++systemInfo`, and it does not stop being true
because the camera was switched off. That is why G8's "keep known devices, mark unavailable"
is right: it is not a workaround, it is restoring the axis the server flattened.

Given remembered membership, both disappearances become deterministic:

| camera known from a prior `++systemInfo`, now absent | `camStatus.enabled` | meaning |
|---|---|---|
| yes | `false` | **disabled** — a state; keep the device, mark unavailable |
| yes | `true` | **de-permissioned** — a visibility change; keep the device, mark unavailable |
| never seen | either | not ours — **create nothing** |

Note both known cases lead to the same action, so the discriminator matters for what the user
is *told*, not for what is done.

### This is a gap in AD-17

AD-17 computes availability from three causes: server unreachable, camera offline via the
status-poll connected flag, and stream loss. **A camera absent from the inventory is a fourth
cause and fits none of them** — it is not a server failure, the connected flag is unreadable
because the camera is not in the permission-scoped payload at all, and no stream is involved.
Whatever epic 2 and 3 decide, AD-17 needs a fourth layer or an explicit statement that
inventory absence is handled elsewhere. Recorded as a decision input; not decided here.

## Open defects found, and their status

| # | Defect | Story | Status |
|---|---|---|---|
| 1 | `403` reported as rejected credentials; permission bitmask missing three bits | 1.11 | ✅ done |
| 2 | `systemInfo` camera inventory decodes to zero against a real server | 1.12 | ✅ done |
| 3 | `Capture.file_size` reads a float-MB field with `_as_int`, losing 99.92% of values and implying bytes | 1.15 | Specced, `ready-for-dev` |
| 4 | Research doc corrections (permissions, trigger keys, `systemInfo` shape, override count, `caplist` fields) | n/a | Annotated inline in the reference doc |
| 5 | Server timezone published as `seconds-from-gmt` but ignored; every event and capture timestamp is off by the server's UTC offset | 1.13 | Specced, `ready-for-dev` |
| 6 | `CameraSettings.presence_rect` reads `presenceRect`, absent on all 11 cameras, so it is permanently `None` | none yet | Low priority; may be custom-model-conditional and untested |
| 7 | Media endpoints return `401` for a *permission* failure, byte-identical to a wrong password, so a Live-only account trips credential reauth forever instead of being told it lacks capture access | 1.14 | Specced, `ready-for-dev`; also invalidates a story 1.11 acceptance row |
| 8 | `async_set_camera_arming` sends the capture modes as if they were an armed state; `mode` actually selects which modes a write targets, so an all-false call is a silent no-op returning `200 OK` | 1.16 | Specced, `ready-for-dev` |

## Keeping the OpenAPI description honest

`aiosecurityspy/docs/securityspy-openapi.yaml` is now a shipped artifact: it travels in the
sdist and CI fails if it stops validating or if any operation loses its `x-verification`
marker. Two rules keep it worth trusting:

1. **Adding or changing an endpoint in the library means updating the description in the
   same change.** A description that lags the client is worse than none, because it reads as
   authoritative.
2. **Never upgrade an `x-verification` marker without evidence.** `research-only` becomes
   `live-6.21` only when a live response has actually been observed. Closing the gaps above
   is what moves those markers. As of 2026-08-29, **8 of 9 operations are `live-6.21`**; only
   `++ssSetSchedule` remains `client-source`, because that write was never performed against
   the live server. Do not upgrade it without doing so.

## Documentation follow-ups

- The 6.20 reference doc is annotated section-by-section where 6.21 contradicts it. It should
  eventually be either rewritten against 6.21 or retitled as a 6.20-era record.
- `caplist` keys `i` and `z` remain unconfirmed. `z` does **not** track `m` as §4.1 claims
  (equal on 1,046 of 10,476 live entries); `i` is an int of unknown meaning.
- **Schedule presets are unmodelled.** `schedule-preset-list` is a real, populatable
  `{name, id}` array (G2) that the library ignores entirely. If any epic-6 story ("see which
  schedule governs a camera", "arm and disarm each mode") ever needs to apply a preset, that
  is an API change and lands in `aiosecurityspy` first per AD-19, along with an OpenAPI
  schema for the field.
- **Schedule and preset ids exceed int32.** Observed 3186401225 for a preset. Any future
  decode, storage, or entity attribute must treat these as arbitrary-width ints.
- **`server.wan-address` is not redacted by `anonymize()`.** Under an Administrator account it
  carries the server's registered remote-access hostname (a personal `*.viewcam.me` name);
  under a lesser account it echoes the connected host. It is not a credential, so story 1.7
  holds as written, but it is personally identifying network information that would travel
  verbatim in a diagnostics dump attached to a public issue. Decide deliberately whether the
  anonymizer should cover identifying hostnames as well as credentials (§5.11).
- **Permission bit 5 (32) has never been observed set** under any of the four permission types
  tested, including Administrator. Unlike bit 1 it appears unused rather than merely unnamed.
- **Decide the inventory of record before epic 2.** `++camStatus` reports 11 cameras and
  `++systemInfo` reports 10 when one is disabled (§5.12). Building devices from `++systemInfo`
  means a camera disabled in SecuritySpy loses its Home Assistant entities instead of going
  unavailable — the exact failure story 3.1 targets. Stories 2.3, 2.7 and 3.1 all depend on
  this choice; it should be made once, in the architecture, not three times.
- **`++ssSetSchedule` — CLOSED by live write 2026-08-29 (§5.14).** Performed on Kitchen with a
  `PERM_SCHED` account, read back at every step, restored with zero fields differing. It
  exposed defect 8: `mode` is a target selector, not an armed state. All 9 OpenAPI operations
  now carry `x-verification: live-6.21`.
- **`ssSetPreset?id={presetId}` is unmodelled.** Found in the shipped client beside
  `ssSetSchedule` (§5.14); it applies a schedule preset (§5.4). Not tested, not in the library,
  not in the OpenAPI description. Relevant to epic 6 if presets are ever surfaced.
- **Unmodelled endpoints found in the browser capture** (§5.15, §5.17), none of them defects,
  all of them relevant to later epics: `ptzcommand`, `clip`, `cliplist`, `dashImage`,
  `setTags`, `delete`, `deviceList`, `hls`, `++image`, `++video`, `++audio`, `ssSetPreset`,
  and the `/video` WebSocket with its binary opcodes. Anything the integration needs from
  these lands in `aiosecurityspy` first, per AD-19.
- **`anonymize()` covers neither `wan-address` nor `deviceList`.** Both publish internal
  network layout (a personal `*.viewcam.me` hostname; camera LAN IPs and ONVIF UUIDs). Neither
  is a credential, so story 1.7 holds as written — but a diagnostics dump attached to a public
  issue would carry them. One decision, covering both (§5.11, §5.17.2).
- **`is_credential_key` misses SecuritySpy's `*Pass` fields.** `setPass`, `fsPass` and
  `quitPass` on `++settings-general` are real passwords and are not matched, while
  `videoPassthrough` is correctly *not* matched (§5.18.3). Latent today because the library
  reads none of those pages. These are SecuritySpy's *application* passwords, and the risk is a
  diagnostics dump attached to a public issue — not LAN traffic, which is plain HTTP to the
  cameras regardless. Cheap to fix and squarely within that function's purpose. **Specced as story 1.17**, which
  also covers `wan-address`, `deviceList` and both `auth=` forms under the widened AD-13.
- **Read the vendor spec first for DISCOVERY, then verify everything live.** It is stale — it
  names 6.20-era settings fields and a `ptz/controls` path that 404s — so it is useful for
  learning what exists and unreliable on exact shapes. Mirrored locally at
  `~/doc-repos/securityspy/` with a README explaining how far to trust it; upstream is
  https://bensoftware.com/securityspy/web-server-spec.html. **This was established on day one**
  in `securityspy-api-reference.md`'s preamble and re-derived in §5.19 for want of reading it.
  documents `cameramodes` (armed state as plain text, and it answers for disabled cameras) and
  `getptzcapabilities` (a PTZ bitmask) — both rediscovered the hard way, and both better sources
  than what the library currently derives (§5.19).
- **Three of nine operations are undocumented**: `camStatus`, `caplist`, `getpreview`. Keep
  using them. The vendor spec is stale and unmaintained, so "undocumented" is a weak signal —
  and all three are called by the shipped web client on every page load, which is arguably
  better evidence of support. `x-vendor-documented` in the OpenAPI is provenance, not a warning.
- **Prefer the documented name `setSchedule`** over `ssSetSchedule`; both work on 6.21 (§5.19.1).
- **Adopt `++cameramodes` for arming state.** It may also resolve the inventory-of-record
  problem for arming specifically, since it answers for cameras `systemInfo` omits (§5.12).
- **⚠ Account writes through the web settings form did not persist on 6.21.** Two separate
  changes made through the account editor — a per-camera permission matrix and a password
  rotation — were submitted with a well-formed `POST` body and **neither reached the server**:
  the permission masks never changed, and the prior password still authenticated afterwards
  while the new one returned `401`. By contrast a `++settings-cameras` write in the same
  session (G4) persisted and restored cleanly, so this is specific to the account/web settings
  form, not to writes generally. Cause not established — candidates are a configured settings
  password (`setPass`, §5.18.3) gating the write, or the form requiring a separate apply step.
  **Operational lesson: never trust the dialog. Verify an account change by authenticating with
  the new credential.** A rotation that silently fails leaves the old password live while the
  operator believes it is retired.
