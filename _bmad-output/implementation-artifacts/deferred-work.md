# Deferred Work

- source_spec: `_bmad-output/implementation-artifacts/spec-1-1-publishable-library-skeleton.md`
  summary: Pin `actions/checkout` and `astral-sh/setup-uv` to commit SHAs in the library's workflows, especially `publish.yml`, which is the only job holding `id-token: write` against the PyPI trusted publisher.
  evidence: Both workflows reference floating tags (`@v4`, `@v5`). A compromised or force-moved tag executes attacker code inside the OIDC-privileged release job and can mint a PyPI-scoped token. Resolving the correct commit SHAs requires network access to GitHub, so it was not done in this unattended run.
