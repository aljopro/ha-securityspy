---
title: 'Story 2.1 — Add a SecuritySpy server through the UI'
type: 'feature'
created: '2026-08-16'
status: 'done'
baseline_revision: '69c6702295c1956e5bc0a2bf7db2367920cd2b7e'
final_revision: '42734a5'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** The `aiosecurityspy` library exists but no Home Assistant integration does, so a user has no way to add a SecuritySpy server at all. This story bootstraps `custom_components/securityspy/` and its UI config flow — the entry point every later Epic-2 story extends.

**Approach:** Create a minimal but correct custom integration: a `config_flow.py` user step that validates host/port/username/password against the live server before creating an entry, keys the entry on the server UUID, and shows a distinct translated error per failure class; plus an `__init__.py` that sets the entry up with the single AD-6 exception-mapping seam and typed `runtime_data`. No coordinator, no platforms, no entities yet — those are stories 2.3+.

## Boundaries & Constraints

**Always:**
- Config entry `unique_id` is `ServerInfo.uuid` and nothing else (AD-5). Never hostname, IP, or user-editable name.
- Validation happens before the entry is created (`test-before-configure`) and again at setup (`test-before-setup`).
- The integration holds zero SecuritySpy protocol knowledge (AD-2): no endpoint URLs, no payload keys, no version parsing. Anything it needs from the wire comes off a library model.
- Library errors are mapped exactly once, at the adapter layer (AD-6): `SecuritySpyConnectError` → `cannot_connect`/`ConfigEntryNotReady`, `SecuritySpyAuthError` → `invalid_auth`/`ConfigEntryAuthFailed`, `SecuritySpyUnsupportedVersionError` → `unsupported_version`/`ConfigEntryError`.
- Every user-visible error and abort string is a translation key present in both `strings.json` and `translations/en.json`.
- Errors redisplay the form with the submitted values preserved; the flow never aborts on a recoverable error.
- Use `entry.runtime_data` with a typed `SecuritySpyConfigEntry` alias — never `hass.data[DOMAIN]` (AD-12).
- Credentials never reach a log line, an exception message, or a form-description string (AD-13).
- The HA client session is injected into the library; the integration never constructs an `aiohttp.ClientSession`.

**Block If:**
- The server UUID turns out to be genuinely optional on real SecuritySpy servers (this spec fails closed on an empty UUID; making it succeed would require inventing a fallback identity, which AD-5 forbids).

**Never:**
- No HTTPS scheme selector or certificate-verification toggle (story 2.2), no devices or entities (2.3+), no coordinator, no reauth step, no reconfigure step, no options flow. Do not stub them.
- No YAML configuration path, no discovery step.
- Do not vendor the library into the integration; pin it in `manifest.json`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Happy path | Reachable server, valid credentials, version ≥ minimum | Entry created; `unique_id` = server UUID; title = server name; data holds host, port, username, password | No error expected |
| Unreachable host | Host that refuses/times out | Form redisplayed with entered values | `base` error `cannot_connect` |
| Bad credentials | Server rejects auth (401/403) | Form redisplayed with entered values | `base` error `invalid_auth` |
| Too-old server | Server below the library minimum, or an unlocatable payload shape | Form redisplayed with entered values | `base` error `unsupported_version` |
| Malformed host/credential | Host with a scheme, port, path, or an unencodable credential | Form redisplayed before any network call | `base` error `invalid_host` |
| No server UUID | Server validates but reports an empty UUID | Form redisplayed; no entry created | `base` error `no_server_uuid` |
| Duplicate server | Same server already configured, added under a different address | Flow aborts; no second entry | Abort reason `already_configured` |
| Setup after HA restart, server down | Existing entry, server unreachable | Entry retried later by HA | `ConfigEntryNotReady` |
| Setup, credentials revoked | Existing entry, auth rejected | Entry marked as needing attention | `ConfigEntryAuthFailed` |
| Setup, server downgraded | Existing entry, version below minimum | Entry marked failed, not retried | `ConfigEntryError` |
| Unload | Loaded entry | Unloads cleanly; state `NOT_LOADED` | No error expected |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/models.py` -- `ServerInfo` (frozen, `from_api`) — decodes `++systemInfo`; currently exposes `uuid`, `version`, `version_info`, `camera_count`, `cameras` but no display name.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `SecuritySpyClient(session, host, port, *, username, password, use_https, verify_ssl, timeout)`; `async_get_server_info()` is the only call this story makes. Constructor raises `ValueError`/`TypeError` on unusable host/port/credentials.
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- the typed hierarchy the adapter maps.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- `DEFAULT_PORT` (8000).
- `aiosecurityspy/tests/fixtures/system_info.json` -- the recorded payload; its `server` block carries `bonjour-name`.
- `docs/ha-integration-reference.md` -- §1 manifest shape, §2 runtime data, §5 config flow, §8 testing conventions.
- `custom_components/securityspy/` -- does not exist; created by this story.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add a `name: str` field to `ServerInfo`, decoded in `from_api()` from the server block's `bonjour-name` with a trailing `.local` stripped, falling back to `"SecuritySpy"` when absent or blank -- the integration needs a display title for the entry and AD-2 forbids it knowing the wire key.
- [x] `aiosecurityspy/tests/test_models.py` -- cover name decoding: `.local` stripped, bare name kept, absent/blank falls back -- the fallback is what a title-less server depends on.
- [x] `aiosecurityspy/pyproject.toml`, `aiosecurityspy/CHANGELOG.md` -- bump to `0.2.0` and record the added field -- the integration pins an exact version and the public model changed.
- [x] `custom_components/securityspy/manifest.json` -- domain `securityspy`, `config_flow: true`, `integration_type: hub`, `iot_class: local_push`, `quality_scale: bronze`, `version`, `requirements: ["aiosecurityspy==0.2.0"]` -- HACS and hassfest both read this.
- [x] `custom_components/securityspy/const.py` -- `DOMAIN`, and the default port re-exported from the library -- one place for shared constants.
- [x] `custom_components/securityspy/config_flow.py` -- the `user` step per the I/O matrix: build a client, call `async_get_server_info()`, set unique ID from the UUID, abort if configured, create the entry titled with the server name -- this is the story.
- [x] `custom_components/securityspy/__init__.py` -- `SecuritySpyConfigEntry` type alias and `SecuritySpyRuntimeData` dataclass, `async_setup_entry` performing test-before-setup with the AD-6 mapping, `async_unload_entry` -- an entry that cannot be set up is not "added".
- [x] `custom_components/securityspy/strings.json`, `custom_components/securityspy/translations/en.json` -- field labels, per-error messages naming the fix, and the `already_configured` abort -- every message must be translated and actionable.
- [x] `hacs.json`, `pyproject.toml`, `.gitignore` -- HACS metadata at the repo root plus the integration's test environment (`pytest-homeassistant-custom-component`, `pytest-cov`, ruff/mypy config, the library as a local source) -- nothing can be verified without a runnable environment.
- [x] `tests/conftest.py`, `tests/test_config_flow.py`, `tests/test_init.py` -- fixtures (`enable_custom_integrations`, a mocked `SecuritySpyClient`) and one test per I/O-matrix row, driving flows through `hass.config_entries.flow` -- the Bronze rule demands 100% on `config_flow.py` including every abort and error path.

**Acceptance Criteria:**
- Given a fresh Home Assistant with the integration installed, when the user starts the SecuritySpy config flow, then a form requests host, port, username and password, and no YAML is involved at any point.
- Given a successfully validated server, when the entry is created, then its `unique_id` equals the server UUID, its title is the server's name, and its data contains exactly the four submitted fields.
- Given the same server reached by a second address, when it is added again, then the flow aborts with `already_configured` and the entry count stays at one.
- Given `config_flow.py`, when coverage is measured, then it is 100% with every branch exercised.
- Given the library test suite, when it runs, then it still imports no Home Assistant module and passes.

## Spec Change Log

## Review Triage Log

### 2026-08-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 9: (high 0, medium 5, low 4)
- defer: 3: (high 0, medium 3, low 0)
- reject: 5: (high 0, medium 2, low 3)
- addressed_findings:
  - `[medium]` `[patch]` The `TypeError`/`ValueError` catch wrapped the whole validation call, so a decoding or transport error inside `async_get_server_info()` would have been reported as `invalid_host` — the user retypes a valid host forever. Split client construction (`_build_client`) from the request; only construction is guarded.
  - `[medium]` `[patch]` Neither the flow nor setup had a fallback for a `SecuritySpyError` outside AD-6's three classes, so one would escape as a traceback and an aborted flow. Added an `unknown` error key (flow) and a `ConfigEntryNotReady` mapping (setup), with `_error_key()` matching by `isinstance` so a future library subclass inherits its parent's message.
  - `[medium]` `[patch]` `async_setup_entry` did not guard client construction, so unusable stored entry data raised a bare `ValueError` mid-setup. Now mapped to `ConfigEntryError` with an `invalid_stored_data` key.
  - `[medium]` `[patch]` The redisplayed form re-sent the plaintext password to the browser as a suggested value, and a test asserted it. `_preserved_values()` now excludes the password (AD-13); host, port and username are still preserved.
  - `[medium]` `[patch]` `strings.json` / `translations/en.json` parity was only a manual check, so a divergence would ship a raw key to the user with a green suite. Added `tests/test_translations.py` asserting equality plus per-key presence for every error, exception and form field.
  - `[low]` `[patch]` `_decode_server_name()` stripped whitespace before removing `.local` and never re-trimmed, so `"Basement NVR .local"` yielded a trailing space in the entry title. Re-trims after suffix removal; added cases for that, `"local.local"`, `"nvr.local.local"` and `"  .local  "`.
  - `[low]` `[patch]` The `0.2.0` changelog recorded `ServerInfo.name` as purely additive, but the field was inserted second and shifts three positional fields. Added a `### Changed` breaking-change note.
  - `[low]` `[patch]` `test_revoked_credentials_start_a_reauth_flow` asserted no such thing. Renamed to describe the actual contract and extended to assert no flow starts, documenting why that is correct until story 2.8.
  - `[low]` `[patch]` `const.LOGGER` was defined but imported by nothing. Removed.

Rejected: both reviewers reported `except TypeError, ValueError:` as a fatal `SyntaxError` — an artifact of parsing with Python 3.11. It is valid PEP 758 on the project's declared 3.14 floor (verified: parses on 3.14.4, and `ruff format` produces this exact form). Both also predicted that `ConfigEntryAuthFailed` without an `async_step_reauth` raises `UnknownStep` and strands the user; Home Assistant calls `async_start_reauth_if_available` (`config_entries.py:831`), which no-ops when the handler has no reauth step — confirmed empirically (no flow, no error log, entry in `SETUP_ERROR` with a translated message). Also rejected: `quality_scale`/`iot_class` metadata being forward-looking, `SecuritySpyRuntimeData` not being frozen, and a speculative `KeyError` on missing entry data at schema VERSION 1.

### 2026-08-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 2, low 2)
- defer: 1: (high 0, medium 1, low 0)
- reject: 14: (high 0, medium 5, low 9)
- addressed_findings:
  - `[medium]` `[patch]` `_async_probe()` caught only `SecuritySpyError`, so anything the library failed to wrap — an unwrapped transport error, a decoding bug — escaped and aborted the flow with a traceback, violating the contract that a recoverable failure always redisplays the form. Added a logged catch-all returning the existing `unknown` key, plus `tests/test_config_flow.py::test_unexpected_error_keeps_the_flow_alive` to hold the branch.
  - `[medium]` `[patch]` `tests/test_translations.py` re-listed the flow's error keys as parametrize literals, so adding a mapping to `_ERROR_KEYS` without a message left the suite green — the exact drift the file's docstring claims to close. The expected key set is now derived from `config_flow._ERROR_KEYS` plus the three literal returns, and `test_no_unused_error_messages` asserts the `config.error` block matches it exactly in both directions.
  - `[low]` `[patch]` `test_setup_maps_library_errors` asserted only `entry.state`, so a mapping that reached the right state carrying the wrong message passed. Now asserts `error_reason_translation_key` per case.
  - `[low]` `[patch]` `_decode_server_name()`'s comment described stripping "a trailing dot" while `rstrip(".")` strips all of them. Corrected the comment to state the actual (and intended) behaviour and pinned it with `"nvr.local..."` and `"Attic..."` cases.

Rejected: both reviewers again led with `except TypeError, ValueError:` as a fatal `SyntaxError` — the same Python 3.11-parser artifact rejected last pass, re-confirmed here (`uv run python` on 3.14.4 parses it; PEP 758 landed in 3.14, and the full suite runs). Also rejected: no HTTPS/TLS field (story 2.2 by the intent contract's **Never**), no reauth step (2.8), no reconfigure/`updates=` on abort (2.9, and already in the ledger), duplicate detection running after validation (inherent to UUID identity under AD-5 — the UUID is unknowable without a call), `_async_probe`'s `ServerInfo | str` return being type-sniffed (style), `strings.json`/`en.json` duplication (Home Assistant's own convention, and drift is tested), the shared two-site client mock in `conftest.py`, `COM812` ignored without `COM` selected (ruff's documented formatter-compat pair), the forward-looking `iot_class`/`quality_scale` manifest values (rejected last pass), a speculative `KeyError` on missing entry data at schema VERSION 1 (rejected last pass), `ServerInfo.name`'s documented positional break, the `## [0.2.0]` heading absorbing previously-unreleased entries (that is what cutting a release does), and the absence of a credential-leak test for `ServerInfo.__repr__` (the model holds no credential to leak).

## Design Notes

**Why `bonjour-name` for the title.** The recorded `++systemInfo` payload has no server-name field; `bonjour-name` (`nvr.local`) is the only human-chosen identifier the server publishes. Stripping `.local` yields the Mac's sharing name, which is what a user recognises. The stripping lives in the library because AD-2 puts every wire-format fact there. The `"SecuritySpy"` fallback keeps the entry titled rather than blank; the title is cosmetic and user-editable, so a wrong guess costs nothing — unlike the UUID, which is permanent.

**Why an empty UUID fails.** `ServerInfo.uuid` currently defaults to `""` when the field is absent (a known open question in the deferred-work ledger). Since the UUID becomes the config entry `unique_id` and every future device identifier, two UUID-less servers would collapse into one entry. This story fails closed with its own `no_server_uuid` error rather than inventing a fallback identity; that leaves the library question open without letting a corrupt identity become permanent.

**Scope of `__init__.py`.** Setup validates and stores a client, nothing more — `PLATFORMS` is empty and there is no coordinator, because neither exists yet. Story 2.3 adds both. The exception-mapping seam is written now because AD-6 requires exactly one, and retrofitting it means touching every call site.

## Verification

**Commands:**
- `uv run --directory aiosecurityspy pytest` -- expected: all library tests pass, including the new `ServerInfo.name` cases.
- `uv run --directory aiosecurityspy mypy --strict src/aiosecurityspy` -- expected: clean.
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` -- expected: all tests pass and coverage is 100%, `config_flow.py` included. (coverage.py's `--cov` takes an importable module or a directory, never a `.py` path — a file path silently collects nothing.)
- `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests` -- expected: clean.
- `uv run mypy custom_components/securityspy` -- expected: clean.

**Manual checks (if no CLI):**
- `custom_components/securityspy/strings.json` and `translations/en.json` carry the same key set, covering `cannot_connect`, `invalid_auth`, `unsupported_version`, `invalid_host`, `no_server_uuid`, and `already_configured`.

## Auto Run Result

Status: done

**Change:** Follow-up review pass over story 2.1 (the SecuritySpy custom integration bootstrap and its UI config flow). No intent gaps and no spec defects were found; the implementation matched the intent contract and the I/O matrix row for row. Four review findings were patched, one was deferred.

**Files changed in this pass:**
- `custom_components/securityspy/config_flow.py` — added a module logger and a logged catch-all in `_async_probe()` so an unwrapped exception returns the `unknown` error key instead of aborting the flow.
- `tests/test_config_flow.py` — new `test_unexpected_error_keeps_the_flow_alive` covering that branch.
- `tests/test_translations.py` — expected error-key set now derived from `config_flow._ERROR_KEYS`; added `test_no_unused_error_messages` for the reverse direction.
- `tests/test_init.py` — `test_setup_maps_library_errors` now asserts `error_reason_translation_key` alongside the entry state.
- `aiosecurityspy/src/aiosecurityspy/models.py` — corrected the `_decode_server_name()` trailing-dot comment to match the code.
- `aiosecurityspy/tests/test_models.py` — added multi-trailing-dot decoding cases.
- `_bmad-output/implementation-artifacts/deferred-work.md` — one new entry (missing repo-root README while `hacs.json` sets `render_readme: true`).

**Findings breakdown:** 4 patched (2 medium, 2 low), 1 deferred, 14 rejected. Both reviewers again led with the `except TypeError, ValueError:` "SyntaxError", which is a Python 3.11-parser artifact — PEP 758 makes it valid on the project's 3.14 floor, re-confirmed empirically this pass. Most other rejections were work the intent contract explicitly assigns to stories 2.2, 2.8 and 2.9.

**Verification (all green after the patches):**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-fail-under=100` — 34 passed, 100% statement and branch coverage on `config_flow.py`, `__init__.py` and `const.py`.
- `uv run ruff check custom_components tests` — clean; `ruff format --check` — 8 files already formatted.
- `uv run mypy custom_components/securityspy` — clean.
- `uv run --directory aiosecurityspy pytest` — 599 passed; `mypy --strict src/aiosecurityspy` — clean.

**Residual risks:** All carried in the deferred-work ledger, none blocking this story: `aiosecurityspy` 0.2.0 is not yet on PyPI while `manifest.json` pins it, the integration has no CI workflows so these gates only run by hand, re-adding a moved server still discards the new address until story 2.9, and there is no repo-root README for HACS to render.

**Follow-up review recommended:** false — the patches were four localized, low-consequence fixes (one small defensive branch plus three test strengthenings) on a change that was already sound.
