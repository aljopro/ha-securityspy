---
title: "Story 1.17: Redact secrets and identifying detail, not just credentials"
type: 'bugfix'
created: '2026-08-29'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `anonymize()` is the single exit path for diagnostics (AD-13), but `is_credential_key` only recognises a narrow set of names. Live capture of the settings surface found three genuine SecuritySpy passwords it does not match -- `setPass`, `fsPass`, `quitPass` on `++settings-general` (research §5.18.3) -- and two payloads carrying identifying network detail that is not a credential and passes through verbatim: `server.wan-address`, a personal `*.viewcam.me` hostname visible to privileged accounts (§5.11), and `deviceList`, which publishes camera LAN IPs and ONVIF UUIDs (§5.17.2). AD-13 was widened on 2026-08-29 to cover *anything that is PII, a secret, or a password*. The exposure is latent -- the library reads none of those pages today -- but a Home Assistant diagnostics dump is deliberately exported and routinely attached to public issues, which is the one path where this data leaves the network on purpose.

**Approach:** Teach the anonymizer the categories AD-13 now names, rather than adding three field names. Recognise SecuritySpy's `*Pass` convention as credential-bearing, treat identifying network detail as its own disclosure class, and make an unrecognised field default to redacted rather than to disclosed. Where a value genuinely cannot be withheld, it is reduced rather than dropped and recorded in a **disclosure register** that ships with the library, so every deliberate exposure is documented rather than merely defensible.

## Boundaries & Constraints

**Always:** The scope is everything shareable, not only the diagnostics dump — **log output at every level, including debug, is in scope**, since a pasted debug log is as public as a dump. Any value that must remain disclosed is reduced to the least revealing useful form and entered in the disclosure register in the same change. The anonymizer stays dependency-free and non-throwing -- it is the last thing that runs before a dump leaves, so it can never be the thing that fails. A redacted value is replaced by the existing `REDACTED` sentinel and never partially masked, so a dump cannot be mined for a prefix. `is_credential_key` remains precise about what it claims: it says a key is *credential-bearing*, and identifying-but-not-secret fields are handled as their own class rather than by widening that predicate's meaning. Redaction is keyed on the field's category, not on the value's shape, so a password that happens to look like a hostname is still redacted. The `!`-prefixed `auth` token is treated as a secret wherever it appears.

**Block If:** a field genuinely cannot be withheld without making a dump useless for debugging. Do not settle that silently: the field then wants a *reduced* form (a stable hash, or a shape like `192.168.x.x`) and an entry in the disclosure register, and which fields qualify is a judgement to raise.

**Never:** No allow-list of field names as the primary mechanism -- that is what failed here, and it fails again for the next endpoint. No encryption in the anonymizer: AD-13 says "redacted or encrypted", and for a diagnostics dump redaction is the correct half; a dump the user cannot read is not a diagnostic. No change to what the client sends on the wire -- this story is about what leaves in a dump. No construction of the base64 `auth=` form anywhere, now or later (§5.16.1); if any code path would need it, stop.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| SecuritySpy app passwords | `setPass`, `fsPass`, `quitPass` | Redacted | No error expected |
| Known credential names | `password`, `username` | Redacted, as today | No error expected |
| False-positive guard | `videoPassthrough` | **Not** redacted -- it is not a secret | No error expected |
| Remote-access hostname | `wan-address: "example.viewcam.me"` | Not disclosed verbatim | No error expected |
| Device inventory | `deviceList` entries with `ip` and ONVIF `uuid` | Not disclosed verbatim | No error expected |
| Scoped stream token | A value beginning `!` in an `auth` field or URL | Redacted | No error expected |
| Credentials in a URL | `?auth=<base64>` in any captured URL | Redacted | No error expected |
| Unknown new field | A key the anonymizer has never seen | Redacted by default | Documented as the default |
| Non-string values | `None`, ints, nested structures | Walked as today, without raising | Never raises |
| Anonymizer given something unwalkable | An object whose attribute access raises | Degrades to the existing marker | Never raises |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- `is_credential_key` and `anonymize` (module docstring states the no-dependency, never-fail contract; `redact_url` at ~line 143 handles URLs). The `REDACTED` sentinel comes from `const.py`.
- `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- `redact_url` (~line 143-201): already redacts userinfo in a URL; the `auth=` query parameter in both forms belongs here.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- `REDACTED`; also the natural home for any named set of credential-bearing or identifying keys.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §5.11, §5.16.1, §5.17.2, §5.18.3 -- the live evidence for every field named above.
- `.../architecture/.../ARCHITECTURE-SPINE.md` AD-13 -- the widened rule this story implements; do not restate it, implement it.
- `custom_components/securityspy/diagnostics.py` (if present) -- the integration's dump must still route through the library anonymizer as its only exit path.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- recognise SecuritySpy's `*Pass` naming as credential-bearing -- three real passwords are missed today by a predicate whose whole job is to know this protocol's credential names.
- [ ] `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- handle identifying network detail as its own class, and default an unrecognised key to redacted -- an allow-list is what let these through, and the next endpoint will bring fields nobody has enumerated.
- [ ] `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- redact both `auth=` forms in URLs -- the base64 form is literally the account's credentials, and the `!` token is a bearer secret.
- [ ] `aiosecurityspy/tests/test_diagnostics.py` -- cover every matrix row, including the `videoPassthrough` non-redaction and the redact-by-default case -- a test suite that only asserts known-bad names would have passed before this story and after it.
- [ ] `aiosecurityspy/docs/` -- add the disclosure register: every field deliberately left visible in a shareable artifact, the artifact, why it could not be withheld, and its reduced form -- an undocumented exposure is a defect even when it was the right call.
- [ ] `aiosecurityspy/src/aiosecurityspy/` -- audit existing `_LOGGER` calls against the widened rule -- logs are shared as readily as dumps and are not currently covered by the anonymizer at all.
- [ ] `aiosecurityspy/CHANGELOG.md` -- record the behaviour change -- a consumer may be relying on a field currently appearing in dumps.

**Acceptance Criteria:**
- Given a payload containing `setPass`, `fsPass` or `quitPass`, when it is anonymised, then no value survives in the output.
- Given a field named `videoPassthrough`, when it is anonymised, then its value is preserved -- the rule must not become "anything containing 'pass'".
- Given a URL carrying `auth=` in either form, when it is anonymised, then the value does not appear in the output.
- Given a key the anonymizer has never seen, when it is anonymised, then the value is not disclosed.
- Given any field deliberately left visible in a shareable artifact, when the library is released, then that field appears in the disclosure register with its justification and reduced form.

## Spec Change Log

## Review Triage Log

## Design Notes

The failure mode worth naming: the anonymizer was written against the fields the library reads, so it is correct for today's payloads and silently wrong for tomorrow's. Redact-by-default inverts that -- a new field is safe until someone decides it is disclosable, instead of disclosed until someone notices.

AD-13's "redacted **or encrypted**" is deliberately not both here. Encryption is the right half of that rule for credentials at rest in a config entry; a diagnostics dump is read by the user who exports it, so an encrypted dump is not a diagnostic. Redaction is the correct half for this story.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest` -- expected: all tests pass
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src` -- expected: clean
- `uv run pytest` (repository root) -- expected: the integration's diagnostics tests still pass

**Manual checks (if no CLI):**
- Anonymise a real `++systemInfo` and a real `deviceList` response and confirm no hostname, LAN IP, ONVIF UUID or password value appears in the output.
