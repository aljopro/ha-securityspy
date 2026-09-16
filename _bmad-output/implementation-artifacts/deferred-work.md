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
status: closed 2026-09-03 by 4ac98c7f (third follow-up review found 2 high-severity defects invisible to the 1,021-test suite; both patched with regression tests; `followup_review_recommended` is now false)

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
status: closed (2026-09-12, T2): aiosecurityspy 0.2.0 published (T1), subtree deleted, `[tool.uv.sources]` dropped, `pyproject.toml` dev dependency and `manifest.json` requirement both pin `aiosecurityspy==0.2.0` exactly, `ci.yml` and `scripts/check_library_pin.py` updated to verify against the published package only. To change the library going forward: edit it in its own repo, release normally, bump the pin here. To test an unreleased change: publish it from the standalone repo as a PyPI pre-release (e.g. `0.2.1a1`) and pin both `pyproject.toml` and `manifest.json` to that exact version temporarily -- pip/uv never resolve a pre-release unless pinned exactly, so it cannot leak to a real install. See AGENTS.md's "Working with `aiosecurityspy`" section.

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
status: closed  # 2026-09-03: independent follow-up review run (R3, bmad-dev-auto) -- see spec-1-7-credential-safe-diagnostics.md's fourth Review Triage Log entry. 5 findings patched, 5 pre-existing out-of-scope findings newly deferred below, 0 rejected. followup_review_recommended now false.

### DW-4: Follow-up review still recommended for 1-8-server-and-camera-health-decoding after the damping cap was spent
origin: review-budget-followup
location: n/a
source_spec: `spec-1-8-server-and-camera-health-decoding.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260828-195436-607b; this entry preserves the lingering recommendation for a deliberate later review.
status: closed  # 2026-09-03: independent follow-up review run (R3, bmad-dev-auto) -- see spec-1-8-server-and-camera-health-decoding.md's fourth Review Triage Log entry. 1 finding patched, 10 pre-existing out-of-scope findings newly deferred below, 3 rejected. followup_review_recommended now false.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-13-timestamps-use-the-servers-own-timezone.md`
  summary: This story ships as a breaking pre-1.0 change (`server_timezone` required on four entry points) with no semver-bump note or CHANGELOG guidance on how it interacts with the first PyPI release the project is about to cut.
  evidence: Blind Hunter review flagged that `pyproject.toml` still shows `0.1.0` and the CHANGELOG only adds `[Unreleased]` entries; three separate CHANGELOG bullets in this story call the change "BREAKING" with no accompanying version-bump or release-process note. Not caused by this story's code, and not blocking merge, but worth a deliberate pass before the first release ships.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-15-capture-size-is-megabytes-and-fractional.md`
  summary: This story ships as a breaking pre-1.0 change (`Capture.file_size` renamed `Capture.file_size_mb`, decoded as fractional megabytes) with no semver-bump note or manifest.json pin update, matching the 1.13 precedent.
  evidence: The spec's Always clause says "the version bump, the changelog and the `manifest.json` pin move together (AD-19)", but `pyproject.toml` still shows `0.1.0` and `custom_components/securityspy/manifest.json` still pins `aiosecurityspy==0.1.0`; bumping now would pin a version that is not yet on PyPI. Review flagged the mismatch; deferred to the first-release pass, exactly as story 1.13's equivalent deferral was handled.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-16-mode-selects-which-capture-modes-a-write-targets.md`
  summary: This story ships as a breaking pre-1.0 change (`async_set_camera_arming` now treats its capture modes as the set a write targets and raises `ValueError` on an all-false set) with no semver-bump note or manifest.json pin update, matching the 1.13 and 1.15 precedent.
  evidence: The spec's Always clause says "the version bump, the changelog and the `manifest.json` pin move together (AD-19)", but `pyproject.toml` still shows `0.1.0` and `custom_components/securityspy/manifest.json` still pins `aiosecurityspy==0.1.0`; bumping now would pin a version that is not yet on PyPI. A consumer relying on the old all-false call was relying on a silent no-op (`200 OK`, nothing applied), so the break is safe for real callers but must be called out deliberately. Deferred to the first-release pass, exactly as stories 1.13 and 1.15's equivalent deferrals were handled.

### DW-5: `++systemInfo` scopes its inventory to PERM_LIVEVIDEO, so a user with non-video rights sees no cameras

origin: live verification against SecuritySpy 6.21, 2026-08-30
location: `aiosecurityspy/src/aiosecurityspy/client.py` (`async_get_server_info`,
`async_get_visible_cameras`), `epics.md` Story 2.7, FR-28, NFR-9
source_spec: `spec-1-18-one-call-for-the-cameras-you-may-see.md`
severity: high
reason: Measured with a per-camera-custom-permissions account across all eleven
  cameras, each granted a different single permission. Only the three cameras
  with "Get live video and images" appeared in `++systemInfo`. Cameras granted
  camera control (PTZ), trigger, set-camera-settings, get-captured-footage,
  delete-captured-footage, set-PTZ-presets or send-live-audio were absent from
  the inventory entirely, despite holding real permissions the API will honour.
  `async_get_visible_cameras()` is documented as answering "which cameras may
  this account see", and story 1.18 treats `++systemInfo` as the only
  permission-scoped inventory surface -- but the scoping predicate is live video
  specifically, not "holds any permission". The consequence lands on FR-28 and
  story 2.7: a least-privileged account of exactly the kind NFR-9 requires us to
  document -- arm/disarm plus capture access, no live video -- yields an
  integration with zero entities, silently. Every visible camera decoded exactly
  against the UI checkboxes, so this is not a decoding fault; the inventory
  endpoint itself is narrower than the permission model. Needs a decision before
  story 2.7 is written: either document live video as a hard prerequisite for
  the integration, or find a second inventory surface (`++camStatus` returns
  every camera to any authenticated account) and reconcile the two.
decision: **Option 1, taken by Jensen on 2026-08-30.** Live video is a hard
  prerequisite: a camera is visible, and therefore manageable, only where the
  configured account holds `PERM_LIVEVIDEO` on it. The library reports the
  server's rule rather than working around it, and `++camStatus` is not widened
  to surface cameras `++systemInfo` withheld. Rationale: it matches SecuritySpy's
  own model, it avoids creating PTZ or arming entities for a camera the user can
  never see a frame from, and the alternative would leave the integration's
  entity set disagreeing with what every other SecuritySpy client shows.
consequences:
  - `async_get_visible_cameras()` states the rule in its docstring, and
    `test_live_inventory_is_scoped_to_live_video` fails if a future server admits
    a camera without live video.
  - NFR-9's least-privileged-user documentation must require live video on every
    camera the integration is expected to manage; an account without it yields no
    entities for that camera, correctly and by design.
  - Story 2.7 (FR-28) may assume every camera it receives holds live video, and
    should gate the remaining entity types on the other bits as planned.
  - Setup should consider telling a user whose account sees zero cameras that
    live-video permission is the likely cause, rather than reporting an empty
    server.
status: resolved-by-decision

### DW-6: permission bit 1 (value 2) is set by the server alongside PERM_FILES and is not user-assignable

origin: live verification against SecuritySpy 6.21, 2026-08-30
location: `aiosecurityspy/src/aiosecurityspy/const.py`,
`_bmad-output/planning-artifacts/research/securityspy-api-reference.md` section 9
severity: low
reason: The per-camera permissions UI exposes exactly ten checkboxes and none of
  them is bit 1. A camera with all ten checked reports 4063, while those ten bits
  sum to 4061 -- the difference is bit 1. Across seven independently observed
  masks (1, 513, 519, 839, 4063, 10207, 12255) bit 1 is set if and only if
  PERM_FILES (4) is set, so the server appears to set it automatically alongside
  "Get captured footage". `securityspy-6.21-verification.md` section 4.1
  currently records it as "set on live cameras and named nowhere", which the
  Driveway camera disproves: live video only, mask 1, bit 1 clear. Decoding is
  unaffected -- unknown bits are ignored by design and the raw mask is retained
  on the model -- so this is a documentation correction, plus the option of
  naming the bit now that its meaning is constrained.
resolution: Documented 2026-08-30 in `securityspy-6.21-verification.md` §5.20.4,
  and §4.1's "set on live cameras" claim is marked superseded in place. The bit
  stays unnamed in `const.py`: its correlation is exact but its meaning is still
  unknown, and naming it would assert more than has been observed. Decoding is
  unaffected either way. Upgraded from correlation to isolation on 2026-08-30:
  Back Patio and Driveway differ by exactly the "Get captured footage" checkbox,
  and their masks are 7 and 1 -- one box flips both bit 2 and bit 1.
status: documented

## Deferred from: code review of spec-1-5-detection-episode-reducer (2026-08-30)

- **A leaked live-server transport makes the suite intermittently fail on an unrelated test.**
  `tests/test_live_server.py` leaves an aiohttp transport unclosed against the real server
  (`ResourceWarning: unclosed transport <_SelectorSocketTransport fd=17>`, socket to
  `…:8001`). Python finalizes it at an arbitrary later moment, and pytest's
  `unraisableexception` plugin raises it as an `ExceptionGroup` during whichever test is
  then in setup — observed landing on `test_models.py::test_class_slug[-unknown]` and
  `[__weird__-weird]`, neither of which touches a socket. Under `pytest-randomly` the
  victim varies, so the failure looks like a different test each time.
  Roughly 1 run in 4 locally. **Confirmed pre-existing:** reproduced with the story-1.5
  review patches stashed, on unmodified `HEAD`. Not caused by the episode reducer, which
  opens no socket. Fix belongs with the live-server fixture — close the client/session in
  teardown — not with this story.

- **PRD Open Q5: the gap default is settled at 30 s; the vehicle threshold is not.**
  Superseding the earlier entry here (which recommended raising the gap to 45-60 s on the
  strength of a 90 s capture): a 3 h capture of 4,469 `CLASSIFY` records found **no natural
  boundary** in the gap distribution — 3,712 inter-signal gaps decay smoothly with no
  valley, and 30 s already covers **97.68 %** of them against 98.71 % for 60 s. Moving the
  default would absorb 38 gaps out of 3,712, an unknown share of which are genuinely
  separate visits. **Keep 30 s**; it is already injectable per camera per object class
  (AD-3, FR-8), so a differing site overrides it. The same capture also *reversed* the
  earlier claim that debounce is inert — over 3 h, debounce 1 → 5 moves 97 episodes to 64
  and removes exactly the marginal 70-73 confidence episodes it exists to remove, so
  `DEFAULT_DETECTION_DEBOUNCE = 3` is now justified.
  **What remains open:** `VEHICLE` confidence peaked at 41 and 44 in two observations
  against a human median of 98, suggesting vehicles need a lower per-class threshold via
  `(None, "vehicle")`. No capture yet contains a vehicle crossing that *should* have opened
  an episode, so this is still two data points. An exterior capture during vehicle traffic
  is the missing input. Evidence:
  `_bmad-output/planning-artifacts/research/classification-tuning-evidence.md` §8.
  **Also open (Epic 5):** none of these values is exposed through the Home Assistant
  options flow yet; story 1.5 deliberately scoped that out.

- source_spec: `spec-1-7-credential-safe-diagnostics.md`
  summary: `client.py`'s plain `_request()` (used by `async_get_server_info`, `async_get_camera_settings`, `async_set_camera_settings`, `async_set_camera_arming`, `async_get_captures`, `async_get_camera_status` — almost every call) awaits `_map_status()` from inside `async with ... as response:`, before releasing the connection, unlike `_request_bytes()`/`_stream_bytes()` which release first; a 401 triggers `_map_status`'s disambiguation probe, a second request on the same session, while the failed response still holds a connection, which can stall on a constrained pool.
  evidence: Blind Hunter review of the diff since story 1.7's baseline (75a1137a..HEAD) found the asymmetry: `_request_bytes`/`_stream_bytes` both carry an explicit comment explaining why release must happen before `_map_status`, and `_request()` never got the same fix.

- source_spec: `spec-1-7-credential-safe-diagnostics.md`
  summary: `stream.py`'s bounded delivery queue (`_offer`, 512-item cap) evicts the oldest queued item under backpressure without distinguishing an ordinary `StreamEvent` from a one-shot lifecycle `_Signal` (`DISCONNECTED`/`AUTH_FAILED`/`CONNECTED`/`RECONNECTED`); since a signal fires exactly once per transition, an evicted signal never fires again and a consumer's view of connection state can desync permanently with no error surfaced. The drop-count logging also always increments `_dropped_events` even when the dropped item was a signal, misreporting what was lost, and `_run`'s `queue.join()` timeout on the auth-pause exit path can silently discard a queued `AUTH_FAILED` signal with no log.
  evidence: Corroborated independently by both reviewers (Blind Hunter and Edge Case Hunter) run in parallel against the same diff, each flagging the eviction/queue-sizing hazard from a different angle (delivery semantics vs. drop-accounting/timeout-drain).

- source_spec: `spec-1-7-credential-safe-diagnostics.md`
  summary: `events.py`'s `_decode_classification` resync-by-one, on hitting a token that fails to parse as a confidence, can misattribute the next pair rather than just dropping the bad one — for `fields = ["HUMAN", "abc", "88"]` it skips `"abc"` as a label attempt, then reads `fields[1]="abc"` as a label and `fields[2]="88"` as its confidence, fabricating `classes["abc"] = 88.0`, a class name paired with a confidence that never described it and that silently feeds `EpisodeReducer`. A related case (Edge Case Hunter): the trailing unpaired field after a resync landing on an odd boundary is dropped with no debug log, unlike the module's other skip paths.
  evidence: Both reviewers independently walked `_decode_classification`'s resync loop against the same diff and traced concrete field sequences producing the misattribution; the resync strategy itself is intentional per the docstring, but this specific fabrication case is not discussed or tested.

- source_spec: `spec-1-7-credential-safe-diagnostics.md`
  summary: `client.py`'s `CaptureFileStream` (added by story 1.9) has no finalizer safety net: if a caller obtains one from `async_get_capture_file` but never enters its `async with`/iterates it (e.g. an exception raised between the call returning and the caller consuming it), the underlying response/connection stays checked out of the aiohttp pool indefinitely, since only iteration or `aclose()` releases it and relying on garbage collection is documented as explicitly not enough.
  evidence: Edge Case Hunter review of the diff since story 1.7's baseline traced the class's own docstring, which already documents the GC risk but not this reference-dropped variant, as a real unhandled path.

- source_spec: `spec-1-7-credential-safe-diagnostics.md`
  summary: `events.py`'s prior `_should_report`/`_REPORTED_UNKNOWN_TYPES` debug-log path for an event type with no decoded payload was removed with no replacement left in `parse_event_line` itself; a consumer calling the public `parse_event_line()` directly (not through `SecuritySpyEventStream`) loses that diagnostic entirely, though it is undocumented that the logging moved to the stream layer only.
  evidence: Edge Case Hunter review flagged the deletion by diffing `events.py`'s history against the current `parse_event_line` call sites; confidence marked low by the reviewer since it is a debug-log regression, not a correctness one.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: (Corroborates DW-3's stream.py finding above, independently re-surfaced against a newer diff.) `stream.py`'s bounded delivery queue (`_offer`) still evicts the oldest queued item under backpressure without distinguishing an ordinary `StreamEvent` from a one-shot lifecycle `_Signal` (`DISCONNECTED`/`AUTH_FAILED`/`CONNECTED`/`RECONNECTED`), so a lifecycle transition can be silently dropped and never re-fire, permanently desyncing a consumer's view of connectivity with no error surfaced. `_run()`'s `queue.join()` timeout safety net covers only the auth-pause/natural-stop exit paths, not the ordinary reconnect-after-drop path where the race actually occurs.
  evidence: Both reviewers (Blind Hunter and Edge Case Hunter) independently flagged this again against the diff since story 1.8's baseline, from different angles (eviction race vs. join-timeout drain path), same as the corroboration recorded against story 1.7's baseline.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: (Corroborates DW-3's `client.py` finding above.) `_request()` (the plain JSON path used by `async_get_server_info`, `async_get_camera_settings`, `async_set_camera_settings`, `async_set_camera_arming`, `async_get_captures`, `async_get_camera_status`) still awaits `_map_status()` from inside `async with ... as response:`, before releasing the connection, unlike `_request_bytes()`/`_stream_bytes()`; a 401 triggers `_map_status`'s disambiguation probe -- a second request on the same session -- while the failed response still holds a connection, risking a stall under a constrained pool.
  evidence: Edge Case Hunter review of the diff since story 1.8's baseline re-found the same asymmetry independently flagged against story 1.7's baseline.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: The 401-disambiguation probe wired into every permission-checked call (`_map_status` calling `_probe_confirms_permission_denial` -> `async_get_server_info`, story 1.11) undercuts `async_get_camera_status()`'s own reason for existing -- the "cheap poll" story 1.8 built specifically to avoid parsing the heavy `++systemInfo` payload on every cycle. An account missing the required permission gets a `401` on every single `++camStatus` poll, and each one now silently doubles into a full `++systemInfo` fetch to disambiguate it, so a permission-denied consumer polling on a tight cycle fetches the expensive endpoint every cycle instead of the cheap one.
  evidence: Blind Hunter review of the diff since story 1.8's baseline traced the interaction between `_map_status` (story 1.11) and `async_get_camera_status` (story 1.8); not a defect in either story's own code in isolation, but a real emergent cost at their intersection.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `_decode_cameras` (story 1.2) now raises `SecuritySpyUnsupportedVersionError` when none of the `cameralist`/`camera-list`/`camera` keys are present at all, rather than returning an empty camera list -- a behavior change for any payload genuinely omitting all three spellings, reported under a misleading "unsupported version" diagnostic for what is actually "no camera-list key located".
  evidence: Blind Hunter review of the diff since story 1.8's baseline traced the hard-fail path in `_decode_cameras` and confirmed, via `git log -S`, that the function predates story 1.8 (introduced in story 1.2).

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `client.py`'s `CaptureFileStream` (story 1.9) guards against sequential re-iteration (`self._iterated`) but not against a caller calling `aclose()` (or exiting `async with`) before ever iterating, then calling `__aiter__` afterward -- `content.read()` runs against an already-released response and raises an unclassified error outside the documented `SecuritySpyConnectError` contract, rather than a clear "stream already closed" `RuntimeError`.
  evidence: Both reviewers independently flagged this against the diff since story 1.8's baseline: Blind Hunter framed it as a released-response read, Edge Case Hunter proposed the specific `if self._released: raise RuntimeError(...)` guard that is missing.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `client.py`'s `_request_bytes` (story 1.9) inner read loop passes `_MAX_BODY_BYTES + 1 - total` as the chunk size to `response.content.read()`; as `total` approaches the 8 MiB cap this shrinks toward reading one byte at a time, a latent performance cliff for any response landing close to (but under) the cap, unlike the fixed `_STREAM_CHUNK_BYTES`-sized reads `CaptureFileStream` uses elsewhere in the same file.
  evidence: Blind Hunter review of the diff since story 1.8's baseline traced the shrinking read-size arithmetic directly in `_request_bytes`.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `Camera.current_fps`/`data_rate`/`last_error` (added by this story) are not liveness-gated the way `can_receive_audio`/`can_send_audio` are (which return `None` when `connected` is `False`) -- a disconnected camera's stale pre-disconnection numbers are surfaced as if live, with nothing in the model telling a consumer they may be stale relative to `connected=False`. Not a violation of this story's own Always clause (which enumerates only omitted/non-numeric/negative as the `None` conditions), so not fixed as part of this review pass -- but a real design-consistency gap worth a deliberate later decision, given the audio-liveness precedent already exists in the same model.
  evidence: Blind Hunter review of the diff since story 1.8's baseline drew the direct comparison to the existing `can_receive_audio`/`can_send_audio` liveness-gating pattern in the same `Camera` dataclass.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `client.py`'s `_stream_bytes` (story 1.9), unlike `_request_bytes`, never calls `_check_declared_length` before opening the stream -- a server declaring an enormous `Content-Length` on a capture-file fetch is not rejected early the way an oversized JSON/preview body is, and no docstring calls out whether this asymmetry is a deliberate scope decision (streamed files are meant to be arbitrarily large) or an oversight.
  evidence: Blind Hunter review of the diff since story 1.8's baseline compared `_stream_bytes` against `_request_bytes`'s explicit `_check_declared_length` call and found no equivalent guard or documented rationale for its absence.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `EpisodeReducer._absorb` (story 1.5) now always runs `self._expire(...)` even for a signal classified as unusable, whereas previously an unusable signal short-circuited before any expiry ran -- a stream of malformed/unusable classifier payloads for a given `(camera, class)` key can now trigger real episode-closure side effects (`EpisodeClosed` events) purely from the *timestamp* of noise data, a subtle expansion of what "unusable" input is allowed to affect.
  evidence: Blind Hunter review of the diff since story 1.8's baseline traced the control-flow change in `_absorb` against what the function did before the behavior changed.

- source_spec: `spec-1-8-server-and-camera-health-decoding.md`
  summary: `client.py`'s `async_get_capture_file` (story 1.9) accepts either a `CAPTURE_FILE_BANDWIDTH_*` int constant or a hand-constructed `CaptureFileBandwidth` record for its `bandwidth` parameter; a caller passing a `CaptureFileBandwidth` with an arbitrary, non-validated `endpoint` string bypasses the constant lookup entirely and that string is used directly as the request path.
  evidence: Edge Case Hunter review of the diff since story 1.8's baseline traced the two branches of the `bandwidth` type check and found the `isinstance(bandwidth, CaptureFileBandwidth)` branch skips the validating `capture_file_bandwidth()` lookup the `int` branch goes through.

- source_spec: `spec-1-10-schedule-names-and-camera-enable-write.md`
  summary: `client.py`'s `async_get_visible_cameras` (story 1.18) issues two sequential, non-atomic requests (`async_get_server_info()` then `async_get_camera_status()`) with no timestamp pairing them to a common instant; a camera's permission/membership can change on the server between the two awaits (e.g. a live-video permission revoked, or a camera added), so the returned `CameraView` tuple can silently pair stale `++systemInfo` membership with a materially later `++camStatus` snapshot, with no way for a caller to detect the skew.
  evidence: Blind Hunter review of the diff since story 1.10's baseline traced the two sequential awaits in `async_get_visible_cameras` and confirmed, via `git log -S`, that the method belongs to story 1.18, not 1.10.

- source_spec: `spec-1-10-schedule-names-and-camera-enable-write.md`
  summary: The 401-disambiguation probe (`_map_status` -> `_probe_confirms_permission_denial` -> `async_get_server_info`, story 1.11) doubles request cost on *every* guarded endpoint when credentials are genuinely rejected -- not only `async_get_camera_status`, the only case named in the existing deferred entry about this mechanism. Captures, capture preview, capture file, settings read/write, and arming all pay the same doubled cost under a 401. Broadens the scope of the previously-deferred `async_get_camera_status`-specific concern to the mechanism as a whole.
  evidence: Blind Hunter review of the diff since story 1.10's baseline traced `_map_status`'s `disambiguate` parameter, which defaults to `True` on every guarded call site except `++systemInfo` itself.

- source_spec: `spec-1-3-event-stream-client-with-cr-framing-and-heartbeat.md`
  summary: Determine experimentally whether SecuritySpy accepts two concurrent `++eventStream?version=3` connections, and record the answer -- accepted, refused, or the first silently displaced. If concurrent streams are supported, a second consumer can tail the stream independently of Home Assistant; if the first connection is displaced instead, any second consumer becomes an availability hazard for the integration and must be documented as unsupported.
  evidence: NFR-21 states the integration must not assume it is SecuritySpy's only client, naming HomeHelper, the iOS app and the web client -- but that is a statement about the server having multiple clients, not about this endpoint accepting multiple simultaneous stream connections, and no research note or live capture covers it. The three outcomes have opposite consequences and silent displacement is indistinguishable from a network drop at the client, so the reconnect-with-backoff path (FR-31) would mask it as a flapping stream rather than surface it. Settling it needs the live server: two concurrent `curl -k -N` reads against `media-server.taila59979.ts.net`, checking whether both receive the 10-second `NULL` heartbeats and whether each connection's event numbers stay contiguous. Read-only, no writes, reversible by closing both connections.

### DW-7: Split the camera device-connection fields out of `CameraSettingsPatch` into their own writable surface

origin: operator suggestion during network-segmentation planning, 2026-09-05
location: `aiosecurityspy/src/aiosecurityspy/models.py` (`CameraSettingsPatch`, `_SETTINGS_*_FIELDS`), `aiosecurityspy/src/aiosecurityspy/client.py` (`async_set_camera_settings`), `aiosecurityspy/docs/securityspy-openapi.yaml`
severity: medium
reason: A pending home-network change moves all 11 cameras onto an IoT VLAN, which requires rewriting each camera's device `address` in SecuritySpy -- a bulk, scripted edit that the library has no way to express today. The obvious fix, adding `address` to `CameraSettingsPatch`, is the wrong shape: that patch is a single flat allowlist covering tuning fields (`motion_sensitivity`, `brightness`, capture triggers), presentation fields (`name`, `overlay_text`) and one service-state field, and `address` is none of those. It is a device-connection field, it sits in the region of the `++settings-cameras` payload that also carries the camera's plaintext `username` and `password` (research §8.3), and writing it wrong silently disconnects a camera from a live security system. Folding it into the existing patch would hand every current call site -- including the Home Assistant integration, which only ever nudges sensitivities -- the ability to disconnect a camera by typo. The proposal is a separate `CameraConnectionPatch` plus `async_set_camera_connection()`, over the same verified transport (`formData` sentinel, `cameraNum` in the body, partial-write semantics, `PERM_SETTINGS`); only the interface splits, so no new wire verification is needed beyond the one field name. There is precedent in the codebase: `enabled` was already given its own method (`async_set_camera_enabled`) rather than left as a bare patch field, for exactly this reason. Three properties follow. Blast radius becomes typed rather than conventional -- a caller holding a `CameraSettingsPatch` cannot express an address change. The credential boundary becomes explicit: `username`/`password` are currently excluded by mere absence from a list, whereas a type whose declared job is "the device-connection fields" makes their omission a documented, deliberate hole, as `aScript`/`aShellCommand` already are. And `CameraSettingsPatch` is untouched, so no consumer migration. Worth noting the read path needs nothing new and should stay that way: `address` is already served by `++systemInfo` (verified live 2026-09-05 -- all 11 cameras return `address`, `port` and `port-rtsp`), which requires no `PERM_SETTINGS` bit and carries no credentials, so a migration tool can read from `++systemInfo`, write via the new method, and verify by re-reading `++systemInfo` and diffing -- never fetching the credential-bearing `GET ++settings-cameras` body at all. Adding a read-side `CameraConnection` model would undo that and should be resisted. Per the change-routing rule this is a library change and `securityspy-openapi.yaml` must be updated in the same commit.
blocked_on: The `++settings-cameras` wire key for the device address is unconfirmed. `++systemInfo` calls it `address`, but the settings page uses different names for some fields and the project's own history (seven defects from wire shapes written off research notes rather than the server) forbids guessing it. The account in `~/projects/ha-securityspy/.env` returns `403` on `GET ++settings-cameras?cameraNum=0&format=json` -- it lacks permission bit 4 (value 16, "Set camera settings"), exactly as the endpoint's `x-quirks` note predicts. Closing this needs a temporary account carrying bit 4, then an enumeration of the 129 keys (names only; the body carries device credentials in plaintext and must not be dumped) to identify the field. The design does not depend on the answer -- only one constant does -- so the split and its tests can be built ahead of it.
status: open

- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-cameras-appear-as-devices-under-one-server-hub.md`
  summary: `SecuritySpyDataUpdateCoordinator.async_start()`'s initial device-registry sync runs outside `_async_reconcile`'s exception handling, so a failure there propagates as a raw, untranslated exception straight out of `async_setup_entry` instead of the module's stated single exception-mapping seam (`ConfigEntryNotReady`/`ConfigEntryError`).
  evidence: Both an adversarial and an edge-case review pass of story 2.3's diff independently flagged this gap. Low practical risk today -- `device_registry.async_get_or_create()` is a local, synchronous, in-memory write with no network call, unlike every failure mode the existing seam actually guards against -- so it was not treated as blocking, but worth a look if this path ever proves reachable (e.g. a future story adding fields to `DeviceInfo` that the registry can reject).

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-see-server-and-camera-health.md`
  summary: A camera added to the SecuritySpy inventory after setup gets a device (via story 2.3's reconciliation) but no sensor entities until the config entry is reloaded -- `sensor.py`'s `async_setup_entry` only builds camera sensors from `coordinator.data.server.cameras` once, at platform setup, with no coordinator listener wiring new cameras into `AddEntitiesCallback` later.
  evidence: Edge Case Hunter review of the diff since story 2.3's baseline traced `async_setup_entry`'s single build-time loop over `server.cameras`; no `coordinator.async_add_listener` callback in `sensor.py` adds entities for a camera number not present at setup. Story 2.4's own acceptance criteria only require the sensors to exist for a camera whose device already exists, not that they appear live -- so this is a real gap against the epic's stated "dynamic-devices ... from the start" intent (story 2.3's own device layer already does this), not a broken AC of this story. Low severity in practice: the coordinator's own 10-minute reconcile timer still creates the device promptly, and a manual reload immediately backfills the missing sensors.
status: open

- source_spec: `_bmad-output/implementation-artifacts/spec-1-19-relay-live-video-without-handing-out-credentials.md`
  summary: `SecuritySpyClient` logs the server's host and port at DEBUG on every request (`Requesting %s from %s:%s`), which story 1.17's identifying-detail policy may not intend.
  evidence: Surfaced during the story 1.19 live relay check on 2026-09-13; the relay itself logs no host, but the pre-existing client request log line did, and it predates this story.

- source_spec: `_bmad-output/implementation-artifacts/spec-2-8-re-enter-credentials-when-they-stop-working.md`
  summary: `coordinator._async_reconcile` guards only `SecuritySpyError` around `async_get_server_info()`, unlike `_async_poll_light_status`, which also catches `Exception`; a non-library error escaping the fetch surfaces as an unhandled timer-task exception rather than the intended logged retry.
  evidence: Blind Hunter review of story 2.8's diff compared the two poll methods' except-clauses; the asymmetry predates story 2.8 (the heavy fetch's handler was untouched apart from auth counting).

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-report-unavailable-rather-than-stale.md`
  summary: A failing heavy `++systemInfo` reconcile is masked by the next successful light `++camStatus` poll, which restores `last_update_success`. Inventory, names and `Camera.connected` can then stay stale while entities show as available.
  evidence: Blind Hunter and Edge Case Hunter both flagged it; the test `test_a_failed_poll_marks_the_update_failed_once_and_success_restores_it` shows a light success restoring availability after a reconcile failure. The server is reachable in that state, so it was triaged out of 3.1's "unreachable" scope. It fits 3.2's reconciliation work.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-1-report-unavailable-rather-than-stale.md`
  summary: Reconcile no longer removes devices, and `async_remove_config_entry_device` allows only parseable current-UUID camera devices. A device with a malformed or foreign-UUID identifier under the entry can therefore never be removed.
  evidence: Both reviewers flagged it. Today such devices can only arise from an out-of-band registry write, because reconfigure aborts on `wrong_server`. The intent contract limits removal to `{uuid}_{n}` devices.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-recover-from-connection-loss-without-being-asked.md`
  summary: A credential valid for the poll endpoints but specifically denied on `++eventStream` gets exactly one `on_auth_failed` call; the library pauses its own reconnection until `resume()`, which nothing in the integration ever calls, so `stream_connected` can stay permanently `False` with no repair issue or distinguishing log line pointing at the cause (poll-plane successes keep resetting the shared AD-18 counter below the reauth threshold).
  evidence: Blind Hunter review of the story 3.2 diff. Push-derived entities do go unavailable (correct per 3.1's availability layer), but nothing in the log or UI explains why the outage never resolves, unlike a genuine network drop, which does recover.

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-recover-from-connection-loss-without-being-asked.md`
  summary: `_async_reconcile`/`_async_poll_light_status` have no guard against two concurrent invocations (e.g. a slow fetch from the periodic timer still in flight when the stream's `on_reconnected` handler calls the same coroutines); the slower response finishing last can publish stale data over fresher data via `async_set_updated_data(replace(self.data, ...))`.
  evidence: Blind Hunter review of the story 3.2 diff. The race predates 3.2 (two overlapping timer ticks could already interleave); this story adds a third caller into the same unguarded window, making it more likely to trigger around the outages this story targets.
