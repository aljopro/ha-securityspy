---
title: 'API_-prefix diagnostic hint on SecuritySpyAuthError'
type: 'feature'
created: '2026-09-16'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: false
context: []
baseline_revision: 'c88099517b34a701cdcbe00635655add7f19e80e'
final_revision: '1f596f5'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Live-confirmed (Story 1.22 follow-up): a SecuritySpy account whose password merely starts with `API_` (not the full 36-char key shape) is refused with a plain 401 on every API/RTSP endpoint this library calls, even with no real API key configured — indistinguishable today from an ordinary wrong password, while the same password logs into the SecuritySpy web UI fine. This makes the failure hard for a caller to diagnose.

**Approach:** Detect the `API_` prefix on the password once, at connection-settings construction time (the last point the plaintext password is in scope, per this library's existing invariant of never retaining it), and store only a boolean flag. When `_map_status` maps a 401 to `SecuritySpyAuthError`, pass that flag through so the exception can append one extra, credential-free sentence to its message when the flag is set.

## Boundaries & Constraints

**Always:**
- Never store, log, or include the plaintext password (or any substring of it) anywhere beyond the single `startswith("API_")` check at construction time. Only a `bool` may be retained.
- `SecuritySpyAuthError`'s existing constructor signature and message format for the flag-off case must be unchanged, byte-for-byte, so no existing caller or test observing today's message breaks.
- The added hint text must be generic (never quote or reference the actual password value) and must make clear this is an *observed SecuritySpy behavior*, not a guarantee — the library does not know why the server rejects it.
- Follow this codebase's existing conventions: `_ConnectionSettings` stays a frozen `@dataclass(slots=True)`; new tests use the existing credential-containment sentinel pattern in `tests/test_credential_containment.py`.

**Ask First:** (none — this is a self-contained diagnostic-message change with no external dependency or irreversible action)

**Never:**
- Do not change authentication behavior: the password is still sent to the server exactly as given, unmodified, regardless of its shape. This is a message-clarity change only.
- Do not attempt to detect the *full* key shape (`API_` + 32 base62 chars) — that is the SAMEKEY case, a separate, already-documented server-side behavior this change does not address.
- Do not add this check anywhere else (e.g. `validate_credentials`, which must keep raising only for RFC 7617 / latin-1 violations).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordinary password, 401 | Password does not start with `API_` | `SecuritySpyAuthError` message unchanged from today | N/A |
| `API_`-prefixed password, 401 | Password starts with `API_` (any length/shape) | `SecuritySpyAuthError` message includes today's text plus one added sentence noting the prefix and that it may be rejected on the API surface even if web-UI login works | N/A |
| `API_`-prefixed password, 403 (permission denied) | Password starts with `API_`, but status maps to `SecuritySpyPermissionError`, not `SecuritySpyAuthError` | No hint added — `SecuritySpyPermissionError` is unaffected; the flag is only consulted in the 401 branch | N/A |
| `API_`-prefixed password, request succeeds | No exception raised | No behavior change — the flag is only read when constructing `SecuritySpyAuthError` | N/A |

</frozen-after-approval>

## Code Map

- `src/aiosecurityspy/connection.py` -- `_ConnectionSettings`: add a frozen `password_has_api_key_prefix: bool` field, computed in `create()` from the plaintext `password` argument before it goes out of scope.
- `src/aiosecurityspy/exceptions.py` -- `SecuritySpyAuthError.__init__`: add an optional `password_has_api_key_prefix: bool = False` parameter; append the hint sentence to the message only when `True`.
- `src/aiosecurityspy/client.py:1270` -- the 401 branch of `_map_status`: pass `self._connection.password_has_api_key_prefix` to `SecuritySpyAuthError`.
- `tests/test_exceptions.py` (or nearest existing exceptions test module) -- new unit tests for both message variants.
- `tests/test_credential_containment.py` -- extend the existing sentinel sweep with an `API_`-prefixed password case, asserting the actual password value never appears in the exception's `str()`/`repr()` even though the hint is present.

## Tasks & Acceptance

**Execution:**
- [x] `src/aiosecurityspy/connection.py` -- add `password_has_api_key_prefix: bool` to `_ConnectionSettings` and set it in `create()` via `password.startswith("API_")` -- captures the signal at the only point the plaintext password exists, without retaining the password itself.
- [x] `src/aiosecurityspy/exceptions.py` -- add the optional constructor parameter to `SecuritySpyAuthError` and the conditional hint sentence -- keeps the flag-off message identical to today's for backward compatibility.
- [x] `src/aiosecurityspy/client.py` -- pass `self._connection.password_has_api_key_prefix` at the existing `SecuritySpyAuthError(...)` call site in `_map_status`'s 401 branch.
- [x] `tests/test_exceptions.py` -- unit tests: flag `False` produces today's exact message; flag `True` produces today's message plus the hint sentence, and the hint text does not reference any password value.
- [x] `tests/test_credential_containment.py` -- add an `API_`-prefixed sentinel password to the sweep; assert it never appears in any exception `str()`/`repr()`/log record even when the hint fires.

**Acceptance Criteria:**
- Given a client constructed with a password not starting with `API_`, when a request receives a 401 that is not disambiguated as a permission denial, then the raised `SecuritySpyAuthError`'s message is byte-identical to today's format.
- Given a client constructed with a password starting with `API_` (of any length or shape), when the same 401 path is hit, then the raised `SecuritySpyAuthError`'s message includes one additional, generic sentence about the `API_` prefix, and never includes the password itself.
- Given the credential-containment sweep, when it runs with the new `API_`-prefixed sentinel, then that sentinel is confirmed absent from every exception string and log record, exactly like the existing sentinels.
- Given a 403 response (permission denial) on an account with an `API_`-prefixed password, when `_map_status` runs, then `SecuritySpyPermissionError` is raised as before, unaffected by the new flag.

## Review Triage Log

### 2026-09-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 2: (high 0, medium 1, low 1)
- defer: 0
- reject: 14
- addressed_findings:
  - `[medium]` `[patch]` The hint text said the password "is the shape of a SecuritySpy 6.22+ per-account API key," but the check is prefix-only (`startswith("API_")`), so it also fires for an ordinary, non-key-shaped password (exactly as the diff's own `PARTIAL_KEY_PASSWORD` test fixture demonstrates) -- overstating confidence. Reworded to "the same prefix ... use[s]" and added an explicit hedge that this may not be the cause of this specific rejection, addressing the same overclaim both reviewers independently flagged.
  - `[low]` `[patch]` The "6.22+" version claim and the underlying observed behavior had no traceable source from the code itself. Added a docstring citation to Story 1.22 and `research/securityspy-api-keys-6.22.md` in the planning repo, and tightened the tested-build language to "6.22b9-6.22b10" (the builds this project actually tested against) rather than an open-ended "6.22+".
  - `[reject]` "Flag could go stale if connection settings are mutated outside `create()`" -- `_ConnectionSettings` is `@dataclass(frozen=True, slots=True)`; it cannot be mutated after construction, so this is structurally impossible, not a real gap.
  - `[reject]` "Case-sensitive `API_` check misses `api_`/`Api_` passwords" -- correct behavior, not a bug: SecuritySpy's own real key prefix and every sample this project has observed are uppercase `API_`; a lowercase variant isn't shaped like the vendor's own convention, so matching its exact case is intentional, not an oversight.
  - `[reject]` "Docstring claims this is the only trace of the password retained past `create()`, an unenforced claim about the rest of the codebase" -- matches this file's existing documentation convention (e.g. `_ConnectionSettings`'s own class docstring already asserts a similar cross-cutting invariant); not a new problem this diff introduces.
  - `[reject]` "No test/fixture establishes the underlying behavior was actually observed" -- inherent to any change encoding a real vendor-server finding from live testing outside this repo (the live evidence lives in `research/securityspy-api-keys-6.22.md` and Story 1.22's live test suite, not in an offline unit test); matches how other vendor-observed quirks are already documented in this codebase (e.g. the unnamed permission bit).
  - `[reject]` "Bolting a diagnostic flag onto a public exception constructor couples a general error type to one historical bug" -- this is exactly the approach the human-approved `<frozen-after-approval>` spec intent specifies; the parameter is optional and keyword-only, so no existing caller breaks.
  - `[reject]` "`test_auth_error_hint_is_phrased_as_observed_not_guaranteed` is a weak, purely lexical check" -- true but low-value to strengthen further; the substantive leak-safety and content assertions are carried by the other three tests in the same file plus the full sweep in `test_credential_containment.py`.
  - `[reject]` "`repr()`/`str()` count comparison only checks the 4-char `API_` token, not a full password leak" -- correct, but that is a supplementary check in `test_exceptions.py`; the actual leak-proof is `test_credential_containment.py`'s full sentinel sweep over `caplog.text` and every rendered exception, which does check the complete sentinel string.
  - `[reject]` "`PARTIAL_KEY_PASSWORD` sentinel and the hint's own `API_` substring could collide in the containment sweep" -- a misreading: the sentinel-absence loop checks the full 26-character sentinel string, while the separate hint-fired assertion checks only for the substring `"API_"`, which the static hint text legitimately contains regardless of the sentinel's value; the two assertions test different things and do not conflict.
  - `[reject]` "Comment claiming `PARTIAL_KEY_PASSWORD` is 'not SAMEKEY-shaped' is unverified" -- true but a trivial, non-blocking documentation nitpick; the sentinel's actual value is visibly a different length and character set than `API_KEY` in the same file.
  - `[reject]` "The 401 branch always passes the flag regardless of the failure's real cause (e.g. IP block, revoked key)" -- addressed by the medium-severity wording patch above (the hedge now explicitly says this may not be why this particular request was rejected), so no code-level restriction is needed on top of that.
  - `[reject]` "No end-to-end test through the real `SecuritySpyClient` with realistic host/port" -- `test_credential_containment.py`'s `make_client_with_partial_key_prefix` already constructs a real `SecuritySpyClient`/`_ConnectionSettings` and drives it against a `FakeServer` returning 401, which is genuinely end-to-end through the real code path; only the exact host/port values are synthetic, which is true of every other test in that file.
  - `[reject]` "`noqa: S105` suppressions copy-pasted without per-instance justification" -- matches the existing convention already used for the sibling `API_KEY` sentinel a few lines above in the same file.

## Design Notes

**Why a boolean, not the password.** `_ConnectionSettings` is deliberately frozen with a documented invariant that only `auth_header` (already base64) survives past construction — adding the raw password as a field would be a regression against that invariant and against `__repr__`'s credential-safety guarantee. A single boolean computed once at the last point the plaintext exists preserves the invariant while still letting the exception layer act on the signal.

**Why not detect this server-side/in the relay.** The relay and `connection.py` never inspect password *content* today, only its encodability (`validate_credentials`). This change is intentionally narrow: one derived fact, one call site, one message. It does not attempt to explain or work around SecuritySpy's behavior — only to name it in the error a caller already receives.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, including the new exception and containment tests.
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: clean.
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: clean.

## Auto Run Result

**Summary:** Added a narrow, credential-safe diagnostic hint to `SecuritySpyAuthError`: when a password starts with `API_` (the prefix SecuritySpy 6.22+ per-account API keys use, though this check matches the prefix only, not a key's full shape), a 401 now carries one extra, hedged sentence naming this as a possible contributing factor -- never a guarantee, never quoting the password. No authentication behavior changed; the password is still sent to the server exactly as given.

**Files changed (all in `aiosecurityspy`):**
- `src/aiosecurityspy/connection.py` -- `_ConnectionSettings` gained `password_has_api_key_prefix: bool`, computed once in `create()` from `password.startswith("API_")`; the plaintext password itself is never retained past this point.
- `src/aiosecurityspy/exceptions.py` -- `SecuritySpyAuthError.__init__` gained an optional keyword-only `password_has_api_key_prefix` parameter; flag-off message is byte-identical to before, flag-on appends the hedged hint sentence.
- `src/aiosecurityspy/client.py` -- `_map_status`'s 401 branch passes the new flag through; the 403 (`SecuritySpyPermissionError`) branch is untouched.
- `tests/test_exceptions.py` (new file) -- 4 unit tests covering both message variants and the no-credential-leak guarantee.
- `tests/test_credential_containment.py` -- added an `API_`-prefixed (non-key-shaped) sentinel password/username pair, drove a real `SecuritySpyClient` through the existing 401 sweep with it, and asserted both that the sentinel never leaks and that the hint actually fires (not a vacuous check).

**Review findings:** 2 patched (1 medium, 1 low; both applied), 0 deferred, 14 rejected as noise (several based on the frozen-dataclass invariant making a concern structurally impossible, matches to existing codebase conventions, one reviewer misreading of the sentinel-vs-substring distinction, and inherent limits of encoding a live vendor finding in an offline test suite). The medium finding was substantive: the original hint text overclaimed that a merely-`API_`-prefixed password was "the shape of" a real key, when the check is prefix-only — reworded to be accurate and to explicitly hedge that this may not be the cause of any specific 401.

**Verification:**
- `uv run pytest -q -k "not live"` -- 1079 passed.
- `uv run ruff check . && uv run ruff format --check .` -- clean.
- `uv run mypy --strict src tests` -- clean, 26 source files.

**Residual risks:** none identified beyond what the hedged wording already accounts for. The pre-existing, unrelated live RTSP-relay test failure (documented in prior stories) is untouched by this change.

Status: done
