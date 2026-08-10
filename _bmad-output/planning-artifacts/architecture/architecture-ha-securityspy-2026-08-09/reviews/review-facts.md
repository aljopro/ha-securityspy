# Fact-Verification Review — ARCHITECTURE-SPINE.md

Reviewer: fact-verification pass against live web sources, 2026-08-09.
Scope: every committed technology/version claim in the spine's stack table and ADs.

## Verdict

Largely accurate, with one materially stale claim (Python floor >= 3.13) and two nuances worth correcting before implementation.

## Findings

### HIGH — Python ">= 3.13" is stale for the declared HA range

- Spine claims: `Python >= 3.13` alongside `current HA 2026.8.1`, min `2026.2`.
- Verified: Home Assistant Core dropped Python 3.13 at **2026.3**, which requires **Python 3.14** (PyPI `homeassistant` 2026.8.1 metadata: `requires_python >= 3.14.2`; core issue #166255 "Custom integration requirements not installed after upgrade to 2026.3 (Python 3.14)"; community thread confirming 2026.3 venv upgrades need 3.14.2).
- Consequence: any CI matrix or dev env testing against current HA (or anything >= 2026.3) must run Python 3.14. `pytest-homeassistant-custom-component` latest (0.13.355) itself declares `requires_python >= 3.14`. Keeping 3.13 only makes sense as the floor for supporting HA 2026.2 exactly — and then the test kit pinned to current HA will not install on 3.13.
- Recommendation: state Python `>= 3.14` for dev/CI (or dual-matrix 3.13-for-2026.2 / 3.14-for-current and pin an older test-kit version for the 3.13 leg — probably not worth the cost). Alternatively raise min HA to 2026.3 and declare 3.14 flatly.
- Sources: https://pypi.org/pypi/homeassistant/json · https://github.com/home-assistant/core/issues/166255 · https://community.home-assistant.io/t/solved-with-python-3-14-2-2026-3-update-on-venv-fails/992830

### VERIFIED — HA current 2026.8.1 / min 2026.2 reasonableness

- 2026.8 released 2026-08-05; patch **2026.8.1** released 2026-08-07. Claim of "current 2026.8.1" is correct as of review date.
- Min 2026.2 is a plausible ~6-month floor, but note it straddles the Python 3.13→3.14 boundary (see HIGH above). No feature in the spine's ADs appears to require anything newer than long-stable APIs, so 2026.2 is not otherwise problematic. The `[ASSUMPTION]` tag is appropriate.
- Sources: https://www.home-assistant.io/blog/2026/08/05/release-20268/ · https://github.com/home-assistant/core/releases

### VERIFIED — aiohttp `>=3.12,<4`

- Latest aiohttp on PyPI is **3.14.3** (production/stable, Python 3.10–3.14). A `>=3.12,<4` range is current, compatible with HA's bundled aiohttp, and appropriately permissive for a caller-injected-session library. No aiohttp 4.x release exists, so the `<4` cap is precautionary and correct.
- Source: https://pypi.org/pypi/aiohttp/json

### VERIFIED — hatchling + uv + src-layout; PyPI trusted-publisher OIDC

- Trusted Publishing via GitHub Actions OIDC is the documented, recommended PyPI publishing path; `uv publish` auto-detects GitHub Actions, exchanges the OIDC token (needs `permissions: id-token: write` in the workflow — worth writing into the CI story). hatchling + `pyproject.toml` + `src/` layout remains mainstream current practice.
- Sources: https://docs.pypi.org/trusted-publishers/ · https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-pypi · https://pydevtools.com/handbook/how-to/how-to-publish-to-pypi-with-trusted-publishing/

### VERIFIED — pytest-homeassistant-custom-component maintained

- Latest 0.13.355, "updated daily according to the latest homeassistant release including beta." Actively maintained. Note again: requires Python >= 3.14.
- Source: https://pypi.org/pypi/pytest-homeassistant-custom-component/json

### VERIFIED — HACS custom repository + hacs.json

- Requirements confirmed: public GitHub repo with a description; `hacs.json` at repo root with required `name` key (optional `homeassistant` min-version key — the spine should use it to encode min 2026.2); one integration per repo under `custom_components/INTEGRATION_NAME/`. HACS Action exists for CI validation as the spine assumes.
- Sources: https://www.hacs.xyz/docs/publish/start/ · https://www.hacs.xyz/docs/publish/integration/ · https://www.hacs.xyz/docs/publish/action/

### VERIFIED with NUANCE — hassfest in custom-integration CI; quality-scale tooling

- `home-assistant/actions/hassfest@master` explicitly supports custom integrations and is a one-step workflow. Confirmed.
- Nuance 1: hassfest's quality-scale validation is driven by a `quality_scale.yaml` file plus manifest `quality_scale`; the formal quality-scale program is a core-integration program — for a custom integration the spine's "Bronze verified on every change" is a self-imposed discipline enforced only to the extent hassfest checks run, not an official certification. Fine as written, but stories should not promise a displayed Bronze badge in HA.
- Nuance 2: the `parallel-updates` quality-scale check migrated from hassfest to **pylint** in HA 2026.6 — a pure hassfest CI gate no longer machine-checks that rule; the spine's AD ("drift from the machine-validated quality-scale rules") slightly overstates hassfest's current coverage.
- Sources: https://developers.home-assistant.io/blog/2020/04/16/hassfest/ · https://github.com/home-assistant/actions · https://www.home-assistant.io/changelogs/core-2026.6/

### VERIFIED — HA APIs named in ADs

- `DataUpdateCoordinator` with push pattern (`async_set_updated_data`, no `update_interval` for push) — current developer docs document exactly this. Confirmed.
- `entry.runtime_data` — current docs use it as the standard pattern (`config_entry.runtime_data`). Confirmed; `hass.data[DOMAIN]` avoidance remains correct guidance.
- `PARALLEL_UPDATES` — still in active use (added to core integrations as recently as 2026.8 changelog). Confirmed.
- `DeviceEntryType.SERVICE` — device registry docs list `entry_type` with DeviceEntryType enum ("only service"); no deprecation noted. Confirmed.
- Repair issues — `repairs.py` platform + issue registry documented and current. Confirmed.
- Options update listener (`entry.add_update_listener`) — not directly confirmed on the pages fetched; it is a long-stable API with no removal found in 2026 changelogs searched. **Verified-by-absence only** — implementer should confirm against current config-entry options docs when writing the options flow story. Also note the separate, ongoing OptionsFlow modernization in core (e.g. deprecation of self-assigned `config_entry` on OptionsFlow) — follow current docs, not older blog examples.
- Sources: https://developers.home-assistant.io/docs/integration_fetching_data/ · https://developers.home-assistant.io/docs/device_registry_index/ · https://developers.home-assistant.io/docs/core/platform/repairs/ · https://www.home-assistant.io/changelogs/core-2026.8/

### UNVERIFIABLE — PyPI name `aiosecurityspy` "verified free 2026-08-09"

- The spine asserts the name was checked free on the review date. Not re-verified in this pass; name availability is race-prone until registered. Recommend registering (or reserving via a first publish) early in Epic 1.

## Summary table

| Claim | Status |
|---|---|
| HA current 2026.8.1 | Verified |
| HA min 2026.2 | Reasonable, assumption-tagged; straddles Python boundary |
| Python >= 3.13 | **Stale — HA >= 2026.3 requires 3.14** |
| aiohttp >=3.12,<4 | Verified current |
| hatchling + uv + src layout | Verified current practice |
| PyPI trusted-publisher OIDC | Verified (needs `id-token: write`) |
| pytest-homeassistant-custom-component | Verified maintained (requires py3.14) |
| HACS custom repo + hacs.json | Verified |
| hassfest in custom CI / quality scale | Verified with nuances (parallel-updates check moved to pylint 2026.6; Bronze is self-imposed) |
| Coordinator push APIs, runtime_data, PARALLEL_UPDATES, DeviceEntryType.SERVICE, repairs | Verified |
| Options update listener | Stable, verified-by-absence only |
| `aiosecurityspy` name free | Unverified as of this review |
