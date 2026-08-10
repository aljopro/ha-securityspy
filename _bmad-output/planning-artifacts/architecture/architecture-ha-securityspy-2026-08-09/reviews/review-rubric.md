# Rubric Review — ARCHITECTURE-SPINE.md (ha-securityspy)

Reviewer: rubric-walker · Date: 2026-08-09
Target: `../ARCHITECTURE-SPINE.md` · Driving PRD: `prd-ha-securityspy-2026-08-09/prd.md` (FR-1..FR-45)

**Verdict: PASS with gaps — the spine fixes the real divergence points and covers all 45 FRs, but leaves the integration's own release/versioning mechanics and two smaller consistency dimensions silent.**

---

## Rubric walk

### (1) Fixes the real divergence points for independent epic/story agents; misses none

The high-risk divergence points for this system are correctly identified and pinned:

- **Truth source** (AD-1): the single most likely divergence — one story building persistent state off the stream, another off polls — is closed with a testable rule (hydrate from poll, reconcile on reconnect, push may only advance state a poll would confirm). This is exactly the predecessor's defect and the PRD's core claim (FR-2, §11.3).
- **Layer boundary** (AD-2 + paradigm): "entities import types, never call I/O" is precise enough that two platform-module stories cannot drift.
- **Identity** (AD-5): fully specified format strings — no room for a story to invent its own unique-ID scheme. Correctly flagged permanent.
- **Exception classification** (AD-6): the single-seam rule plus the 3-consecutive-auth-failure count prevents per-platform divergence on failure handling.
- **Polling shape** (AD-10): the cameras×classes fan-out (PRD §10.2, Open Q4) is decided, with the four trigger conditions enumerated — two stories cannot each invent a poll schedule.
- **Reducer ownership** (AD-3), **coordinator singleton** (AD-4), **override-only arming** (AD-7), **partial POSTs** (AD-8), **open class vocabulary** (AD-9), **stream lifecycle ownership** (AD-11), **HA runtime conventions** (AD-12), **credential containment** (AD-13), **repo split** (AD-14) — all real, all divergence-preventing.

**Misses (residual divergence points not pinned):**

- **M1 — Per-camera availability signal.** FR-30 requires per-Camera-Device unavailability when one camera goes offline while the server is up. AD-11 covers *stream*-level availability only; nothing says which signal (status-poll field? stream event? enabled flag from FR-16?) decides a *single camera* is offline. Two stories (binary_sensor vs sensor platforms, or coordinator vs entity base) could classify camera-offline differently. Should be a sentence in AD-11 or the entity.py convention.
- **M2 — Options schema for per-camera overrides.** The conventions table says tuning lives in options, but the *shape* of per-camera overrides (nested dict keyed by camera_number? flat prefixed keys?) is undecided. Config-flow story and coordinator story can diverge here; options schemas are semi-permanent once users have entries.
- **M3 — Default-disabled entity rule.** FR-22 (camera entities disabled by default) and FR-23 (diagnostic category) appear only in the capability map; no convention states `entity_registry_enabled_default` / `EntityCategory` usage, which independent platform stories could apply inconsistently. Low risk (HA idiom is strong) but this altitude owns it.

### (2) Every AD's Rule is enforceable and prevents its stated divergence

Yes, with minor softness:

- AD-1, AD-4, AD-5, AD-6, AD-7, AD-9, AD-13, AD-14: mechanically checkable (grep-able, testable, CI-able). Good.
- AD-2's enumeration of protocol knowledge is unusually concrete (bool read/write asymmetry, `f`+`s` decoding) — enforceable via "no wire-format literals in integration" review plus library test fixtures.
- AD-8 "verified non-destructive" is enforceable only if a test asserts unrelated settings are unchanged after a write (FR-17 consequence exists in the PRD); acceptable.
- AD-10's bracketed assumptions (7 d / 10 min / 5 s) are correctly marked and are defaults, not divergence points, since they live in options.
- AD-12 bundles many rules but each maps to a machine-validated quality-scale rule, so enforcement is CI-borne. Fine.

### (3) Nothing under Deferred could let two units diverge

Each deferral checked:

- Custom Model entity mechanism — safe: AD-9 freezes the schema meanwhile. ✓
- Threshold/debounce defaults — safe: options-adjustable, and AD-3 fixes where they're injected. ✓
- Reconciliation freshness bound — safe: only a documentation claim, AD-10 fixes the mechanism. ✓
- v2 features, multi-server, tokens, HACS default store, Gold/Platinum, SecuritySpy version floor — all either foreclosed-nothing or single-owner decisions. ✓
- **Borderline:** "SecuritySpy minimum version floor" deferral means the config-flow story must ship *some* check (FR-38/§11.5 require enforcement at setup with `SecuritySpyUnsupportedVersionError` — which AD-6 does name), so the mechanism exists and only the constant is deferred. Acceptable.

No deferral hides a two-unit divergence. ✓

### (4) Named tech plausibly current (Aug 2026)

- Python ≥3.13 — plausible (3.13 is ~2 yrs old; HA 2026.x era requirement).
- HA 2026.2 min / 2026.8.1 current — internally consistent with today's date; min flagged `[ASSUMPTION]`. ✓
- aiohttp `>=3.12,<4`, hatchling, uv (with OIDC publish), ruff, mypy --strict, pytest-homeassistant-custom-component, hassfest + HACS Action, PyPI trusted publishing — all current, mainstream choices as of knowledge date; nothing anachronistic or deprecated. ✓
- Minor: mypy --strict for the library is fine, but the spine is silent on the *integration's* type-checking regime (HA core uses mypy too); trivial.

### (5) Covers the PRD's capabilities (FR-1..FR-45)

Walked the Capability → Architecture Map against the PRD: all of FR-1..FR-45 are claimed by a row, and each row cites a governing AD. Spot-checks:

- FR-44 (download service) → services.py + AD-6 error mapping ✓; destination-unwritable vs no-recording distinct errors follow from AD-6's ServiceValidationError/HomeAssistantError split ✓.
- FR-45 (default-install trap) → repairs.py ✓.
- FR-37 blueprints → seed includes `blueprints/automation/securityspy/` ✓.
- FR-24 (update entity) → `update.py` in seed ✓.
- FR-39 (Silver gates announcement) — thinnest coverage: "Bronze verified on every change" is in AD-14 but the Silver coverage-threshold gate before announcement is not mentioned anywhere. Process-level, but the CI dimension is where it would live. (See M4.)

No FR is orphaned. ✓

### (6) Every owned dimension decided, deferred, or open — silence scan

Operational/environmental envelope:

- **Deployment & environments:** covered adequately for this product class — distribution *is* deployment (HACS custom repo + PyPI, AD-14, Stack). Runtime environment is HA itself; min versions stated. ✓
- **CI:** covered (AD-14 + Stack rows). ✓
- **Release mechanics — GAP (M4):** the *library's* release mechanics are decided (tags → OIDC → PyPI). The *integration's* are wholly silent: versioning scheme (semver? `manifest.json` version bump discipline), how a HACS release is cut (GitHub release / zip_release in hacs.json), changelog, and where the FR-39 Silver-coverage gate is enforced. Two stories (packaging vs CI) could diverge, and FR-36's "installs without manual file copying" depends on it.
- **Operations/observability:** logging discipline (AD-11, conventions), diagnostics (AD-13), repairs (AD-12) — covered. No metrics/telemetry, correctly so for a local HA integration. ✓
- **Security envelope:** AD-13 + config-flow HTTPS toggle — covered. ✓
- **Testing strategy:** conventions row covers frameworks and fixture policy; coverage gates named in AD-14. Adequate. ✓
- **i18n:** translation_key mandated (AD-12); "full translations" deferred by the PRD itself. ✓
- **Docs:** vocabulary convention exists; README/removal docs (FR-38) implied by seed. Thin but acceptable.
- **Wholly silent dimensions found:** integration release/versioning (M4), per-camera availability signal (M1), options schema shape (M2), default-disabled/category conventions (M3). Nothing else at this altitude is silent — notably the domain-draft-skipping check found the operational side mostly *not* skipped, which is better than typical.

---

## Findings

| ID | Tier | Finding |
| --- | --- | --- |
| M4 | High | Integration release mechanics wholly silent: versioning scheme, HACS release cut (hacs.json zip_release / GitHub releases), changelog, and where FR-39's Silver-coverage announcement gate is enforced — the only owned operational dimension with no decision, deferral, or open question. |
| M1 | High | Per-camera (vs server-wide) unavailability signal for FR-30 is undecided — AD-11 handles stream loss only, leaving independent platform stories to classify single-camera-offline divergently. |
| M2 | Medium | Options-schema shape for per-camera threshold/debounce/timeout overrides is unspecified; config-flow and coordinator stories can diverge on a structure that is semi-permanent once user entries exist. |
| M3 | Low | No convention pins `entity_registry_enabled_default` (FR-22) and `EntityCategory` (FR-23, FR-12 "configuration") usage across platform modules. |
| M5 | Low | Integration-side type-checking regime unstated (library gets mypy --strict; integration gets nothing named). |

Everything else on the rubric passes: ADs are enforceable and matched to their stated divergences, the Deferred list is divergence-safe, the stack is plausibly current for Aug 2026, and all 45 FRs are mapped to owning modules and governing ADs.
