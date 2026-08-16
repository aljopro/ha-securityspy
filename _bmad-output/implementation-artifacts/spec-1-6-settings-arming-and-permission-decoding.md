---
title: 'Story 1.6: Settings, arming, and permission decoding'
type: 'feature'
created: '2026-08-16'
status: 'done'
baseline_revision: 'd9808e0571a7842b3eb838ba0b623992b5261b9c'
final_revision: 'd681c42'
review_loop_iteration: 0
followup_review_recommended: false  # 4 patches, 1 medium and localized: one transport-frame credential scrub with a mutation-checked test, plus two comment/README corrections. The pass's main output was rejecting a false-positive blocking report, not changing code.
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/research/securityspy-api-reference.md'
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `aiosecurityspy` reads the inventory, the event stream and capture history, but cannot read or change a camera's configuration or arming state. SecuritySpy's settings write is a trap: a partial form-encoded POST whose body must open with the literal `formData` sentinel, carry `cameraNum` in the body rather than the query string (the query form 404s), and write booleans as `1`/`0` while the same fields read back as JSON `true`/`false` (research §8.0). Arming is a different endpoint again — a concatenated mode-letter string against a bounded transient override (§5). Epic 6 consumes all of it, and every asymmetry has to be absorbed here, once, or each call site re-derives it wrongly.

**Approach:** Add a settings/arming plane to the client: a typed `CameraSettings` read model over `++settings-cameras`, a `CameraSettingsPatch` whose rendering owns the sentinel and the boolean write encoding, and an arming write over `++ssSetSchedule` taking three independent capture-mode booleans plus a typed override value. Permission and trigger-reason decoding already exist in `const.py`; this story locks their contract with tests, adds the arm-state read to `Camera`, and gives `SecuritySpyPermissionError` its first caller-facing guard.

## Boundaries & Constraints

**Always:**
- The settings write is `POST` to the bare path `++settings-cameras` with **no query string**, `Content-Type: application/x-www-form-urlencoded`, and a body that begins with the literal sentinel `formData`, then `&cameraNum=<n>`, then the changed fields. The body is assembled by the library as an ordered string, never handed to aiohttp as a dict, because sentinel-first ordering is part of the contract.
- Values are **percent-encoded like `encodeURIComponent`** (space → `%20`), matching the reference body `formData&cameraNum=3&overlayText=Front%20Gate` in research §8.0 verbatim. Not `quote_plus`: whether the server decodes with a form decoder or a URI decoder is unknown, and `%20` is correct under both while `+` is correct under only one.
- Writes are **partial**: only the fields the caller changed are sent. No read-modify-write, no re-posting of untouched keys (research §8.0 verified partial writes safe).
- The boolean asymmetry is absorbed inside the library: reads decode JSON `true`/`false` through the existing `_as_bool`; writes render `True`/`False` as `"1"`/`"0"` inside the patch renderer. No call site ever sees `1`/`0`.
- Arming is `GET ++ssSetSchedule?cameraNum=N&mode=<letters>&override=<id>`. The three capture modes are **independent booleans** (`C` continuous, `M` motion, `A` actions) concatenated in that fixed order; all eight combinations are expressible, including the empty string for none.
- **`schedule=` is never sent and no method mutates a schedule assignment** (AD-7, research §5.3). Schedule ids read from `++systemInfo` are read-only data.
- A settings payload contains per-camera device credentials in plaintext (research §8.3). `CameraSettings` therefore stores only a curated, declared set of non-credential fields — unknown keys are dropped at decode, never retained in a raw dict — and settings payloads are never logged at any level, including debug. Its `__repr__` is hand-written and credential-free, matching the other models.
- Permission and trigger-reason decoding degrade rather than raise: an unknown or disabled bit simply does not appear in the returned `frozenset[str]`, and its absence is not an error. Negative and non-`int` masks yield an empty set (the existing `decode_*` contract, unchanged).
- New models are frozen, slotted, fully typed with `from_api()` constructors and no `Any` in a public signature (AD-15); camera number is `int`; absent values are `None`. New public names are exported from both the defining module's `__all__` and the package `__all__` in RUF022 sorted order.
- Reuse the single transport seam. `_request_json` is refactored so GET-JSON, GET-text and POST-form share one implementation of URL building, BasicAuth, the SSL flag, timeout, status-to-exception mapping, the 8 MiB body cap and the never-echo-the-body rule. No second copy of that logic.
- Zero Home Assistant imports. `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict src tests` and `uv run pytest -q` stay clean with no gate disabled and no blanket ignore, and all 480 pre-existing tests still pass.

**Block If:**
- The library's own gates cannot pass without disabling a gate or adding a blanket ignore.

**Never:**
- Do not add any method, public or private, that deletes captures (`++delete`, `++deleteclip`) or executes shell commands, AppleScript or shortcuts (`doShell`, `doShortcut`) — not wrapped, not private-but-present (AD-2). Do not expose the `aScript` / `aShellCommand` settings keys as writable fields: writing them is shell execution by proxy, so they stay out.
- Do not POST `settings-sched`, `settings-storage` or `settings-web`, and do not send `schedule=` to `++ssSetSchedule`.
- Do not model all ~120 settings keys. Do not retain a raw settings dict on any model.
- Do not invent protocol facts the research does not state: override value `15` is undocumented (the table lists `-1`…`14`) and permission bits 1, 4, 5 and 12+ are undecoded. Leave both alone.
- Do not implement the anonymizer (1.7), Home Assistant entities, switches or repair issues (Epics 2/5/6). Do not change `episodes.py`, `stream.py` or `events.py` behaviour.
- Do not touch `sprint-status.yaml` or add `custom_components/` files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Read settings | `async_get_camera_settings(3)` | `GET ++settings-cameras?cameraNum=3&format=json`; typed `CameraSettings` | — |
| Write one field | patch with `overlay_text="Front Gate"` only, camera 3 | POST to bare `++settings-cameras`, no query string, body exactly `formData&cameraNum=3&overlayText=Front%20Gate`, form-urlencoded header | — |
| Reserved characters | patch value containing `&`, `=`, `+`, `%`, non-ASCII | each percent-encoded UTF-8; a literal `+` survives round-trip as `%2B` | — |
| Partial-write proof | read settings, write one field, read again against a fake applying only posted keys | every other decoded field identical before and after | — |
| Boolean write encoding | patch `motion_capture_triggers_human=True`, `..._vehicle=False` | body carries `mcTriggerMotionH=1&mcTriggerMotionV=0`; no call site sees `1`/`0` | — |
| Boolean read encoding | JSON `{"mcTriggerMotionH": true, "ccMovie": false}` | decoded as Python `True`/`False` | unrecognised token → documented default, no raise |
| Credential keys | settings payload carrying `username`/`password` | absent from every field, `repr` and `str` of `CameraSettings` | — |
| Empty patch | patch with every field `None` | `ValueError` naming the problem; no request issued | Caller mistake |
| Arming, all three | `CaptureModes(continuous=True, motion=True, actions=True)` | query `mode=CMA` | — |
| Arming, none | `CaptureModes(False, False, False)` | `mode=` present and empty — disarming all three is a legal instruction | — |
| All eight combinations | each of the 8 boolean triples | 8 distinct mode strings, letter order always `C`,`M`,`A` | — |
| No schedule mutation | any arming call | query carries `cameraNum`, `mode`, `override` and **no** `schedule` key | — |
| Override data | `arm_override(6)` | typed record: armed, `timedelta(hours=2)`, label | unknown value → `ValueError` |
| Override, until-next | `arm_override(2)` | armed, `duration is None`, `until_next_scheduled` true | — |
| Override, unchanged/none | `arm_override(-1)`, `arm_override(0)` | typed records with `armed is None` and no duration | — |
| Undocumented override | `arm_override(15)` | `ValueError` — not in the published table | Caller mistake |
| Arm-state read | `++systemInfo` camera with `mc-mode`, `cc-schedule-id`, `mc-schedule-override` | `Camera.capture_modes` and `Camera.schedules` populated; absent → defaults `False` / `None` | — |
| Permission decode | `permissions=10207` | `frozenset` of the documented names present in the mask; undocumented bits ignored | No raise |
| Permission absent | mask `0`, negative, non-`int` | empty `frozenset` | No raise |
| Permission guard | `require_permission(camera, PERMISSION_SCHEDULE)` on a camera lacking the bit | `SecuritySpyPermissionError` carrying the permission name and camera number | — |
| Trigger reasons, default install | mask `1` | `{"video_motion"}` — bits 7-16 disabled in SecuritySpy simply do not appear | Absence is not an error |
| Bad camera number | non-`int`, `bool`, or negative camera on any new method | `ValueError` naming the field, no request issued | Caller mistake |
| Write rejected | server answers 401/403 / 500 / non-JSON to a new method | `SecuritySpyAuthError` / `SecuritySpyConnectError`; body never echoed into the message | Typed, as elsewhere |
| Excluded surface | enumerate the public API and grep `src/` | no delete/shell/shortcut name or endpoint string anywhere | — |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `ENDPOINT_SETTINGS_CAMERAS` (`++settings-cameras`), `ENDPOINT_SET_SCHEDULE` (`++ssSetSchedule`), `SETTINGS_FORM_SENTINEL` (`"formData"`), `MODE_CONTINUOUS`/`MODE_MOTION`/`MODE_ACTIONS` letters, and the `ARM_OVERRIDE_*` int constants. `PERMISSION_NAMES`, `TRIGGER_REASON_NAMES`, `decode_permissions`, `decode_trigger_reasons` already live here — read them, do not restate them. `const.py` imports nothing from the library; keep it that way.
- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: `CaptureModes`, `CameraScheduleAssignment`, `ArmOverride` + `ARM_OVERRIDES` + `arm_override()`, `CameraSettings`, `CameraSettingsPatch`, `require_permission()`; extend `Camera.from_api` with arm state. `_as_bool`/`_as_int`/`_as_str` and the hand-written credential-free `__repr__` are the house pattern.
- `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: refactor `_request_json` into a shared `_request` returning decoded text plus thin JSON/text/form wrappers; add `async_get_camera_settings`, `async_set_camera_settings`, `async_set_camera_arming`. `_validated_camera_numbers` is the existing camera-number validator.
- `aiosecurityspy/src/aiosecurityspy/exceptions.py` -- read only: `SecuritySpyPermissionError(permission, camera_number=None)` already exists and is raised nowhere; this story is its first caller.
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: re-export the new surface in RUF022 sorted order.
- `aiosecurityspy/tests/test_client.py` -- the in-process `FakeSession`/`FakeResponse` stub pattern the new client tests follow; it has only `.get()` today and needs a `.post()` recording into the same `calls` list. `session.calls[0]` is how requests are asserted.
- `aiosecurityspy/tests/test_client_transport.py` -- the real in-process aiohttp server; a new verb and endpoint must get a case here.
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §5 (arming, override table, mode letters), §8.0-8.3 (settings read/write, sentinel, credential exposure), §9 (permissions), §3.4 (trigger reasons), §10 (per-camera `*-mode` / `*-schedule-id` fields).
- `git show attempt-preserve/20260810-075208-b5b3-306c15af` -- a prior, complete attempt at this story preserved off the current `main` tip. Usable as reference, but every protocol literal must be re-checked against the research; its `quote_plus` value encoding is a known defect this spec corrects.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add the two endpoint constants, the form sentinel, the three mode letters and the `ARM_OVERRIDE_*` values `-1`..`14`, each with a comment citing research §5.2; note in a comment that `15` is undocumented -- protocol vocabulary belongs in one place, and the gap must be visible rather than silently filled.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: add `CaptureModes` (three booleans, `mode_string` property, `from_api`), `CameraScheduleAssignment` (three schedule ids + three override ids, `from_api`), frozen `ArmOverride` with `ARM_OVERRIDES` mapping and `arm_override(value)` lookup, `CameraSettings` (curated typed fields, `from_api`, credential-free `__repr__`), `CameraSettingsPatch` (all-optional fields, `form_fields()` rendering booleans as `1`/`0` and raising on an empty patch), and `require_permission(camera, permission)`; extend `Camera` with `capture_modes` and `schedules` -- the read/write asymmetry and the override vocabulary must be typed data, not call-site knowledge.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: refactor the transport seam so one implementation serves GET-JSON, GET-text and POST-form; add `async_get_camera_settings`, `async_set_camera_settings` (bare path, sentinel-first ordered body, `encodeURIComponent`-style percent-encoded values, form-urlencoded header) and `async_set_camera_arming` (never sends `schedule=`) -- one seam, so credential handling and error mapping cannot diverge between verbs.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export the new names in `__all__` -- the published API is a contract from first release.
- [x] `aiosecurityspy/tests/test_settings.py` -- create: cover every I/O-matrix row, including the byte-exact sentinel body, the reserved-character encoding row, all eight mode combinations, the read-write-read partial-update proof against a fake that applies only posted keys, and a test asserting a settings payload carrying `username`/`password` leaves no trace in the model's fields, `repr` or `str`.
- [x] `aiosecurityspy/tests/test_client.py` -- edit: give `FakeSession` a `.post()` recording into the same `calls` list -- the stub must be able to observe a verb it has never seen.
- [x] `aiosecurityspy/tests/test_client_transport.py` -- edit: add a case proving the form POST reaches a real aiohttp server with the bare `++settings-cameras` path, no query string, the urlencoded content type and a body starting with `formData` that the server's own form parser decodes back to the original value; and one proving `++ssSetSchedule` carries `mode`/`override` and no `schedule` -- the stub cannot prove aiohttp honours these.
- [x] `aiosecurityspy/tests/test_package.py` -- edit: assert the public API contains no name and `src/` no endpoint string matching capture deletion, `doShell`, `doShortcut` or `deleteclip` -- AD-2's exclusion is an enumerable property, so enumerate it.
- [x] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- edit: a runnable snippet reading settings, writing one field and arming a camera, stating that the override is transient and bounded and that schedules are read-only -- the "usable from an ordinary script" criterion, and transience is the thing a consumer will otherwise assume wrong.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and the 480 pre-existing tests still pass.
- Given `grep -rn` over `src/`, when searching for `doShell`, `doShortcut`, `deleteclip`, `++delete`, `aScript` and `aShellCommand`, then there are no matches outside a comment recording the exclusion.
- Given a consumer running `mypy --strict` against code importing the new surface, then every public name resolves through `__all__` with complete type information and no `Any` in a public signature.
- Given the library at debug log level while reading and writing settings, when the log output is inspected, then no settings payload and no credential appears at any level.

## Spec Change Log

## Review Triage Log

### 2026-08-16 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 1, low 3)
- defer: 2: (high 0, medium 2, low 0)
- reject: 13
- addressed_findings:
  - `[medium]` `[patch]` The credential scrub stopped one frame short of the frame that holds the bytes. `async_get_camera_settings` scrubs `payload`/`mapping`, but `_request` binds `chunks`, `raw` and the walrus-bound `chunk` — the whole `++settings-cameras` body, plaintext device password included (research §8.3) — and every failure exit from the read (byte cap, undecodable body, socket dropped mid-stream) raises from inside *that* frame, leaving the payload in a traceback frame local no caller-level scrub can reach. Now an unconditional `try/finally` in `_request`. `chunk` was the operative leak: clearing only `chunks` and `raw` still failed the new test.
  - `[low]` `[patch]` New test `test_the_transport_frame_holds_no_payload_when_the_read_itself_fails` walks the traceback for `aiosecurityspy.*` frames on a mid-read `ConnectionResetError`. Mutation-checked: it fails without the `finally`.
  - `[low]` `[patch]` `SETTINGS_PAGE_KEY_QUORUM`'s comment argued the bar "costs nothing" because a real page carries all 23 keys, while the constant sat at exactly the 3 ordinary words the same comment names as the threat — so a body of `{name, brightness, contrast, error}` still clears it. Comment corrected to state what the quorum does and does not exclude, and why raising it needs a second server version to read. Threshold deliberately unchanged: this is a public read path and there is no evidence to justify re-tightening it unattended.
  - `[low]` `[patch]` README example guarded a *read* under a comment saying "run it before any write", and indexed `info.cameras[3]` with no existence check (`KeyError` on any server without camera 3). Comment now says "before touching a plane" and names that `camera_control` covers reading the settings page too; lookup uses `.get`.
- notes:
  - Both review subagents reported, as blocking, that `client.py:850` (`except RuntimeError, LookupError:`) is a Python 2 syntax error making the package unimportable and every test in the story uncollectable. **This is a false positive** and is the source of several derived findings ("no test has ever run", "the CHANGELOG's verification claims are unsupported"), all rejected with it. PEP 758 makes unparenthesized `except` tuples valid in Python 3.14; the project sets `requires-python = ">=3.14"` and `target-version = "py314"`, and `ruff format` normalizes *to* that form — it reverted a parenthesizing edit twice. Both reviewers validated with the system Python 3.11. On the project interpreter (3.14.4) the module parses and all gates pass. Recorded here because the same trap will catch the next reviewer.
  - Also rejected: "the strict decode path is unguarded" — `_decode_body` is called at `client.py:796` inside the `try` whose handlers at 797/808 already catch `RuntimeError`, `UnicodeDecodeError` and `LookupError`. And "`_as_arm_mode` silently decodes integer `2` to disarmed" — `_as_bool` maps `2` to `True`, and logs every non-`None` value it cannot decode, so the unlogged-silent-disarm case does not exist.

### 2026-08-16 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 13: (high 1, medium 5, low 7)
- defer: 0
- reject: 6
- addressed_findings:
  - `[high]` `[patch]` `async_set_camera_arming` validated only the `int` branch of `override: ArmOverride | int`. `ArmOverride` is public and freely constructible, so a hand-built `ArmOverride(value=15, ...)` reached the wire unvalidated — precisely the undocumented value the method's docstring, the README and the CHANGELOG all promise it rejects, arriving through the typed door instead of the int one. Every override now goes through `arm_override()` whichever branch it came from.
  - `[medium]` `[patch]` The `++settings-cameras` payload carries the camera's device password in plaintext, and `async_get_camera_settings` left it bound to `payload`/`mapping` in the frame it raised from — so Sentry, `cgitb` and `pytest --showlocals` would print it verbatim. Dropping the raw dict from the *returned model* was never enough. Both locals (and `_request_json`'s `body`) are now deleted before the raise, with a test that walks the exception's traceback frames asserting the sentinel password appears in none of them.
  - `[medium]` `[patch]` `form_fields()` tested `isinstance(value, bool)` before anything else, so `CameraSettingsPatch(name=True)` rendered `{"name": "1"}` and renamed the camera to "1". A `bool` is an `int` and reads as one to every runtime check, so only the field's *declaration* can decide the write encoding; the renderer is now keyed off `_SETTINGS_BOOL_KEYS`.
  - `[medium]` `[patch]` An empty or unrelated JSON object decoded to an all-default `CameraSettings` indistinguishable from a genuinely configured camera — the mapping check only asked whether the body was a `dict`. It now requires at least one curated settings key, via a `SETTINGS_PAGE_KEYS` derived from the same allowlist.
  - `[medium]` `[patch]` `require_permission` accepted any string, and an unknown name can never be granted by any camera — so a misspelling denied every camera unconditionally, dressing a caller bug as a permission failure. Unknown names now raise `ValueError` naming the valid set, derived from `PERMISSION_NAMES` so the two cannot drift.
  - `[medium]` `[patch]` `_as_arm_mode` fell through to `_as_bool` for any spelling it did not know, which returns `False` — reporting an armed camera as disarmed, silently, on a security product, for a field whose wire spelling research §10 does not record. The unrecognised token is now logged at debug (`*-mode` comes from `++systemInfo` and carries no credential), making an unrecorded spelling discoverable.
  - `[low]` `[patch]` `_as_str` folds `""` to `None`, so a *cleared* overlay text was indistinguishable from a page that never carried the key — and only the first is something a consumer can write back. A settings-local coercion now preserves the empty string.
  - `[low]` `[patch]` The read allowlist and the write field tables were two hand-maintained lists with nothing asserting they agree; the entire credential-safety argument rests on the allowlist being one source of truth. A parity test now pins decoded fields, writable fields and wire keys to each other.
  - `[low]` `[patch]` `_validated_camera_number` was a copy of the plural validator's loop body with a divergent message. The plural now delegates to the singular, so the read and write paths cannot drift about what a camera number is.
  - `[low]` `[patch]` The README example read the camera *before* the write and then printed `camera.capture_modes` under a comment claiming it was the current arm state — `Camera` is frozen, so it printed the pre-write state. It also placed `require_permission` after the settings write, leaving the more consequential call unguarded. Both corrected.
  - `[low]` `[patch]` `CaptureModes.__repr__` and `CameraScheduleAssignment.__repr__` were byte-identical hand-written copies of the repr the dataclass already generates, justified as "cannot carry credentials" for classes whose fields are exclusively `bool` and `int | None` — boilerplate to keep in sync by hand, with nothing suppressed. Deleted, with a comment recording why the custom reprs elsewhere stay. Conversely `Camera.__repr__` named the new `capture_modes` but not `schedules`; it now names both.
  - `[low]` `[patch]` The "empty `mode` means disarm all three" semantic — the library's one departure from every other client — was proven only against the stub's `params` dict. A real-socket test now asserts `mode=` survives yarl's query encoding present-but-empty.
  - `[low]` `[patch]` The arming write is a state-changing `GET`, so the camera number and arm state land in proxy logs and `Referer` headers. That is SecuritySpy's protocol and not the library's choice, but a module documenting redirect handling and body echoing at length said nothing about it. Noted on the endpoint constant.
- Rejected (recorded for traceability, not acted on): checking the write receipt's body for a `camUpdate` acknowledgement (research documents no failure shape, so any check would be invented, and the spec forbids inventing protocol facts — a false negative on a successful write is worse than the gap); range-validating settings values such as `motionSensitivity` (same reason — no published bounds, and guessing them would reject legal writes); collapsing the discarded return of `_request_text`/`_post_form` and its `_decode_body(response: Any)` seam (a real simplification, but churn on the one working transport seam outweighs it, and the decode does prove the body was readable); `test_package.py` scanning only `src/` and exempting comment lines (that is exactly what the acceptance criterion specifies); runtime coercion of non-`bool` `CaptureModes` fields and non-`int` patch values (statically typed, and the library's runtime guards exist where *wire* data and camera numbers enter, not on every field); and the absence of an upper bound on camera numbers (no published maximum).

### 2026-08-16 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 5: (high 0, medium 3, low 2)
- defer: 0
- reject: 13
- addressed_findings:
  - `[medium]` `[patch]` The "is this a settings page?" guard accepted on a **single** overlapping key (`bool(SETTINGS_PAGE_KEYS & mapping.keys())`), and `name`, `brightness` and `contrast` are ordinary words. A reverse-proxy error page or wrong-endpoint body like `{"name": "...", "error": "camera not found"}` therefore decoded to a `CameraSettings` reporting every trigger `False` and every sensitivity `None` — indistinguishable from a camera whose detection is genuinely all switched off, which on a security product is the wrong way to be wrong. The previous pass added this check but only ever tested it against `{}`. Now requires `SETTINGS_PAGE_KEY_QUORUM` (3) curated keys; a real page carries all 23, so the bar costs nothing. The transport fixture's 2-key stub body was made representative rather than the guard weakened.
  - `[medium]` `[patch]` The credential scrub was branch-local: `del payload, mapping` ran on the refusal branch and the success return, so a raise from inside `CameraSettings.from_api` left the plaintext device password bound in the frame — exactly the exposure the previous pass's scrub was written to close, reachable by a different exit. Now a `try/finally`, making the guarantee unconditional. Mutation-checked: removing the `finally` fails both this and the pre-existing scrub test.
  - `[medium]` `[patch]` The README's worked example guarded the **settings write** with `require_permission(camera, "schedule")` — the arming permission — and its comment claimed `"files"` covers settings reads. A reader copying the pattern ships a guard that passes while the server rejects the write. Now guards the settings write with `"camera_control"` and the arming call with `"schedule"`, stating they are separate grants.
  - `[low]` `[patch]` `CameraSettings.from_api` restates the attribute→wire-key pairing by hand, and the existing parity test compared only *set equality* — swapping `humanSensitivity` and `vehicleSensitivity` inside `from_api` kept both sets identical while `human_sensitivity` silently reported the vehicle threshold, and a read-then-patch round trip would write the wrong value back to the camera. A sentinel-value test now pins the pairing itself; mutation-checked against that exact swap.
  - `[low]` `[patch]` The lenient (`strict_encoding=False`) decode path introduced by this story was dead-untested: no test supplied a write receipt with a bogus charset or undecodable bytes. Both are now covered for the settings POST and the arming GET, asserting a write the server accepted is not reported as failed because its discarded receipt was malformed.
- Rejected (recorded for traceability, not acted on): both reviewers reported the unparenthesized `except A, B:` (PEP 758) as a syntax error and one called the working tree "broadly broken" — an artifact of running `ast.parse` under Python 3.11/3.13 when the project declares `requires-python = ">=3.14"`, where the syntax is valid and the suite passes; checking the write receipt for a `camUpdate` acknowledgement and range-validating settings ints (both re-raised from the previous pass and rejected for the same reason — the spec forbids inventing protocol facts the research does not state); `override=-1` reaching the wire (research §5.2 publishes `-1`, so transmitting it is correct, not a leaked sentinel); `CaptureModes()` disarming all three (the spec's I/O matrix specifies exactly this, and all eight combinations are the design); adding a `None`/"unchanged" mode state and making `_as_arm_mode` return `bool | None` (public API changes beyond this story's contract, which specifies `absent → False`); `require_permission` gaining optional enforcement inside the client methods (the Design Notes rule this out deliberately — the library holds no camera inventory); runtime type-guards on statically typed patch and `CaptureModes` fields and on `require_permission`'s `camera` argument (re-raised from the previous pass, rejected for the same reason); `cc-mode` non-zero ints other than `1`; the two divergent `FakeSession` stubs (real duplication, but the house rule forbids a `conftest.py` and the spec directed both); and `test_package.py`'s comment exemption (re-raised from the previous pass — it is what the acceptance criterion specifies).

## Design Notes

**The sentinel is ordering, not just content.** The server's own client builds the body as `let str='formData'; for(pair of formData.entries()) str+='&'+k+'='+v`. Handing aiohttp a dict would let it choose its own ordering, so the body is assembled as a string:

```python
parts = [SETTINGS_FORM_SENTINEL, f"cameraNum={number}"]
parts.extend(f"{key}={quote(value, safe='')}" for key, value in fields.items())
body = "&".join(parts)
```

`form_fields()` returns already-stringified values, which is where `True` became `"1"` — the asymmetry has exactly one home. `quote(..., safe="")` and not `quote_plus`: research §8.0's observed body is `overlayText=Front%20Gate`, so the reference client percent-encodes rather than plus-encodes, and `%20` decodes to a space under a URI decoder *and* a form decoder while `+` only does under the latter.

**Why the read model drops unknown keys.** `++settings-cameras` returns the camera's `username` and `password` in plaintext alongside ~120 other keys. A model that kept a raw dict would carry live credentials into every consumer's diagnostics, and 1.7's anonymizer would then be load-bearing for a leak a curated decode simply never creates. Dropping unknown keys costs a code change per newly-needed field; that is the right trade.

**Arming writes the override, never the schedule.** `++ssSetSchedule` also accepts `schedule=`, which permanently reassigns the camera's schedule — the endpoint name is misleading. This library sends only `cameraNum`, `mode` and `override`, and the absence of `schedule=` is asserted in a test rather than left as a convention.

**Permissions were already decoded; this story makes them enforceable.** `decode_permissions` and `Camera.has_permission` shipped in 1.2. What was missing is the failure path: `SecuritySpyPermissionError` existed unused. `require_permission` is a pure, synchronous guard so a consumer can refuse an arming call without a round trip; the client methods do not call it themselves, because the library holds no camera inventory and must not fetch one to serve a write.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, the 480 pre-existing included
- `grep -rn "doShell\|doShortcut\|deleteclip\|++delete\|aScript\|aShellCommand" aiosecurityspy/src/` -- expected: no matches outside an exclusion comment
- `grep -rn "schedule=" aiosecurityspy/src/aiosecurityspy/client.py` -- expected: no matches
- `grep -rn "quote_plus" aiosecurityspy/src/aiosecurityspy/client.py` -- expected: no matches

**Manual checks (if no CLI):**
- The settings write body, as asserted in `test_settings.py`, begins with `formData` and contains `cameraNum`; the request URL for that call carries no query string.



## Auto Run Result

Status: done — follow-up review pass over the story-1.6 settings/arming/permission plane.

**Change in this pass.** No re-derivation: the story's implementation was already in place and correct. This pass closed one real credential-exposure gap in the transport seam, corrected two pieces of prose that overstated or misdescribed what the code does, and rejected a false-positive "blocking" report from both review subagents.

**Files changed**
- `aiosecurityspy/src/aiosecurityspy/client.py` — `_request` now clears `chunks`, `raw` and `chunk` in an unconditional `finally`, so a read that fails mid-stream cannot leave the plaintext settings payload bound as a traceback frame local.
- `aiosecurityspy/tests/test_settings.py` — new frame-locals test for that path, plus the `_MidStreamFailureResponse`/`_FailingContent` stubs it needs.
- `aiosecurityspy/src/aiosecurityspy/models.py` — comment-only: `SETTINGS_PAGE_KEY_QUORUM` now states honestly what the quorum excludes and why it is not raised.
- `aiosecurityspy/README.md` — worked example guards the settings *read* correctly and no longer `KeyError`s on a server without camera 3.

**Review findings breakdown.** 4 patches applied (1 medium, 3 low), 2 deferred, 13 rejected, 0 intent gaps, 0 spec loopbacks. The largest single category of rejections traces to one shared false premise: both subagents validated the code with Python 3.11 and reported `except RuntimeError, LookupError:` as a fatal Python 2 syntax error. PEP 758 makes that form valid on Python 3.14, which is what this project requires and what `ruff format` normalizes to. See the triage log for the full note.

**Verification.** All four gates run on the project interpreter (CPython 3.14.4), from `aiosecurityspy/`:
- `uv run ruff check .` — All checks passed
- `uv run ruff format --check .` — 20 files already formatted
- `uv run mypy --strict src tests` — no issues in 18 source files
- `uv run pytest -q` — 584 passed (583 before this pass, +1 new test)

The new scrub test was mutation-checked: it fails against the pre-patch `_request`, and it also failed against a first fix that cleared `chunks` and `raw` but not the walrus-bound `chunk` — which is how that leak was found.

**Residual risks.** Both deferred items are unresolvable without a live SecuritySpy server: writes report success on any 2xx with the acknowledgement discarded unread, and `override=-1` is sent on the wire despite being documented as a client-side sentinel. Neither is a regression from this pass. The `SETTINGS_PAGE_KEY_QUORUM` objection is real but was deliberately left as a documented trade rather than tightened on a public read path without evidence.
