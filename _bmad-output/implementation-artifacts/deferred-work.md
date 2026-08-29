# Deferred Work

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-publishable-library-skeleton.md`
  summary: Pin `actions/checkout` and `astral-sh/setup-uv` to commit SHAs in the library's workflows, especially `publish.yml`, which is the only job holding `id-token: write` against the PyPI trusted publisher.
  evidence: Both workflows reference floating tags (`@v4`, `@v5`). A compromised or force-moved tag executes attacker code inside the OIDC-privileged release job and can mint a PyPI-scoped token. Resolving the correct commit SHAs requires network access to GitHub, so it was not done in this unattended run.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-authenticated-client-with-injected-session.md`
  summary: Confirm the earliest sufficient SecuritySpy 6.x release and narrow `MIN_SERVER_VERSION` in `aiosecurityspy/src/aiosecurityspy/const.py` (PRD Open Q8).
  evidence: The floor is currently the `(6, 0)` assumption the architecture left open. It is enforced as a hard rejection, so a wrong floor either locks out a working server or admits one that cannot serve the endpoints later stories need. Resolving it requires a decision or a live server, neither available to an unattended run.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-authenticated-client-with-injected-session.md`
  summary: Correct the arithmetic in `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §9, where the decomposition of the observed permissions bitmask `10207` is wrong.
  evidence: The prose says `10207` = LIVEVIDEO+FILES+FILEDEL+CAMCONTROL+SCHED+AUDIORCV+TRIGGER+AUDIOSND, which sums to 3805. `10207` actually has bit 8 (PERM_PTZSET, 256) set and bit 11 (PERM_AUDIOSND, 2048) clear. The bit table is right; only the prose is wrong. It is currently recorded in a test docstring, so the next reader of the research doc re-derives the same contradiction.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-authenticated-client-with-injected-session.md`
  summary: Plan the migration off `aiohttp.BasicAuth` and the `auth=` request kwarg, both deprecated in aiohttp 3.12 for removal in 4.0, in favour of `aiohttp.encode_basic_auth()` with an explicit Authorization header.
  evidence: The suite emits a DeprecationWarning on every client construction and every request. The `<4` pin contains the breakage for now, but the warnings are noise today and become a gate failure the moment `filterwarnings = ["error"]` is added. The spec's Always constraint mandates `BasicAuth`, so changing it is a spec-level decision, not a patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-authenticated-client-with-injected-session.md`
  summary: Decide whether a `++systemInfo` payload with no `uuid` is a supported server, and stop defaulting `ServerInfo.uuid` to `""` in `aiosecurityspy/src/aiosecurityspy/models.py`.
  evidence: `ServerInfo.from_api({"server": {"version": "6.0"}})` returns `uuid=""`. The model's own docstring calls `uuid` the stable hub identifier and forbids keying off hostname or IP, so downstream it becomes a Home Assistant `unique_id` — two uuid-less servers would collide into one device. Either it is load-bearing and a missing value must raise, or it is optional and the type should be `str | None`; `""` is the worst of the three. Choosing requires knowing whether a real 6.x server can omit it, which needs a live capture.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-authenticated-client-with-injected-session.md`
  summary: Add real-TLS transport coverage for `verify_ssl` in `aiosecurityspy/tests/`, covering a certificate mismatch under `verify_ssl=True` and the bypass under `verify_ssl=False`.
  evidence: `tests/test_client_transport.py` exists specifically to prove the installed aiohttp honours the kwargs the client passes, and its docstring names `ssl` among them — but every test in it runs over plain HTTP, so `ssl=` is the one kwarg never exercised against TLS. The offline tests only assert the kwarg's value against a stub. Closing this needs a generated self-signed certificate and an HTTPS test server, which is a fixture-infrastructure task rather than a patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-event-stream-client-with-cr-framing-and-heartbeat.md`
  summary: Establish the SecuritySpy server's timezone and stop defaulting `server_timezone` to UTC in `aiosecurityspy/src/aiosecurityspy/stream.py`, `events.py`, `client.event_stream()`, `models.Capture.from_api()` and `client.async_get_captures()`.
  evidence: Event-stream records carry a bare 14-character `YYYYMMDDHHMMSS` wall-clock time (research §3.2) and no endpoint in the research exposes the server's zone, so `parse_event_line()` interprets it as UTC unless the consumer says otherwise. A server running in any other zone therefore reports every event hours off, which is silently wrong rather than visibly broken — episode spans, capture correlation and Home Assistant timestamps all inherit the error. `raw_timestamp` preserves the original string so nothing is lost, but choosing the right default needs either a live server probe or a decision that the consumer must always supply the zone. Story 1.4 extends the same unresolved assumption to capture history: `++caplist` sends a folder date plus seconds since *local* midnight (research §4.1) and no absolute time at all, so `Capture.start` inherits the identical error with no preserved raw field to recover from — a wrong zone silently shifts every "when was a human last seen" answer by the offset. One decision resolves both planes.

### DW-1: Follow-up review still recommended for 1-2-authenticated-client-with-injected-session after the damping cap was spent
origin: review-budget-followup
location: n/a
source_spec: `spec-1-2-authenticated-client-with-injected-session.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260810-075208-b5b3; this entry preserves the lingering recommendation for a deliberate later review.
status: open

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-capture-history-decoding.md`
  summary: Decide whether `caplist.g == 0` means "untagged" and, if so, decode `Capture.tag_id` to `None` instead of `0` in `aiosecurityspy/src/aiosecurityspy/models.py`.
  evidence: Every other optional field on `Capture` collapses absent-or-unusable to `None`, but `g` has two representations of "no tag": absent yields `None` and `0` yields `0`. Research §4.1 calls `g` a user tag ID rendered as `img/tag-N.png`, which makes `0` almost certainly "no tag" — but "almost certainly" is a guess about a wire format, and a consumer branching on `tag_id is None` will get it wrong either way until someone confirms it against a server with and without tags applied.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-capture-history-decoding.md`
  summary: Consider moving `server_timezone` from a per-call argument on both `client.event_stream()` and `client.async_get_captures()` to constructor-level configuration with a per-call override.
  evidence: The stream plane and the poll plane now each take their own default-UTC `server_timezone`, so a consumer must pass the same value at two unrelated call sites or the two planes will disagree about when the same thing happened — which is precisely the correlation AD-1's push/poll reconciliation depends on. This is a public-API shape decision rather than a patch, and it interacts with the still-unresolved question of what the server's zone actually is.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-settings-arming-and-permission-decoding.md`
  summary: Decide whether `async_set_camera_settings` and `async_set_camera_arming` should verify the write acknowledgement instead of treating any 2xx as success.
  evidence: Both writes discard the response body unread, so a SecuritySpy server that answers 200 with an error page — or that silently ignores a write from an account lacking `camera_control`/`schedule` — is indistinguishable from a server that applied it. The acknowledgement shape is partly known (the tests' fakes return `{"camUpdate": {"num": "3"}}`), but whether that envelope is emitted on every version and what a refusal actually looks like has not been read off a real server. On a security product "the camera is disarmed" returning cleanly when nothing changed is the expensive failure, but guessing at the refusal shape would turn successful writes into spurious errors, which is worse. Needs a live server to settle.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-6-settings-arming-and-permission-decoding.md`
  summary: Confirm against a live server whether `++ssSetSchedule` tolerates `override=-1`, or whether the parameter should be omitted when the override is unchanged.
  evidence: `ARM_OVERRIDE_UNCHANGED = -1` is commented in `const.py` as a "client sentinel: leave as-is", and research §5.2 likewise annotates −1 as *(client sentinel)* — yet it is the default for `async_set_camera_arming` and is transmitted as `override=-1` on every arming call that does not name one, i.e. the most common call in the API. If −1 is genuinely a UI-side picker value rather than a wire value, every default arming call depends on undocumented server tolerance of it. The intent contract mandates the three-parameter form (`cameraNum`, `mode`, `override`), so suppressing the parameter is a spec-level change, not a patch.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-add-a-securityspy-server-through-the-ui.md`
  summary: Publish `aiosecurityspy` 0.2.0 to PyPI, or the `requirements: ["aiosecurityspy==0.2.0"]` pin in `custom_components/securityspy/manifest.json` will fail to install for any real HACS user.
  evidence: The integration's tests import the library through `[tool.uv.sources]` as an editable local path, so nothing in the suite or in CI proves the pinned version is installable. A user installing through HACS triggers `pip install aiosecurityspy==0.2.0` at setup, which cannot resolve until the version is released. The library repo has a trusted-publisher release workflow, so this is a release action rather than a code change, and it must happen before the first integration release.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-add-a-securityspy-server-through-the-ui.md`
  summary: Add repository-root CI workflows for the integration — pytest with the config-flow coverage gate, ruff, mypy, hassfest and the HACS Action — mirroring what already exists under `aiosecurityspy/.github/workflows/`.
  evidence: Only the library has CI. The integration's Bronze-mandated 100% config-flow coverage, its lint and type gates, and the hassfest/HACS manifest validation currently run only when someone invokes them by hand, so a regression reaches `main` unchallenged. AD-14 names these checks as the integration repo's CI contract and Epic 7's release gating depends on them, but no story in Epic 2 owns creating them.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-add-a-securityspy-server-through-the-ui.md`
  summary: Decide whether `_abort_if_unique_id_configured()` in `custom_components/securityspy/config_flow.py` should pass `updates={CONF_HOST: ..., CONF_PORT: ...}` so re-adding a moved server refreshes its stored address.
  evidence: The abort currently discards the newly-entered address. If the NVR's DHCP lease changes, the user's natural repair — re-adding it at the new address — aborts as already configured while the entry keeps the dead host and stays in SETUP_RETRY. Story 2.9 ("change connection details without losing history") owns address changes and will add a reconfigure step, so the fix belongs there rather than here; but if 2.9 lands only a reconfigure flow, this re-add path stays a dead end and should be closed deliberately rather than by omission.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-add-a-securityspy-server-through-the-ui.md`
  summary: Add a repository-root `README.md`; `hacs.json` sets `"render_readme": true` but no README exists.
  evidence: HACS renders the repository README as the integration's description page, and `hacs.json` opts into that. With no README in the repo root, a user browsing HACS gets an empty description for a security-camera integration they are about to grant credentials to. The HACS Action validation also expects one. No Epic 2 story owns repo-level documentation, and Epic 7 handles release packaging.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-connect-over-https-with-a-verification-toggle.md`
  summary: Make `aiosecurityspy`'s event-stream reader treat `SecuritySpyCertificateError` as non-retryable (or surface it) instead of folding it into indefinite backoff, when Epic 3 wires the stream into the coordinator.
  evidence: `aiosecurityspy/src/aiosecurityspy/stream.py:330` catches `Exception` from the reader and converts everything into a backoff-and-reconnect cycle, by design for transient faults. A certificate that expires or is replaced while an entry is loaded is not transient: setup already succeeded, so nothing re-runs the setup-time mapping, and the stream would retry forever with no log line, entity state or repair issue naming the certificate. Story 2.2 gives the failure a distinct type; only Epic 3 owns what the reader does with it.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-connect-over-https-with-a-verification-toggle.md`
  summary: Log the underlying `aiosecurityspy` exception when `async_setup_entry` converts a library failure into `ConfigEntryNotReady`/`ConfigEntryError`, so the diagnostic detail the library produces reaches the Home Assistant log.
  evidence: `_tls_reason()` in `aiosecurityspy/src/aiosecurityspy/client.py` works to extract the one discriminating fact about a TLS failure — `CERTIFICATE_HAS_EXPIRED` vs `CERTIFICATE_VERIFY_FAILED` vs `WRONG_VERSION_NUMBER` — and embeds it in the exception message. `custom_components/securityspy/__init__.py` then raises `ConfigEntryNotReady(translation_domain=..., translation_key=...)` with no `message` and never logs `err`, so Home Assistant's "not ready yet: %s" line renders the empty translated form and the OpenSSL reason reaches no log at all. The same holds for the `cannot_connect` and `invalid_auth` clauses, so this is a pattern across the whole setup path rather than anything story 2.2 introduced, and choosing between a `_LOGGER.debug(..., exc_info=err)` and populating the exception's `message` is a convention decision that should be made once for every clause.

### DW-2: Delete the `aiosecurityspy/` subtree from ha-securityspy and consume the published library instead

origin: operator request during the library repo split, 2026-08-16
location: `aiosecurityspy/` (whole subtree), `pyproject.toml` `[tool.uv.sources]`, `custom_components/securityspy/manifest.json`
severity: medium
reason: The library now exists twice — as this subtree, where bmad-loop develops it, and as the standalone public repo `aljopro/aiosecurityspy` pushed on 2026-08-16. Nothing enforces that the standalone repo only ever receives `git subtree split` merges, so the two can silently diverge and a direct edit to either side would have to be reconciled by hand. AD-14 mandates two separate repositories with the integration depending on the library as an ordinary pinned version, which removes the duplication entirely. Blocked on the release: `manifest.json` already pins `aiosecurityspy==0.2.0` and `[tool.uv.sources]` still resolves it to the local editable path, so deleting the subtree before that version is on PyPI would break both the test suite and integration setup. Sequence is publish first (see the spec-2-1 entry covering the 0.2.0 release), then drop `[tool.uv.sources]`, then delete the subtree.
status: open

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-connect-over-https-with-a-verification-toggle.md`
  summary: Surface TLS and certificate failures raised by the long-lived event stream, which today inherits story 2.2's TLS flags but none of its new diagnosis.
  evidence: `async_setup_entry` now maps `SecuritySpyCertificateError` to a certificate-specific, user-visible failure, but that mapping only covers the one-shot setup call. `_run()` in `aiosecurityspy/src/aiosecurityspy/stream.py` catches every exception into `_LOGGER.debug("... %s", type(err).__name__)` and backs off, so a certificate that expires while Home Assistant is already running produces an indefinite silent reconnect loop with no warning and no user-visible signal — the case the new exception type exists to name. Story 2.2's intent contract forbids changing `stream.py`'s reconnect policy, and there is no consumer of the stream's failures until Epic 3, so this belongs to whichever Epic 3 story owns stream health reporting.

- source_spec: `_bmad-output/implementation-artifacts/spec-1-7-credential-safe-diagnostics.md`
  summary: `test_settings_payload_is_never_logged_at_any_level` in `aiosecurityspy/tests/test_settings.py` can pass vacuously — its `caplog.at_level(0, logger="aiosecurityspy")` captures nothing, so the "no credential in the log" search runs over an empty string.
  evidence: level `0` is `logging.NOTSET`, i.e. "inherit", and the root logger that caplog attaches its handler to sits at `WARNING`, so every library `DEBUG` line is dropped before the handler sees it. The test would stay green if the library started logging the settings payload in full. Story 1.7's new `test_credential_containment.py` works around this for its own sweep by nesting the call inside `caplog.at_level(logging.DEBUG)` and asserting a minimum `DEBUG` record count, but the pre-existing story-1.6 test was outside this story's scope to modify and still has the hole.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-7-credential-safe-diagnostics.md`
  summary: `aiohttp.BasicAuth` and the `auth=` request kwarg are both deprecated and slated for removal in aiohttp 4.0, and they are the library's sole credential transport.
  evidence: The suite emits 268 DeprecationWarnings, e.g. `stream.py:377` — "The 'auth' parameter is deprecated and will be removed in v4; pass headers={'Authorization': aiohttp.encode_basic_auth(login, password)} instead". Pre-existing, not caused by story 1.7, but it invalidates the "credentials travel as `auth=`, never in a URL" design once aiohttp 4 lands; migrating to an `Authorization` header preserves that property and needs its own story.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-7-credential-safe-diagnostics.md`
  summary: A redirect followed by aiohttp carries the `auth=` credential to whatever host the redirect names, and nothing asserts that it does not reach a third-party one.
  evidence: `test_credential_containment.py`'s URL sweep inspects the URLs the library itself hands to the session, which is all it can inspect through a stub. aiohttp's own redirect handling re-sends `auth=` on a cross-host redirect, and a SecuritySpy instance behind a misconfigured reverse proxy is the shape that produces one — precisely the research §7 leak, arriving by a path this story's assertions do not cover. Pre-existing: the `auth=` transport predates story 1.7. Fixing it means either disabling redirects on the library's requests or dropping auth across an origin change, both of which change request behaviour and belong in their own story.

### DW-3: Follow-up review still recommended for 1-7-credential-safe-diagnostics after the damping cap was spent
origin: review-budget-followup
location: n/a
source_spec: `spec-1-7-credential-safe-diagnostics.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260817-080028-f442; this entry preserves the lingering recommendation for a deliberate later review.
status: open

### DW-4: Follow-up review still recommended for 1-8-server-and-camera-health-decoding after the damping cap was spent
origin: review-budget-followup
location: n/a
source_spec: `spec-1-8-server-and-camera-health-decoding.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260828-195436-607b; this entry preserves the lingering recommendation for a deliberate later review.
status: open
- source_spec: `_bmad-output/implementation-artifacts/spec-1-13-timestamps-use-the-servers-own-timezone.md`
  summary: This story ships as a breaking pre-1.0 change (`server_timezone` required on four entry points) with no semver-bump note or CHANGELOG guidance on how it interacts with the first PyPI release the project is about to cut.
  evidence: Blind Hunter review flagged that `pyproject.toml` still shows `0.1.0` and the CHANGELOG only adds `[Unreleased]` entries; three separate CHANGELOG bullets in this story call the change "BREAKING" with no accompanying version-bump or release-process note. Not caused by this story's code, and not blocking merge, but worth a deliberate pass before the first release ships.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-15-capture-size-is-megabytes-and-fractional.md`
  summary: This story ships as a breaking pre-1.0 change (`Capture.file_size` renamed `Capture.file_size_mb`, decoded as fractional megabytes) with no semver-bump note or manifest.json pin update, matching the 1.13 precedent.
  evidence: The spec's Always clause says "the version bump, the changelog and the `manifest.json` pin move together (AD-19)", but `pyproject.toml` still shows `0.1.0` and `custom_components/securityspy/manifest.json` still pins `aiosecurityspy==0.1.0`; bumping now would pin a version that is not yet on PyPI. Review flagged the mismatch; deferred to the first-release pass, exactly as story 1.13's equivalent deferral was handled.
