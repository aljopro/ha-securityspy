---
title: 'Story 1.11: A permission denial is not an authentication failure'
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

**Problem:** `_map_status` maps both `401` and `403` to `SecuritySpyAuthError`, whose message reads "credentials were rejected". Verified against a live 6.21 server, `403` means the credentials are *correct* and the account merely lacks a permission bit -- so a user running the least-privileged account the security guidance recommends is told to check a password that is right, and a consumer implementing FR-27 opens a reauth flow for a problem no re-authentication can fix. The permission bitmask is also incomplete: it is missing the very bit that gates settings writes.

**Approach:** Split the two failures at the transport seam. `403` raises `SecuritySpyPermissionError`; `401` keeps raising `SecuritySpyAuthError` exactly as today. Complete `PERMISSION_NAMES` with the three bits the 6.21 account editor defines, and give the one inverted-sense bit a representation that cannot be read as a granted capability.

## Boundaries & Constraints

**Always:** `401` keeps its current behaviour and message, unchanged. `403` raises `SecuritySpyPermissionError`, which already exists and already carries a permission name and optional camera number. Where the endpoint implies the permission, name it; where it does not, the error must still be raised, carrying whatever the library can honestly state. Both errors stay credential-free (AD-13) and both remain `SecuritySpyError` subclasses. `PERM_SETTINGS = 16` (bit 4, "Set camera settings"), `PERM_NODOWNLOAD = 4096` (bit 12), `PERM_PUSH_STREAMS = 8192` (bit 13) are added as documented constants and exported.

**Block If:** none identified -- the 401/403 split, the three bit values and their labels are all verified against the running 6.21 server and its shipped account editor (verification doc §4.1, §5.2).

**Never:** No parsing of the `403` response body to discover the permission -- the server sends only the fixed string `403 Access Denied`. No inspection of the `WWW-Authenticate` header to make the decision; the status code alone decides, because the numeric status is the one thing the server reports reliably (its reason phrase is not: `403` arrives as `403 OK`). No pre-flight permission fetch before a write -- the library holds no camera inventory and must not acquire one to serve a request. No change to `require_permission`'s pure-guard contract. No rename or resignature of `SecuritySpyPermissionError`. Bit 1 (value 2) is **not** given a name: it is set on live cameras but named nowhere in the application.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Unprivileged account, settings read | `++settings-cameras` answers `403` | `SecuritySpyPermissionError` naming the `settings` permission | Typed; never `SecuritySpyAuthError` |
| Unprivileged account, camera-scoped call | `403` on a request whose camera number is known | The error carries that camera number | Typed |
| `403` on an endpoint with no implied permission | Any other endpoint answers `403` | `SecuritySpyPermissionError` is still raised, without a camera number | Typed |
| Wrong password | Server answers `401` | `SecuritySpyAuthError`, message and type unchanged from today | Typed |
| Nonexistent user / no credentials | Server answers `401` | `SecuritySpyAuthError`, unchanged | Typed |
| Consumer distinguishing the two | Catches `SecuritySpyError` | The two are separable by type alone, with no message-string matching | -- |
| Decoding a complete bitmask | `permissions = 839` | The five granted names decode; the undocumented bit 1 is ignored, not reported | No error |
| Inverted-sense bit set | `permissions` includes `4096` | The camera is **not** reported as granting a "no download" capability | No error |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `PERM_SETTINGS = 16`, `PERM_NODOWNLOAD = 4096`, `PERM_PUSH_STREAMS = 8192` beside the existing non-contiguous `PERM_*` block (~line 246-256), each with a doc comment citing verification §4.1; add `PERM_SETTINGS`/`PERM_PUSH_STREAMS` to `PERMISSION_NAMES` as `"settings"` and `"push_streams"`. `PERM_NODOWNLOAD` is deliberately **excluded** from `PERMISSION_NAMES` -- that mapping feeds `has_permission`, which means "grants", and a deny-bit cannot be answered there. Export every new name in sorted (RUF022) order.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: `_map_status` (~line 776) currently raises `SecuritySpyAuthError` for `(_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN)`. Split: `401` keeps `SecuritySpyAuthError`; `403` raises `SecuritySpyPermissionError`. `_map_status` takes only a status today, so it needs the caller's context to name a permission -- add an optional parameter carrying the permission name (and camera number where the call site has one) and pass it from the settings and arming call sites. Every existing caller that passes nothing still raises the typed permission error.
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- read: `SecuritySpyPermissionError.__init__(permission, camera_number=None)` (~line 105) and the module docstring's rule that caller mistakes stay outside the hierarchy. The message is already credential-free; no change expected.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- read: `has_permission` / `require_permission` (~line 590-620) and `_PERMISSION_NAME_SET`, which derive from `PERMISSION_NAMES` and therefore pick up the new names automatically. Confirm the derivation, and that a deny-bit's absence from the mapping is deliberate and commented.
- `aiosecurityspy/tests/test_client.py` -- the `FakeSession`/`FakeResponse` harness and the existing `401`/`403` status tests, which currently assert `SecuritySpyAuthError` for both and must be split.
- `aiosecurityspy/tests/test_models.py` -- permission decoding tests, to extend with the new bits and the real `permissions = 839`.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §4.1, §5.2, §7.1 -- the evidence for the bit table and the 401/403 split.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/const.py` -- add the three permission constants and extend `PERMISSION_NAMES` with two of them -- the library cannot name the permission that gates a settings write without bit 4.
- [ ] `aiosecurityspy/src/aiosecurityspy/client.py` -- split `403` from `401` in `_map_status` and thread an optional permission context from the call sites that know one -- this is the defect.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- confirm and comment that `PERM_NODOWNLOAD` is excluded from the grant-shaped mapping on purpose -- an inverted bit reported as a grant is worse than an absent one.
- [ ] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export the new constants in sorted order.
- [ ] `aiosecurityspy/tests/test_client.py`, `aiosecurityspy/tests/test_models.py` -- cover every I/O-matrix row, including that `401` behaviour is unchanged and that a `403` on a context-less endpoint still raises the permission error.
- [ ] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document the behaviour change; this is a breaking change for any consumer currently catching `SecuritySpyAuthError` to handle a `403`.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a consumer that catches `SecuritySpyAuthError` to trigger a credential re-prompt, when the server answers `403`, then that consumer is not triggered.

## Spec Change Log

## Review Triage Log

## Design Notes

**Why the status code alone decides.** The server offers three signals -- status, body text, and the presence of `WWW-Authenticate` -- and only the status is worth depending on. The body is a fixed string with no permission in it, and the reason phrase is actively unreliable (`403 OK`, `400 OK`). Depending on the header would add a second condition that can only ever agree with the status.

**Why `PERM_NODOWNLOAD` is a constant but not a name.** `PERMISSION_NAMES` feeds `has_permission(name)`, which reads as "this camera grants X". Bit 12 means *deny download*, so `has_permission("no_download")` returning `True` would be read by every call site as a capability the camera has. Exporting the constant lets a consumer test the bit deliberately; leaving it out of the name mapping stops it being answered accidentally.

**Naming the permission is best-effort by design.** The server never says which bit it wanted. Endpoints whose required permission is known from the research (`settings-*` -> `settings`, `ssSetSchedule` -> `schedule`) can name it; anything else raises the same typed error with no name rather than guessing.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, including the pre-existing `401` tests unchanged
