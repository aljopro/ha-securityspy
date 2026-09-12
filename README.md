# SecuritySpy for Home Assistant

A Home Assistant integration for [Ben Software SecuritySpy](https://www.bensoftware.com/securityspy/), the macOS video-surveillance server: cameras, capture history, live detection events, and arming controls as native Home Assistant devices and entities — not a `generic` camera entity pointed at an IP address.

**Status: early, active development.** The custom component is not yet feature-complete and is not on the default HACS store. If you install it today, expect to add a server and see it connect over the config flow (below); most of the entities and controls described in the [roadmap](#roadmap) are not there yet. Track progress in [`_bmad-output/planning-artifacts/epics.md`](_bmad-output/planning-artifacts/epics.md) and [`_bmad-output/implementation-artifacts/sprint-status.yaml`](_bmad-output/implementation-artifacts/sprint-status.yaml).

## Why this exists

The previous SecuritySpy integration for Home Assistant ([`briis/securityspy`](https://github.com/briis/securityspy)) was archived in 2024 and its backing library has not shipped since 2022 — HACS quietly dropped it from the default store, and users found out when it broke. SecuritySpy 6 also shipped a JSON API, undocumented but reverse-engineered here, that exposes per-recording object classification (human/vehicle/animal) SecuritySpy has already computed and stored. Nothing in Home Assistant has ever been told about it.

This project's headline goal is an **Observation Record**: what SecuritySpy has seen, on which camera, and when — correct immediately after a Home Assistant restart, kept current by the live event stream, and made durable by the capture history SecuritySpy already maintains on disk. Video streaming already works today over ONVIF; that is deliberately not this project's focus.

## Requirements

- Home Assistant 2026.8.0 or newer
- A SecuritySpy server (6.x) reachable on your network, with a configured user account
- Network access from Home Assistant to the SecuritySpy server's web-server port

## Installation

### HACS (custom repository)

This integration is not yet on the default HACS store. Add it as a custom repository:

1. HACS → the **⋮** menu (top right) → **Custom repositories**
2. Repository: `https://github.com/aljopro/ha-securityspy`, Type: **Integration**
3. Install **SecuritySpy**, then restart Home Assistant

### Manual

Copy `custom_components/securityspy` into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Setup

1. **Settings → Devices & Services → Add Integration**, search for **SecuritySpy**
2. Enter your server's host, port, and the username/password of a SecuritySpy user account
3. If the server uses HTTPS, enable it in the form; certificate verification is on by default and can be turned off for a self-signed certificate

A least-privileged SecuritySpy account is supported and recommended: this integration is designed to create only the entities and controls that account is actually permitted to use, and to distinguish a wrong password from a missing permission rather than looping you through reauth for a permission problem.

## Roadmap

The full plan lives in the [PRD](_bmad-output/planning-artifacts/prds/prd-ha-securityspy-2026-08-09/prd.md) and [epics](_bmad-output/planning-artifacts/epics.md). At a high level:

- **Connect and model** — a SecuritySpy server as a hub device, each camera as a device beneath it, named and identified correctly with no manual renaming
- **Reliability** — entities report unavailable rather than stale on disconnect, and recover without user intervention
- **Live detection** — per-class presence, classification events with peak confidence, motion presence, and configurable per-camera tuning
- **The Observation Record** — the latest capture as a fetchable image, its object classes, a "download latest recording" service, and a record that survives a restart
- **Arming** — each capture mode (continuous, motion, actions) controllable independently, with state that follows what SecuritySpy itself reports
- **HACS and quality scale** — installable from the default HACS store, targeting Home Assistant's Silver quality scale

## Architecture

All SecuritySpy protocol knowledge — endpoint URLs, event-stream framing, bitmask and capture decoding, credential-safe diagnostics — lives in [`aiosecurityspy`](https://github.com/aljopro/aiosecurityspy), a standalone, async, fully-typed Python library [published independently on PyPI](https://pypi.org/project/aiosecurityspy/). This integration only ever consumes the published package (never an in-tree copy) and adds nothing that talks to SecuritySpy's wire format directly. See the library's own README if you want to use it outside Home Assistant, or its `docs/securityspy-openapi.yaml` for the reverse-engineered API description itself.

## Contributing / issues

Issues and pull requests are welcome at [github.com/aljopro/ha-securityspy](https://github.com/aljopro/ha-securityspy). This project is built with the [BMad](https://github.com/bmadcode/bmad-method) planning-and-implementation workflow; the full paper trail — PRD, architecture, epics, and per-story specs — lives under [`_bmad-output/`](_bmad-output/).

## License

MIT — see [`LICENSE`](LICENSE).
