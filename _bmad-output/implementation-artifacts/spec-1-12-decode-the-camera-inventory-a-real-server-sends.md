---
title: 'Story 1.12: Decode the camera inventory a real server actually sends'
type: 'bugfix'
created: '2026-08-29'
status: 'ready-for-dev'
review_loop_iteration: 0
followup_review_recommended: false
context: ['{project-root}/_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md']
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `ServerInfo._decode_cameras` looks for `cameralist.camera` or a bare `camera` key. A live 6.21 server sends **`camera-list`** as a top-level array, so `async_get_server_info()` returns an inventory of **zero cameras** against a server reporting eleven -- while `uuid`, `name`, `version` and `camera_count` all decode correctly, making the result look successful. `Camera.from_api` decodes those same live entries perfectly; only the envelope key is wrong. Every camera-scoped requirement in every epic is blocked behind this, and the sole runtime signal today is one debug line.

**Approach:** Locate the camera list across the envelope shapes real servers send, `camera-list` included. Then close the class of failure rather than just this instance: an inventory that cannot be located, or that decodes to nothing while the server reports cameras, becomes a typed decode failure instead of a plausible-looking empty result. Pin it with a fixture captured from a real server, so a shape the server does not send can no longer pass.

## Boundaries & Constraints

**Always:** Every currently-accepted envelope keeps working -- `cameralist.camera` as a list, `cameralist.camera` as a single object, and a bare `camera` key -- because no evidence says which SecuritySpy versions emit them and this story removes no support. `camera-list` is added as a recognised form, holding a list or a single object on the same terms. The list is located from the same `system` mapping the method already receives, so the wrapped (`{"system": ...}`) and bare envelopes both keep working. A **genuinely empty** inventory stays a success: a located list with no entries yields no cameras and no error. Per-entry tolerance is unchanged -- a malformed entry, a `Camera.from_api` rejection and a duplicate camera number each stay a skip-with-debug-log.

**Block If:** none identified -- the live envelope is captured, and the failure is reproduced by decoding that capture through the current code.

**Never:** No change to `Camera.from_api`, to any per-camera field name, or to any other `systemInfo` decoding -- the live capture proves those are correct, and widening the change would put verified-working code at risk. No silent coercion of an unrecognised shape into an empty inventory; that is the defect. No new exception type -- `from_api` already raises `SecuritySpyUnsupportedVersionError` for a payload whose shape is not locatable, and its docstring already says so. No network access from a test; the fixture is a file. No real camera names, addresses, hostnames, paths or server identifiers in that fixture.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Live 6.21 envelope | Top-level `camera-list` array of 11 entries, `camera-count: 11` | All 11 cameras decode, keyed by camera number | No error expected |
| Legacy wrapped envelope | `cameralist: {camera: [...]}` | Decodes exactly as today | No error expected |
| Single-camera object | `cameralist.camera` or `camera-list` holding one object, not a list | That one camera decodes | No error expected |
| Bare `camera` key | `camera: [...]` | Decodes exactly as today | No error expected |
| Genuinely empty server | A located list with zero entries, `camera-count: 0` | An empty inventory, reported as success | No error expected |
| Unlocatable envelope | No recognised camera-list key present at all | `SecuritySpyUnsupportedVersionError` | Typed; never an empty inventory |
| Located but nothing decoded | `camera-count` is positive, yet zero entries survive decoding | `SecuritySpyUnsupportedVersionError` | Typed -- this is the exact symptom of the bug |
| Partial decode | `camera-count: 11`, one entry malformed, 10 decode | The 10 decode; the mismatch stays a debug log | No error -- partial data beats none |
| Count absent | No `camera-count`, list located and decoded | Decodes; `camera_count` falls back to the decoded count as today | No error expected |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: `ServerInfo._decode_cameras` (~line 919). Today: `cameralist = _as_mapping(system.get("cameralist"))` then `raw = system.get("camera") if cameralist is None else cameralist.get("camera")`, with `raw is None` collapsing to `entries = []`. Add `camera-list` to the lookup and distinguish *absent* from *empty*: the method currently cannot tell "no key" from "empty list", which is why the bug is invisible. Return that distinction to the caller rather than deciding policy here.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: `ServerInfo.from_api` (~line 888) already compares `camera-count` against the decoded count and logs a debug line. That comparison is the detection point for the zero-decoded case; promote it per the matrix while leaving the partial-mismatch case a debug log.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- read: `_as_mapping` (~line 324) returns `None` for a list, which is precisely why a top-level `camera-list` array falls through to `system.get("camera")` and then to `[]`.
- `aiosecurityspy/tests/fixtures/` -- new: a scrubbed real-server `systemInfo` capture. See Design Notes for what must be replaced.
- `aiosecurityspy/tests/test_models.py` -- the `ServerInfo.from_api` tests; every envelope row above needs a case, and the fixture-backed test is the one that would have caught this.
- `aiosecurityspy/src/aiosecurityspy/diagnostics.py` -- read: `anonymize()` redacts **credential-shaped keys only**, so it is necessary but *not sufficient* for building the fixture; it leaves camera names, addresses and DDNS intact.
- `_bmad-output/planning-artifacts/research/securityspy-6.21-verification.md` §4.3 -- the six top-level keys a live 6.21 `systemInfo` carries.

## Tasks & Acceptance

**Execution:**
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- recognise `camera-list`, and separate "no camera list found" from "camera list is empty" -- the defect, and the reason it was undetectable.
- [ ] `aiosecurityspy/src/aiosecurityspy/models.py` -- raise `SecuritySpyUnsupportedVersionError` for an unlocatable inventory and for zero-decoded-against-a-positive-count; keep partial mismatches a debug log -- an empty inventory must never again be mistaken for a server with no cameras.
- [ ] `aiosecurityspy/tests/fixtures/` -- add the scrubbed real-server capture -- a fixture the library authored is what let a wrong envelope pass for four stories.
- [ ] `aiosecurityspy/tests/test_models.py` -- cover every I/O-matrix row, including the fixture-backed decode asserting all 11 cameras and a count matching `camera-count`.
- [ ] `aiosecurityspy/CHANGELOG.md` -- record the fix and that an unlocatable inventory now raises where it previously returned empty.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given the fixture, when the pre-fix `_decode_cameras` is restored, then the fixture-backed test fails -- the test must be verified to catch the original defect, not merely to pass beside it.
- Given the committed fixture, when it is inspected, then it carries no real camera name, device name, address, storage path, preset name, server name, hostname, DDNS name, WAN address, LAN address or server UUID.

## Spec Change Log

## Review Triage Log

## Design Notes

**Why an unlocatable inventory raises rather than returning empty.** The two are indistinguishable to a consumer, and the consequences are opposite: an empty inventory says "this server has no cameras, create no entities", while an unlocatable one says "the library does not understand this server". Returning the first for the second is what made a total decode failure look like a working setup for four stories. `SecuritySpyUnsupportedVersionError` is the established carrier -- `from_api` already raises it when the server block is not locatable, and its docstring already promises it for a payload shape that is not locatable.

**Why the zero-decoded cross-check exists at all.** Recognising `camera-list` fixes today's envelope. The cross-check fixes the *class*: if a future version renames the key again, the library fails loudly on the first call instead of silently reporting an empty house. It is deliberately narrow -- only a positive `camera-count` with zero decoded -- so a partially malformed payload still yields the cameras that did decode.

**Building the fixture.** `anonymize()` handles credential-shaped keys, and `systemInfo` carries none in its camera entries, so it is not enough on its own. The capture must additionally have these replaced with synthetic values of the same shape and type: server `uuid`, `name`, `server-name`, `bonjour-name`, `ddns-name`, `wan-address`, `wan-proxy`, `ip1`, `ip2`; and per camera `name`, `device-name`, `address`, `path`, `storage-path`, `preset-name-1..10`. Keep every other value, key order, type and the full 72-key camera shape exactly as captured -- the fixture's worth is that it is *not* idealised.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, every pre-existing test included
- `cd aiosecurityspy && grep -ri "<the real server name>\|<the real ddns name>\|<the real uuid>" tests/` -- expected: no matches, confirming the scrub

**Manual checks (if no CLI):**
- Temporarily restore the pre-fix envelope lookup and confirm the fixture-backed test fails, then restore the fix. A test that passes against both is not testing the defect.
