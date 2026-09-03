---
title: 'Story 1.7: Credential-safe diagnostics'
type: 'feature'
created: '2026-08-17'
status: 'done'
baseline_revision: '75a1137a4d01748cee06706f350da218e70599a4'
review_loop_iteration: 0
final_revision: 'edbbbbb9c6a4bb27ba8f97399a165ec011078f4a'
followup_review_recommended: false  # fourth pass (R3) 2026-09-03: 5 patches applied (2 medium security/PII coverage gaps, 3 low-severity edge cases), all localized to diagnostics.py; 5 pre-existing out-of-scope issues deferred to DW; 0 rejected
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `++settings-cameras` returns per-camera device `username`/`password` in plaintext (research §8.3), and a credential-bearing URL such as `rtsp://user:pass@host/...` was observed being echoed verbatim by an external tool (research §7). The library scrubs these ad hoc — a curated `CameraSettings` decode, hand-written `__repr__`s, `try/finally` frame clears — but there is no anonymizer a consumer can point a diagnostics dump at, and no single declared key set to extend when a future SecuritySpy version adds a credential-shaped key.

**Approach:** Add one small pure module, `diagnostics.py`, exporting a recursive `anonymize()`, a `redact_url()`, and the `is_credential_key()` predicate all redaction decisions route through; declare the credential key vocabulary once in `const.py`. Prove the standing "nothing leaks" claims with a whole-library test rather than leaving them as prose.

## Boundaries & Constraints

**Always:** Redaction decisions go through exactly one predicate over one declared key set in `const.py` — no second list, no inline key literal at a call site. `anonymize()` is pure and fail-closed: an input shape it does not understand degrades to a type marker, never to `repr()`. Structure survives redaction — keys, container types, and non-credential values are preserved so the output is still diagnosable. `aiohttp.BasicAuth` and every other `NamedTuple` is walked by field name, never positionally. Existing public names keep their name, type and meaning.

**Block If:** honouring these constraints would require changing an existing public signature, or removing an existing log call that carries real diagnostic value.

**Never:** No diagnostics-dump builder, no `SecuritySpyClient.async_get_diagnostics()` — the library supplies the anonymizer, the consumer supplies the dump. No auth-token support (research §1b: format unverified). No network, no I/O, no Home Assistant import in `diagnostics.py`. No `conftest.py`. No change to how credentials reach the wire (`auth=` kwarg only, never a URL).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Settings payload | raw `++settings-cameras` dict with `username`, `password`, ~120 other keys | both credential values become `REDACTED`; every other key and value survives unchanged | No error expected |
| Key normalization | `Password`, `authToken`, `auth_token`, `AUTH-TOKEN` | all match; matching is on the key lowercased with non-alphanumerics stripped | No error expected |
| Non-credential lookalike | `passwordProtected: True`, `userCount: 3` | preserved unredacted — membership is exact over the normalized key, not substring | No error expected |
| Credential key, odd value | credential key whose value is `None`, `0`, a dict, or a list | value becomes `REDACTED` regardless of type; the subtree is not walked | No error expected |
| URL with userinfo | `rtsp://ad min:s3cret@host:8000/++stream?auth=Ym9i` (string value anywhere in the input, or passed to `redact_url`) | userinfo replaced by `REDACTED:REDACTED`, `auth` param value replaced by `REDACTED`; scheme, host, port, path and non-credential params intact | No error expected |
| Non-URL string | `"Front Gate"`, `"a:b"`, `""` | returned unchanged — `redact_url` only acts on a string with a scheme and `://` | No error expected |
| Unparseable URL | a string that starts `http://` but `urlsplit` rejects | whole string becomes `REDACTED` | Fail closed, no raise |
| NamedTuple | `aiohttp.BasicAuth("bob", "s3cret")` | walked by `_fields`; `login`/`password` redacted, `encoding` kept | No error expected |
| Dataclass | any library model, e.g. `Camera`, `CameraSettings` | walked by field name into a `dict`; credential-shaped fields redacted | No error expected |
| Opaque object | an `aiohttp.ClientSession`, a class, a lambda | `<ClientSession>` — the type name only, never `repr()` | Fail closed, no raise |
| Bytes | `b"..."` of length 27 | `<bytes: 27>` | No error expected |
| Cycle / deep nest | a dict containing itself; nesting past the depth cap | `<recursive>` / `<truncated>` marker at the boundary; no `RecursionError` | Fail closed, no raise |
| Known literal secrets | `anonymize(value, secrets=["s3cret"])` | every occurrence of `s3cret` inside any produced string is replaced by `REDACTED`, including inside a value under a non-credential key | No error expected |
| Empty secret | `secrets=["", "  ", None-ish]` | ignored — an empty secret must not shred every string | No error expected |
| Full session at debug | client request, settings read, settings write, arming write and a stream session run under `caplog.at_level(0, logger="aiosecurityspy")` | neither connection credential, neither device credential, and no settings-payload marker value appears in `caplog.text` | No error expected |
| Credentials never in a URL | `ConnectionSettings.build_url` over every endpoint constant; every URL the client and stream hand to the session | no userinfo, no `auth`/`username`/`password` query parameter | Asserted, not assumed |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `REDACTED` and `CREDENTIAL_KEYS`. The vocabulary home; it imports nothing from the library, so keep it that way. `PERMISSION_NAMES` and `class_slug` show the house shape for a `Final` table plus a normalizing helper.
- `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- create: `is_credential_key`, `redact_url`, `anonymize`. New module, pure, no logger.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: re-export the four new names in RUF022 sorted order.
- `aiosecurityspy/src/aiosecurityspy/connection.py` -- read only: `build_url`/`base_url` (the only two URL-building expressions in the library) and the `BasicAuth` field at `__init__`; `ConnectionSettings.__repr__` documents why `BasicAuth`'s default repr is the hazard.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- read only: `_request` (the `auth=` kwarg, the `try/finally` body scrub) and the three `_LOGGER.debug` sites; nothing here changes.
- `aiosecurityspy/tests/test_settings.py` -- the prior art to follow and not duplicate: `test_settings_never_retain_or_print_device_credentials` (the `dir()`-walk haystack) and `test_settings_payload_is_never_logged_at_any_level` (`caplog.at_level(0, logger="aiosecurityspy")`). Its `FakeSession` and settings-page fixture are the pattern the session sweep reuses.
- `aiosecurityspy/tests/test_stream.py` -- the stubbed-session stream lifecycle harness the session sweep drives for the stream half.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §8.3 (the plaintext credential leak and its three client requirements), §7 "Credentials in RTSP URLs", §1b (tokens, unverified — out of scope).

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `REDACTED: Final = "**REDACTED**"` and `CREDENTIAL_KEYS: Final[frozenset[str]]` holding the normalized credential-shaped key names (at minimum SecuritySpy's own `username` and `password` per research §8.3, plus `auth`, `authtoken`, `token`, `secret`, `apikey`, `authorization`, `passwd`, `pass`), each with a comment citing why it is in the set -- AC3 asks for one declared set extensible in one place, so the set must be data in the vocabulary module rather than a literal in the walker.
- [x] `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- create: `is_credential_key(key)` (normalize to lowercase, strip non-alphanumerics, test membership; non-`str` degrades to `False`), `redact_url(url)` (userinfo → `REDACTED:REDACTED`, credential-shaped query parameters → `REDACTED`, everything else preserved, unparseable → `REDACTED`, non-URL string returned unchanged), and `anonymize(value, *, secrets=())` (recursive walk over mappings, `NamedTuple`s by `_fields`, dataclasses by field name, list/tuple/set, `str` through `redact_url`, `bytes` → length marker, scalars as-is, anything else → `<TypeName>`; depth cap and identity-based cycle guard; literal `secrets` substring-replaced in every produced string, empty/blank secrets ignored) -- one predicate, one walker, so a future key set change lands everywhere at once.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export `CREDENTIAL_KEYS`, `REDACTED`, `anonymize`, `is_credential_key`, `redact_url` -- the published API is a contract from first release.
- [x] `aiosecurityspy/tests/test_diagnostics.py` -- create: cover every I/O-matrix row above the last two, including the `aiohttp.BasicAuth` positional-leak row, the `passwordProtected` false-positive row, the self-referential dict, and a `CameraSettings`/`Camera` round trip proving a library model anonymizes into a readable dict.
- [x] `aiosecurityspy/tests/test_credential_containment.py` -- create: the two whole-library rows. One drives a full session against the stubbed session and stream harnesses — system-info read, settings read, settings write, arming write, a stream connect/event/disconnect, plus a failing request on each path — under `caplog.at_level(0, logger="aiosecurityspy")` with distinct sentinel connection and device credentials, asserting none of them and no settings-payload marker reaches `caplog.text`, any raised exception's `str`/`repr`, or its rendered traceback. The other asserts `build_url` over every exported endpoint constant, and every URL recorded by the stub for both client and stream, carries no userinfo and no credential-shaped query parameter -- these are the story's standing claims, and a claim nothing executes is not a claim.
- [x] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- edit: a runnable snippet anonymizing a settings dict and redacting an RTSP URL, stating that `redact_url` is what a consumer must use before a credential-bearing stream URL reaches a log or a subprocess argument, and that `CREDENTIAL_KEYS` is the one place to extend -- research §7's hazard belongs to the consumer, so the library must hand them the tool and say so.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a consumer module importing the new surface, when `mypy --strict` is run against it, then every new name resolves through `__all__` with complete type information and no `Any` in a public signature.
- Given the `src/` tree, when `grep -rn` searches for a credential key literal outside `const.py`, then `CREDENTIAL_KEYS` is the only source of those strings.
- Given `diagnostics.py`, when its imports are inspected, then only the standard library and `.const` appear — no `aiohttp`, no network, no Home Assistant.
- Given a new credential-shaped key added to `CREDENTIAL_KEYS` and nothing else changed, when the suite runs, then both `anonymize` and `redact_url` redact it — proven by a test that extends the set at runtime rather than by inspection.

## Spec Change Log

## Review Triage Log

### 2026-08-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 19: (high 4, medium 7, low 8)
- defer: 1: (high 0, medium 1, low 0)
- reject: 6: (high 1, medium 2, low 3)
- addressed_findings:
  - `[high]` `[patch]` A URL embedded in free text leaked verbatim — `anonymize("connecting to rtsp://bob:pw@host/x")` returned it unchanged, and free-text messages are the canonical diagnostics content. Added an embedded-URL pass alongside the anchored `redact_url`, keeping every matrix row for `"Front Gate"` / `"a:b"` / `""` intact.
  - `[high]` `[patch]` A non-string mapping key defeated the predicate — `anonymize({b"password": "LEAK"})` published the value. Keys are now rendered to a string form before `is_credential_key` runs.
  - `[high]` `[patch]` `anonymize()` could raise, violating the intent contract's fail-closed Always constraint: a mapping whose `items()` raised propagated out of the anonymizer. Every container branch, member read and `str()` render is now guarded and degrades to `<unwalkable TypeName>`.
  - `[high]` `[patch]` `CREDENTIAL_KEYS` was not extensible at its declared home — `from .const import CREDENTIAL_KEYS` created a private third binding, so setting `const.CREDENTIAL_KEYS` had no effect and the AC5 test only proved the weaker claim by patching the private name. `diagnostics` now reads `const.CREDENTIAL_KEYS` at call time; the AC5 test patches the declared home.
  - `[medium]` `[patch]` Diagnostically valuable values flattened to a bare type name — `Capture.start`/`duration` anonymized to `<datetime>`/`<timedelta>`, the "safe and useless" outcome the Always constraint forbids. `datetime`/`date`/`time`/`timedelta`/`Decimal`/`UUID`/`PurePath`/`Enum`/`BaseException` now render via `str()` through the same string pipeline; everything else still fails closed.
  - `[medium]` `[patch]` A protocol-relative reference (`//user:pw@host/x`) leaked its userinfo.
  - `[medium]` `[patch]` A credential parked in the URL fragment (`#auth=...`) was never redacted; the fragment now goes through the query redactor.
  - `[medium]` `[patch]` The legacy `;` query separator bypassed redaction — `?cameraNum=3;auth=Ym9i` kept `auth` in the clear.
  - `[medium]` `[patch]` A known secret used as a mapping key was not scrubbed, contradicting the documented "every string the walk produces".
  - `[medium]` `[patch]` A bare `str` passed as `secrets` shredded every string, since `str` is a valid `Iterable[str]`; it is now treated as one secret.
  - `[medium]` `[patch]` Distinct mapping keys collapsed silently — `{1: "a", "1": "b"}` lost an entry with no marker; colliding rendered keys are now disambiguated.
  - `[low]` `[patch]` `<bytes: N>` counted elements rather than bytes for a cast `memoryview`; it now prefers `.nbytes`.
  - `[low]` `[patch]` An empty userinfo fabricated a credential — `http://@host/x` reported one that was never present.
  - `[low]` `[patch]` The scheme was lowercased by the `urlsplit`/`urlunsplit` round trip, falsifying the documented "byte for byte" preservation; the redactor now slices the original string.
  - `[low]` `[patch]` Widening the redactor to protocol-relative references introduced a false positive that mangled ordinary prose (`"// see a@b.com"`); the `//` form now requires a whitespace-free authority. Found and fixed in this pass, not reported by a reviewer.
  - `[low]` `[patch]` The endpoint sweep's guard reduced to `>= 2`, so four of the five endpoints could vanish from `__all__` unnoticed; it now asserts the exact endpoint set.
  - `[low]` `[patch]` The log sweep's anti-tautology guard (`assert caplog.text.strip()`) was satisfiable by one stray line; it now floors the count of `DEBUG` records from the `aiosecurityspy` logger.
  - `[low]` `[patch]` The README example ended on a dangling `print(sorted(CREDENTIAL_KEYS))` with no output comment.
  - `[low]` `[patch]` The CHANGELOG described the internal test sweep to consumers; trimmed to the guarantee a consumer actually gains.

Rejected, with reasons: the Blind Hunter's blocking claim that the package does not import because `client.py:927` holds a Python-2 `except RuntimeError, LookupError:` — **false**, that form is valid Python 3.14 syntax (PEP 758); the file compiles, the package imports and the suite passes. Also rejected: set-ordering nondeterminism and set-member collision (speculative for these payload shapes), `deque`/arbitrary-`Sequence` support and base64/percent-encoded `secrets` variants (beyond the declared shapes), and preserving an empty trailing `?` delimiter.

### 2026-08-17 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 11: (high 3, medium 5, low 3)
- defer: 1: (high 0, medium 1, low 0)
- reject: 11: (high 1, medium 3, low 7)
- addressed_findings:
  - `[high]` `[patch]` An exception's arguments leaked through `str()` — `anonymize({"e": ValueError(BasicAuth("bob", "s3cret"))})` returned `"ValueError: BasicAuth(login='bob', password='s3cret')"`, reaching the `repr` the whole module refuses to call. Exceptions are now walked argument by argument (`_walk_exception`); the single-string shape still renders as the readable `Type: message` one-liner.
  - `[high]` `[patch]` An embedded protocol-relative reference leaked its userinfo — the whole-string redactor accepted `//user:pw@host/x` but `_EMBEDDED_URL_RE` required a scheme, so the two passes disagreed about what a URL is. The embedded pattern now admits the `//` form at a word boundary with an `@` in its authority; the `"// see a@b.com"` prose false positive stays a false positive.
  - `[high]` `[patch]` A URL nested inside another URL's parameter value kept its userinfo — `_redact_query` inspected parameter *names* only and the outer match consumed the inner URL. Non-credential parameter values now go through the embedded-URL pass.
  - `[medium]` `[patch]` A credential in an RFC 3986 path matrix parameter (`/x;auth=s3cret`) was never redacted; the path now goes through the same parameter redactor as the query.
  - `[medium]` `[patch]` An `IntEnum` member escaped the walk as a live object, since it matches `isinstance(value, int)` before the render branch — contradicting the documented "plain containers, strings, scalars and markers" return and handing the consumer's serializer an arbitrary `__str__`. `Enum` is now tested before the scalar branch.
  - `[medium]` `[patch]` `CREDENTIAL_KEYS` missed the header names the docstring advertises. Added `xapikey`, `cookie`, `setcookie`, `bearer`, `sessionid`, `passphrase`, `privatekey`, `credentials` — a header mapping is one of the two dump shapes the set exists for.
  - `[medium]` `[patch]` A declared secret that arrived as a number was never scrubbed — substring replacement only sees strings, so `anonymize({"pin": 1234}, secrets=["1234"])` published it. Non-string scalars are now matched on their rendered form.
  - `[medium]` `[patch]` The URL sweep's assertion searched for only two of the five sentinels and only as exact plaintext; it now covers all five plus their percent-encoded and base64 forms — the `auth=Ym9i` shape the module itself models.
  - `[medium]` `[patch]` The endpoint sweep's docstring claimed it "covers every URL any future story can construct too" while driving a hand-rolled `FakeServer`; trimmed to what it proves, pointing at `test_stream_transport.py` for the real-socket half.
  - `[low]` `[patch]` `http://bob@host/x` fabricated a password — the same argument the empty-userinfo branch already makes four lines above, not applied one case over. The colon is now replayed only if it arrived.
  - `[low]` `[patch]` `anonymize`'s docstring, the README and the CHANGELOG all claimed "sequences keep their order and container type" while a `deque` or `range` flattens to a type marker. Narrowed the claim to lists and tuples and said what happens to the rest, rather than widening the walker past the declared shapes (that widening was rejected in the prior pass and stays rejected).

Rejected, with reasons: the Blind Hunter's blocking claim that the package is unimportable because `client.py:927` holds Python-2 `except RuntimeError, LookupError:` — **false again**, and re-verified this pass: Python 3.14.4, `import aiosecurityspy` succeeds and 703 tests pass. Its dependent claims (that no test in the diff can have run, that the README describes an unimportable package) fall with it. Also rejected: a minimum length or word boundary for `secrets` (a short real password must still redact; corrupting a dump is the lesser failure), case-insensitive secret matching (a case variant is a different string, not the credential), `?token` with no value (a name is not a secret), catching `BaseException` in the walk (would swallow `KeyboardInterrupt` and `CancelledError`), a `_MAX_DEPTH` knob and a non-`object` return type (both widen the public API the spec fixes), set-member collapse and secret-ordering inside inserted markers (cosmetic, and re-raised from the prior pass), JSON-serializability of preserved sets and tuples (the spec declares container types are preserved), and tightening `MINIMUM_DEBUG_RECORDS` (arbitrary at any value).

### 2026-08-17 — Review pass (third)
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 4, medium 4, low 4)
- defer: 1: (high 0, medium 1, low 0)
- reject: 7: (high 0, medium 2, low 5)
- addressed_findings:
  - `[high]` `[patch]` A URL nested in another URL's **path** kept its userinfo — `redact_url("http://h/proxy/http://u:s3cret@z/")` returned it unchanged. The prior pass patched exactly this hazard in the query and left the path out, so the defence was half applied: the outer match consumes the nested URL and no later pass looks at it. `_redact_path` now runs the embedded pass over the path and its matrix-parameter values.
  - `[high]` `[patch]` A **percent-encoded** nested URL leaked — `?next=http%3A%2F%2Fu%3As3cret%40z%2F` survived, and one `unquote` recovers the credential. Percent-encoding is the normal way to nest a URL in a parameter. The value is now examined decoded, and re-encoded only when the decoded form actually held a credential, so an untouched parameter still comes back byte for byte.
  - `[high]` `[patch]` The two URL matchers still disagreed, and free text was the leaking side: `_SCHEME_RE` accepted `//host/x?auth=Ym9i` but `_EMBEDDED_URL_RE` required an `@` in the authority, so `anonymize({"n": "see //host/x?auth=Ym9i now"})` published the credential. The embedded pattern now admits the `//` form on exactly the terms the anchored one does; the `"// see a@b.com"` prose case stays a false positive.
  - `[high]` `[patch]` `_usable_secrets` failed open on the last line of defence — a caller's generator that yielded a secret and then raised dropped *every* secret it had already handed over, so a credential no key names was published. Secrets are now collected as they arrive.
  - `[medium]` `[patch]` `anonymize()` was quadratic in string length: the unbounded scheme in `_EMBEDDED_URL_RE` scanned to end-of-string at every start position, so a 100 KB base64 blob or captured HTML body — an ordinary dump member — took twelve seconds, and 200 KB took roughly a minute. Bounding the scheme makes it linear; 200 KB now walks in 0.02s.
  - `[medium]` `[patch]` A declared secret destroyed booleans — `str(True) == "True"`, so a caller declaring its config's values wholesale would silently shred every matching flag, the "safe and useless" outcome the module is written against. `bool` and `None` are exempt from the rendered-form match; a numeric passcode is still caught.
  - `[medium]` `[patch]` One hostile leaf discarded every sibling in the dump — a released `memoryview` made `len()` raise inside `_walk_mapping`, which only guarded `.items()`, so `anonymize({"name": "Driveway", "buf": view})` returned `"<unwalkable dict>"`. The size computation degrades to `<bytes: unknown>` and each mapping entry is now guarded independently.
  - `[medium]` `[patch]` The containment sweep's `assert errors` was weaker than its docstring: it asserted only that the *combined* list from three phases was non-empty, so the 401 phase could stop raising — the exact regression it exists to catch — and still pass on another phase's errors. Asserted per phase now.
  - `[low]` `[patch]` `REDACTED` was annotated bare `Final`, inferring `Literal["**REDACTED**"]` where every neighbouring constant carries an explicit type. Now `Final[str]`.
  - `[low]` `[patch]` `MINIMUM_DEBUG_RECORDS`'s justification cited a fabricated number ("the three phases emit roughly twice this", and a second comment arriving at 18). The measured count is 21; both comments now say so.
  - `[low]` `[patch]` Fifteen test docstrings opened with `Patch 6:`, `Patch 13:` and the like — references to a review history no future reader can resolve. Rewritten to state the hazard.
  - `[low]` `[patch]` The CHANGELOG's nested-URL and numeric-secret claims no longer matched the code after the patches above.

Rejected, with reasons: `_MAX_DEPTH = 12` justified by one example (no concrete payload was shown to exceed it, and the cap already marks rather than raises); the URL sweep proving its claim only against a stub (the genuine gap in it — a cross-host redirect re-sending `auth=` — is deferred rather than rejected; the rest is aiohttp's contract, which the docstring already concedes); `redact_url` returning `**REDACTED**` rather than a distinguishable marker for a non-string (fail-closed is the documented contract for that branch); set-member collapse under redaction and secret-ordering inside inserted markers (cosmetic, and now re-raised for the third consecutive pass); a marker in the *input* being indistinguishable from a redaction in the output (same class); comment and CHANGELOG volume (style, and the specific comments that asserted properties the code lacked were fixed above); and the README "Status" wording.

### 2026-09-03 — Review pass (fourth, follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 1, medium 2, low 2)
- defer: 5: (high 1, medium 3, low 1)
- reject: 0
- addressed_findings:
  - `[high]` `[patch]` A URL nested in the path's *bare* segment survived percent-encoded — `_redact_path` routed the matrix-parameter value through the decode-then-recheck logic but sent `segments[0]` (everything before the first `;`) through the literal-pattern pass alone, so `redact_url("http://h/proxy/" + quote("http://bob:s3cret@z/", safe=""))` kept the credential intact once decoded. The third pass's changelog claimed the path-nesting case was fixed, but no test covered its percent-encoded form (only the literal path and the percent-encoded query were tested) — the "fixed" claim overstated coverage. Extracted the decode-then-recheck logic shared by `_redact_parameter_value` into `_redact_nested_urls_deep` and routed `segments[0]` through it too.
  - `[medium]` `[patch]` `IDENTIFYING_KEYS` was wired into `anonymize()`'s mapping walk but never into `redact_url()` — a URL carrying `?ddnsName=...` or `;wanAddress=...`, the exact PII values AD-13's 2026-08-29 widening added the constant to catch, passed `redact_url()` untouched even though the same key in a dict is redacted. `_redact_query`/`_redact_path`'s key checks now also test `is_identifying_key`, via a shared `_is_redacted_key` helper.
  - `[medium]` `[patch]` The credential-containment sweep — the spec's own standing "no URL the library builds carries a credential" test — was never extended to the capture-media paths (`async_get_capture_preview`/`async_get_capture_file`, added by story 1.9 after this story landed), the two paths most likely to carry a path-derived credential-looking string. `drive_every_path` now also fetches a preview and drains a capture file; `FakeResponse` gained `release()` and `__await__` so the fake session serves `_stream_bytes`'s non-context-managed `await session.get(...)` call, not only the `async with` shape the other paths use.
  - `[low]` `[patch]` `_redact_userinfo` treated a present-but-empty password (`http://bob:@host/`) the same as a present one, emitting a fabricated `REDACTED` for a password that was never there — the exact "never invent a password" violation the function's own comment argues against one branch up. Now distinguishes no-colon, colon-with-empty-password, and colon-with-password.
  - `[low]` `[patch]` The module docstring claimed `?auth=` redaction has form-specific handling for "both its base64 and `!`-prefixed scoped-token forms" — the redactor replaces the whole value regardless of prefix; no such branch exists. Reworded to state what the code actually does.
- Findings were surfaced by two independent reviewers (Blind Hunter, Edge Case Hunter) run in parallel against the diff since baseline `75a1137a`, which by now spans this story plus eleven subsequent stories. Findings outside `diagnostics.py`'s own scope (`client.py`'s `_request()` release-ordering, `stream.py`'s lifecycle-signal eviction under backpressure, `events.py`'s classification resync, `client.py`'s `CaptureFileStream` finalizer gap, `events.py`'s lost debug log on a deleted code path) are real but pre-existing and out of this story's scope — deferred to `deferred-work.md` rather than fixed here.

Rejected: none this pass — every finding routed to `patch` (in scope) or `defer` (out of scope).

## Design Notes

**Fail closed on the shapes, fail open on the structure.** An anonymizer that `repr()`s an object it does not recognize is one `BasicAuth` away from printing a password — so an unrecognized object degrades to `<TypeName>`. But redaction that flattens the payload is useless for its actual purpose, so containers, keys and ordinary values survive intact. The `NamedTuple` case is the one that makes this concrete: walked as a sequence, `BasicAuth("bob", "s3cret")` yields `["bob", "s3cret"]` with no key to match on. Check `_fields` before the sequence branch.

```python
def is_credential_key(key: str) -> bool:
    if not isinstance(cast("object", key), str):
        return False
    return "".join(ch for ch in key.lower() if ch.isalnum()) in CREDENTIAL_KEYS
```

**Exact membership, not substring.** `"password" in key.lower()` would redact `passwordProtected` — a boolean that tells a maintainer whether the camera is even using auth. Normalizing then testing membership catches `authToken`, `auth_token` and `AUTH-TOKEN` without inventing matches.

**`secrets=` exists because key matching cannot see a value out of context.** The consumer knows its own configured password; the anonymizer does not. Substring replacement over the produced strings is the only thing that catches a credential embedded in a free-text field or a message. Blank secrets are dropped rather than honoured, because `str.replace("", ...)` shreds every string it touches.

**What is not changing, and why that is the finding.** The library already keeps credentials out of URLs (`auth=` kwarg only), out of exception messages (curated `reason` strings), and out of logs (counts and type names, never values). This story does not repair those; it makes them executable assertions. The one residual exposure is `stream.py`'s two `_LOGGER.exception` calls, which render a *consumer's* callback traceback — frames outside library control that could hold anything. Losing that traceback would cost more debuggability than it buys, so it stays and is documented here rather than silently accepted.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, every pre-existing test included
- `cd aiosecurityspy && uv run python -c "import aiosecurityspy.diagnostics"` with `aiohttp` importable -- expected: succeeds; then `grep -n "^import\|^from" src/aiosecurityspy/diagnostics.py` -- expected: standard library and `.const` only
- `grep -rn "password\|username\|authtoken" aiosecurityspy/src/aiosecurityspy/ --include=*.py` -- expected: matches only in `const.py`'s key set, in `connection.py`'s credential validation, in docstrings/comments, and in `models.py`'s comment recording the dropped settings keys


## Auto Run Result

Status: done

**Implemented change.** A fourth review pass over story 1.7 (bmad-dev-auto, sprint-status action R3). No intent gap and no spec defect; five findings patched, all inside `diagnostics.py` or the tests that exercise it. Two closed real gaps in the redaction/PII contract itself: a percent-encoded URL nested in the bare path segment (not a matrix parameter) survived, and `IDENTIFYING_KEYS` was never checked by `redact_url()` even though `anonymize()` already checked it. A third closed a coverage gap in the story's own standing credential-containment test, which had never been extended to the capture-preview/capture-file paths story 1.9 added afterward. The remaining two were a userinfo-redaction edge case (present-but-empty password) and a docstring correction.

**Files changed.**
- `aiosecurityspy/src/aiosecurityspy/diagnostics.py` — added `_redact_nested_urls_deep` (percent-decode-then-recheck, shared by the path's bare segment and parameter values) and `_is_redacted_key` (credential-or-identifying, shared by the query and path-matrix key checks); `_redact_userinfo` now distinguishes no-colon / empty-password / real-password; module docstring's `?auth=` claim corrected.
- `aiosecurityspy/tests/test_diagnostics.py` — three regression tests: percent-encoded nested URL in the bare path, identifying keys in query/matrix position, and the three userinfo-colon cases.
- `aiosecurityspy/tests/test_credential_containment.py` — `drive_every_path` now also fetches a capture preview and drains a capture file; `FakeResponse` gained `release()` and `__await__` to serve `_stream_bytes`'s non-context-managed `await session.get(...)` shape; `FakeServer._respond` answers the two new endpoints with byte bodies.

**Review findings breakdown.** 5 patches applied (1 high, 2 medium, 2 low), 5 deferred (1 high, 3 medium, 1 low — all pre-existing, outside `diagnostics.py`: `client.py`'s `_request()` connection-release ordering, `stream.py`'s lifecycle-signal eviction under backpressure, `events.py`'s classification resync fabricating a class on a corrupted confidence, `client.py`'s `CaptureFileStream` finalizer gap, `events.py`'s lost debug log for a direct `parse_event_line()` caller), 0 rejected.

**Verification performed.**
- `uv run ruff check .` — all checks passed
- `uv run mypy src/aiosecurityspy/diagnostics.py` — no issues
- `uv run pytest -q -m "not live"` — 1015 passed, 14 deselected, 0 failed (full suite, including the three new regression tests this pass added)
- Each of the five findings reproduced by direct execution before the fix (percent-encoded path leak, `ddnsName`/`wanAddress` surviving `redact_url`, capture-media URLs unexercised by the containment sweep, fabricated `REDACTED:` on an empty password) and confirmed fixed after.

**Residual risks.**
- The five deferred findings are real per two independent reviewers but outside this story's scope (stream lifecycle, event decoding, client connection pooling) — logged to `deferred-work.md` for separate follow-up (closes DW-3, the "follow-up review still recommended" placeholder for this story).
- The prior passes' residual risks (cross-host redirect `auth=` re-send, unbounded-length `secrets=` substring matching, unvalidated `_MAX_DEPTH`) are unchanged by this pass.
