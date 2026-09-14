---
status: blocked
---

# BMad Dev Auto Result

Status: blocked

Blocking condition: intent gaps. Story 2.6 needs a live still-image method that `aiosecurityspy` 0.3.0
does not have. The integration can't supply that method itself, and adding it takes a library release that
this unattended run should not cut.

## Auto Run Result

State established before the halt. Only one file was rewritten:
`epic-2-context.md`, which was stale because `epics.md` is newer and was recompiled by subagent. No
integration or library code was touched and no spec was written.

- Workflow customization: no prepend or append steps, and no `on_complete` hook.
- Version control: tree clean on `main`, which matches the recent epic-2 story commits.
- Continuity source: `spec-2-5-know-when-a-securityspy-update-is-available.md` (`done`).
- Planned spec path: `spec-2-6-live-video-without-exposing-credentials.md` (not created).

### Evidence for the block

- AC 2 in `epics.md` (around line 943) says the entity's still image "comes from SecuritySpy's snapshot
  endpoint with header authentication, not from the stream".
- Library 0.3.0's endpoints are systemInfo, eventStream, caplist, camStatus, settings-cameras,
  ssSetSchedule, getpreview and getfile. There is no `++image`. The only JPEG method is
  `async_get_capture_preview(capture)`, and it serves recorded captures, not live frames.
- AGENTS.md AD-2 says all SecuritySpy protocol knowledge lives in the library. The integration
  therefore can't call `++image` itself, and it can't reach the private `_ConnectionSettings.auth_header`.
- AGENTS.md says library changes ship as a release in `/Users/jensen/projects/aiosecurityspy`, with the pin
  bumped in both `manifest.json` and `pyproject.toml`. PyPI has only 0.1.0, 0.2.0 and 0.3.0.
- Research §`securityspy-6.21-verification.md` (around line 821) confirms `++image?cameraNum=N` returns
  `200 image/jpeg` and honours `width=` and `quality=`. This is enough to specify the library method.

### Questions for Jensen

1. Should a library story come first, for example 1.20 `async_get_camera_image(camera_number, *, width=None,
   quality=None)` released as 0.4.0 or as a pre-release pin? Or do you want to authorize this run to
   cut that library change and release?
2. Or should AC 2 be relaxed, so the still image comes from HA's stream-derived frame for now?

### Other findings for planning (not blocking)

- The integration has no options flow yet. The option name also differs: epic context and
  `docs/ha-integration-reference.md` use `create_camera_entities`, while the AC wording is "Create live
  video entities".
- Tokens from `RtspRelay` live as long as the relay and can't be revoked one at a time. Turning the option
  off therefore has to stop the relay, or reload the entry, to "stop issuing their addresses".
- Deferred item (story 2.4): a camera added after setup gets no entities until reload. Camera entities
  would inherit this gap.

## Resumption

Settle question 1 or 2. Once the library method is released and pinned, or AC 2 is amended, re-run
`/bmad-dev-auto 2-6`.
