# PRD Addendum — Home Assistant Integration for SecuritySpy

This addendum captures depth that informed the PRD but belongs in downstream documents (architecture, epics, CI setup), plus research surfaced during the PRD run that is not in the brief or its addendum. The brief's own addendum (`../../briefs/brief-ha-securityspy-2026-08-09/addendum.md`) remains the canonical entity-level and protocol-level reference; nothing here duplicates it.

## 1. Quality scale — exact rule sets (for architecture and CI)

Rule sets verified 2026-08-09 from `script/hassfest/quality_scale.py` in `home-assistant/core` (the authoritative list CI enforces, not the prose docs). Re-verify at implementation start; the docs-* family has grown over time.

**Bronze (20):** `action-setup`, `appropriate-polling`, `brands`, `common-modules`, `config-flow`, `config-flow-test-coverage`, `dependency-transparency`, `docs-actions`, `docs-conditions`, `docs-high-level-description`, `docs-installation-instructions`, `docs-removal-instructions`, `docs-triggers`, `entity-event-setup`, `entity-unique-id`, `has-entity-name`, `runtime-data`, `test-before-configure`, `test-before-setup`, `unique-config-entry`

**Silver (10):** `action-exceptions`, `config-entry-unloading`, `docs-configuration-parameters`, `docs-installation-parameters`, `entity-unavailable`, `integration-owner`, `log-when-unavailable`, `parallel-updates`, `reauthentication-flow`, `test-coverage`

Notes that bite:
- `config-flow-test-coverage` demands 100% config-flow coverage including every abort/error path — the single biggest Bronze cost.
- `runtime-data`: typed `ConfigEntry` alias + `entry.runtime_data`, not `hass.data[DOMAIN]`. Machine-validated.
- `appropriate-polling`: for `iot_class: local_push`, usually `exempt` with comment.
- `brands` requires a PR to `home-assistant/brands` — external review latency; start early.
- Silver `test-coverage` is >95% across all integration modules.
- `parallel-updates`: explicit `PARALLEL_UPDATES` constant in every platform module.
- `action-exceptions`: `ServiceValidationError` for user error, `HomeAssistantError` for failures.
- Gold rules `dynamic-devices` and `stale-devices` are cheap to design in from the start and expensive to retrofit — worth honoring in the Phase 1 device model even without committing Gold.
- Platinum (`async-dependency`, `inject-websession`, `strict-typing`) is nearly free if made a library design constraint from day one — this is FR-41's rationale.
- The scale is a core-integration mechanism; hassfest must be wired into the project's own CI. Claim phrasing: "meets the rule set as verified by our own hassfest run," never "certified."

## 2. HACS mechanics (for the ship phase)

- Ship as a custom repository from day one; **default-store listing is post-launch** (review "can take months" per HACS's own docs).
- Default-store requirements: public non-archived repo with description + topics; HACS Action and hassfest actions passing; at least one real GitHub Release created *after* actions pass; brands PR merged; exactly one integration per repo; `hacs/default` PR from a personal account.
- `hacs.json` keys: `name` (required), `homeassistant` (min HA version), `hacs`, `content_in_root`, `zip_release`, `filename`, `hide_default_branch`, `country`, `persistent_directory`.
- HACS auto-removes archived repos from the default store — the mechanism that silently orphaned briis users around HA 2025.1.

## 3. Blueprint mechanics (for FR-37)

- No HACS blueprint category exists (integration, plugin, theme, template, appdaemon, python_script only). Blueprints live in the repo, e.g. `blueprints/automation/<domain>/`.
- One-click import: `https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=<url-encoded raw GitHub URL>`, rendered as the standard My-HA badge in the README.
- Each blueprint sets `source_url:` to its canonical raw URL — this is what enables HA's built-in re-import/update.
- Typed selectors only (`selector: entity: filter: integration: securityspy`), never hardcoded entity IDs.
- Do not promise auto-update; a third-party "Blueprints Updater" integration exists but must not be a dependency.

## 4. Competitive detail (for positioning and outreach)

| | briis/securityspy | JoshADC/securityspy | HomeHelper | This project |
|---|---|---|---|---|
| Status | Archived 2024-09-23, v1.1.9 | Active, v1.4.0 (2026-04-13) | Vendor, v1.2, free | — |
| Library | pysecspy (dead, PyPI 1.3.5 Aug 2022) | **None — inline `xmltodict`** | n/a | Typed async PyPI package |
| Entities in HA | Motion + classification-as-attribute | + schedule presets, cam enable/disable, AI score sensors | **None** (external rules engine) | Full model incl. Observation Record |
| HACS default store | Removed on archive | Not listed | n/a | Post-launch goal |
| Quality scale | None | None | n/a | Bronze at release / Silver gates announcement |

- JoshADC manifest facts: `iot_class: local_push`, `config_flow: true`, min HA 2024.4.0, 8 stars.
- HomeHelper: HA support added v1.1 (2025-02-17); rules run in the Mac app, bidirectional; requires an always-running Mac app + iCloud sign-in; no camera streams into HA; low adoption (too few App Store ratings to aggregate).
- Demand signal lives on the Ben Software forum, not the HA forum: threads 4542 (abandonment, ~8 participants, Ben participates directly), 4847 (JoshADC's dev thread — users prefer integration over HomeKit/HomeHelper; asks include per-camera privacy toggles, SSL options, schedule presets, local LLM video analysis), 4850 (setup help). Strongest churn datum: a user contemplating switching back to Blue Iris purely over the lost integration.
- Detection-modeling precedent: unifiprotect (Platinum) uses `event` entities for smart detections and ships *both* binary sensor and event for vehicle (presence vs. confidence) — the pattern the PRD adopts. Reolink (Platinum) uses per-class binary sensors + sub-classification sensors + per-AI-type `number` tuning. Frigate uses per-object occupancy binary sensors; confidence only via MQTT, with an open feature request for it as an entity — evidence the confidence-as-payload choice has demand. **No mainstream integration exposes a last-seen-per-class Observation Record; the concept is this project's own.**

## 5. Decision rationale captured during the PRD run

(Full audit trail in `.memlog.md`.)

- **Arming = override-only + read-only schedule visibility.** Writing schedules destroys user config in SecuritySpy; overrides are transient and correct for automation-driven arming. Read-only schedule surfaces "what governs this camera" without clobber risk. Rejected: full three-dimensional control (schedule-destruction hazard), defer-to-architecture (the destruction risk is a product decision, not a mechanism detail).
- **Tuning = global default + per-camera override.** The reference system's indoor/outdoor split is exactly the case where one number cannot fit; indoor cameras dominate classification traffic.
- **Image access = HA-proxied only.** No promise of direct SecuritySpy reachability; avoids topology leakage and the credential-in-URL hazard (a password was observed echoed into logs by ffprobe during research). Does not assume the reference tailnet.
- **CoreML = full dynamic entity creation, gated on a spike.** Expands the brief (which was schema-only for v1). The unconditional part (open vocabulary, FR-34) is separated from the conditional part (entity creation, FR-35) because the payload shape is undocumented and empirically undiscovered.
- **v1 scope holds the brief's line**: get_clip and media_source both deferred despite differentiator status — shipping smaller beats differentiating later, given the predecessor died of fatigue. get_clip additionally carries a disk-fill hazard (generated clips persist server-side until deleted); any future implementation must clean up or expose deletion.
- **Detection model = both surfaces** (per-class binary sensors + once-per-episode event with peak confidence), reconfirmed against ecosystem research; matches the addendum's discriminator rule and unifiprotect's Platinum precedent.
- **Positioning = acknowledge the JoshADC fork, differentiate on structural depth.** The brief's "abandoned and unreplaced" is superseded. No outreach dependency added to the plan; outreach logged as Open Question 9.
- **Silver gates public announcement, not release** (reviewer-gate resolution). Quiet HACS release at verified Bronze; forum announcement only at Silver. Resolves the adversarial finding that Silver-at-release reproduced the predecessor's death pattern (>95% coverage, solo dev, pre-value).
- **All three brief items restored** after reconciliation caught the silent drop: captured-file reference in the Classification Event payload (FR-6), trigger events with decoded reasons (FR-43), download-latest-recording service (FR-44). FR-45 (default-install trap detection) added from the research reconciliation: per-class triggers are off on a default SecuritySpy install, so the Observation Record starts empty and the integration must say so rather than sit silently empty.

## 6. Deliberately excluded from the PRD

- All endpoint names, field decodings, bitmasks, framing details (CR-only), and settings read/write mechanics — canonical in the API reference and brief addendum; the PRD references effects, not mechanisms.
- The `DataUpdateCoordinator` shape, entity platform assignments, and unique-ID format strings — architecture-phase decisions, pre-researched in `architecture-implications.md`.
- The 794 B vs 27 KB status-endpoint comparison appears in the PRD only as an NFR hint (§11.1); endpoint selection is architecture.
