---
title: "Engineering Documentation Index — ha-securityspy"
status: living
created: 2026-08-09
updated: 2026-08-09
---

# Engineering Documentation Index

Everything an engineer or dev agent needs to implement a story in this project. Read the two that apply to your story; don't read all of it.

## Start here

| If you are… | Read |
|---|---|
| Writing integration code (entities, coordinator, config flow) | [ha-integration-reference.md](ha-integration-reference.md) |
| Writing library code (protocol, stream, decoding) | [SecuritySpy API reference](../_bmad-output/planning-artifacts/research/securityspy-api-reference.md) |
| Packaging, CI, blueprints, or releasing | [hacs-packaging-and-blueprints.md](hacs-packaging-and-blueprints.md) |
| Unsure whether a decision is yours to make | [Architecture Spine](../_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md) |
| New to the project entirely | [Solution Design](../_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/SOLUTION-DESIGN.md), then the spine |

## The documents

### Engineering references (this folder)

- **[ha-integration-reference.md](ha-integration-reference.md)** — Home Assistant integration development, written the way this project's architecture requires: manifest and file structure, `runtime_data` setup, the push-fed coordinator, entity naming and identity, config/reauth/reconfigure/options flows, availability and exception taxonomy, diagnostics and repairs, testing, and the full quality-scale rule sets. Verified against `developers.home-assistant.io`, August 2026.
- **[hacs-packaging-and-blueprints.md](hacs-packaging-and-blueprints.md)** — what HACS is and how custom-repository distribution works, `hacs.json` and CI workflows, PyPI trusted publishing for the library, blueprint authoring with typed selectors and one-click import, and the Bronze-release / Silver-announcement sequence.

### Protocol reference (research)

- **[securityspy-api-reference.md](../_bmad-output/planning-artifacts/research/securityspy-api-reference.md)** — the reverse-engineered SecuritySpy 6.x Web API: the endpoint catalogue including the 25+ undocumented endpoints the vendor's own client uses, event-stream framing and event types, `caplist` field decoding, settings read/write mechanics, the arming model, and the permissions bitmask. **This is the authority on protocol behavior, and it supersedes the vendor's published specification** wherever they disagree.

  Three things in it will bite you if you skip them: event-stream lines are **CR-terminated only** (a standard `readline()` hangs, and this is named the single most likely bug in any SecuritySpy client); settings write bodies must begin with the literal sentinel `formData` and use `1`/`0` where JSON reads return `true`/`false`; and the `t` field means different things in `caplist` than in `clip`, so the enums must not be shared.

- **[architecture-implications.md](../_bmad-output/planning-artifacts/research/architecture-implications.md)** — the design conclusions drawn from that protocol research, with the evidence for each. Largely folded into the architecture spine; useful when you want the reasoning rather than the rule.

### Planning artifacts

- **[Architecture Spine](../_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/ARCHITECTURE-SPINE.md)** — the binding contract. 18 architecture decisions (AD-1…AD-18), consistency conventions, the pinned stack, and what is deliberately deferred. **If your story seems to need a decision this doesn't make, it is either in Deferred or it is a hole — surface it, don't invent it.**
- **[Solution Design](../_bmad-output/planning-artifacts/architecture/architecture-ha-securityspy-2026-08-09/SOLUTION-DESIGN.md)** — the same architecture as readable prose, explaining why each decision exists.
- **[PRD](../_bmad-output/planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md)** — requirements FR-1…FR-45, the glossary (§4, use these terms verbatim), success metrics, and open questions.
- **[PRD addendum](../_bmad-output/planning-artifacts/prds/prd-ha-securityspy-2026-08-09/addendum.md)** — exact quality-scale rule sets verified from hassfest source, HACS mechanics, blueprint mechanics, competitive detail, and captured decision rationale.
- **[Epic breakdown](../_bmad-output/planning-artifacts/epics.md)** — requirements inventory, FR coverage map, and the epic and story breakdown.

## Non-negotiables

Five things that are settled, so no story re-litigates them:

1. **The event stream is never the source of persistent truth** (AD-1). Every persistent value derives from the capture-history poll plane. Push may only advance state.
2. **All protocol knowledge lives in the library** (AD-2). The integration contains zero SecuritySpy wire-format knowledge, and destructive endpoints are absent from the library surface entirely.
3. **Identity is server UUID plus camera number** (AD-5), and it is permanent — changing it orphans every customization a user has made.
4. **Object Class is an open string** (AD-9), never a three-value enum.
5. **Credentials never reach logs or diagnostics** (AD-13). SecuritySpy's settings endpoint returns camera passwords in plaintext, so this is a live hazard rather than a precaution.

## Vocabulary

Use the PRD Glossary (§4) terms verbatim in code, comments, docs, and translation strings: *SecuritySpy Server, Hub Device, Camera Device, Config Entry, Event Stream, Capture History, Capture, Object Class, Custom Model, Classification Signal, Detection Episode, Detection Threshold, Detection Debounce, Peak Confidence, Observation Record, Latest Capture, Arm Mode, Arm Schedule, Arm Override, Detection Trigger, API Library.* Introducing a synonym is a discipline violation — the distinction between a Classification Signal and a Detection Episode, and between SecuritySpy's own sensitivities and the integration's Detection Threshold, is load-bearing.
- [SecuritySpy OpenAPI description](../aiosecurityspy/docs/securityspy-openapi.yaml) — machine-readable description of the HTTP calls, with explicit annotations for the parts OpenAPI cannot express
