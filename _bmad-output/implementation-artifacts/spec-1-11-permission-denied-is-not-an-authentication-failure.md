---
title: 'Story 1.11: A permission denial is not an authentication failure'
type: 'bugfix'
created: '2026-08-29'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
baseline_revision: '2c215f85cb212adac18c1ae22e412fe3366f4de0'
final_revision: '917da39'
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
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- add the three permission constants and extend `PERMISSION_NAMES` with two of them -- the library cannot name the permission that gates a settings write without bit 4.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- split `403` from `401` in `_map_status` and thread an optional permission context from the call sites that know one -- this is the defect.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- confirm and comment that `PERM_NODOWNLOAD` is excluded from the grant-shaped mapping on purpose -- an inverted bit reported as a grant is worse than an absent one.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export the new constants in sorted order.
- [x] `aiosecurityspy/tests/test_client.py`, `aiosecurityspy/tests/test_models.py` -- cover every I/O-matrix row, including that `401` behaviour is unchanged and that a `403` on a context-less endpoint still raises the permission error.
- [x] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document the behaviour change; this is a breaking change for any consumer currently catching `SecuritySpyAuthError` to handle a `403`.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a consumer that catches `SecuritySpyAuthError` to trigger a credential re-prompt, when the server answers `403`, then that consumer is not triggered.

## Spec Change Log

- `SecuritySpyPermissionError.__init__` takes a required `permission: str`, with no
  unnamed/optional form (and the spec's "Never" section forbids resignaturing it). For a
  `403` on an endpoint whose required permission this library does not know, `_map_status`
  passes the literal string `"unknown"` (named `_PERMISSION_UNKNOWN` in `client.py`) rather
  than leaving the field empty or guessing a real permission name. This is the one honest
  string available under the existing signature.
- Threaded `permission`/`camera_number` as optional keyword-only parameters through the
  shared transport seam (`_map_status`, `_request`, `_request_json`, `_request_text`,
  `_post_form`) rather than adding a second status-mapping function, so there is still
  exactly one place -- `_map_status` -- that decides what a status code means.
  `_request_bytes` and `_stream_bytes` (previews and capture-file downloads) were left
  without the new parameters: neither endpoint implies a specific permission, so a `403`
  there raises `SecuritySpyPermissionError` with the `"unknown"` sentinel, matching every
  other context-less endpoint.
- While updating the README's settings/arming example, corrected a pre-existing inaccuracy
  in its `require_permission` guard: it named `"camera_control"` as covering the settings
  page, but bit 4 (`PERM_SETTINGS`, newly named "settings" by this story) is the permission
  that actually gates it. `"camera_control"` (bit 6) is a separate grant. Updated the
  example to guard with `"settings"`.
- `test_permission_decode_of_the_observed_mask` (`test_settings.py`) and
  `test_observed_bitmask_decodes_bit_by_bit` (`test_models.py`) both assert against the
  research §9 mask `10207`, which turns out to already have bit 4 (`PERM_SETTINGS`) and
  bit 13 (`PERM_PUSH_STREAMS`) set. Both tests' expected sets were extended to include
  `"settings"` and `"push_streams"` -- this is the existing fixture value decoding more
  completely, not a new fixture.

- [x] [Review][Patch] (2026-09-12, independent follow-up review, R3) `async_get_captures()` (`++caplist`) documents that it can raise `SecuritySpyPermissionError` but its `_request_json` call passed no `permission=` context, unlike the sibling media methods (`async_get_capture_preview`, `async_get_capture_file`) that correctly pass `PERMISSION_NAMES[PERM_FILES]` for the same 'files'-gated capture-access surface (research §5, "Get captured footage" -> `PERM_FILES`). A denied account got `SecuritySpyPermissionError("unknown", ...)` from this one call site instead of the correctly-named `"files"` — directly undermining this story's own point for one endpoint. **Fix:** pass `permission=PERMISSION_NAMES[PERM_FILES]` (no `camera_number`, since the request spans every camera in the batch). Strengthened `test_permission_rejection_surfaces_from_the_shared_seam` to assert `err.value.permission == PERMISSION_NAMES[PERM_FILES]`, matching the assertion style already used for the sibling methods. All gates green, 1019 passed.

## Review Triage Log

### 2026-08-29 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 1 (high 1)
- defer: 0
- reject: 9
- addressed_findings:
  - `[high]` `[patch]` Edge Case Hunter flagged that hard-coding `permission="settings"`/`"schedule"` on the settings/arming call sites means any `403` there is reported as a missing permission even when the real cause is unrelated. Blind Hunter separately flagged, correctly, that this repo's own downstream consumer -- `custom_components/securityspy/__init__.py` and `config_flow.py` -- catches only `SecuritySpyAuthError`, and would silently stop getting precise handling for a permission-denied `403` once this story ships, since `SecuritySpyPermissionError` is a sibling type, not a subtype. Both `except SecuritySpyAuthError` sites already fall through to a generic `except SecuritySpyError` / `isinstance` default (`"unknown"`), so this was not a crash, but it was a real precision regression relative to today's `"invalid_auth"` messaging for the exact same `403`. Added `except SecuritySpyPermissionError` in `__init__.py` (`ConfigEntryError`, translation key `permission_denied`, with a comment on why `ConfigEntryAuthFailed`/`ConfigEntryNotReady` are both wrong here) and a `(SecuritySpyPermissionError, "permission_denied")` row in `config_flow.py`'s `_ERROR_KEYS`; added the `permission_denied` string to both `strings.json` and `translations/en.json` (`config.error` and `exceptions`); added a parametrized row to each of `tests/test_config_flow.py`, `tests/test_init.py`, and the hardcoded key list in `tests/test_translations.py`. This is outside the spec's Code Map (which scoped changes to `aiosecurityspy/` only) but is a same-repo, same-commit consumer of the exact type this story introduces, so it was fixed in this pass rather than deferred.

Rejected: the claim that naming `permission="settings"` on a settings-endpoint `403` is an unverified generalization (this is exactly what the spec's Code Map and I/O matrix direct); the "breaking change needs a compat shim / version bump" findings (the spec explicitly calls this a breaking change with no shim required, and versioning is a release concern outside this bugfix's scope); the claim that `camera_number` should thread through to `async_get_capture_preview`/`async_get_capture_file` (the spec's Code Map explicitly scopes camera-number threading to "the settings and arming call sites" only); the `noqa: PLR0913` and `PERM_PUSH_STREAMS`-has-no-guard-call-site findings (both spec-directed, not defects); and the remaining meta-commentary (docstring duplication between `models.py` and `const.py`, the `_PERMISSION_UNKNOWN` magic-string naming, a hypothetical future firmware changing 403's meaning) as non-actionable or already covered by the Spec Change Log.

## Design Notes

**Why the status code alone decides.** The server offers three signals -- status, body text, and the presence of `WWW-Authenticate` -- and only the status is worth depending on. The body is a fixed string with no permission in it, and the reason phrase is actively unreliable (`403 OK`, `400 OK`). Depending on the header would add a second condition that can only ever agree with the status.

**Why `PERM_NODOWNLOAD` is a constant but not a name.** `PERMISSION_NAMES` feeds `has_permission(name)`, which reads as "this camera grants X". Bit 12 means *deny download*, so `has_permission("no_download")` returning `True` would be read by every call site as a capability the camera has. Exporting the constant lets a consumer test the bit deliberately; leaving it out of the name mapping stops it being answered accidentally.

**Naming the permission is best-effort by design.** The server never says which bit it wanted. Endpoints whose required permission is known from the research (`settings-*` -> `settings`, `ssSetSchedule` -> `schedule`) can name it; anything else raises the same typed error with no name rather than guessing.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, including the pre-existing `401` tests unchanged

## Auto Run Result

Status: done

**Summary of implemented change.** `_map_status` in `aiosecurityspy` now splits HTTP `403` from `401`: `401` keeps raising `SecuritySpyAuthError` unchanged, `403` now raises `SecuritySpyPermissionError`, since a live 6.21 server answers `403` for a permission gap on correct credentials, not a rejected login. `PERMISSION_NAMES` gained `PERM_SETTINGS` ("settings") and `PERM_PUSH_STREAMS` ("push_streams"); `PERM_NODOWNLOAD` (an inverted deny-bit) is exported but deliberately excluded from that grant-shaped mapping. During review, both agents independently surfaced that this repo's own SecuritySpy integration (`custom_components/securityspy/`) only caught `SecuritySpyAuthError` and would lose precise handling of a permission-denied setup failure -- fixed in the same pass by adding a dedicated `SecuritySpyPermissionError` branch with its own translation strings.

**Files changed:**
- [`aiosecurityspy/src/aiosecurityspy/const.py`](../../aiosecurityspy/src/aiosecurityspy/const.py) -- three new `PERM_*` constants, two new `PERMISSION_NAMES` entries.
- [`aiosecurityspy/src/aiosecurityspy/client.py`](../../aiosecurityspy/src/aiosecurityspy/client.py) -- `_map_status` 401/403 split; `permission`/`camera_number` threaded through the transport seam and named at the settings/arming call sites.
- [`aiosecurityspy/src/aiosecurityspy/models.py`](../../aiosecurityspy/src/aiosecurityspy/models.py) -- `has_permission` docstring documents the `PERM_NODOWNLOAD` exclusion.
- [`aiosecurityspy/src/aiosecurityspy/__init__.py`](../../aiosecurityspy/src/aiosecurityspy/__init__.py), [`aiosecurityspy/README.md`](../../aiosecurityspy/README.md), [`aiosecurityspy/CHANGELOG.md`](../../aiosecurityspy/CHANGELOG.md) -- exports, docs, and a BREAKING changelog entry.
- [`aiosecurityspy/tests/test_client.py`](../../aiosecurityspy/tests/test_client.py), [`aiosecurityspy/tests/test_models.py`](../../aiosecurityspy/tests/test_models.py), [`aiosecurityspy/tests/test_settings.py`](../../aiosecurityspy/tests/test_settings.py) -- full I/O-matrix coverage, the 401-vs-403 type-distinguishability tests, and the new permission-bit decode tests.
- [`custom_components/securityspy/__init__.py`](../../custom_components/securityspy/__init__.py), [`custom_components/securityspy/config_flow.py`](../../custom_components/securityspy/config_flow.py) -- review-pass fix: a dedicated `SecuritySpyPermissionError` -> `permission_denied` mapping, alongside the existing `invalid_auth` one.
- [`custom_components/securityspy/strings.json`](../../custom_components/securityspy/strings.json), [`custom_components/securityspy/translations/en.json`](../../custom_components/securityspy/translations/en.json) -- review-pass fix: the new `permission_denied` string, in both `config.error` and `exceptions`.
- [`tests/test_config_flow.py`](../../tests/test_config_flow.py), [`tests/test_init.py`](../../tests/test_init.py), [`tests/test_translations.py`](../../tests/test_translations.py) -- review-pass fix: coverage for the new `permission_denied` path.

**Review findings breakdown:** 1 patch applied (high severity -- the downstream consumer precision regression, addressed by both reviewers independently), 0 deferred, 9 rejected as spec-directed behavior or non-actionable meta-commentary. No intent gaps, no bad-spec loopbacks.

**Verification performed:** In `aiosecurityspy/`: `ruff check`, `ruff format --check`, `mypy --strict src tests`, `pytest -q` all pass (864 tests). At the repo root (the `custom_components` consumer this review pass touched): `ruff check`/`ruff format --check custom_components tests` pass; `mypy --strict custom_components` passes cleanly (running it jointly with `tests/` hits a pre-existing, unrelated mypy module-path collision, not introduced by this change); `pytest tests -q` passes (54 tests, including the three new `permission_denied` rows).

**Follow-up review recommended: true.** The review pass added new cross-package behavior (a config-flow error path and two new user-facing translation strings) that was outside the spec's original Code Map, in direct response to a real gap two independent reviewers found. That is more than a localized low-consequence fix -- it changes what a user sees during setup -- so an independent follow-up review of this addition is warranted before the story is considered fully settled.

**Residual risks:** The `403 -> SecuritySpyPermissionError` semantics were verified against the live 6.21 server only for the settings and arming endpoints (research §4.1, §5.2, §7.1); every other endpoint's `403` behavior is extrapolated from the same status-code contract, per the spec's explicit design ("the status code alone decides"), but has not been individually verified live. If a future SecuritySpy version or firmware variant uses `403` differently on an unverified endpoint, this library's classification would need revisiting -- out of scope for this story, and not contradicted by any evidence gathered so far.
