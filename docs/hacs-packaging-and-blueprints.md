---
title: "HACS Packaging, Blueprints, and Release — Engineering Reference"
status: living
created: 2026-08-09
updated: 2026-08-29
verified_against: "hacs.xyz and home-assistant.io, August 2026"
---

# HACS Packaging, Blueprints, and Release

How `ha-securityspy` reaches users, and how `aiosecurityspy` reaches PyPI. Companion to [ha-integration-reference.md](ha-integration-reference.md).

---

## 1. What HACS is, in one paragraph

HACS (Home Assistant Community Store) is a custom integration that acts as a package manager for *other* community content. A user installs HACS once, then uses it to download integrations, dashboard cards, and themes from GitHub. HACS has two modes of distribution:

- **Default store** — curated, searchable in HACS out of the box. Requires a review whose own documentation warns it "can take months," plus a merged `home-assistant/brands` PR.
- **Custom repository** — the user pastes a GitHub URL into HACS and it installs immediately. No review, no waiting.

**This project ships as a custom repository from day one** (FR-36). Default-store listing is a post-launch milestone, deliberately not a launch gate. This matters historically: HACS *automatically removes archived repositories* from the default store, which is exactly the mechanism that silently orphaned `briis/securityspy` users around HA 2025.1.

## 2. Repository requirements

| Requirement | Detail |
|---|---|
| Structure | Everything in `custom_components/securityspy/` at the repo root |
| One per repo | Exactly one integration per repository — this is why AD-14 mandates two repos |
| `manifest.json` | Must include `domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version` |
| Brand assets | A `brand/` directory containing at least `icon.png` |
| Releases | Optional but recommended; HACS shows the 5 latest releases plus the default branch |

Minimum valid layout:

```
custom_components/securityspy/__init__.py
custom_components/securityspy/manifest.json
hacs.json
README.md
brand/icon.png
```

### hacs.json

```json
{
  "name": "SecuritySpy",
  "homeassistant": "2026.3.0",
  "render_readme": true
}
```

| Key | Meaning |
|---|---|
| `name` | **Required.** Display name in HACS |
| `homeassistant` | Minimum HA version — enforces FR-36/NFR-17 |
| `content_in_root` | Only if not using `custom_components/` (we are, so omit) |
| `zip_release` + `filename` | Ship a built zip asset instead of raw source |
| `hide_default_branch` | Hide the branch so users only see tagged releases |
| `persistent_directory` | A directory preserved across updates |
| `country` | Restrict visibility by country |

`homeassistant` here and `version` in `manifest.json` are the two version declarations that must not drift.

### Default-store requirements (post-launch)

Public non-archived repo with a description and topics · HACS Action and hassfest Action both passing · at least one real GitHub Release created *after* those actions pass · a merged `home-assistant/brands` PR · exactly one integration per repo · the `hacs/default` PR submitted from a personal account.

**Start the brands PR early** — it has external review latency and nothing downstream depends on it, so it can run in the background.

## 3. CI

Two workflows in the integration repo, both required by FR-38.

```yaml
# .github/workflows/validate.yml
name: Validate
on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"        # catches upstream HA changes breaking us

jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master

  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: integration
```

The scheduled run is not decoration: it is how you learn that an HA release broke the integration before a user does — directly serving the "still works in three years" bar.

> **Quality-scale gap to close:** hassfest no longer checks `parallel-updates` (it moved to the Home Assistant **pylint plugin** in HA 2026.6). Add a pylint job using HA's plugin, or that Silver rule silently goes unverified.

### Two test suites, two scopes — always run the library's scoped

This repo has two `pyproject.toml` files with incompatible pytest configs, and running the wrong one against the wrong tests fails loudly and confusingly:

| | Root (`ha-securityspy/pyproject.toml`) | Library (`aiosecurityspy/pyproject.toml`) |
|---|---|---|
| Tests | `tests/` (the integration) | `aiosecurityspy/tests/` (the library) |
| `asyncio_mode` | `auto` | `strict` |
| Why | `pytest-homeassistant-custom-component`'s fixtures are plain async functions with no explicit marker; `auto` is required for them to run at all | the library has no dependency on that plugin and marks its own coroutines explicitly |
| Extra | — | `filterwarnings = ["error"]` — a deprecation warning fails the run rather than accumulating silently |

Invoking plain `pytest` (or `pytest aiosecurityspy/tests`) from the repo root picks up the **root** config regardless of which tests you point it at. Pointed at the library's tests, that collides: `pytest-asyncio`'s strict-mode markers on the library's coroutines fight `pytest-homeassistant-custom-component`'s fixture setup, and all ~700 library tests error at setup — not fail, error, before the test body ever runs. This is a scoping problem, not a code problem; it reproduces identically on old and new library code.

Always run the library's suite from inside `aiosecurityspy/`, so it picks up its own config:

```bash
uv run --directory aiosecurityspy pytest -q
# or: cd aiosecurityspy && uv run pytest -q
```

This is exactly what `.bmad-loop/policy.toml`'s `[verify].commands` already do — the loop's automated gate has always been scoped correctly. The trap is only for a human or an ad hoc agent invocation from the repo root.

### Library release (PyPI trusted publishing)

No API tokens, no secrets — OIDC.

```yaml
# aiosecurityspy/.github/workflows/publish.yml
on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write          # required for trusted publishing
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - run: uv publish        # authenticates via OIDC
```

Configure the trusted publisher once at <https://pypi.org/manage/account/publishing/>. This satisfies Bronze `dependency-transparency`: published from a public repo, built in CI from source, versions matching tagged releases.

## 4. Blueprints

Blueprints are reusable automation templates a user imports and fills in — no YAML editing. Two ship with this project (FR-37), and they double as the **entity-model design test**: if a blueprint is awkward to write, the entity model is wrong.

**HACS has no blueprint category** (only integration, plugin, theme, template, appdaemon, python_script). Blueprints therefore live in the repo and are imported directly. Do not promise auto-update.

### Location and structure

```
blueprints/automation/securityspy/notify_with_picture.yaml
blueprints/automation/securityspy/capture_image_on_detection.yaml
```

```yaml
blueprint:
  name: SecuritySpy — Notify with picture when a person is seen
  description: >
    Sends a notification with the latest capture image when SecuritySpy
    detects a human on the selected camera.
  domain: automation
  source_url: https://github.com/<owner>/ha-securityspy/blob/main/blueprints/automation/securityspy/notify_with_picture.yaml
  input:
    detection_sensor:
      name: Human detection sensor
      description: The SecuritySpy per-class presence sensor to watch.
      selector:
        entity:
          filter:
            - integration: securityspy
              domain: binary_sensor
              device_class: occupancy
    capture_image:
      name: Latest capture image
      selector:
        entity:
          filter:
            - integration: securityspy
              domain: image
    notify_device:
      name: Device to notify
      selector:
        device:
          filter:
            - integration: mobile_app

triggers:
  - trigger: state
    entity_id: !input detection_sensor
    to: "on"

actions:
  - action: notify.mobile_app
    data:
      message: "Person detected"
      data:
        image: !input capture_image
```

Three rules, all load-bearing:

1. **`source_url` is mandatory** for re-import/update to work. Point it at the canonical repo URL.
2. **Typed selectors filtered to `integration: securityspy`** — never hardcoded entity IDs. This is what makes the blueprint work on anyone's system.
3. **`!input` references the input name**, and inputs must be defined before use.

### One-click import

```
https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=<URL-ENCODED RAW GITHUB URL>
```

Rendered in the README as the standard My Home Assistant badge:

```markdown
[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2F<owner>%2Fha-securityspy%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fsecurityspy%2Fnotify_with_picture.yaml)
```

The `blueprint_url` must be percent-encoded. Test the badge on a clean instance before release — SM-3 requires both blueprints work unmodified.

## 5. Release sequence

1. Library CI green → tag `v0.1.0` → GitHub Release → PyPI publish via OIDC.
2. Integration pins `aiosecurityspy==0.1.0` in `manifest.json`; hassfest, pylint, HACS Action, and coverage all green.
3. **Full Bronze rule set verified** → tag and cut the GitHub Release. This is the HACS custom-repository release (FR-38). Early adopters get it here; **no forum announcement**.
4. Brands PR opened (runs in the background, gates nothing).
5. **Full Silver rule set verified**, including > 95 % coverage → announce on the Ben Software forum and the Home Assistant community forum (FR-39).
6. Post-launch: `hacs/default` PR for default-store listing.

The Bronze/Silver split is deliberate risk management, not perfectionism: the predecessor died of maintainer fatigue, so a quiet release at Bronze beats a polished one that never ships.

## 6. Quick links

| Topic | URL |
|---|---|
| HACS docs | <https://www.hacs.xyz/docs/publish/start/> |
| Publish an integration | <https://www.hacs.xyz/docs/publish/integration/> |
| hacs.json reference | <https://www.hacs.xyz/docs/publish/config/> |
| Default store inclusion | <https://www.hacs.xyz/docs/publish/include/> |
| HACS Action | <https://github.com/hacs/action> |
| Brands repository | <https://github.com/home-assistant/brands> |
| Blueprint tutorial | <https://www.home-assistant.io/docs/blueprint/tutorial/> |
| Blueprint schema | <https://www.home-assistant.io/docs/blueprint/schema/> |
| Selectors reference | <https://www.home-assistant.io/docs/blueprint/selectors/> |
| My Home Assistant links | <https://my.home-assistant.io/> |
| PyPI trusted publishing | <https://docs.pypi.org/trusted-publishers/> |
