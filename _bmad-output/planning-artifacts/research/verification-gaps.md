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

### G1 — Event stream is entirely unverified 🔴
**Blocks:** confidence in story 1.3 (CR framing, heartbeat) — a long-lived streaming parser
built wholly from research, and the highest-consequence code still resting on assumptions.
**Access needed:** none believed — the existing probe account should reach `++eventStream`.
**Risk:** none; a read-only streaming GET, disconnect when done.
**Action:** probe `++eventStream?version=3`, capture a sample, verify CR-only framing and the
heartbeat interval against the story 1.3 implementation.

### G2 — No user-defined schedules exist 🟢
**Blocks:** story 1.10's AC "including both the built-in defaults and any the user defined".
`schedule-list` holds only built-ins 0–3 and `schedule-preset-list` is `[]`, so the
user-defined case is untested and the id a new schedule receives is unknown.
**Access needed:** Jensen creates one throwaway schedule in the SecuritySpy UI.
**Risk:** very low, fully reversible.
**Action:** create a schedule → re-read `++systemInfo` → confirm the id and shape → delete it.

### G3 — No admin-privileged read 🔴
**Blocks:** the largest remaining block of unverified guesses. The probe account lacks bit 4
("Set camera settings"), so every `++settings-*` returns 403. Cannot confirm `enabled` in the
`++settings-cameras` JSON read; cannot validate research §8.1's ~120 keys against reality;
cannot read `++settings-sched` for the user-defined schedule object shape; cannot see the
`settings-web` accounts structure.
**Access needed:** an account granted bit 4, ideally created for this and deleted afterward.
**Risk:** moderate — such an account can also *write*. Prefer a temporary account over
promoting the existing probe user, so the least-privileged probe stays least-privileged.
**Action:** with access, re-verify §8.1 wholesale; that section has never been checked.

### G4 — No write has ever been performed 🟡
**Blocks:** story 1.10's enable write is read from shipped client source, not round-trip
verified. Also unverified on 6.21: that partial writes are genuinely non-destructive, and the
acknowledgement shape (`{"camUpdate": …}` vs `{"reload": true}`).
**Access needed:** explicit go-ahead, plus a camera Jensen names as safe.
**Risk:** real — a write to a live security system. Must be a deliberate, named, reversible
toggle (`enabled` on, then off), never a batch.
**Action:** toggle `enabled` on the named camera, confirm via `++camStatus`, confirm no other
settings key changed, toggle back.

### G5 — No camera-scoped 403 observed 🟡
**Blocks:** story 1.11's matrix row "the error carries that camera number". Only
server-scoped 403s on settings endpoints were produced.
**Access needed:** an account with live-video but *without* `PERM_FILES`, then a capture
fetch. Requires G3.
**Risk:** low once G3 exists.

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
