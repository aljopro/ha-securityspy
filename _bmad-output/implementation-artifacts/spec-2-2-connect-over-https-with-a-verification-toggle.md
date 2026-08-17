---
title: 'Story 2.2 — Connect over HTTPS with a verification toggle'
type: 'feature'
created: '2026-08-16'
status: 'done'
baseline_revision: '9057141738c680bbeec76154ea0e22fa78abef82'
final_revision: '9553b9b'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** The config flow built in story 2.1 speaks plain HTTP only. The reference server runs HTTPS on 8001 with a certificate issued for a DDNS hostname (`chappell.viewcam.me`), so connecting by LAN IP fails a hostname check the user cannot fix — and today that failure arrives as the generic `cannot_connect` message, which sends them hunting for a network problem that does not exist.

**Approach:** Add two fields to the user step — use HTTPS, and verify the certificate (on by default) — persist both with the entry, and pass them to every client the integration builds. Give the certificate failure its own typed library error so the flow can name the mismatch instead of blaming the network.

## Boundaries & Constraints

**Always:**
- The certificate distinction is a *library* fact (AD-2): the integration must never inspect an `aiohttp` or `ssl` exception. `aiosecurityspy` raises a new `SecuritySpyCertificateError`, a **subclass of `SecuritySpyConnectError`**, so every existing consumer that catches connect errors keeps working unchanged.
- Because it is a subclass, every `except`/`isinstance` chain that handles both must test the certificate error **first**. This applies to `config_flow._ERROR_KEYS` and to `async_setup_entry`.
- Both flags are stored in `entry.data` under Home Assistant's own `CONF_SSL` and `CONF_VERIFY_SSL` keys, and both are read back at setup so the choice applies to the client, and therefore to the event stream that Epic 3 spawns from it.
- The session is selected with `async_get_clientsession(hass, verify_ssl=...)` **and** the flag is passed to the client. Both are required: aiohttp resolves a request-level `ssl=True` by falling back to the connector's context (`connector.py:1268-1271`), which is the one Home Assistant preconfigured off-loop; `ssl=False` short-circuits to aiohttp's module-level unverified context.
- Verification defaults to on. Its `data_description` states the consequence of turning it off in plain language.
- Everything story 2.1 established holds: entry `unique_id` is the server UUID, a recoverable error redisplays the form with the submitted values (never the password), all strings are translation keys present in both `strings.json` and `translations/en.json`, and `config_flow.py` keeps 100% coverage.

**Block If:**
- Nothing. Every decision here is settled by the epic context, the research reference (§ Transport) and the code.

**Never:**
- No reauth, reconfigure or options flow (2.8 / 2.9), no coordinator, devices or entities (2.3+), no config-entry migration or `VERSION` bump — nothing is released, so no entry written by the old schema can exist (the same reasoning that rejected a speculative `KeyError` guard in 2.1).
- No `ssl.SSLContext` construction, no certificate pinning, no custom CA bundle, no per-request session creation.
- No change to `stream.py`'s reconnect policy; it already inherits the scheme and TLS flag through the shared `ConnectionSettings`.
- Do not add a real-TLS test server: that is an open fixture-infrastructure entry in the deferred-work ledger and needs a dependency (`trustme`/`cryptography`) this repo does not have.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| HTTP unchanged | Toggles left at defaults (HTTPS off, verify on) | Client built with `use_https=False`; behaviour identical to story 2.1 | No error expected |
| HTTPS happy path | HTTPS on, verify on, hostname matches the certificate | Entry created; data carries `ssl: true`, `verify_ssl: true` | No error expected |
| Certificate mismatch | HTTPS on, verify on, connecting by LAN IP to a DDNS certificate | Form redisplayed, toggles preserved | `base` error `invalid_certificate`, naming the certificate specifically |
| Verification disabled | Same server, verify off | Client built with `verify_ssl=False`; entry created | No error expected |
| Plain HTTP against a TLS server | HTTPS off against a server that 301s to its HTTPS port | Form redisplayed | `base` error `cannot_connect` (library already names the redirect) |
| Setup, certificate now invalid | Stored entry with verify on, certificate expired or replaced | Entry retried later by HA with the certificate-specific message | `ConfigEntryNotReady`, translation key `invalid_certificate` |
| Library raises a bare `ssl.SSLError` | Transport fails TLS outside aiohttp's connector wrapper | Same as a certificate mismatch | `SecuritySpyCertificateError` |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- the typed hierarchy; `SecuritySpyConnectError(host, port, reason)` is the parent the new error extends.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `_request()` (~line 694) is the single transport seam; its `except` chain currently ends `TimeoutError` → `aiohttp.ClientError` → `OSError`, and `aiohttp.ClientSSLError` is a subclass of both of the latter, so the new clause must precede them.
- `aiosecurityspy/src/aiosecurityspy/connection.py` -- `ConnectionSettings.create(..., use_https, verify_ssl)` already exists and is shared with the stream; no change needed.
- `aiosecurityspy/tests/test_client.py` -- `FakeCertificateError` / `certificate_error()` (lines 199-217) and `failure_rows()` already model this failure; `test_certificate_error_maps_to_connect_error` (line 350) is the test to tighten.
- `custom_components/securityspy/config_flow.py` -- `STEP_USER_DATA_SCHEMA`, `_ERROR_KEYS`, `_build_client()`, `_preserved_values()`.
- `custom_components/securityspy/__init__.py` -- `async_setup_entry()`'s client construction and AD-6 mapping chain.
- `custom_components/securityspy/strings.json`, `translations/en.json` -- must stay key-for-key identical; `tests/test_translations.py` derives its expected error set from `config_flow._ERROR_KEYS`.
- `tests/conftest.py` -- `MOCK_USER_INPUT` is the shared four-field payload every flow test posts; it becomes six fields.
- `docs/ha-integration-reference.md` §5 -- the `async_get_clientsession(hass, verify_ssl=...)` pattern this story adopts.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §Transport -- HTTP 8000 redirects to HTTPS 8001; certificates are issued for the DDNS hostname.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- add `SecuritySpyCertificateError(SecuritySpyConnectError)` whose message names the certificate and states that verification can be disabled; export it in `__all__` -- a caller cannot act on "transport failure (ClientConnectorCertificateError)".
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- re-export the new error from the package (import list and `__all__`) -- the integration imports library names from the package root only.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- in `_request()`, catch `aiohttp.ClientSSLError` and `ssl.SSLError` **before** the `TimeoutError`/`ClientError`/`OSError` clauses and raise the new error; import `ssl` -- ordering is the whole correctness of this change.
- [x] `aiosecurityspy/tests/test_client.py` -- tighten `test_certificate_error_maps_to_connect_error` to assert the new type, that it is still a `SecuritySpyConnectError`, that the message names the certificate and not the credential, and that `__cause__` is preserved; add a bare `ssl.SSLError` row to the failure matrix -- the subclass relationship is what keeps every existing consumer working.
- [x] `aiosecurityspy/pyproject.toml`, `aiosecurityspy/CHANGELOG.md` -- bump to `0.3.0` and record the added exception under `### Added` -- the integration pins an exact version and the public surface grew.
- [x] `custom_components/securityspy/manifest.json` -- pin `aiosecurityspy==0.3.0` -- the flow depends on the new error type existing.
- [x] `custom_components/securityspy/config_flow.py` -- add `CONF_SSL` (`BooleanSelector`, default `False`) and `CONF_VERIFY_SSL` (`BooleanSelector`, default `True`) to the schema; pass both to the client in `_build_client()` and select the session with `async_get_clientsession(hass, verify_ssl=...)`; put `(SecuritySpyCertificateError, "invalid_certificate")` **first** in `_ERROR_KEYS` and replace the comment that says the order carries no meaning -- this is the story.
- [x] `custom_components/securityspy/__init__.py` -- read both flags from `entry.data`, apply them to the session and the client, and add a `SecuritySpyCertificateError` clause **before** the `SecuritySpyConnectError` clause raising `ConfigEntryNotReady` with key `invalid_certificate` -- otherwise the specific message is unreachable at setup.
- [x] `custom_components/securityspy/strings.json`, `custom_components/securityspy/translations/en.json` -- add labels and `data_description`s for both toggles (the verify description states the consequence: nothing proves the server is the one you think it is, so use it only on a network you trust), the `invalid_certificate` error naming the LAN-IP/DDNS mismatch and pointing at the toggle, the matching `exceptions.invalid_certificate` message, and a note on the port description that HTTPS is usually 8001 -- both files must stay identical.
- [x] `tests/conftest.py` -- extend `MOCK_USER_INPUT` with `ssl: False`, `verify_ssl: True` and add a helper (or fixture) for the HTTPS variant -- every flow test posts through this payload.
- [x] `tests/test_config_flow.py` -- one test per new I/O row: HTTPS entry data, certificate mismatch → `invalid_certificate` with the toggles preserved, retry with verification off succeeding, and assertions that `SecuritySpyClient` was called with the expected `use_https`/`verify_ssl` and that `async_get_clientsession` was asked for the matching session -- 100% coverage on `config_flow.py` including the new branch.
- [x] `tests/test_init.py` -- setup builds the client with the stored flags, and a certificate error yields `SETUP_RETRY` with `error_reason_translation_key == "invalid_certificate"` -- the mapping order is easy to regress silently.

**Acceptance Criteria:**
- Given the user step, when it is displayed, then it offers an HTTPS toggle and a certificate-verification toggle that defaults to on, and the verification field carries a description of what disabling it costs.
- Given a stored config entry, when the integration sets it up, then the client and the Home Assistant session it uses both reflect the persisted HTTPS and verification choices, so the event stream Epic 3 spawns from that client inherits them without re-reading the entry.
- Given a `SecuritySpyCertificateError`, when any existing consumer catches `SecuritySpyConnectError`, then it still catches it.
- Given the library test suite, when it runs, then it still imports no Home Assistant module and passes.

## Spec Change Log

## Review Triage Log

### 2026-08-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 1, medium 4, low 5)
- defer: 1: (high 0, medium 0, low 1)
- reject: 6: (high 0, medium 2, low 4)
- addressed_findings:
  - `[high]` `[patch]` The mapping caught `aiohttp.ClientSSLError`/`ssl.SSLError` wholesale, so *every* TLS failure claimed the certificate was rejected and advised turning verification off. Verified against a live aiohttp server that speaking TLS to a plain-HTTP port raises `ClientConnectorSSLError` (`WRONG_VERSION_NUMBER`) with verification on **and** off — which is the likeliest first mistake, since the HTTPS toggle sits beside a port field defaulting to 8000. The catch is now narrowed to `ClientConnectorCertificateError`/`ssl.SSLCertVerificationError`; every other TLS failure becomes a `SecuritySpyConnectError` naming the reason and the wrong-port possibility. This narrows the I/O matrix's bare-`ssl.SSLError` row to certificate-verification failures — nothing leaks untyped, and the row's purpose (a TLS failure is always a typed connect error) still holds.
  - `[medium]` `[patch]` A key missing from stored entry data raised a bare `KeyError` past the `(TypeError, ValueError)` guard and out of `async_setup_entry` as a raw traceback. `KeyError` added to the guard, so it becomes the translated permanent `invalid_stored_data` failure the path already promises; covered by a new test. (The `.get()`-with-defaults migration the reviewers wanted is rejected — see below.)
  - `[medium]` `[patch]` The certificate message threw away the one discriminating detail. Added `_tls_reason()`, which unwraps aiohttp's `certificate_error`/`os_error` to the OpenSSL reason (`CERTIFICATE_VERIFY_FAILED`, `WRONG_VERSION_NUMBER`) — a fixed OpenSSL constant, so nothing user-supplied — and falls back to the type name.
  - `[medium]` `[patch]` Disabling verification was stored silently and never mentioned again, while the HTTP Basic credential rides on every unverified request. `async_setup_entry` now logs a warning naming host and port (no credential) whenever the entry loads with verification off.
  - `[medium]` `[patch]` The setup-time message told the user to "change the address", which has no UI path before story 2.9 — re-adding aborts as already-configured. Reworded to the remedy that exists today (remove and re-add), and the flow message now leads with expiry as well as the hostname mismatch.
  - `[low]` `[patch]` `verify_ssl` is collected and stored even with HTTPS off. Its description now says it applies only when HTTPS is on, and names the credential exposure. (Forcing the value is rejected — see below.)
  - `[low]` `[patch]` `cannot_connect` said nothing about the wrong-port case that now lands there. It now points at the HTTPS port explicitly.
  - `[low]` `[patch]` `test_setup_applies_the_stored_tls_choices` was parametrized only over HTTPS payloads, so a hard-coded `use_https=True` in setup would have kept the suite green at 100%. Parametrized over the plain-HTTP payload too.
  - `[low]` `[patch]` `test_every_form_field_is_labelled_and_described` restated the field set as a literal, so a new unlabelled form field would pass. The set is now read off `STEP_USER_DATA_SCHEMA`.
  - `[low]` `[patch]` The certificate test fixture was a bare `ClientSSLError` subclass that could not distinguish the two branches. Rebuilt on the genuine `ClientConnectorCertificateError`/`ClientConnectorSSLError` types carrying their inner `ssl` errors, plus a **real-transport** test (`tests/test_client_transport.py`) proving the wrong-port handshake is not reported as a certificate problem, with verification on and off. The changelog wording was corrected to match the narrowed behaviour.

Rejected: `entry.data.get(CONF_SSL, False)` / `.get(CONF_VERIFY_SSL, True)` defaults for entries written by story 2.1 — the intent contract's **Never** forbids a config-entry migration, nothing is released, and the `KeyError` guard above already turns the only reachable case into a translated error rather than a traceback. Forcing `verify_ssl` to `True` when HTTPS is off — it silently rewrites a stored user choice and would surprise story 2.9 when HTTPS is later enabled; the description now states the coupling instead. `ConfigEntryNotReady` retrying forever on a permanently mismatched certificate — that is the spec's deliberate choice (expiry self-heals), and the repair path is story 2.9. "100% coverage is being read as proof of correctness" — meta-commentary, answered by the concrete tests added above. Extracting the `except` chain behind a `_transport_error()` helper to drop `# noqa: PLR0912` — style, and the suppression is knowingly documented. The certificate message advising "verification can be disabled" when it already is — unreachable after the narrowing above, since with `ssl=False` a verification failure cannot occur.

### 2026-08-16 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 1, low 2)
- defer: 1: (high 0, medium 0, low 1)
- reject: 11: (high 0, medium 3, low 8)
- addressed_findings:
  - `[medium]` `[patch]` The "certificate verification is disabled" warning in `async_setup_entry` was gated on `not verify_ssl` alone. Nothing in the form couples the two toggles, so a plain-HTTP entry can carry verification off — and that entry logged, on every load, that "its identity is not being checked on any connection" for a connection that never presents a certificate. The gate is now `use_https and not verify_ssl`, matching the field's own description ("only used when Connect over HTTPS is on"); a new test (`test_setup_does_not_warn_about_verification_on_a_plain_http_entry`) pins it. A warning that fires on a safe configuration is what teaches the reader to skip it on the unsafe one, which is the entire value of the line added in the previous pass.
  - `[low]` `[patch]` `test_tls_failure_without_a_reason_falls_back_to_the_type_name` asserted `"SSLError" in str(err.value)`, a substring also satisfied by `"SSLCertVerificationError"` — so the test would have stayed green if the no-reason fallback were ever misrouted to the certificate branch, which is the one thing it exists to prevent. Tightened to `"(SSLError)"` plus an explicit `not isinstance(..., SecuritySpyCertificateError)`.
  - `[low]` `[patch]` `FakeCertificateError` and `FakeHandshakeError` build genuine aiohttp connector-error types via `Exception.__init__`, leaving aiohttp's private `_conn_key` unset; `str()` on either raises `AttributeError` (verified). Production only reads `_tls_reason(err)`, so the suite passes — but the moment any test using them *fails*, pytest renders the chained `__cause__` and the report itself blows up, masking the real failure. Both now override `__str__` to render from the message.

Rejected: **"`except TypeError, ValueError:` at `config_flow.py:229` is a Python 2 SyntaxError"** — false, and the most consequential rejection of the pass. PEP 758 makes unparenthesized `except` groups valid in Python 3.14, which `requires-python = ">=3.14"` mandates; the reviewer compiled with the system Python 3.11. Verified both ways: `python3.11 -m py_compile` fails, `uv run python -m py_compile` succeeds, and the full suite runs 608 green with `__pycache__` cleared. **Entry migration / `entry.data.get()` defaults for pre-2.2 entries** and **an options or reconfigure flow so the toggles can be changed** — both re-raised from the previous pass and both still forbidden by the intent contract's **Never** (no migration, no `VERSION` bump, no reconfigure/options flow; those are stories 2.8/2.9, and nothing is released, so no old-schema entry can exist). **`ConfigEntryNotReady` retrying forever on a permanently mismatched certificate** — the spec's I/O matrix decides this explicitly. **A non-bool stored flag should be type-checked** — speculative guard against a hand-edited entry, the same class the contract rejected in 2.1. **`ssl.SSLCertVerificationError` is also a `ValueError`, so a future `except ValueError` could swallow it** — verified there is no bare `ValueError` clause anywhere in `_request()`'s chain (`RuntimeError` → `UnicodeDecodeError, LookupError` → the two TLS clauses → `TimeoutError` → `ClientError` → `OSError`), and both integration-side `(KeyError, TypeError, ValueError)` guards wrap client *construction*, not a live call; a hazard that does not exist is not a finding. **The subclass-ordering rule is encoded in two places** — both are documented invariants and both are pinned by a test that fails if the order flips. **Config-flow tests would not catch a `use_https`/`verify_ssl` transposition** — `test_setup_applies_the_stored_tls_choices` covers it with its plain-HTTP row, which is why that row was added last pass. **CHANGELOG 0.3.0 carries maintainer rationale under `### Added`, shares 0.2.0's date, and leaves `[Unreleased]` empty** — cosmetic. **`ConnectionSettings.__repr__` prints `verify_ssl` even for an `http` scheme** — cosmetic; the value is inert for plain HTTP. **README does not document the new toggles** — real but out of scope; the spec scopes no documentation work, and the ledger already tracks the docs plane.

### 2026-08-16 — Review pass (verification repair)

- intent_gap: 0
- bad_spec: 0
- patch: 3: (high 0, medium 0, low 3)
- defer: 1: (high 0, medium 0, low 1)
- reject: 15: (high 0, medium 3, low 12)
- addressed_findings:
  - `[low]` `[patch]` The incoming verification failure: `mypy --strict` rejected `FakeCertificateError.__str__` at `aiosecurityspy/tests/test_client.py:230` with *"Incompatible return value type (got `ConnectionKey`, expected `str`)"* and *"If condition is always true"*. Cause: aiohttp's `ClientConnectorCertificateError.__init__` re-assigns `self.args = (connection_key, certificate_error)`, which narrows the declared element type of `args` for every subclass — so the previous pass's `self.args[0]` is a `ConnectionKey` to the type checker even though the fake's `Exception.__init__(self, message)` puts a `str` there at runtime. Both fakes now carry the message on their own `_message` attribute and render from it; the override still does its job (verified: `str()` on both returns the message rather than raising `AttributeError` on the unset `_conn_key`). `FakeHandshakeError` was changed the same way even though only the certificate fake tripped the checker — its docstring points at `FakeCertificateError.__str__` for the rationale, and `ClientConnectorSSLError` not re-assigning `args` today is not a reason for the two to drift.
  - `[low]` `[patch]` The comment justifying `ConfigEntryNotReady` in `custom_components/securityspy/__init__.py` claimed *"the usual cause ... is expiry"*, while the `config.error.invalid_certificate` string added by the same story tells the user the hostname mismatch is the one that happens *"most often"*. The retry policy is right (the Design Notes settle it, and both prior passes upheld it) but the stated reason for it was not: it holds because the recoverable cause self-heals, not because it is the common one. Reworded to say that, and to name story 2.9 as the repair path for the permanent cause. A comment that contradicts the shipped string is what gets the policy "corrected" by the next reader.
  - `[low]` `[patch]` `aiosecurityspy/CHANGELOG.md` grew a `## [0.3.0]` heading with no matching link definition, and `[Unreleased]` still compared from `v0.2.0`. On GitHub that renders the new heading as literal brackets and shows 0.3.0's contents a second time under Unreleased. Added the `[0.3.0]` compare link and moved `[Unreleased]` to `v0.3.0...HEAD`.
  - `[low]` `[patch]` `test_http_defaults_reach_the_client_unchanged` asserted only on `mock_client_class.call_args_list[0].kwargs` and never on the flow result — but the client is constructed on the *failure* path too, so a flow that started erroring and redisplaying the form would have left this test green while its claim ("the defaults reproduce story 2.1's behaviour exactly") went unverified. Added the `FlowResultType.CREATE_ENTRY` assertion its sibling `test_https_choices_reach_the_entry_the_client_and_the_session` already carries.

Deferred: the event stream inherits the TLS flags but none of the new diagnosis — `stream.py`'s `_run()` swallows every exception into a `DEBUG` reconnect loop, so a certificate that expires while Home Assistant is *running* produces a silent reconnect loop where the setup path would have named the certificate. Real, but Epic 3's problem: the intent contract's **Never** forbids touching `stream.py`'s reconnect policy in this story, and there is no consumer of the stream's failures yet. Filed to the ledger.

Rejected: the two structural findings this pass raised as HIGH — **no config-entry migration for entries written by story 2.1** and **no `isinstance` type check on the stored TLS flags** — are both re-raises, for the third time, of what the intent contract's **Never** forbids and what the Design Notes answer explicitly (nothing is released, so no old-schema entry exists; the hand-edited-`.storage` guard is the same speculative class rejected in 2.1). Also re-raised and again rejected: **an options/reconfigure flow** (stories 2.8/2.9), **`ConfigEntryNotReady` retrying forever on a permanent mismatch** (decided by the I/O matrix), **forcing `verify_ssl=True` when HTTPS is off**, and **the `# noqa: PLR0912` suppression**. New this pass and rejected: **`async_get_clientsession(hass, verify_ssl=False)` for a plain-HTTP entry allocates HA's unverified session needlessly** — the session is inert for `http://` requests and HA creates it on demand regardless; **the warning should be an `issue_registry` repair, and plain HTTP should warn about cleartext credentials** — both are new user-facing surface the spec does not scope, and the repairs plane belongs to 2.8/2.9; **`SecuritySpyCertificateError` should keep the raw OpenSSL reason on a dedicated attribute** — speculative, the *type* is the branch point by design and no consumer reads `.reason`; **the real-transport test pins `WRONG_VERSION_NUMBER`, which varies by TLS stack** — the assertion that carries the story's claim is `not isinstance(..., SecuritySpyCertificateError)` and it is stack-independent, and the project has a single supported toolchain (`requires-python = ">=3.14"`); **only fakes, never a real self-signed server, prove the certificate path** — a genuine depth limit, but standing up an in-process TLS server is new work the spec does not scope and the fakes are a documented, deliberate choice; **`README` and the five `Raises:` docstrings do not name the new subclass** — it *is* a `SecuritySpyConnectError`, so nothing documented is wrong, and the spec scopes no documentation work; **a bare `aiohttp.ClientSSLError` (neither connector subclass) has no test row** — it reaches the same clause and the same `_tls_reason` fallback that `ssl.SSLError` already covers; **`test_translations` still hardcodes the setup-failure key list**; **`_tls_reason`'s type-name fallback can surface `ClientConnectorSSLError` to a user** — pinned deliberately by a test the previous pass tightened; **the password is not preserved when the form redisplays** — story 2.1's stated behaviour, in the intent contract; **`manifest.json` pins a version not yet on PyPI** — known and tracked in the ledger (DW-2), and true of `0.2.0` before it.

### 2026-08-16 — Review pass (follow-up, no changes)

- intent_gap: 0
- bad_spec: 0
- patch: 0
- defer: 0
- reject: 14: (high 0, medium 4, low 10)
- addressed_findings:
  - none

Rejected: **"`except TypeError, ValueError:` (`config_flow.py:229`) and the two equivalents in `client.py` are Python 3 `SyntaxError`s, so the module cannot import and every green-gate claim for this story is fabricated"** — raised independently by *both* reviewers this pass as the blocking finding, and false for the third time. PEP 758 makes unparenthesized `except` groups valid in Python 3.14, which `requires-python = ">=3.14"` mandates; both reviewers compiled with an older system interpreter. Verified directly: `uv run python -VV` reports **3.14.4**, the same interpreter rejects `type X = ...` at `__init__.py:70` (a 3.12 feature) which nobody claims is broken, and all gates run clean on it — 608 library tests, 50 integration tests, `mypy --strict` clean on both trees, `ruff check` clean, and `config_flow.py` at **100% branch coverage**, which is unreachable for a module that does not import. Confirmed a second way: parenthesizing all three by hand and running `ruff format` reverted every one, because the formatter removes the redundant parentheses under this target version — the unparenthesized form is the project's ruff-enforced style, not a defect. This false positive has now cost three passes; it is recorded here at length so a fourth reviewer's identical claim can be dismissed on sight.
  Re-raised and again rejected, all previously adjudicated: **no config-entry migration / `VERSION` bump for story-2.1 entries** (fourth raise; intent contract **Never**, nothing is released, and the `KeyError` guard already turns the only reachable case into a translated error); **`ConfigEntryNotReady` retries forever on a permanent mismatch** (settled by the I/O matrix and Design Notes); **`_tls_reason`'s type-name fallback can surface `ClientConnectorSSLError` to a user** (pinned deliberately by a test); **only fakes, never a real self-signed TLS server, prove the certificate path** (a genuine depth limit, already weighed and rejected as unscoped new work; the real-transport test covers the wrong-port branch); **`manifest.json` pins `aiosecurityspy==0.3.0`, unpublished** (known, tracked as DW-2, and true of `0.2.0` before it); **the fakes bypass the real constructors**, **`README` does not document the new subclass**, **the warning should be an `issue_registry` repair**, **a non-bool stored flag should be type-checked**, **`_build_client`'s `KeyError` is uncaught for a future non-form caller** (2.8/2.9 do not exist), **a bare `aiohttp.ClientSSLError` has no test row**, **`MOCK_HTTPS_USER_INPUT` duplicates `https_input()`**, **`str(marker)` vs `.schema` in `test_translations`**, and **`EXPECTED_VALIDATION_CALLS` / `call_args_list` indexing is positional** — the last four cosmetic.

## Design Notes

**Why a subclass rather than a new sibling error.** `SecuritySpyConnectError` is documented as "unreachable host, timeout, TLS or bad body", and both the client and every consumer treat it as the retryable class. A sibling would silently fall through to `unknown` in `_error_key()` and to the `SecuritySpyError` catch-all in `async_setup_entry`. A subclass is additive: old code keeps its behaviour, new code opts into the detail by testing it first. The cost is that ordering now matters in two places, which is why both are called out as invariants rather than left to the reader.

**Why both the session flag and the client flag.** They do different jobs. `async_get_clientsession(hass, verify_ssl=False)` gets an aiohttp connector Home Assistant built for that purpose; passing `verify_ssl` into the library keeps the per-request `ssl=` kwarg consistent with it. With verification on, the library sends `ssl=True`, which aiohttp resolves *by deferring to the connector*, so the context Home Assistant already built off-loop is the one used — no SSL context is ever created in the event loop.

**Why `ConfigEntryNotReady` and not `ConfigEntryError` at setup.** A mismatched certificate will not fix itself, but an *expired* one usually does — the reference server's certificate auto-renews. `NotReady` recovers on its own when that happens; `ConfigEntryError` would strand the entry until a manual reload. The user still gets the certificate-specific message either way. Reconfiguring the toggle is story 2.9's job.

**Why no entry migration.** The library is not on PyPI and the integration has no HACS release, so the only entries in existence are developer test entries. Adding a `.get()` fallback would create an untested branch defending against a state that cannot occur — the same call made in story 2.1 for missing entry data.

## Verification

**Commands:**
- `uv run --directory aiosecurityspy pytest` -- expected: all library tests pass, including the tightened certificate cases.
- `uv run --directory aiosecurityspy mypy --strict src/aiosecurityspy` -- expected: clean.
- `uv run --directory aiosecurityspy ruff check src tests && uv run --directory aiosecurityspy ruff format --check src tests` -- expected: clean.
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` -- expected: all tests pass, 100% coverage. (`--cov` takes an importable module or a directory, never a `.py` path.)
- `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests` -- expected: clean.
- `uv run mypy custom_components/securityspy` -- expected: clean.

**Manual checks (if no CLI):**
- `strings.json` and `translations/en.json` carry identical key sets, including `config.step.user.data.ssl`, `.verify_ssl`, their `data_description` entries, `config.error.invalid_certificate` and `exceptions.invalid_certificate`.
- `manifest.json` pins the same version `aiosecurityspy/pyproject.toml` declares.




## Auto Run Result

Status: done

**Implemented change.** The config flow collects two new toggles — *Connect over HTTPS* (`CONF_SSL`, off by default) and *Verify the certificate* (`CONF_VERIFY_SSL`, on by default) — persists both with the entry, and applies them at setup to the client and to the Home Assistant session it is given. `aiosecurityspy` grew `SecuritySpyCertificateError`, a **subclass** of `SecuritySpyConnectError` raised only for a genuine certificate-verification failure, so a hostname mismatch is named as a certificate problem instead of arriving as a generic `cannot_connect`. Every other TLS failure stays a plain connect error naming the OpenSSL reason and the wrong-port possibility.

**Files changed** (unchanged this pass; carried from the earlier passes recorded above):
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` — the new `SecuritySpyCertificateError` and its subclass rationale.
- `aiosecurityspy/src/aiosecurityspy/client.py` — `_tls_reason()` plus the two TLS `except` clauses, both ordered ahead of the `TimeoutError`/`ClientError`/`OSError` chain they would otherwise be swallowed by.
- `aiosecurityspy/src/aiosecurityspy/__init__.py`, `pyproject.toml`, `CHANGELOG.md` — export and 0.3.0 release metadata.
- `custom_components/securityspy/config_flow.py` — the two form fields, the certificate-first `_ERROR_KEYS` ordering, session selection by `verify_ssl`.
- `custom_components/securityspy/__init__.py` — both flags read from the entry, the certificate-first `except` ordering, the unverified-TLS warning gated on `use_https and not verify_ssl`, `KeyError` folded into the stored-data guard.
- `custom_components/securityspy/strings.json`, `translations/en.json`, `manifest.json` — new strings and the 0.3.0 pin.
- `aiosecurityspy/tests/`, `tests/` — certificate and handshake coverage, a real-transport wrong-port test, TLS-choice propagation tests.

**Review findings this pass.** 0 intent_gap, 0 bad_spec, 0 patch, 0 defer, 14 reject. No change was made to any file this pass. Both reviewers led with the same false `SyntaxError` claim, rejected at length in the triage log above — the unparenthesized `except` groups are valid under PEP 758 on this project's Python 3.14 and are the formatter-enforced style.

**Verification performed** (all commands run, all green):
- `uv run --directory aiosecurityspy pytest` — 608 passed.
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-fail-under=100` — 50 passed, **100%** statement and branch coverage (`config_flow.py` 53/53, `__init__.py` 43/43).
- `uv run --directory aiosecurityspy mypy --strict src/aiosecurityspy` — clean, 9 files.
- `uv run mypy --strict custom_components/securityspy` — clean, 3 files.
- `uv run ruff check custom_components tests aiosecurityspy` and `ruff format --check` — clean, 28 files.
- `uv run python -VV` — Python 3.14.4, the interpreter all of the above ran on.

**Residual risks.**
- The certificate branch is proven by hand-built fakes over aiohttp's genuine connector types plus a real-transport test of the *wrong-port* case; no test stands up a real self-signed TLS server. A change to aiohttp's private `_certificate_error`/`_os_error` attributes would let the fakes pass while production fell through to the handshake branch. Weighed and rejected twice as unscoped new work.
- `manifest.json` pins `aiosecurityspy==0.3.0`, which is not on PyPI; a real HACS install of this commit cannot resolve it. Deliberate and tracked as DW-2 — the first release is intentionally deferred.
- A certificate that expires while Home Assistant is already running produces a silent reconnect loop in `stream.py`, which inherits the TLS flags but none of the new diagnosis. Filed to the deferred-work ledger for Epic 3.
