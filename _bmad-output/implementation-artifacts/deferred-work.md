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

### DW-1: Follow-up review still recommended for 1-2-authenticated-client-with-injected-session after the damping cap was spent
origin: review-budget-followup
location: n/a
source_spec: `spec-1-2-authenticated-client-with-injected-session.md`
severity: low
reason: The follow-up-review damping cap (limits.max_followup_reviews = 1) was spent with the story finalized (status: done, verify green) while the review pass still recommended an independent follow-up. The work was committed by bmad-loop run 20260810-075208-b5b3; this entry preserves the lingering recommendation for a deliberate later review.
status: open
