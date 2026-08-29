---
title: "Story 1.15: Capture size is megabytes, and fractional"
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

**Problem:** `Capture.file_size` is typed `int | None` and decoded with `_as_int(payload.get("m"))`, but `caplist.m` is a **float in megabytes**. SecuritySpy's own client names the parameter `mb` and formats it as `parseInt(mb*1000)+' KB'` (§5.6). `_as_int` is deliberately strict and returns `None` for any non-integral float, so across 10,476 live captures -- observed range `0.04` to `9129.763` -- **only 8 decode to a value**; the other 10,468 silently become `None`. The 8 that survive are megabyte counts wearing a name that reads as bytes. The damage is not only the missing field: `_tiebreak` (`client.py:373`) uses `file_size` as an ordering key, substituting `-1` when it is `None`, so the "every observable field participates" guarantee collapses to a constant for 99.92% of captures and the documented determinism quietly leans on the fields that remain.

**Approach:** Decode the value as what the server sends -- a float count of megabytes -- and name the field so its unit is unmistakable. Do not convert to bytes: multiplying a 3-decimal megabyte figure by a million fabricates precision the server never transmitted, and SecuritySpy's own client treats the unit as decimal MB, so even the multiplier would be a guess dressed as a fact.

## Boundaries & Constraints

**Always:** The field's name states its unit, so no caller has to infer it. A float is preserved as a float; a value the server sends as an integer is still valid and decodes. Negative and non-finite values (`NaN`, `Infinity`, which `json.loads` accepts) remain rejected as `None`, exactly as the strictness of `_as_int` intends today. `_tiebreak` continues to include the size so its "every observable field participates" claim stays true, and its sentinel stays outside the range a real value can take. This is a **breaking rename of a public field** -- the version bump, the changelog and the `manifest.json` pin move together (AD-19).

**Block If:** a consumer requires the size in bytes. None exists today -- `_tiebreak` is the only reader in either repository -- but if a Home Assistant sensor is later found to need bytes, stop and decide the multiplier deliberately rather than picking 1,000,000 or 1,048,576 in passing. The HA `data_size` device class accepts megabytes natively, so this is expected to stay theoretical.

**Never:** No conversion to bytes, and no rounding to an integer of any unit -- both invent precision. No retention of the old `file_size` name as an alias: an alias that silently means something different from before is worse than a rename that fails loudly. No re-derivation of the size from `z`, whose meaning is still unconfirmed and which §5.6 shows does **not** track `m` (equal on only 1,046 of 10,476 entries). No change to `_as_int` itself -- its strictness is correct and other fields depend on it; the wrong choice was applying it to a float field.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Typical capture | `m: 0.945` | Decodes to 0.945 MB | No error expected |
| Large capture | `m: 9129.763` | Decodes to 9129.763 MB; no overflow or truncation | No error expected |
| Integral value | `m: 24` | Decodes to 24.0 MB -- still valid | No error expected |
| Numeric string | `m: "0.945"` | Decodes, consistent with the other decoders' tolerance | No error expected |
| Zero | `m: 0` | A real zero, distinct from unknown | No error expected |
| Absent | No `m` key | `None`; the rest of the capture decodes | No error expected |
| Negative | `m: -1` | `None` -- a size cannot be negative | No error expected |
| Non-finite | `m: NaN` or `Infinity` | `None` | Never raises |
| Wrong type | `m: true`, `m: {}` | `None` | Never raises |
| Ordering | Two captures identical but for size | `_tiebreak` still separates them | No error expected |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/models.py` -- `Capture.file_size` declaration (line 1098) and its decode (lines 1134, 1148). The `>= 0` guard already there is correct and should survive the retype.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `_as_int` (line 101): read, do not change. Its float branch (line 115) rejecting non-integral values is exactly why 10,468 captures decode to `None`; the fault is the call site.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `_tiebreak` (line 373): the only reader of the field. Its `-1` sentinel must stay unreachable by a real value.
- `aiosecurityspy/tests/test_models.py` -- lines 741, 767: `FIXTURE_MOVIE_SIZE` and the unusable-value cases. The fixture pins an integral size, which is why no test could fail -- §5.6 shows an integral `m` is 8-in-10,476 on a real server.
- `aiosecurityspy/tests/test_client.py` -- lines 1284, 1552, 1763: `Capture` constructions to update.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export list, sorted (RUF022), if a public name changes.
- `aiosecurityspy/docs/securityspy-openapi.yaml` -- the `caplist` entry schema types and documents `m`; AD-19 requires it to move in the same change.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §5.6 -- the live evidence and the shipped-client formatting that establishes the unit.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- decode `m` as a fractional megabyte count under a name that states the unit -- a size field that is `None` for 99.92% of real captures is worse than absent, because it reads as "this capture has no size".
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- keep the size in `_tiebreak` with a sentinel a real value cannot reach -- the ordering guarantee is stated in its docstring and must remain true.
- [ ] `aiosecurityspy/docs/securityspy-openapi.yaml` -- type `m` as a number and state the unit -- it is currently the only written record a future reader would trust.
- [ ] `aiosecurityspy/tests/test_models.py` -- replace the integral fixture size with a fractional one and cover every matrix row -- the integral fixture is precisely what made the defect invisible.
- [ ] `aiosecurityspy/CHANGELOG.md` -- record the breaking rename -- a consumer pinning the old name must find out at upgrade, not at runtime.

**Acceptance Criteria:**
- Given the live `caplist` sample of 10,476 entries, when it is decoded, then every entry carrying an `m` value yields a size, not `None`.
- Given a capture of 0.945 MB, when a consumer reads its size, then the unit is unambiguous from the field name alone, with no conversion applied.
- Given two captures differing only in size, when they are ordered, then they are separated deterministically.

## Spec Change Log

## Review Triage Log

## Design Notes

This is the same failure class as stories 1.11 and 1.12, and the third instance: a wire type inferred from research, then pinned by a fixture written to match the inference, so no test could contradict it. The fixture is the load-bearing part. Choosing a *fractional* size in the new fixture is not incidental -- an integral one reproduces the original blind spot exactly.

`m` was verified as float on **every one of 10,476 live entries**; the 8 integral-valued ones are coincidence, not a second shape.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest` -- expected: all tests pass
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src` -- expected: clean
- `cd aiosecurityspy && uv run python -c "import openapi_spec_validator,yaml;openapi_spec_validator.validate(yaml.safe_load(open('docs/securityspy-openapi.yaml')))"` -- expected: no output
- `uv run pytest` (repository root) -- expected: the integration suite still passes against the renamed field

**Manual checks (if no CLI):**
- Decode a live `++caplist` response and confirm the count of captures with a usable size matches the count carrying an `m` key, rather than collapsing to a handful.
