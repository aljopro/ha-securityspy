---
title: 'Relay live video without handing out credentials'
type: 'feature'
created: '2026-09-13'
status: 'done'
baseline_revision: 'da1778a3bcb724f1e3d5831fb0829b0f8d129310' # aiosecurityspy HEAD; ha-securityspy HEAD 00863d78a3b9c50d425e7ed7b20f93bdce0b77ba
final_revision: '96b42640b71ede10b5831c212b30db372e1a12cf' # aiosecurityspy HEAD, after the follow-up review fixes (story commit 03774b6)
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/../aiosecurityspy/AGENTS.md'
warnings: ['oversized']
---

<intent-contract>

## Intent

**Problem:** An RTSP consumer (go2rtc, ffmpeg, VLC, Frigate) can only play a SecuritySpy camera by holding a URL that carries the account credential (`user:pass@` or `auth=`), and research §7 records exactly such a URL being echoed verbatim by an external tool. Story 2.6 cannot ship live video until the library can hand out a stream address that carries no credential.

**Approach:** Add an asyncio RTSP relay to `aiosecurityspy` that listens locally, maps an unguessable per-camera identifier to a SecuritySpy stream, authenticates upstream with an `Authorization: Basic` header, rewrites every SecuritySpy URL in responses to point back at the relay, and then copies interleaved RTP bytes untouched. Also add `ServerInfo.rtsp_port` and a credential-free `unsecured_stream_url`.

## Boundaries & Constraints

**Always:**
- The upstream credential travels only as an `Authorization: Basic` header built from the client's existing `_ConnectionSettings.auth_header`. No URL, upstream or downstream, ever carries userinfo or `auth=`. Live verification (2026-09-13) confirmed SecuritySpy RTSP accepts the header; see the `_basic_auth` fixture.
- The rewrite rules are derived from the three committed captures in `aiosecurityspy/tests/fixtures/rtsp_handshake_*.log`. Tests replay those exchanges, so AC1 is carried by the fixtures.
- Recognise both `rtsp://host:port/…` and SecuritySpy's malformed single-slash `rtsp:/host:port/…` wherever an upstream URL appears.
- Rewrite `Content-Base`, `Content-Location` and every `url=` in `RTP-Info` to `rtsp://<host the consumer addressed>:<relay port>/<id>` plus the same suffix, e.g. `/trackID=0`. Any upstream URL in an SDP body is rewritten too, with `Content-Length` recomputed.
- Drop `WWW-Authenticate`, `SS-UUID` and `Server` from responses to the consumer. They would prompt for a credential or disclose server identity.
- Map a consumer request for `/<id>` or `/<id>/<suffix>` to `rtsp://{url_host}:{rtsp_port}/stream?cameraNum=N&vcodec=h26x&acodec=src` with `/<suffix>` appended after the query string. That is the form the server accepted in the captures.
- Discard any consumer-supplied `Authorization` header and replace it with the relay's own. Pass every other request header, including `CSeq`, `Session` and `Transport`, through unchanged.
- Frame both directions: `$`-prefixed interleaved packets (`$`, channel, 2-byte length) pass through verbatim, and RTSP messages are delimited by the blank line plus `Content-Length`. RTSP requests after `PLAY`, such as keep-alive `OPTIONS` and `TEARDOWN`, are still rewritten.
- One upstream TCP connection per consumer connection. When either side closes or errors, close the other.
- Log records at every level never contain the password, the base64 credential, the `Authorization` value, a relay identifier, or a requested path. Loggers follow the `_LOGGER = logging.getLogger(__name__)` convention.
- No new runtime dependency (stdlib `asyncio`, `secrets`); `mypy --strict`, `ruff` and `filterwarnings=error` stay clean. Per-connection failures, upstream or consumer, never propagate out of the relay's serving tasks. The one exception allowed out is `OSError` from `async_start()` when the caller's own `bind_host`/`bind_port` cannot be bound. It is documented, and its message never names a stream or credential.

**Block If:**
- A replayed fixture exchange cannot be made to pass without inventing server behaviour the captures don't show.
- Satisfying an AC appears to require putting a credential in any URL or log.

**Never:**
- UDP transport, RTSPS, fan-out (sharing one upstream across consumers), transcoding, or parsing RTP payloads.
- RTSP in `docs/securityspy-openapi.yaml`, which describes HTTP only.
- Changes to the containment test's URL claim to make room for a credential. The relay must pass it unmodified.
- Home Assistant imports, or any change to `SecuritySpyClient`'s session ownership.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Default start | `relay.stream_url(4)` on a relay started with defaults | `rtsp://127.0.0.1:<bound port>/<id>`; ffmpeg's OPTIONS→DESCRIBE→SETUP×N→PLAY→TEARDOWN succeeds against it | None expected |
| Repeated / new relay | `stream_url(4)` twice; a second relay | Same URL twice; a different `<id>` on the second relay | None expected |
| Camera not visible | `stream_url(n)` for `n` not in `server_info.cameras` | No identifier is issued | `SecuritySpyPermissionError` for the live-view permission, message without secrets |
| Unknown identifier | Consumer requests `/<bogus>` | `RTSP/1.0 404 Not Found` echoing `CSeq`, then close; nothing sent upstream | One log record, no path |
| UDP SETUP | `Transport` lacks `RTP/AVP/TCP` or `interleaved=` | `RTSP/1.0 461 Unsupported Transport`, not forwarded upstream | One log record, no path |
| Upstream 401 | Server answers DESCRIBE `401` (denied fixture) | Consumer gets `RTSP/1.0 403 Forbidden` without `WWW-Authenticate` | Warning log, no path or credential |
| Upstream unreachable | Connect to SecuritySpy fails or times out (`connection.timeout`) | Consumer gets `RTSP/1.0 503 Service Unavailable`, then close | Log without address-bearing path or credential |
| Connection loss | Upstream closes mid-PLAY, or consumer disconnects | Other side closed; relay keeps serving new connections | Debug log only |
| Oversized header | RTSP message head over 8 KiB, or malformed request line | Connection closed | Log without content |
| Wildcard bind | `bind_host="0.0.0.0"` with no `advertised_host` | Construction refused | `ValueError` naming the parameter |
| HTTP disabled | `server_info.rtsp_port is None` | Neither URL nor relay can be produced | `ValueError`, "server is not serving RTSP" |

</intent-contract>

## Code Map

The library repo is at `/Users/jensen/projects/aiosecurityspy`, written below as `aiosecurityspy/`. Run commands from that repo's root.

- `aiosecurityspy/src/aiosecurityspy/connection.py` -- `_ConnectionSettings`: `url_host`, `timeout` and `auth_header` (a ready `Basic …` value, ~line 137). This is the relay's only source of the credential.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- `SecuritySpyClient` (ctor ~422, `_connection` ~461, `async_get_server_info` ~566). Home of the relay factory and `unsecured_stream_url`.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- `ServerInfo` (~975) and `from_api` (~1035, `_as_int`/`_as_str` helpers). The server block's `http-enabled` is `"yes"` in the fixture and `true` in live JSON; `http-port` is 8000 on the reference server. Per-camera `port-rtsp` is the camera device's own port and must not be used.
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- `SecuritySpyPermissionError(permission, camera_number)`.
- `aiosecurityspy/src/aiosecurityspy/const.py` -- `PERMISSION_NAMES` (live-view name), `CREDENTIAL_KEYS`.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- explicit import plus the alphabetised `__all__`, which is asserted in `tests/test_package.py`.
- `aiosecurityspy/tests/test_credential_containment.py` -- `assert_url_carries_no_credential` (~476), the caplog double-`at_level` pattern (~444) and the `SENTINELS` constant, all to reuse.
- `aiosecurityspy/tests/fixtures/rtsp_handshake_cam_allowed.log`, `…_denied.log`, `…_allowed_basic_auth.log` -- ffmpeg `-loglevel trace` captures. Requests follow a `Sending:` line; response headers appear as `line='…'`; the SDP follows `SDP:`. Host is `securityspy.local`; credentials and server UUID are redacted.
- `aiosecurityspy/tests/live_env.py` -- `.env` reader for `@pytest.mark.live` tests.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add `ServerInfo.rtsp_port: int | None`, which is `http-port` when `http-enabled` is truthy (`yes`/`true`/`1`) and otherwise `None`. A malformed value decodes to `None`, never fails the whole decode -- RTSP is served on the web server's HTTP port (captures and live `++systemInfo` both show 8000).
- [x] `aiosecurityspy/src/aiosecurityspy/relay.py` (new) -- `RtspRelay`, containing the framing, identifier map, request mapping, response rewriting and refusals described in the contract and matrix. Exposes `async_start()`, `async_stop()`, `async with` support, `stream_url(camera_number) -> str` and a `bound_port` property. Identifiers are `secrets.token_urlsafe(16)`, issued lazily and fixed for the relay's life -- it is the single component that ever holds the credential alongside a stream.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- add `create_rtsp_relay(server_info, *, bind_host="127.0.0.1", bind_port=0, advertised_host=None) -> RtspRelay` and `unsecured_stream_url(server_info, camera_number) -> str`. The second returns `rtsp://{url_host}:{rtsp_port}/stream?cameraNum=N&vcodec=h26x&acodec=src`. Both refuse cameras absent from `server_info.cameras` -- membership comes from the permission-scoped half, following the story-1.18 precedent.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export `RtspRelay`, and update `tests/test_package.py` expectations -- the public surface is asserted.
- [x] `aiosecurityspy/tests/test_relay.py` (new) -- one test per matrix row, all against real sockets: a fake upstream built on `asyncio.start_server` that replays the parsed fixture responses and records what it received, and a raw consumer that replays the fixture's requests re-addressed to the relay. Assert for each exchange: the upstream saw `Authorization` with no credential in any URL; the consumer saw only relay URLs, including under the single-slash `Content-Base` and in `RTP-Info`; `$` frames round-trip byte-identically; and after running every row, no `SENTINELS` value, base64 credential, identifier or path appears in `caplog.text` at DEBUG -- this is the story's executable proof of AC1 and the no-leak claim.
- [x] `aiosecurityspy/tests/test_credential_containment.py` -- add `unsecured_stream_url` and every relay `stream_url` to the URL sweep through the unchanged `assert_url_carries_no_credential` -- the new URL builders must be covered by the existing claim.
- [x] `aiosecurityspy/tests/test_models.py` -- cover `rtsp_port` for enabled, disabled, missing, malformed and live-JSON boolean `true`.
- [x] `aiosecurityspy/tests/test_live_server.py` -- add a `@pytest.mark.live` test that starts a relay and runs `ffprobe -rtsp_transport tcp` against `stream_url`. It skips when the server, credentials or `ffprobe` are unavailable -- the reference-server check for AC "receives that camera's live stream".
- [x] `aiosecurityspy/README.md` and `CHANGELOG.md` (under `## [Unreleased]`, `### Added`) -- document the relay, `unsecured_stream_url` and `rtsp_port`, including that the relay authenticates upstream in cleartext RTSP on the LAN, as SecuritySpy offers no RTSPS -- AD-19 keeps docs in step.

**Acceptance Criteria:**
- Given the three committed handshake captures, when `tests/test_relay.py` runs, then each captured request sequence replays through the relay against a fake upstream answering with the captured responses, and every rewrite rule is exercised by at least one of them.
- Given a relay started with default settings and a reference server, when ffprobe on the same host opens `stream_url(n)` over TCP, then it decodes the stream, and no URL in any response or SDP it received names SecuritySpy's host or carries `auth=`.
- Given a relay started with an explicit, non-loopback `bind_host`, when a consumer connects to its `stream_url` from another address, then it receives the stream through the same path as a local consumer.
- Given every relay scenario in the matrix, when every log record at every level is inspected, then neither the password, its base64 form, a relay identifier, nor a requested path appears in any of them.

## Spec Change Log

## Review Triage Log

### 2026-09-13 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10 (high 1, medium 3, low 6)
- defer: 1 (low 1)
- reject: 9 (medium 2, low 7)
- addressed_findings:
  - `[high]` `[patch]` A relay URL could be extended with a suffix such as `/&cameraNum=5`. The relay appended it to the upstream query string with the account credential attached, so one identifier could address another camera. The request pattern now allows only a track control (`/trackID=N`) or a bare trailing slash; anything else is a 404 and nothing goes upstream. Test: `test_a_suffix_cannot_reach_another_camera_or_path`.
  - `[medium]` `[patch]` Any RTSP method and body was forwarded with the credential. Only OPTIONS, DESCRIBE, SETUP, PLAY, PAUSE, TEARDOWN and GET_PARAMETER are relayed now; any other method gets a local `405` with a `Public` header. Test: `test_an_unrelayed_method_is_405_and_not_forwarded`.
  - `[medium]` `[patch]` Rewritten URLs always used the relay's bound port, which breaks consumers behind a port forward or NAT. They now use the port the consumer addressed. The consumer's authority is also limited to host and port characters before it reaches a header. Test: `test_rewrites_use_the_port_the_consumer_addressed`.
  - `[medium]` `[patch]` A consumer that went quiet, or a request SecuritySpy never answered, held the connection forever. Before PLAY succeeds, each consumer read is bounded by the client's timeout. The bound is lifted when SecuritySpy accepts the relayed PLAY, so keep-alive gaps don't close a live stream. Tests: `test_a_quiet_consumer_is_closed_before_play`, `test_a_playing_stream_is_not_closed_by_the_timeout`.
  - `[low]` `[patch]` `OPTIONS *` was answered with a 404 and a close. It is now answered locally with `200`. Requests that name no stream are capped at `MAX_UNBOUND_REQUESTS`. Test: `test_options_star_is_answered_locally_and_bounded`.
  - `[low]` `[patch]` A buffered request arriving after SecuritySpy closed the upstream could reopen it. A closed upstream is now never reopened. Test: `test_a_closed_upstream_is_never_reopened`.
  - `[low]` `[patch]` With `bind_port=0`, a `bind_host` that resolves to several addresses bound each one to a different port and advertised only the first. `async_start` now refuses with `ValueError`. Test: `test_a_bind_on_several_ports_is_refused`.
  - `[low]` `[patch]` `stream_url` raised `SecuritySpyPermissionError` for a non-integer camera number, while `unsecured_stream_url` raised `ValueError`. Both now raise `ValueError`. Test: `test_stream_url_rejects_a_non_integer_like_unsecured_stream_url`.
  - `[low]` `[patch]` Every upstream 401 was logged as "may lack live-video access", which is misleading after a password change. The warning is now neutral about the cause.
  - `[low]` `[patch]` The live ffprobe test accepted any output ending in "video" and discarded the trace. It now parses `codec_name,codec_type` exactly and asserts ffprobe's trace carries no SecuritySpy host, `auth=` or challenge. A hardening sweep (`test_hardening_scenarios_log_nothing_secret`) also checks the new scenarios log nothing secret.

## Design Notes

**Header, not `auth=`.** AD-13's 2026-09-13 amendment permits `auth=` inside the relay's upstream connection. The relay doesn't use that allowance, because the basic-auth capture shows SecuritySpy RTSP accepting a Basic header. The stricter form keeps the credential out of every URL, including the ones SecuritySpy echoes back in `Content-Base` and `RTP-Info`. If a rewrite were ever missed, it would therefore leak an address, never the password. It also lets the existing containment URL claim stand without a carve-out.

**Why `unsecured_stream_url` takes `server_info`.** The epic writes it as `unsecured_stream_url(camera_number)`. The RTSP port and visible membership only exist in `++systemInfo`, though. The alternatives were caching that response on the client, which gives a stateless client hidden state, or re-reading 27 KB per call. Passing the half the caller already holds follows `async_refresh_camera_status(server_info)` from story 1.18.

**Rewrite example, from the allowed capture.**
```
upstream  Content-Base: rtsp:/securityspy.local:8000/stream?cameraNum=4&vcodec=h26x&acodec=src
consumer  Content-Base: rtsp://127.0.0.1:52011/Xk3…Qa
upstream  RTP-Info: url=rtsp:/securityspy.local:8000/stream?…&acodec=src/trackID=0;seq=0;rtptime=0
consumer  RTP-Info: url=rtsp://127.0.0.1:52011/Xk3…Qa/trackID=0;seq=0;rtptime=0
consumer  SETUP rtsp://127.0.0.1:52011/Xk3…Qa/trackID=0
upstream  SETUP rtsp://securityspy.local:8000/stream?cameraNum=4&vcodec=h26x&acodec=src/trackID=0
```

**Refusal happens at `DESCRIBE`.** `OPTIONS` returns `200` even for a camera the account can't see, so the relay can't learn permission early and must not treat `OPTIONS 200` as proof of access.

## Verification

**Commands:**
- `uv run pytest` -- expected: all pass; live tests skip without configuration.
- `uv run ruff check && uv run ruff format --check` -- expected: clean.
- `uv run mypy --strict src tests` -- expected: clean.

**Manual checks (if no CLI):**
- Using `ha-securityspy/.env` credentials, start a relay on the reference server and run `ffprobe -rtsp_transport tcp <stream_url>`. Expect the stream to decode, and expect no `8000`, host or `auth` in the ffprobe trace.

## Auto Run Result

Status: done

**Summary.** `aiosecurityspy` now has `RtspRelay`, a local asyncio RTSP relay. It gives consumers a credential-free `rtsp://<relay>/<id>` for each visible camera and authenticates to SecuritySpy with an `Authorization: Basic` header only. It rewrites every SecuritySpy URL in responses, including the single-slash `Content-Base` and `RTP-Info`, and copies interleaved RTP untouched. The rewrite rules and tests are derived from three real handshakes captured from the reference server on 2026-09-13. The story also adds `ServerInfo.rtsp_port` (the server's `http-port`) and `SecuritySpyClient.unsecured_stream_url()`. Commit: `aiosecurityspy@03774b6`.

**Files changed**
- `src/aiosecurityspy/relay.py` (new) -- the relay: framing, per-camera identifiers, request mapping, response rewriting, refusals, timeouts.
- `src/aiosecurityspy/client.py` -- `unsecured_stream_url()` and `create_rtsp_relay()`.
- `src/aiosecurityspy/models.py` -- `ServerInfo.rtsp_port`.
- `src/aiosecurityspy/__init__.py`, `tests/test_package.py` -- `RtspRelay` exported.
- `tests/test_relay.py` (new) -- capture parser, fake upstream, and a real-socket test for every matrix row and review fix, plus two log-leak sweeps.
- `tests/test_credential_containment.py` -- new URL builders run through the unchanged URL claim.
- `tests/test_models.py` -- `rtsp_port` decoding.
- `tests/test_live_server.py` -- live ffprobe test through the relay.
- `tests/fixtures/rtsp_handshake_cam_allowed.log`, `…_denied.log`, `…_allowed_basic_auth.log` -- redacted captures (credential, host and server UUID removed; verified absent).
- `README.md`, `CHANGELOG.md` -- relay docs, including the cleartext-upstream warning.

**Review findings:** 10 patches applied (high 1, medium 3, low 6), 1 deferred, 9 rejected; see the Review Triage Log. The high finding was a suffix that let one identifier steer the credential at another camera. It is fixed and tested.

**Follow-up review recommended: yes.** The review pass changed security-relevant request handling (the suffix restriction and the method allowlist) and added new timeout and state logic in the relay. Those changes were not seen by an independent reviewer.

**Verification**
- `uv run pytest -q`: 1064 passed, 15 skipped. The skips are live tests the `.env` isn't configured for.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- `uv run mypy --strict src tests`: clean.
- Live, against the reference server after the review patches: a relay started with defaults served camera 4, and `ffprobe` decoded h264 at 640x480 through it. The ffprobe trace contained no SecuritySpy host, `:8000`, `auth=`, `WWW-Authenticate` or credential, and `Content-Base` pointed at the relay.

**Residual risks**
- AC3 (a consumer on another host) is only exercised by binding `0.0.0.0` and connecting as `localhost`. It has not been tried from a second machine.
- Server-initiated RTSP requests (such as `GET_PARAMETER` or `ANNOUNCE` from SecuritySpy) end the session. None appear in the captures; this was rejected as unobserved.
- The upstream leg is cleartext RTSP on the LAN even when the client uses HTTPS. This is documented; SecuritySpy offers no RTSPS.
- The relay still reads message heads one byte at a time. That is correct but slow, and heads are rare within a session.
- Deferred: the existing client logs the server host at DEBUG on every request (see `deferred-work.md`).

## Follow-up Reviews (2026-09-13)

Two more independent reviews ran at the user's request after the story was marked done. Their fixes are in `aiosecurityspy@96b4264`.

**Second review of `03774b6`.** Every finding below was fixed, and each fix has a test.
- `[high]` Request smuggling: a lone LF or CR inside a header value was forwarded upstream with the credential appended after it. Control characters now close the connection, header names must be tokens, only allowlisted request headers are forwarded, and request bodies never are.
- `[high]` Suffix steering: `/<id>/cameraNum=9` was appended after SecuritySpy's query string. The only suffix allowed now is `/trackID=N`, canonicalised.
- `[medium]` Any response header, including `Location` and `Via`, reached the consumer. Response headers are now allowlisted, URLs are rewritten in all of them, and a 3xx is answered with 502.
- `[medium]` A reused CSeq could forge "playing" and lift the read timeout. CSeq must now be present and strictly increasing; responses pair with pending requests, and a stream plays only after a paired SETUP and PLAY.
- `[medium]` Connections were unbounded. The relay now serves at most `MAX_CONNECTIONS` (503 beyond that), and a connection that never names a stream gets one absolute deadline.
- `[low]` Consumer `$` frames were forwarded before SETUP. Frames now pass only on channels a successful SETUP negotiated.
- `[low]` Writes had no deadline. Drains are now bounded by the client timeout.

**Re-review of those fixes.** Three problems were confirmed and fixed, and one test that could not fail was replaced.
- `[high]` The SETUP check matched substrings, so a UDP transport listed ahead of TCP, even one with `destination=`, reached SecuritySpy. The relay now sends only a transport it rebuilds itself, `RTP/AVP/TCP;unicast;interleaved=a-(a+1)`.
- `[medium]` Repeated headers were forwarded while only the first copy was checked. A repeat of any forwarded header is now a 400, and a repeated `Content-Length` closes the connection.
- `[medium]` A padded CSeq (`01`) never paired with SecuritySpy's unpadded echo, so a legitimate stream would drop between keep-alives. CSeq values are now compared as numbers.
- `[test]` The old second half of the reused-CSeq test could not fail. It is replaced by a real SETUP and PLAY pairing test that also covers padding, plus a test that frames on an unnegotiated channel are refused. The unbound deadline is now also capped at `UNBOUND_SECONDS`.

**Verification after both rounds**
- `uv run pytest -q`: 1077 passed, 15 skipped.
- `ruff check`, `ruff format --check` and `mypy --strict src tests`: clean.
- Live, on the reference server: camera 4 decoded h264 at 640x480 through the relay, with no host, `:8000`, `auth=`, `WWW-Authenticate`, `SS-UUID` or credential in ffprobe's trace, and `Content-Base` pointing at the relay. A 20-second ffmpeg playback through the relay passed with no errors except SecuritySpy's own dts warnings, which also appear on a direct stream without the relay.

**Remaining known limits** (accepted, not fixed)
- A consumer whose socket stays unwritable for a full client timeout while playing is dropped.
- With a non-loopback bind, a LAN peer can occupy the 16 connection slots. There is no per-peer cap.
- The relay reads message heads one byte at a time.
- AC3 (a consumer on another host) has still not been tried from a second machine.
