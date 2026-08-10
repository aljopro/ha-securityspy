---
title: "Product Brief: Home Assistant Integration for SecuritySpy"
status: draft
created: 2026-08-09
updated: 2026-08-09
---

# Product Brief: Home Assistant Integration for SecuritySpy

## Executive Summary

SecuritySpy is a mature macOS NVR with real-time AI object classification, a push event stream, and — since version 6 — a substantially reworked JSON API that its published specification does not yet describe. **Home Assistant has no native integration for it, and the two paths that exist both stop short.** `briis/securityspy` was abandoned by its author, dropped from the default HACS store around HA 2025.1, and its backing library has not shipped a release since August 2022. The vendor's own answer, HomeHelper, is a separate always-running Mac app that pushes events into Home Assistant over a long-lived token — it carries no AI object detection, no camera streaming, and no arming controls, and Home Assistant ends up with no entity model of SecuritySpy at all. SecuritySpy users are left pointing the generic camera platform at a URL, getting a picture and nothing else.

The gap is not video — that already works, over ONVIF, and stays. It is everything else SecuritySpy knows and cannot say. This project builds the integration that should exist: a server hub with each camera as a device beneath it, turning what SecuritySpy sees into an **observation record** — what has been seen, where, and when — kept current by the live event stream and reconciled against what the server has already stored. Built to Home Assistant's published quality scale rather than to whatever was expedient, because the last one died of not being.

If it works, SecuritySpy stops being a system that records and becomes one that *notices*. The bar is not "better than the abandoned integration." The bar is that in three years it still works and someone else is relying on it.

## The Problem

Eleven SecuritySpy cameras cover the author's home, indoors and out. Every one appears in Home Assistant as a `generic` camera entity pointed at the SecuritySpy host — entity IDs like `camera.192_168_0_2_4`, devices named `192_168_0_2` with manufacturer "Generic," each needing a manual rename to be legible and none related to each other in the device registry.

Between them, these eleven cameras contribute **zero non-camera entities**. No motion, no classification, no arming state, no last-detection timestamp. There is nothing to write an automation against.

Video itself is not the complaint — ONVIF handles it well and the author wants to keep using it. The complaint is that the picture arrives and the knowledge does not. There is no way to ask *has anyone been in the driveway today*, because nothing in Home Assistant has ever been told.

The same house has a Nest doorbell that does this well. It says "there's a package at the door" — a notification that is *useful* in a way "motion detected" never is. SecuritySpy sees as much: it classifies humans, vehicles, and animals in real time with confidence scores, and stores the result against every recording it makes. The information exists, streams in real time, and is already written to disk — and none of it reaches Home Assistant. The result is a surveillance system that records everything and tells you nothing.

## The Solution

A Home Assistant integration where the SecuritySpy server is a hub device and each camera is a device beneath it, exposing what SecuritySpy already tracks.

**The headline is an observation record: knowing what has been seen, where, and when.** Per camera, a *last human seen*, *last vehicle seen*, and *last animal seen* timestamp — derived from the classification SecuritySpy already stores against every recording, so it is correct after a restart rather than reconstructed from whatever happened to be observed while Home Assistant was running. That record is the thing being built; motion sensors and live events are how it stays current.

Alongside it: **the latest capture as an `image` entity whose state is the timestamp of that capture** — a stable Home Assistant URL for the most recent frame, which is what makes downstream vision analysis possible.

Video is deliberately optional. The reference user already pulls SecuritySpy video into Home Assistant over ONVIF and is happy with it; this integration is not a replacement for that transport, so its camera entities are expected to be switched off by many users. The value is the data.

**Blueprints ship with it.** Two canonical automations, importable in one click: *notify me with a picture when a person is seen*, and *capture an image when a person is detected*. These are the automations the abandoned integration documented, and they are what most users actually want on day one. They also serve as executable proof of the entity design — if a blueprint is awkward to write, the entity model is wrong.

The integration's job ends at exposing a clean entity surface. What consumes it — a webhook to a vision agent that fetches the image and narrates what is happening, a notification, a light — is composed by the user in ordinary automations. The integration does not interpret; it makes the raw data easy to reach.

SecuritySpy classifies into three buckets out of the box: human, vehicle, animal. It does not detect packages, recognize faces, or describe scenes. Richer meaning comes from whatever service the user points at the image entity. This split is deliberate: unlike a closed doorbell with a fixed vocabulary, the analysis is replaceable and the notification can say whatever the user wants.

That vocabulary is not fixed at three, either. SecuritySpy can run a **user-supplied CoreML model** per camera and push its raw outputs over the same event stream. The integration will not use this in v1, but its event parsing is built to carry arbitrary labels from the start — an integration that hardcodes three class names locks those users out permanently, and no other camera integration in Home Assistant surfaces user-supplied models at all.

Full entity and platform specification is in `addendum.md` §4.2.

## Who This Serves, and What Success Looks Like

**Primary — the author.** Eleven cameras, an existing Home Assistant install, an unmet need, and daily exposure to the results. Success is:

- **"What has been seen?" is answerable from Home Assistant alone** — per camera, when a human, vehicle, or animal was last observed, correct after a restart.
- The two canonical automations work without reading source code: notify with a picture when a person is seen, and save an image on detection — both writable in the UI automation editor, no attribute-name lore required.
- All eleven cameras appear as correctly named devices under one server hub, with no manual renaming.
- At least one end-to-end automation runs in production: detection → image → downstream analysis → a notification a human would actually want to read.
- The existing ONVIF video setup keeps working untouched alongside it.

**Secondary — SecuritySpy users on Home Assistant.** A population visible in Ben Software's forums and the HA community forums, where the abandonment has been discussed, currently with no maintained option. Success is:

- Installs from HACS and configures entirely through the UI: host, port, credentials, done.
- Meets the Bronze quality scale in full; Silver on release.
- Someone other than the author installs it successfully without asking for help.
- Survives a SecuritySpy restart, a Mac reboot, a network drop, and a Home Assistant upgrade without a Home Assistant restart — entities go unavailable and recover on their own.

**Tertiary, deliberately non-binding — Home Assistant core.** Building to the quality scale keeps a core submission possible without committing to one now.

Further acceptance criteria are in `addendum.md` §7.

## Scope

**In, for v1.** Per-camera AI trigger switches — *trigger on human / vehicle / animal* — exposing controls SecuritySpy 6 has and no prior integration surfaced; per-camera *last human / vehicle / animal seen* timestamps, derived from stored classification so they survive restarts; latest-capture image entities; motion and per-class detection binary sensors driven by the live event stream; classification events carrying peak confidence and a captured-file reference; the three SecuritySpy arm modes as per-camera controls; camera and server health; UI config flow with reauth over HTTP or HTTPS; server hub and per-camera devices; push-driven updates reconciled against polled truth, with correct reconnection and unavailability; a separate async typed API library on PyPI; Bronze quality scale in full.

Blueprints for detection notifications and snapshot capture are v1 deliverables, not documentation afterthoughts.

Camera entities are included but **disabled by default** — users like the author already have working video via ONVIF, and duplicate camera entities are noise rather than benefit. Per-camera detection toggles are included too: indoor cameras generate the large majority of classification events, and an observation record dominated by kitchen traffic is not useful to someone watching a driveway.

HTTPS is in scope for v1: the reference server has it enabled, with plain HTTP redirecting to it. The abandoned integration's lack of SSL support would be a blocker here on day one.

**Explicitly out for v1.** Audio — SecuritySpy's RTSP endpoint documents AAC as its default codec and its `++audio` endpoint demonstrably serves AAC, but no audio track was negotiated onto the RTSP stream in testing, and every camera on the reference system sources G.711. Deferred as unresolved rather than impossible. Vision analysis, scene description, package detection, and face recognition — downstream consumers, not the integration. The webhook and agent pipeline itself. Multi-server support. Editing SecuritySpy settings beyond arming. Any opinion about privacy policy — per-camera arming controls are exposed; policy is the user's to compose (see Open Questions).

**Deferred, wanted, not v1.** Capture archive browsing via `media_source`, backed by SecuritySpy's own capture-listing API — the same one behind its web view and iOS app. Wanted; deferred because v1 delivers value without it. Also: latest-clip-as-entity, PTZ and manual-trigger services, discovery, diagnostics, repair issues, full translations, HTTPS.

## Risks and Open Questions

- **`[RESOLVED 2026-08-09]` Classification is continuous and noisy, not discrete.** A live 100-second capture (1,341 events) shows `CLASSIFY` firing per-frame throughout a motion episode — 191 events on one camera in 95 seconds — with confidence swinging violently frame to frame (4 → 100 for a single person crossing the view). Human, vehicle, and animal must therefore be **binary sensors with a confidence threshold and debounce**, not one-shot event entities. A naive event-per-`CLASSIFY` would fire roughly 190 times per person. The event entity should fire once per *episode*, on threshold crossing. See `addendum.md` §8.

- **`[RESOLVED 2026-08-09]` `MOTION_END` cannot be relied on.** One camera produced 467 `MOTION` events and zero `MOTION_END` across 95 seconds. The integration must run its own inactivity timeout to clear motion state.

- **`[RESOLVED 2026-08-09]` An undocumented JSON API exists and is better than the documented one.** A HAR capture of the official web client revealed `++caplist`, `++camStatus`, `++getpreview`, and others — none in the published spec, all verified working. Critically, **`++caplist` persists the classification result against each recording** as a bitmask, so "last human detected" can be poll-derived rather than reconstructed from a noisy stream, and state is correct after a restart. The architecture becomes push-for-latency, poll-for-truth. See `addendum.md` §8.12.

- **`[RESOLVED 2026-08-09]` The automation requirement is an observation record**, not a set of recipes: *"I want to be able to know what people have been seen."* Primary focus is the outdoor cameras. This is what the *last seen* sensors serve directly.

- **`[RESOLVED 2026-08-09]` The integration holds no privacy opinion.** Indoor cameras get no special treatment; per-camera controls are exposed and policy is the user's to compose. Worth noting the indoor cameras produce most of the classification data, which is a usability argument for per-camera detection toggles independent of privacy.

- **Coexistence with ONVIF is the expected topology, not a failure mode.** Home Assistant has no mechanism to merge devices across integrations, so a user running both will see two devices per physical camera. Since video is explicitly not this integration's value, camera entities ship disabled by default and the duplication mostly disappears.

- **Neither incumbent is the obstacle; both are the evidence.** `briis` proved the demand and died of maintainer fatigue. HomeHelper proves the vendor cares but ships a one-way bridge without classification, streaming, or arming. The gap is a *native entity model*, and nothing occupies it.

- **There is no technical moat.** The API is public — though substantially undocumented, which is a modest and temporary advantage to whoever maps it. Anyone could build this. The advantages are non-technical: the incumbent is abandoned and unreplaced; the author runs eleven cameras daily and will notice what breaks; and building to the published quality scale from the start is what makes an integration survivable. **Longevity is the differentiator, and longevity is earned by execution, not by technology.**

- **Sustainability.** The last integration died of maintainer fatigue. Quality-scale discipline reduces but does not eliminate this risk, and adoption creates obligation.
