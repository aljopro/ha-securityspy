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

### G2 — No user-defined schedules exist 🟢
**Blocks:** story 1.10's AC "including both the built-in defaults and any the user defined".
`schedule-list` holds only built-ins 0–3 and `schedule-preset-list` is `[]`, so the
user-defined case is untested and the id a new schedule receives is unknown.
**Access needed:** Jensen creates one throwaway schedule in the SecuritySpy UI.
**Risk:** very low, fully reversible.
**Action:** create a schedule → re-read `++systemInfo` → confirm the id and shape → delete it.

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

### G5 — No camera-scoped 403 🟡 STILL OPEN
Unchanged. Producing one needs an account with live-video but *without* `PERM_FILES`, then a
capture fetch. The elevated account has more permissions, not fewer, so it could not produce
this. Story 1.11's matrix row for "the error carries that camera number" remains unverified.

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
