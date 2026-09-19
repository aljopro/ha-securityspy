# SecuritySpy API Keys (6.22): Do They Replace Credentials?

**Story:** 1.21 (spike) — PRD Open Question 11, reopened via sprint-change-proposal-2026-09-16.md
**Server tested:** SecuritySpy 6.22b10
**Test account:** a `Live`-permission account (per-account API keys, SecuritySpy 6.22b9+)
**Date:** 2026-09-16

No real credential or key value appears anywhere in this document. Where a
concrete-looking value is shown it is a fixed placeholder (`API_` + 32
arbitrary base62 characters), never a value read from the live server.

## Headline result

A per-account API key works as the **Basic-auth password** on every
HTTP/RTSP endpoint the library calls, with the username ignored. It is
**refused** in the `auth=` query-string form the vendor's own help text
describes, and it is **refused** at the web UI login even though it succeeds
on the API/RTSP surface for the same account.

## Endpoint-by-result table

| Endpoint | Form tested | Result | Notes |
|---|---|---|---|
| `++systemInfo` | `Authorization: Basic base64(username:KEY)`, real username | 200 | Same shape as password auth |
| `++systemInfo` | Basic, empty or made-up username, key as password | 200 | Username is ignored once a key is presented as the password |
| `++image` | Basic, key as password | 200 (JPEG) | Media path accepts the key identically to `++systemInfo` |
| `++eventStream` | Basic, key as password | 200 | Streaming endpoint accepts the key |
| RTSP `DESCRIBE` | Basic, key as password | 200 OK | Key authenticates the RTSP control channel too |
| `++settings-general` (admin-only) | Basic, key as password, `Live`-permission account | 403 | Matches what the account's real password would get — `_map_status` (client.py:1263–1268) disambiguates by the account's permission level, not by whether a key or password was presented, so no change is needed there |
| Any endpoint | `?auth=API_...` (raw key in query string) | 401 | Contradicts the vendor's own help text; observed on both HTTP and RTSP. **Fixed in 6.22b11 (see addendum).** This was a vendor discrepancy, not a library bug — the library's `unsecured_stream_url()` and relay paths never build this form, so nothing here is affected |
| Any endpoint | `?auth=base64(username:key)`, `?auth=base64(:key)`, or `?auth=base64(made-up-username:key)` (key wrapped the same way Basic auth wraps it) | 200 | Base64-wrapping works in the query string even though the raw key does not; the username is ignored here exactly as it is in the Basic-auth header form |
| Web UI `/` | Basic, key as password | 403 | The server actively refuses a key at the web login, versus 200 for the real password and 200 for no auth at all |

## Key format observed

Five freshly generated keys were all of the same shape: `API_` followed by
exactly 32 base62 (`[A-Za-z0-9]`) characters — 36 characters total. This is
consistent with the sentinel used in the new tests
(`aiosecurityspy/tests/test_credential_containment.py`) and could support a
future shape-based check, but adding one is explicitly out of scope for this
spike (see Boundaries in the spec).

## The password-equals-key lock-out (edge case)

A separate account's password was deliberately set equal to its own API key
value. Once that is true, SecuritySpy treats the account as **key-authenticated**
everywhere: HTTP and RTSP endpoints accept it under any username, but the
account's own password is refused (403) at the web UI login. This is a
SecuritySpy-side behavior, not something the library can detect or control —
it falls out of the server treating "password happens to be key-shaped" as
"this is a key," and there is no way for a client to know which
interpretation the server will apply short of trying both. Documented here as
a known edge case, not addressed with any library change.

## Sub-ACs exercised live vs. left open

**Exercised live (this session):**
- Key as Basic password on `++systemInfo`, `++image`, `++eventStream`, RTSP `DESCRIBE`
- Key on an admin-only endpoint with a non-admin account (403, matches password behavior)
- Raw `auth=` query-string form vs. base64-wrapped `auth=` form
- Web UI login behavior with a key
- Password-identical-to-key lock-out behavior

**Left open — require a manual SecuritySpy UI action this run could not perform:**
- **Behavior on a camera number the account cannot see.** Not tested: doing so
  would require reconfiguring the test account's per-camera permissions in the
  SecuritySpy UI, which is a manual action outside this spike's scope. Expected
  behavior based on the permission model is the same 403/permission-denial
  path as with a password, but this is not confirmed.
- **Behavior after regenerating or deleting a key.** Not tested: SecuritySpy
  only exposes key regeneration/deletion through its UI, and doing so would
  invalidate the fixture set this session's other findings depend on. Whether
  a regenerated/deleted key fails cleanly (401) or the server transiently
  accepts a cached credential is unconfirmed.

Both are called out here explicitly rather than silently skipped, per the
spec's constraint against fabricating a result.

## Update (2026-09-16, follow-up)

The `auth=` query-string finding above now has regression coverage:
`test_live_raw_key_in_auth_query_param_is_rejected` and
`test_live_base64_wrapped_key_in_auth_query_param_is_accepted` in
`aiosecurityspy/tests/test_live_server.py`. The base64-wrapped form was
additionally confirmed live with a made-up username (not the account's real
one), closing the one untested combination from the original table above:
any username works in the query-string form too, exactly as it does in the
Basic-auth header form. This closes one of the two items logged to
`deferred-work.md` after the first review pass.

## Update (2026-09-16, second follow-up)

The password-equals-key lock-out finding also now has regression coverage:
`test_live_samekey_password_authenticates_api_endpoints_under_any_username`
and `test_live_samekey_password_is_refused_at_web_login` in
`aiosecurityspy/tests/test_live_server.py`. Both deferred-work items from
Story 1.21's review are now resolved.

One incident during this pass: an early verbose (`-v`) test-failure run
printed the SAMEKEY account's password/key value in full via pytest's
traceback locals, in a terminal session visible to the user. It was a
caught-and-fixed `aiohttp.BasicAuth` deprecation warning treated as an error
(fixed by switching to `aiohttp.encode_basic_auth()`, matching the library's
own convention), not a defect in the shipped tests, but the exposure is
recorded here per this project's disclosure discipline. The user was informed
in-session and the affected account's key should be treated as exposed on
that local test machine.

## Recommendation

Of the three options under AD-13 (no change / relay authenticates upstream
with a key / that plus key-bearing URLs handed to consumers), this spike's
findings support **option 2: the relay may authenticate upstream with a key**
as the most promising direction, without adopting it here:

- A key works identically to the password everywhere the relay's upstream
  connection needs it (Basic auth on HTTP and RTSP), so no new upstream
  authentication mechanism is required in `connection.py`.
- Option 3 (handing key-bearing URLs to consumers) is undermined by the
  `auth=` query-string finding above: the vendor's documented raw-key query
  form does not work, so a key-bearing URL would have to carry a
  base64-wrapped value instead, which is materially the same secret-in-URL
  exposure AD-13's item 3 already ruled out for passwords — it does not become
  safer just because the secret is a key.
- Option 1 (no change) is unaffected by this spike either way; option 2 looks
  additive and reversible on everything tested, though the invisible-camera
  and regenerate/delete sub-ACs remain unconfirmed (see above) and should be
  closed before treating that as settled.

This is a recommendation only. Adopting any option requires a follow-up
correct-course per this story's own acceptance criteria; PRD Open Q11 stays
"reopened."

## Story 1.22 follow-up (2026-09-16)

**Server tested:** SecuritySpy 6.22b10 (same server/build as Story 1.21; no
newer build was available this session).

Closes the three sub-ACs Story 1.21 left unexercised. New regression tests:
`test_live_partial_key_shaped_password_authenticates_normally` and
`test_live_percam_key_on_unpermitted_camera_is_denied` in
`aiosecurityspy/tests/test_live_server.py`, gated on the new optional
`SECURITYSPY_PARTIALKEY_USER`/`_PASS` and `SECURITYSPY_PERCAM_KEY` fixtures
documented in `.env.example`.

**Password shaped like a partial key** -- **confirmed live (2026-09-16, post-done
follow-up)**. An operator configured `SECURITYSPY_PARTIALKEY_USER`/`_PASS`
against the live server with a password starting `API_` but not matching the
full 36-character key shape. Contrary to this document's original hypothesis
(that a partial match would authenticate normally, since it doesn't match the
shape a key-detecting check would use), the actual result is:

- The password **succeeds** at the SecuritySpy **web UI** login form.
- The identical password is **refused with 401** on the Basic-auth **API
  surface** (`++systemInfo`, and by the same code path every other endpoint
  this library calls), confirmed with `test_live_partial_key_shaped_password_is_refused_on_the_api_surface`.
- Confirmed with no API key present on the account at all (the operator
  created one, then deleted it, to rule out interference from a real key
  coexisting on the same account) -- the rejection is not about a stored key
  matching or not matching, it happens even with zero keys configured.

This is the **opposite asymmetry** from the SAMEKEY lock-out: SAMEKEY was a
password matching the *full* key shape being accepted on the API surface but
refused at the web UI. Here, a password merely *starting with* `API_` --
regardless of matching the full shape -- is refused on the API surface but
accepted at the web UI. The most likely explanation is that SecuritySpy's
Basic-auth/API code path checks for the `API_` prefix alone and attempts a key
lookup whenever it sees one, refusing outright when no matching key exists,
while the web login form does not apply that same check. This was not proven
by isolating the exact server-side logic (this project has no visibility into
SecuritySpy's implementation), but the behavior itself -- prefix-triggered,
not shape-triggered, API-surface-only -- is directly observed and now has a
regression test.

**Practical implication:** an ordinary SecuritySpy account whose real password
happens to start with `API_` -- for any reason, not just a deliberately
constructed test fixture -- would be locked out of every API and RTSP
endpoint this library calls, while still being able to log into the web UI
normally. That makes the lockout easy for an affected user to miss (their web
login still works) and hard to diagnose from the library side, since the
library's own `_map_status` (client.py:1263-1268) has no way to distinguish
"wrong password" from "password shaped like a key prefix" -- both are a plain
401.

**Key on a camera the account cannot see** -- **left open**. `SECURITYSPY_PERCAM_KEY`
was not configured in this session's `.env` (obtaining a key for the existing
PERCAM account requires the SecuritySpy web UI, a manual action this run
cannot perform), so `test_live_percam_key_on_unpermitted_camera_is_denied`
skipped. The test is now in place as a regression check: it authenticates as
PERCAM using the key as the Basic-auth password, then requests a camera
number absent from that account's own `++systemInfo` inventory. Per
`client.py::async_get_camera_image`, a camera absent from the inventory is
refused locally with `SecuritySpyPermissionError` before any request is
sent -- this local-refusal path does not depend on whether a key or a
password authenticated the account, so it is expected to hold, but is not
confirmed against a real server with a real key.

**Key regenerate/delete** -- **left open**, unchanged from Story 1.21.
Regenerating or deleting a live account's key is a manual SecuritySpy UI
action that would invalidate the fixture set every other live test in this
suite depends on (the LIVE and SAMEKEY key/password fixtures in particular).
Exercising it would require either a disposable account set up solely to be
broken, or performing the action against a fixture account and then
re-provisioning every other live test's `.env` values afterward -- both are
manual operator actions outside what this automated run can safely do
without risking the rest of the suite. Whether a regenerated/deleted key
fails cleanly (401) or the server transiently accepts a cached credential
remains unconfirmed, exactly as Story 1.21 documented.

### Final recommendation (revised 2026-09-16, post-done follow-up): warn on the `API_` prefix in `async_get_camera_image`'s and the client's exception mapping, but do not implement it in this story

**Adopt a narrow, prefix-only warning -- as a follow-up story, not here.** The
confirmed partial-key-password finding above changes this document's original
"continue deferring" conclusion. Revised rationale:

- The original deferral rested on there being no live evidence that a
  password merely starting with `API_` causes a real problem. That evidence
  now exists: it causes a full lock-out of every API/RTSP endpoint this
  library calls, silently indistinguishable from a wrong password (`_map_status`,
  client.py:1263-1268, has no way to tell them apart), while leaving the web
  UI login working -- an outcome a real operator could hit by accident (a
  password manager generating a string that happens to start `API_`, or a
  user reusing a value they saw called "API Key" without understanding its
  scope) with no clear symptom pointing at the cause.
- This is a **prefix** check, not the fuller `API_[A-Za-z0-9]{32}` shape check
  this document previously discussed and deferred. The SAMEKEY full-shape case
  is still a SecuritySpy-server-side behavior the library cannot influence, and
  that part of the original rationale (a client-side full-shape check would
  not change server behavior) still holds -- the library should not attempt to
  detect or special-case the *full* key shape. Detecting the *prefix* alone is
  different: it lets the library raise a clearer, actionable error (e.g. "this
  password starts with a SecuritySpy API-key prefix and will be rejected by
  the API surface even though it may work in the web UI -- check the password
  is not a key value") instead of a bare `SecuritySpyAuthError`, entirely
  within the library's own exception-mapping layer and without querying or
  guessing at SecuritySpy's internal key-lookup behavior.
- The other two sub-ACs (camera visibility scoping under a key; regenerate/delete)
  remain as documented below and do not bear on this specific recommendation --
  the `API_`-prefix lock-out is independent of both.
- This is a recommendation only, scoped narrowly to *diagnostics* (a clearer
  exception message), not to *authentication behavior* (the library still
  never rejects, alters, or special-cases a caller-supplied password before
  sending it). Implementing even this narrow scope is a new story, adopted
  only through a follow-up correct-course per this story's own boundaries --
  not implemented here.
- This does not change the AD-13 item 2 recommendation above (the relay may
  authenticate upstream with a key): that recommendation concerns how the
  relay *uses* a key it is given, not how the client reports an authentication
  failure, and the two remain independent.

PRD Open Q11 stays "reopened." This recommendation does not close it; adopting
any part of it -- including the narrow diagnostic warning above -- remains a
follow-up correct-course decision per this story's own boundaries.

## Addendum (2026-09-18): vendor fixes in 6.22b11

Ben replied on forum thread 4922 (2026-09-17) and shipped beta 6.22b11:

1. The `auth=` parser now accepts the naked `API_xyz` form.
2. Creating a regular web password with the `API_` prefix is now disallowed
   (he called it a trap).
3. The `API_` prefix is fixed and can be relied on.

Live re-probe against 6.22b11 (`test-live` key, 2026-09-18): raw `auth=<key>`
returns 200 on `++systemInfo`, `++image` and `++eventStream` (401 on b10);
`auth=base64(:KEY)`, Basic `user:KEY` and Basic `:KEY` return 200; the ordinary
user and password still return 200; a well-formed wrong key and no auth return
401; the web UI with a key returns 403. Not re-tested: that the server now
refuses an `API_`-prefixed web password (needs an admin action).

Consequences: the raw-query form is no longer a vendor discrepancy, and the
prefix is a stable contract, which supports the `API_`-prefix diagnostic in the
client's exception mapping (implemented; see deferred-work.md). The diagnostic
still matters for accounts whose passwords were set before b11 and for servers
below 6.22.

