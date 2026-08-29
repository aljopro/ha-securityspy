---
title: SecuritySpy verification gaps and action items
date: 2026-08-29
status: open
companion_to: securityspy-6.21-verification.md
---

# Verification Gaps and Action Items

What could not be verified against the live 6.21 server on 2026-08-29, what each gap
blocks, and what access would close it. Ordered by value-per-risk.

**Why this list exists:** four defects have now been found, and three of them were the same
failure — a wire shape or type *guessed* from research, then pinned by a fixture written to
match the guess, so no test could ever fail. Everything still unverified below is exposed to
that same failure mode.

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

### G6 — No camera in an error state 🟢
**Blocks:** confirming `CameraStatus.error`'s type. All 11 cameras report `err: 0` (an
**int**) and `errDesc: ""`, while the field is typed `str | None`. What a real error value
looks like is unknown.
**Access needed:** a camera briefly disconnected.
**Risk:** low but disruptive to a live system. Lowest priority; take it opportunistically if
a camera ever errors on its own.

### G7 — Permission bit 1 (value 2) is unexplained ⚪
Set on all 11 cameras; named nowhere in the web client, the account editor, or the binary.
**Access needed:** likely a vendor answer. **Action:** none — do not assign it a meaning.
Treat as reserved.

## Open defects found, and their status

| # | Defect | Story | Status |
|---|---|---|---|
| 1 | `403` reported as rejected credentials; permission bitmask missing three bits | 1.11 | Specced, `ready-for-dev` |
| 2 | `systemInfo` camera inventory decodes to zero against a real server | 1.12 | Specced, `ready-for-dev` |
| 3 | `Capture.file_size` reads a float-MB field with `_as_int`, losing 99.92% of values and implying bytes | **none yet** | ⬅ **needs a story — decision pending** |
| 4 | Research doc corrections (permissions, trigger keys, `systemInfo` shape, override count, `caplist` fields) | n/a | Annotated inline in the reference doc |
| 5 | Server timezone published as `seconds-from-gmt` but ignored; every event and capture timestamp is off by the server's UTC offset | 1.13 | Specced, `ready-for-dev` |
| 6 | `CameraSettings.presence_rect` reads `presenceRect`, absent on all 11 cameras, so it is permanently `None` | none yet | Low priority; may be custom-model-conditional and untested |
| 7 | Media endpoints return `401` for a *permission* failure, byte-identical to a wrong password, so a Live-only account trips credential reauth forever instead of being told it lacks capture access | **none yet** | ⬅ **needs a story**; also invalidates a story 1.11 acceptance row |

## Keeping the OpenAPI description honest

`aiosecurityspy/docs/securityspy-openapi.yaml` is now a shipped artifact: it travels in the
sdist and CI fails if it stops validating or if any operation loses its `x-verification`
marker. Two rules keep it worth trusting:

1. **Adding or changing an endpoint in the library means updating the description in the
   same change.** A description that lags the client is worse than none, because it reads as
   authoritative.
2. **Never upgrade an `x-verification` marker without evidence.** `research-only` becomes
   `live-6.21` only when a live response has actually been observed. Closing the gaps above
   is what moves those markers — three of the eight operations are still `research-only`.

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
