---
title: 'Story 1.1: Publishable library skeleton'
type: 'chore'
created: '2026-08-10'
status: 'awaiting-operator'
baseline_revision: '107985aafc1fa47f1332530d910a2d95e3f1f258'
final_revision: '4c3787c29357b86d7974be505dbeb366e65e1007'
review_loop_iteration: 1
followup_review_recommended: false
operator_actions:
  - 'Create the public GitHub repository aljopro/aiosecurityspy (MIT, no starter template, default branch main).'
  - 'Move the aiosecurityspy/ subtree of ha-securityspy into that new repository as its root, push it to main, and confirm GitHub Actions runs the CI workflow green.'
  - 'Register a PyPI trusted publisher for the project name aiosecurityspy at https://pypi.org/manage/account/publishing/ with owner aljopro, repository aiosecurityspy, workflow publish.yml, and environment pypi.'
  - 'Create the GitHub Actions environment named pypi in the aiosecurityspy repository so the publish job can attach to it.'
  - 'Tag v0.1.0 and publish a GitHub Release from it, then confirm the publish workflow uploaded aiosecurityspy 0.1.0 to PyPI via OIDC with no stored token.'
  - 'Confirm the GitHub owner is aljopro; if not, correct the project URLs in aiosecurityspy/pyproject.toml and the links in aiosecurityspy/CHANGELOG.md before tagging.'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/hacs-packaging-and-blueprints.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** No `aiosecurityspy` package exists, so every later Epic 1 story has nowhere to land and the integration cannot pin it as an ordinary versioned dependency (Bronze `dependency-transparency`).

**Approach:** Hand-build the greenfield library scaffold — `src/` layout, hatchling, `pyproject.toml` only, `requires-python >=3.14`, `py.typed`, ruff and `mypy --strict` gates, pytest, and GitHub Actions for CI plus trusted-publisher OIDC release — as an empty-but-typed package that already passes every gate on the first commit.

## Boundaries & Constraints

**Always:**
- `src/` layout, hatchling build backend, configuration in `pyproject.toml` only (no `setup.py`, `setup.cfg`, `mypy.ini`, `ruff.toml`, or `tox.ini`).
- `requires-python = ">=3.14"`; the package is OSI-licensed (MIT) with the license declared in metadata and a `LICENSE` file present.
- `src/aiosecurityspy/py.typed` exists and is included in the wheel.
- Zero Home Assistant imports and no Home Assistant test tooling anywhere in the library tree.
- `aiohttp` is declared as a runtime dependency; the library never creates an HTTP session (nothing in this story creates one either).
- Version is single-sourced so the published version can equal the git tag exactly; the release workflow verifies tag == metadata version and fails otherwise.
- Publish uses PyPI trusted-publisher OIDC (`permissions: id-token: write`); no API token, secret, or credential is stored in the repository.

**Block If:**
- The architecture's declared stack (hatchling / uv / ruff / mypy / `src/` layout / Python 3.14) cannot be satisfied and a substitute build or tooling choice would be required.

**Never:**
- Do not implement any protocol behavior — no client, stream, models, decoding, reducer, or anonymizer (stories 1.2–1.7 own those).
- Do not create or modify a second git repository, and do not touch `sprint-status.yaml`.
- Do not add integration (`custom_components/`) files, HACS packaging, or blueprints.
- Do not vendor dependencies or commit a compiled/exported lockfile of transitive HA packages.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Import in a bare env | `aiosecurityspy` installed, no Home Assistant present | `import aiosecurityspy` succeeds and `aiosecurityspy.__version__` is a non-empty PEP 440 string | No error expected |
| Version single-sourcing | Package metadata read at runtime | `__version__` equals the installed distribution version | No error expected |
| Release tag mismatch | Tag `v0.1.1` published while `pyproject.toml` declares `0.1.0` | Publish job fails before upload | Workflow exits non-zero with a message naming both versions |
| Typed consumer | Consumer runs `mypy --strict` against code importing the package | Type information is found via `py.typed` | No error expected |

</intent-contract>

## Code Map

No code exists yet. This story creates the tree; the paths below are the deliverable.

- `aiosecurityspy/` -- new library tree at the workspace root, mirroring the architecture's Structural Seed (`aiosecurityspy/` beside the integration). It is destined to become its own public repository; that split is an operator action.
- `_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md` -- binding stack and repo decisions (AD-14, Structural Seed).
- `docs/hacs-packaging-and-blueprints.md` -- the reference publish workflow shape and trusted-publishing mechanics.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/pyproject.toml` -- create: hatchling backend, `[project]` metadata (name `aiosecurityspy`, dynamic or static version, description, MIT license + `license-files`, authors, `requires-python = ">=3.14"`, classifiers, project URLs), `dependencies = ["aiohttp>=3.10"]`, `[dependency-groups] dev` with ruff/mypy/pytest/pytest-asyncio, hatch wheel packages pointing at `src/aiosecurityspy`, and `[tool.ruff]`/`[tool.mypy]`/`[tool.pytest.ini_options]` sections -- single configuration file is an Always constraint.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- create: package docstring, `__version__` resolved from installed metadata, `__all__` -- gives the empty-but-typed package a real public surface and satisfies the bare-venv import criterion.
- [x] `aiosecurityspy/src/aiosecurityspy/py.typed` -- create empty marker -- ships type information to consumers.
- [x] `aiosecurityspy/LICENSE` -- create MIT license text, copyright Jensen Chappell -- OSI license required in metadata and on disk.
- [x] `aiosecurityspy/README.md` -- create: what the library is, install line, the no-Home-Assistant promise, injected-session note, status/scope -- becomes the PyPI long description.
- [x] `aiosecurityspy/tests/test_package.py` -- create: cover the I/O matrix rows that are testable in-process (import succeeds, `__version__` non-empty and PEP 440, version matches installed distribution metadata) -- proves the skeleton before any protocol code exists.
- [x] `aiosecurityspy/.github/workflows/ci.yml` -- create: on push/PR, uv-based job running `uv sync`, `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` -- the gates must be enforced by CI, not just locally.
- [x] `aiosecurityspy/.github/workflows/publish.yml` -- create: on `release: published`, `environment: pypi`, `permissions: id-token: write`, steps checkout → setup-uv → verify tag equals project version → `uv build` → `uv publish` -- trusted-publisher OIDC release with no stored token.
- [x] `aiosecurityspy/.gitignore` -- create: Python/uv/build/test artifacts (`.venv/`, `dist/`, `__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`) -- keeps build output out of version control.
- [x] `aiosecurityspy/CHANGELOG.md` -- create with an `Unreleased`/`0.1.0` entry -- AD-14 requires a changelog alongside semver tags.

**Acceptance Criteria:**
- Given a clean checkout of the library tree, when `uv sync` then `uv run pytest` are run, then the project resolves and builds with hatchling from the `src/` layout using only `pyproject.toml`, and the test suite passes.
- Given the same checkout, when `uv run ruff check .` and `uv run mypy --strict src tests` are run, then both report zero findings.
- Given `uv build`, when the produced wheel is inspected, then it contains `aiosecurityspy/py.typed`, and the metadata declares the MIT license and `Requires-Python: >=3.14`.
- Given the built wheel installed into a fresh virtual environment with no Home Assistant present, when `python -c "import aiosecurityspy"` runs, then it exits 0.
- Given a GitHub release published from tag `vX.Y.Z`, when the publish workflow runs, then it authenticates to PyPI via trusted-publisher OIDC with no repository-stored token, and it fails before upload unless `X.Y.Z` equals the version in `pyproject.toml`.

## Spec Change Log

None. No bad_spec loopback occurred.

## Review Triage Log

### 2026-08-10 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 10: (high 1, medium 4, low 5)
- defer: 1: (high 0, medium 1, low 0)
- reject: 7: (high 0, medium 1, low 6)
- addressed_findings:
  - `[high]` `[patch]` `publish.yml` published to PyPI without running any gate — a release cut from a red commit would ship immutably. Added `uv sync --locked`, ruff check, ruff format check, `mypy --strict`, and pytest ahead of `uv build`/`uv publish`.
  - `[medium]` `[patch]` CI ran `uv sync`, silently re-resolving and never validating the committed `uv.lock`. Changed to `uv sync --locked` in both workflows.
  - `[medium]` `[patch]` The headline acceptance criterion (installs and imports in a bare venv with no Home Assistant) was verified manually only. Added CI steps that install the built wheel into a clean 3.14 venv, assert `homeassistant` has no importable spec, and print `__version__`.
  - `[medium]` `[patch]` The wheel's `py.typed` was never checked by CI. Added a step asserting `aiosecurityspy/py.typed` is present in the built wheel.
  - `[medium]` `[patch]` `test_no_home_assistant_dependency` asserted only `"homeassistant" not in sys.modules`, which passes even when Home Assistant is installed. Rewritten as `importlib.util.find_spec("homeassistant") is None`.
  - `[low]` `[patch]` `requires = ["hatchling"]` was unpinned while the metadata uses PEP 639 `license`/`license-files`. Pinned to `hatchling>=1.27`.
  - `[low]` `[patch]` The publish gate compared `${GITHUB_REF_NAME#v}` without checking the ref is a release tag. Added a `vX.Y.Z` shape check that fails before the version comparison.
  - `[low]` `[patch]` `uv publish` could silently fall back to no credentials and failed hard on a re-run after a partial upload. Added `--trusted-publishing always --check-url https://pypi.org/simple/aiosecurityspy/` (both flags verified against the installed uv).
  - `[low]` `[patch]` The PEP 440 test regex rejected local-version segments, so an editable or CI-built install would fail spuriously. Extended the pattern with the optional `+local` segment.
  - `[low]` `[patch]` `pytest-asyncio` emitted an unset-default-loop-scope deprecation. Set `asyncio_default_fixture_loop_scope = "function"`.

## Design Notes

The architecture mandates two separate public repositories (AD-14). This unattended run is confined to the checked-out `ha-securityspy` working tree, so the library is created here as the self-contained subtree `aiosecurityspy/` matching the architecture's Structural Seed. Every file inside it is repository-root-relative for that tree (`.github/`, `LICENSE`, `pyproject.toml` at `aiosecurityspy/`), so promoting it to its own repository later is a move, not a rewrite. Creating the GitHub repository, pushing, and configuring the PyPI trusted publisher are external actions only a human can perform and are recorded as operator actions.

Version single-sourcing: declare the version once in `pyproject.toml` and resolve `__version__` at runtime from installed metadata (`importlib.metadata.version`), with a fallback for an uninstalled source tree. The publish workflow compares `${GITHUB_REF_NAME#v}` against the metadata version and exits non-zero on mismatch.

## Verification

**Commands:**
- `cd aiosecurityspy && uv sync` -- expected: environment resolves on Python 3.14, exit 0
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: zero errors
- `cd aiosecurityspy && uv run pytest -q` -- expected: all tests pass
- `cd aiosecurityspy && uv build` -- expected: sdist + wheel in `dist/`; wheel contains `aiosecurityspy/py.typed`
- Bare-venv check: install the built wheel into a throwaway venv and run `python -c "import aiosecurityspy, sys; print(aiosecurityspy.__version__)"` -- expected: exit 0, prints a version, no Home Assistant installed

**Manual checks (if no CLI):**
- `publish.yml` declares `permissions: id-token: write`, `environment: pypi`, and contains no `secrets.` reference for PyPI credentials.

## Auto Run Result

Status: `awaiting-operator`

**Summary.** Created the greenfield `aiosecurityspy/` library subtree: an empty-but-typed package on a `src/` layout with a hatchling backend, all configuration in `pyproject.toml`, `requires-python >=3.14`, a `py.typed` marker that ships in the wheel, MIT licensing declared in metadata, ruff and `mypy --strict` gates, a pytest suite, and GitHub Actions for CI and a PyPI trusted-publisher (OIDC) release. No protocol code was written — stories 1.2–1.7 own that.

**Files changed** (all new):
- `aiosecurityspy/pyproject.toml` — hatchling build, project metadata, aiohttp dependency, dev group, and the sole ruff/mypy/pytest configuration.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` — package docstring and `__version__` resolved from installed metadata.
- `aiosecurityspy/src/aiosecurityspy/py.typed` — typing marker.
- `aiosecurityspy/tests/test_package.py` — import, PEP 440 version, version-matches-metadata, public surface, and no-Home-Assistant tests.
- `aiosecurityspy/.github/workflows/ci.yml` — lockfile-locked sync, lint, format check, strict type check, tests, build, wheel `py.typed` check, and a bare-venv install-and-import check.
- `aiosecurityspy/.github/workflows/publish.yml` — release-triggered, tag-shape and tag-vs-version gates, full test gate, then OIDC build and publish.
- `aiosecurityspy/LICENSE`, `README.md`, `CHANGELOG.md`, `.gitignore`, `uv.lock` — licensing, docs, and reproducible resolution.
- `_bmad-output/implementation-artifacts/epic-1-context.md` — compiled Epic 1 context.
- `_bmad-output/implementation-artifacts/deferred-work.md` — one deferred item.

**Review findings:** 10 patches applied, 1 item deferred (pin GitHub Actions to commit SHAs — needs network access to resolve them), 7 rejected as noise or as configuration that is correct for the next story.

**Verification performed** (all re-run by the workflow itself, not taken on the implementation agent's word):
- `uv sync --locked` — resolves on CPython 3.14.4, lockfile consistent with `pyproject.toml`.
- `uv run ruff check .` — All checks passed. `uv run ruff format --check .` — 4 files already formatted.
- `uv run mypy --strict src tests` — Success: no issues found in 2 source files.
- `uv run pytest -q` — 5 passed.
- `uv build` — sdist + wheel; `unzip -l` confirms `aiosecurityspy/py.typed`; METADATA declares `License-Expression: MIT`, `License-File: LICENSE`, `Requires-Python: >=3.14`, `Requires-Dist: aiohttp>=3.10`.
- Bare-venv check in a throwaway 3.14 venv outside the repo: `import aiosecurityspy` printed `0.1.0`, exit 0, `find_spec("homeassistant")` was `None`.
- Both workflow files parse as YAML, and the CI heredoc renders as an unindented Python script.
- `uv publish --trusted-publishing` and `--check-url` confirmed present on the installed uv; `uv version --short` confirmed to print exactly `0.1.0`.

**Residual risks.**
- The release half of this story is unverifiable from here: no GitHub repository, no PyPI trusted publisher, and no `pypi` environment exist yet, so the publish workflow has never run. It is reviewed but unexecuted code.
- The architecture mandates two separate repositories (AD-14). The library was created as a self-contained subtree inside the `ha-securityspy` working tree because this unattended run is confined to that checkout. Promoting it is a directory move, but until an operator does it the two-repository decision is only structurally anticipated, not realized.
- GitHub Actions are referenced by floating tags in the OIDC-privileged publish job (deferred).
- The GitHub owner `aljopro` was inferred from the git author email and a sibling `aljopro.github.io` checkout, not confirmed; it appears in project URLs and changelog links.
