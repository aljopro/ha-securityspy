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
| Any endpoint | `?auth=API_...` (raw key in query string) | 401 | Contradicts the vendor's own help text; observed on both HTTP and RTSP. This is a vendor discrepancy, not a library bug — the library's `unsecured_stream_url()` and relay paths never build this form, so nothing here is affected |
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
