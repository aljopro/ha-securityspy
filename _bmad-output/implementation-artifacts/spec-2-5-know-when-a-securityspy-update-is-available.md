---
title: 'Story 2.5 — Know when a SecuritySpy update is available'
type: 'feature'
created: '2026-09-12'
status: 'done'
baseline_revision: 'e4500999b3e44f56d0eb69903c8681d14c7f3966'
final_revision: '73d5c6324317c108a94393de2f6397c5304e02f7'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/docs/ha-integration-reference.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
warnings: []
---

<intent-contract>

## Intent

**Problem:** `PLATFORMS` has no `Platform.UPDATE`, so a user with a SecuritySpy update sitting on the server has no way to learn about it from Home Assistant — they'd only find out by opening SecuritySpy directly.

**Approach:** Add a single read-only `update` entity on the hub device, reusing the existing `SecuritySpyHubEntity` base class (story 2.4), reporting `installed_version` from `ServerInfo.version` and `latest_version` from `ServerInfo.update_version` (falling back to `version` when no update is offered, so the entity reads "up to date" rather than "unknown"). No install action: leaving `supported_features` at its class default of zero already satisfies that.

## Boundaries & Constraints

**Always:**
- One `UpdateEntity` subclass, `SecuritySpyUpdateEntity(SecuritySpyHubEntity, UpdateEntity)`, attached to the hub device via the existing `SecuritySpyHubEntity.__init__(coordinator, key)` pattern (unique ID `f"{server.uuid}_{key}"`, `device_info` from `hub_device_info`).
- `installed_version` returns `coordinator.data.server.version` (always present, non-optional per the library).
- `latest_version` returns `coordinator.data.server.update_version or coordinator.data.server.version` — when no update is offered (`update_version is None`), reporting the installed version as "latest" makes the base class's own `state` computation read `STATE_OFF` (up to date) rather than `unknown`. This is a deliberate HA-side normalization of the library's `None`-means-no-update convention, not a change to the library's semantics.
- Leave `supported_features` unset (class default `UpdateEntityFeature(0)`) and `entity_category` unset — the base class already falls back to `EntityCategory.DIAGNOSTIC` for any update entity without `UpdateEntityFeature.INSTALL`, matching this entity's diagnostic-only nature without hardcoding it.
- `device_class=UpdateDeviceClass.FIRMWARE` (the enum's only member) — consistent with how other integrations report a server/software version update, and gives the entity the standard update-card presentation.
- `translation_key="update"` (single entity, no per-field tuple needed — this platform has exactly one entity, unlike `sensor.py`'s multi-descriptor pattern).
- `PLATFORMS` gains `Platform.UPDATE`; `update.py` sets `PARALLEL_UPDATES = 0` (read-only, coordinator-fed, same as `sensor.py`).
- Extend `tests/conftest.py`'s `make_server_info()`/`make_server_info_with_cameras()` with an `update_version: str | None = None` kwarg, threaded into the `ServerInfo(...)` call (currently missing entirely).

**Block If:**
- Nothing found requiring human input — `ServerInfo.version`/`update_version` already exist in the pinned `aiosecurityspy==0.2.0`; no library change needed.

**Never:**
- No `async_install` override, no `UpdateEntityFeature.INSTALL` (or any other feature flag) — installing is explicitly out of scope for v1 per the story's own AC.
- No polling beyond what the coordinator already does — the entity reads `coordinator.data.server`, already kept current by story 2.4's heavy `RECONCILE_INTERVAL` poll (the only endpoint that reports `new-version`); no new poll cadence.
- No per-camera update entity — this is a single, hub-only entity.
- No change to `sensor.py`, `coordinator.py`, or `entity.py`'s existing classes — `SecuritySpyHubEntity` is reused as-is, not modified.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| Update available | `server.version="6.20"`, `server.update_version="6.21"` | `installed_version="6.20"`, `latest_version="6.21"`, HA computes `state=on` | No error expected |
| No update available | `server.version="6.20"`, `server.update_version=None` | `installed_version="6.20"`, `latest_version="6.20"`, HA computes `state=off` | No error expected |
| Install attempted from HA | Any state | No install control is offered in the UI/service call (no `UpdateEntityFeature.INSTALL`) | Calling `update.install` on this entity raises HA's own "not supported" error; no code path in this entity handles installation |

</intent-contract>

## Code Map

- `custom_components/securityspy/update.py` — **new file.** `SecuritySpyUpdateEntity(SecuritySpyHubEntity, UpdateEntity)` (`device_class=UpdateDeviceClass.FIRMWARE`, `translation_key="update"`, no `supported_features`/`entity_category` override), `async_setup_entry` creating exactly one instance from `entry.runtime_data.coordinator`. `PARALLEL_UPDATES = 0`.
- `custom_components/securityspy/__init__.py` — added `Platform.UPDATE` to `PLATFORMS` (alongside the existing `Platform.SENSOR`).
- `custom_components/securityspy/strings.json` / `translations/en.json` — added an `entity.update.update` block (`{"name": "Update"}`), mirroring the existing `entity.sensor.*` blocks.
- `custom_components/securityspy/icons.json` — added the `update.update` icon entry (`mdi:package-up`).
- `tests/conftest.py` — added `update_version: str | None = None` to `make_server_info()` and `make_server_info_with_cameras()`, threaded into each `ServerInfo(...)` call.
- `tests/test_update.py` — **new file.** One test per I/O-matrix row (`test_update_available`, `test_no_update_available`, `test_no_install_action_offered`) plus `test_unique_id_and_device_linkage`.

## Tasks & Acceptance

**Execution:**
- [x] `tests/conftest.py` — add `update_version` kwarg to both server-info builders.
- [x] `custom_components/securityspy/update.py` — implement `SecuritySpyUpdateEntity` and `async_setup_entry`.
- [x] `custom_components/securityspy/__init__.py` — add `Platform.UPDATE` to `PLATFORMS`.
- [x] `custom_components/securityspy/strings.json`, `translations/en.json` — add the `entity.update.update` name block.
- [x] `custom_components/securityspy/icons.json` — add the `update.update` icon entry (optional but keep parity with `sensor.py`'s coverage of every entity).
- [x] `tests/test_update.py` — cover every I/O-matrix row plus unique ID, device linkage, and `supported_features == UpdateEntityFeature(0)`.

**Acceptance Criteria** (from epics.md Story 2.5):
- Given a server reporting an available update, when the hub device is viewed, then an update entity reports that an update is available and names the offered version, and the currently installed version is also shown.
- Given the update entity, when a user attempts to install from Home Assistant, then no install action is offered.

## Design Notes

**Why fall back to `version` instead of leaving `latest_version` unset when there's no update.** `UpdateEntity.state` (HA's own base-class computation) returns `None`/`unknown` when either `installed_version` or `latest_version` is `None`, and only returns `STATE_OFF` (the "up to date" state a user actually wants to see) when both are set and equal. Leaving `latest_version` as `None` whenever `update_version is None` would make every up-to-date server show `unknown` forever — the far more common case — instead of a clean "no update." This is why the fallback lands in the entity layer, not the library: the library's own docstring is explicit that `update_version=None` is _its_ correct "no update" signal, and this fallback doesn't change that; it just maps that library-level absence onto the frontend-level state HA expects for the same fact.

**Why `UpdateDeviceClass.FIRMWARE` despite this being an application version, not device firmware.** It's the enum's only member, and multiple core HA integrations (e.g. Synology DSM, UniFi, HA Core's own Supervisor updater) use it for server/software version reporting for the same reason — there's no more specific option, and using it gets the standard update-entity card treatment in the UI. Omitting `device_class` entirely would also be valid; this is a cosmetic choice, not a hard requirement.

## Verification

**Commands:**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100` — expected: all tests pass, 100% coverage including `update.py`.
- `uv run ruff check custom_components tests && uv run ruff format --check custom_components tests` — expected: clean.
- `uv run mypy --strict custom_components/securityspy` — expected: clean.

**Manual checks (if no CLI):**
- After setup against a server with `new-version` set, Settings → Devices & Services → the hub device shows an Update entity reporting the offered version, with no "Install" button in its more-info dialog.

## Spec Change Log

No `bad_spec` findings this run — nothing to log.

## Review Triage Log

### 2026-09-12 — Review pass 1
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 0, low 4)
- defer: 0
- reject: 7: (high 0, medium 0, low 7)
- addressed_findings:
  - `[low]` `[patch]` No test asserted the entity actually resolves to `EntityCategory.DIAGNOSTIC` at runtime, despite the spec calling out reliance on the base class's INSTALL-less fallback as a deliberate design decision. Added `test_diagnostic_category_and_firmware_device_class`.
  - `[low]` `[patch]` No test asserted `device_class == UpdateDeviceClass.FIRMWARE`. Covered by the same new test.
  - `[low]` `[patch]` No test verified the update entity stays a single hub-only entity as cameras are added — the spec's "Never" section explicitly forbids a per-camera counterpart, a boundary a future accidental loop over `server.cameras` in `async_setup_entry` could silently violate. Added `test_exactly_one_update_entity_regardless_of_camera_count` (2 cameras, asserts exactly one `update.*` entity).
  - `[low]` `[patch]` No test exercised the entity through a coordinator refresh (only initial setup values were ever asserted), despite the spec's own design notes resting on "kept current by the existing heavy poll." Added `test_state_follows_a_coordinator_refresh` (update available → update installed, asserts state transitions from `on` to `off`).
  - `[low]` `[reject]` Both reviewers flagged `server.update_version or server.version`'s truthy-coercion as unguarded against an empty-string `update_version`. Rejected: confirmed directly against `aiosecurityspy/src/aiosecurityspy/models.py`'s `ServerInfo.update_version` docstring and decode logic — the library itself folds an empty `new-version` to `None` before this layer ever sees it (`(_as_str(...) or "").strip() or None`), so an empty string can never reach this entity under the library's own documented contract. Matches this project's established "trust internal/upstream invariants" convention.
  - `[low]` `[reject]` `test_no_install_action_offered`'s docstring claims "no code path in this entity handles installation," which the reviewer called an overclaim since the entity never defines `async_install` at all. True, but the docstring is accurate as written (there genuinely is no such code path) and the test's actual assertions (`supported_features == UpdateEntityFeature(0)` plus the raised error) are exactly right — a wording nitpick, not a coverage or correctness gap.
  - `[low]` `[reject]` `strings.json`/`translations/en.json` are hand-duplicated rather than generated from one source — this is the exact pattern story 2.4 already established for `entity.sensor.*`; not a new issue introduced by this story.
  - `[low]` `[reject]` The test file's `_entity_id` helper hardcodes the literal `"update"` domain string rather than a shared constant — test-style preference with zero behavioral risk, given `Platform.UPDATE.value == "update"` is Home Assistant's own stable domain name, not project-specific.
  - `[low]` `[reject]` No test enforces that `ServerInfo.version` can never be `None` — speculative guard against a hypothetical future library API change with no current evidence of one; matches this project's established convention of not defending against contradictions of an upstream type's actual contract.
  - `[low]` `[reject]` No test combines the update entity with multiple cameras present (beyond the new exactly-one-entity test added above) — the update entity is per-config-entry, not per-camera, so camera count has no other bearing on it; speculative interaction with no plausible failure mode.
  - `[low]` `[reject]` hassfest/quality-scale validation wasn't run locally against the new platform — same known, already-documented local-tooling gap noted in story 2.3's review (this repo has no `script.hassfest`; the real gate is the CI job), not a new issue.

## Auto Run Result

**What was implemented.** A single hub-level `UpdateEntity`, `SecuritySpyUpdateEntity(SecuritySpyHubEntity, UpdateEntity)`, reusing story 2.4's `SecuritySpyHubEntity` base class exactly. `installed_version` reads `server.version`; `latest_version` reads `server.update_version or server.version`, so an up-to-date server reads `STATE_OFF` rather than `unknown`. `device_class=UpdateDeviceClass.FIRMWARE`, `translation_key="update"`, no `supported_features`/`entity_category` override — the class defaults (`UpdateEntityFeature(0)`, DIAGNOSTIC fallback) already satisfy "no install action" and "diagnostic-only" with zero extra code. `Platform.UPDATE` added to `PLATFORMS`.

**Files changed:**
- `custom_components/securityspy/update.py` — new platform file.
- `custom_components/securityspy/__init__.py` — `Platform.UPDATE` added to `PLATFORMS`.
- `custom_components/securityspy/strings.json`, `translations/en.json`, `icons.json` — `entity.update.update` name/icon entries.
- `tests/conftest.py` — `update_version` kwarg added to both server-info builders.
- `tests/test_update.py` — new file; 7 tests after review-pass patches (up from 4): every I/O-matrix row, unique ID/device linkage, diagnostic category + firmware device class, exactly-one-entity-regardless-of-cameras, and state-follows-a-coordinator-refresh.

**Review findings breakdown:** 11 total findings from Blind Hunter + Edge Case Hunter, deduplicated (the two reviewers converged independently on the same truthy-coercion concern). 4 patched (all low: entity_category/device_class assertions, exactly-one-entity test, coordinator-refresh test). 0 deferred. 7 rejected — most notably the `or`-fallback concern, refuted directly against the library's own decode logic (`update_version` can never be an empty string at this layer), plus several already-settled precedents from stories 2.3/2.4 (strings/translations duplication, hassfest not runnable locally) and speculative/cosmetic nitpicks. No `intent_gap` or `bad_spec` — the spec needed no repair.

**Verification performed (all green after patches):**
- `uv run pytest tests/ --cov=custom_components.securityspy --cov-report=term-missing --cov-fail-under=100`: **93 passed**, **100.00%** coverage across all 7 modules.
- `uv run ruff check custom_components tests` / `uv run ruff format --check custom_components tests`: **clean**.
- `uv run mypy --strict custom_components/securityspy`: **clean**, 7 source files.

**Residual risks / follow-ups.** None beyond what's already logged: the library's own `[ASSUMPTION]` docstring on `update_version` (an up-to-date server might theoretically *echo* the installed version in `new-version` instead of sending empty, which would show a spurious "update available") is a library-level risk, not this story's; if it's ever wrong, this entity would misreport, but nothing here can independently verify a live server's behavior.
