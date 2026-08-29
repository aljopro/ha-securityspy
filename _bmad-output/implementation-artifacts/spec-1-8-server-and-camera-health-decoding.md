---
title: 'Story 1.8: Server and camera health decoding'
type: 'feature'
created: '2026-08-28'
status: 'done'
baseline_revision: 'e0f0d5b0b5221e3ee2e084fddc466f1d63d31f8d'
final_revision: '157cabbc0ffda02b67ae8568daaa1d1460007755'
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: [oversized]
---

<intent-contract>

## Intent

**Problem:** `++systemInfo` already carries CPU usage, memory pressure, certificate expiry, offered-update version, per-camera frame rate, data rate, and last-error fields (research §10), but `ServerInfo`/`Camera` drop them, and the cheap `++camStatus` poll (794 B vs 27 KB) has no typed accessor at all -- a consumer cannot report health without parsing the heavy payload on every cycle.

**Approach:** Extend `ServerInfo` and `Camera` with the new health fields, decoded via the library's existing tolerant-optional helpers (fail to `None`, never raise), and add `CameraStatus` plus `Client.async_get_camera_status()` reading a new `ENDPOINT_CAM_STATUS` endpoint constant.

## Boundaries & Constraints

**Always:** New fields are additive -- no existing `ServerInfo`/`Camera` field changes name, type or meaning. Every new field is `None` when the server omits it, sends a non-numeric value, or (for fields where only a non-negative value is meaningful: CPU usage, memory pressure, frame rate, data rate) sends a negative one; the surrounding decode still succeeds. `update_version` is empty-string-to-`None`, matching the existing `_as_str` convention. `enabled`, `online`, and `open` on `CameraStatus` stay three independent booleans, never collapsed. The `++camStatus` URL and its response shape stay inside the library. New endpoint/model names are added to `__init__.py`'s `__all__` and import blocks in sorted (RUF022) order, matching the existing `ENDPOINT_*`/model export convention exactly.

**Block If:** the `++camStatus` response envelope actually observed does not match the bare-array `[{num, enabled, online, open, err, errDesc}]` shape research §2.2 documents (e.g. it turns out wrapped in an object) -- decoding logic and tests would need a different shape than this spec assumes.

**Never:** No change to `async_get_server_info`'s signature or the existing decoded fields. No datetime type for `cert-expiry-days` (it is a day count, not a timestamp). No equality check between `update_version` and `version` -- an empty `new-version` is the only "no update" signal the API documents.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full health payload | `++systemInfo` server block has `cpu-usage`, `memory-pressure`, `cert-expiry-days`, non-empty `new-version`; camera has `current-fps`, `data-rate`, `last-error`, `last-error-description` | `ServerInfo.cpu_usage`/`memory_pressure`/`cert_expiry_days`/`update_version` and `Camera.current_fps`/`data_rate`/`last_error`/`last_error_description` all populated and typed | No error expected |
| Fields absent | Server/camera blocks omit all new keys (as in the current fixture, minus `current-fps`/`cpu-usage`/`memory-pressure`/`cert-expiry-days`) | All new fields decode to `None`; existing fields unaffected | No error expected |
| No update offered | `new-version` is `""` | `update_version` is `None`, not `""` | No error expected |
| Malformed/negative health values | `cpu-usage: "n/a"`, `current-fps: "-5"`, `data-rate: "abc"` | Each malformed/negative field is `None`; decode of the surrounding `ServerInfo`/`Camera` still succeeds | No error expected, no exception raised |
| Cheap status poll | `++camStatus` returns `[{"num": 0, "enabled": true, "online": true, "open": false, "err": "", "errDesc": ""}, ...]` | `async_get_camera_status()` returns a tuple of typed `CameraStatus`, one per entry, `enabled`/`online`/`open` independent booleans, empty `err`/`errDesc` decode to `None` | No error expected |
| Camera status entry with no usable number | An entry in the `camStatus` array has a missing/non-numeric `num` | That entry is skipped (same precedent as `Camera.from_api` returning `None` for an unusable camera number); the rest of the tuple still decodes | Skipped and logged at debug, no exception |

</intent-contract>

## Code Map

- `aiosecurityspy/src/aiosecurityspy/const.py` -- edit: add `ENDPOINT_CAM_STATUS: Final = f"{ENDPOINT_PREFIX}camStatus"` next to the other `ENDPOINT_*` constants, citing research §2.2; add to `__all__` (sorts before `ENDPOINT_CAPTURE_LIST`).
- `aiosecurityspy/src/aiosecurityspy/models.py` -- edit: add health fields to `ServerInfo` (lines ~645-716) and `Camera` (lines ~543-586); add a new `_as_float` helper alongside `_as_str`/`_as_int`/`_as_bool` (~line 80-140) for `cpu_usage`/`memory_pressure`/`current_fps`/`data_rate`; add new frozen `CameraStatus` dataclass with a `from_api`/list-decoding entry point following the `Camera.from_api` skip-on-unusable-number precedent (~line 562-586).
- `aiosecurityspy/src/aiosecurityspy/client.py` -- edit: add `async_get_camera_status(self) -> tuple[CameraStatus, ...]` next to `async_get_server_info` (~line 391-408), using `self._request_json(ENDPOINT_CAM_STATUS)` (no `format=json` param needed if the endpoint always returns JSON -- verify against research §2.2's `camStatus` row; add the param only if the existing `_request_json(ENDPOINT_SYSTEM_INFO, {"format": "json"})` precedent implies every endpoint needs it).
- `aiosecurityspy/src/aiosecurityspy/__init__.py` -- edit: export `ENDPOINT_CAM_STATUS` and `CameraStatus` from the `.const`/`.models` import blocks and `__all__`, sorted (RUF022).
- `_bmad-output/planning-artifacts/research/securityspy-api-reference.md` §2.2, §10 -- the field-name and shape source for all decoding above.
- `aiosecurityspy/tests/fixtures/system_info.json` -- edit: extend with `data-rate`, `last-error`, `last-error-description` on at least one camera, and a non-empty `new-version` variant (via inline dict override in tests, not necessarily the shared fixture).
- `aiosecurityspy/tests/test_models.py` -- the `load_system_info()`/`wrap()` pattern (~line 41-46) and inline-dict edge-case style (e.g. `test_negative_permission_mask_grants_nothing`, ~line 173) to follow for the new health-field and `CameraStatus` tests.
- `aiosecurityspy/tests/test_client.py` -- the `FakeSession`/`FakeResponse` harness (~line 78-140) that `async_get_camera_status()`'s test drives.

## Tasks & Acceptance

**Execution:**
- [x] `aiosecurityspy/src/aiosecurityspy/const.py` -- add `ENDPOINT_CAM_STATUS` and its `__all__` entry -- new endpoint needs a named constant per the library's protocol-ownership rule.
- [x] `aiosecurityspy/src/aiosecurityspy/models.py` -- add `_as_float`; add `cpu_usage`, `memory_pressure`, `cert_expiry_days`, `update_version` to `ServerInfo` and its `from_api`; add `current_fps`, `data_rate`, `last_error`, `last_error_description` to `Camera` and its `from_api`; add `CameraStatus` (frozen, `number`/`enabled`/`online`/`open`/`error`/`error_description`) with array decoding that skips unusable entries -- the model layer is where all new state lives.
- [x] `aiosecurityspy/src/aiosecurityspy/client.py` -- add `async_get_camera_status()` -- the cheap-poll accessor the story exists to deliver.
- [x] `aiosecurityspy/src/aiosecurityspy/__init__.py` -- export the new constant and model in sorted order -- keeps the published surface complete and RUF022-clean.
- [x] `aiosecurityspy/tests/test_models.py` -- cover every I/O-matrix row for `ServerInfo`/`Camera`/`CameraStatus` decoding, including the malformed/negative fallback rows and the unusable-`num` skip.
- [x] `aiosecurityspy/tests/test_client.py` -- cover `async_get_camera_status()` against a stubbed `++camStatus` response.
- [x] `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` -- document the new fields and `async_get_camera_status()`.

**Acceptance Criteria:**
- Given the library tree, when `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pytest -q` are run, then all pass with zero findings and every pre-existing test still passes.
- Given a payload built with an added health field and nothing else changed, when decoded, then no existing `ServerInfo`/`Camera` field's name, type, or value changes versus the pre-story fixture.

## Spec Change Log

## Review Triage Log

### 2026-08-28 — Review pass (follow-up 2)
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 0, medium 3, low 3)
- defer: 0
- reject: 11: (high 0, medium 5, low 6)
- addressed_findings:
  - `[medium]` `[patch]` `error_description`/`last_error_description` were decoded independently of their code, so a server sending `err: 0` with a non-empty `errDesc` produced `error is None` alongside a populated description -- the README's documented `if status.error is not None` idiom would hide it, while a consumer reading the description on its own (an HA "last error" sensor, say) would show a permanent stale fault on a healthy camera. Both reviewers raised it independently. The description is now decoded *with* its code on both surfaces and is `None` whenever the code is; added tests for every no-error spelling paired with a description, and for a real code keeping its description. README, CHANGELOG and both field docstrings updated.
  - `[medium]` `[patch]` `const.py`'s `ENDPOINT_CAM_STATUS` comment said the response shape was "reconstructed from a third-party client's source rather than vendor documentation" and should be treated "as reverse-engineered until confirmed against a live server" -- directly contradicting `models.py`/`client.py`/README, which cite a live capture. The planning addendum §8.12 settles it: the shape comes from a HAR capture of the *official* web client, with "all endpoints verified working against the live server". Since the zero-sentinel decoding rule rests on that capture, the weaker provenance claim undercut the load-bearing evidence. Corrected the comment to state what the evidence actually is (observed on a live server, undocumented by the vendor, no compatibility promise).
  - `[medium]` `[patch]` `test_camera_status_request_shape` claimed to pin the no-`format=json` assumption but asserted only the URL -- and `FakeSession` records query parameters in `kwargs`, not the URL, so the test passed identically with or without the parameter. Added the missing `params` assertion, and corrected the docstring's "no stubbed test can catch that" to say what a stub does and does not settle.
  - `[low]` `[patch]` A whitespace-only error code (`"  "`) survived `_as_error_code`: `_as_str` keeps it because it is truthy and `_as_float` cannot parse it, so it fell through the `!= 0` test and reported as a live fault on every poll. Now stripped and folded to `None`; added a test.
  - `[low]` `[patch]` A whitespace-only `new-version` reached `update_version` the same way, producing a spurious "update available" on an up-to-date server. Now stripped; added a test.
  - `[low]` `[patch]` `test_camera_status_non_object_entry_is_skipped` built an empty JSON array only to string-`replace` it away. Replaced with the literal body.

Rejected, with reasons: `CameraStatus`'s `enabled`/`online`/`open` defaulting to `False` on an absent key while `Camera.enabled` defaults to `True` (the intent contract fixes these as three plain booleans and the prior pass ruled on the same substance; a `bool | None` widening is a spec change, not a review fix); a shape mismatch raising the same `SecuritySpyConnectError` as a network failure (rejected on identical grounds in the prior pass -- it matches the `_capture_entries` precedent this story extends); duplicate `num` entries not being deduped or logged (rejected in both prior passes); negative and malformed health readings collapsing silently with no debug log (the intent contract mandates exactly this fallback); `cpu_usage`/`memory_pressure` carrying no documented unit or upper bound (rejected in both prior passes -- the unit question belongs to the consuming HA epic); `_as_error_code` rendering `1` and `1.0` as different strings (it carries the server's own value through by design, and no spelling is documented); `list(payload)` and the `{str(key): ...}` rebuild being redundant copies (cosmetic, and the rebuild is the existing `_capture_entries` convention); `TWO_STATUSES` versus inline `# noqa: PLR2004` (cosmetic, rejected in the prior pass); the fixture carrying the new camera fields on two of three cameras (the third's absence is the "fields absent" row, which is coverage rather than a gap); the 794 B / 27 KB figure appearing in five places (the prior pass deliberately restored the camera count to each); a negative `num` being accepted as a camera identity (matches pre-existing `Camera.from_api` behavior, rejected in the prior pass).

### 2026-08-28 — Review pass (follow-up)
- intent_gap: 0
- bad_spec: 0
- patch: 8: (high 1, medium 4, low 3)
- defer: 0
- reject: 9: (high 0, medium 4, low 5)
- addressed_findings:
  - `[high]` `[patch]` `CameraStatus.error` decoded `err` with `_as_str`, so the **only live capture of this endpoint the project holds** (research addendum §8.12: `{"num":0,...,"err":0,"errDesc":""}`) gives every *healthy* camera `error == "0"` -- and the README's own documented idiom, `if status.error is not None`, would then report the entire inventory as errored. Zero, not just the empty string, is this surface's "no error" sentinel. Added `_as_error_code()` (collapses any zero spelling -- `0`, `0.0`, `"0"`, `"0.0"`, `"-0"` -- to `None`, carries any non-zero code through as the server's own string) and wired it into `CameraStatus.error`; added regression tests for every zero spelling and for non-zero codes surviving.
  - `[medium]` `[patch]` `Camera.last_error` had the identical defect via the same `_as_str` path. Research §10 lists `last-error`/`last-error-description` and `camStatus`'s `err`/`errDesc` as one error surface, and this story's own Design Notes call them "the same concept", so a numeric-zero no-error code is at least as likely there. Applied `_as_error_code()` symmetrically; added a regression test.
  - `[medium]` `[patch]` `_as_float` documented itself as `_as_int`'s counterpart but was materially laxer: bare `float(text)` honours PEP-515 underscores, so a wire `"1_0"` decoded as 10.0 fps while `_as_int` deliberately rejects the same spelling. Added the `"_" in text` guard, corrected the docstring to state the strictness rule, and added a test. (Raised independently by both reviewers.)
  - `[medium]` `[patch]` The spec's Code Map explicitly asked to verify whether `++camStatus` needs `format=json`; the implementation answered it by assumption and left no marker, even though a wrong answer raises `SecuritySpyConnectError` on *every* poll and no stubbed test can catch it. Added an `[ASSUMPTION]` block to `async_get_camera_status`'s docstring, following the codebase's existing marker convention (`client.py`, `models.py`, `stream.py`).
  - `[medium]` `[patch]` The "never compared against `version`" rule was presented as documented API fact in three places; the research establishes only that an up-to-date server sends `new-version` *empty*, not that it never echoes the installed version -- a spurious "update available" in a later epic if it does. Added an `[ASSUMPTION]` marker to `ServerInfo.update_version` recording what the evidence does and does not support. No behavior change (the spec's "Never" clause mandates the omission).
  - `[low]` `[patch]` `test_camera_status_independent_booleans_are_not_collapsed`'s docstring claimed "all eight combinations decode" while asserting exactly one. Parametrized it over all eight, making the claim true rather than trimming it.
  - `[low]` `[patch]` Both skip paths logged unactionably -- neither the offending value nor its position. `CameraStatus.from_api` now logs the rejected `num` value; `async_get_camera_status` now logs the entry index and its actual type.
  - `[low]` `[patch]` The "794 B vs 27 KB" figure was repeated in five places with the one detail that makes it meaningful -- *for 11 cameras* (research addendum §8.12) -- dropped from every copy. Restored the camera count at the constant, the client method, the README and the CHANGELOG.

Rejected, with reasons: the non-negative clamp being re-expressed at four call sites rather than extracted, and frozen dataclasses not enforcing it at construction (a DRY nit true of the library's every field, not a defect of this change); negative health readings collapsing to the same `None` as absent/malformed ones, losing a possible `-1` "not measured" sentinel (the intent contract mandates exactly this fallback -- changing it is a spec decision, not a review fix); units/ranges for `cpu_usage`/`memory_pressure`/`data_rate` being undocumented (already disclosed honestly in the docstrings; the `native_unit_of_measurement` question belongs to the consuming HA epic -- consistent with the prior pass's ruling on `data_rate`); the `memory-pressure: 22` fixture value versus the live capture's `1` (an arbitrary decode-test value either way); `_camera_status_entries` being an over-named eleven-line wrapper (cosmetic); `TWO_STATUSES` in one test file versus inline `# noqa: PLR2004` in another (cosmetic); a missing `enabled`/`online`/`open` key reading as `False` rather than "unknown" (the intent contract fixes these as three plain booleans -- a `bool | None` widening is a spec change); a negative `num` being accepted as a camera identity (matches the pre-existing `Camera.from_api` behavior this story extends, so not a new defect); duplicate `num` entries producing duplicate tuple entries (explicitly rejected on the same grounds in the prior pass).

### 2026-08-28 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 6: (high 1, medium 3, low 2)
- defer: 0
- reject: 8: (high 0, medium 3, low 5)
- addressed_findings:
  - `[high]` `[patch]` `_as_float` crashed with an uncaught `OverflowError` on an oversized JSON integer (e.g. `cpu-usage: 10**400`) -- `math.isfinite()`/`float()` raise rather than returning a value for an int too large to convert, violating the spec's "surrounding decode still succeeds" invariant. Wrapped the int/float branch in `try/except OverflowError` (extracted to `_finite_float()` to keep `_as_float` under the return-count lint limit); added a regression test.
  - `[medium]` `[patch]` The `++camStatus` response shape is reconstructed from a third-party client's source, and research §2.2 itself says "assume no vendor testing here" for this endpoint -- but the CHANGELOG, README, and `const.py` presented the shape as settled fact with no hedge anywhere a consumer would read it. Added a caveat to the `ENDPOINT_CAM_STATUS` docstring comment.
  - `[medium]` `[patch]` No test exercised a negative health reading arriving as a native JSON int/float (only as a string), even though `_as_float`/`_as_int` accept both. Added `test_negative_native_number_server_health_field_is_none`.
  - `[medium]` `[patch]` No test exercised `camStatus` `enabled`/`online`/`open` as string tokens (`"yes"`/`"1"`), even though `system_info.json`'s own fixture proves SecuritySpy serializes booleans this way elsewhere and `_as_bool` already supports it. Added `test_camera_status_string_booleans_decode`.
  - `[low]` `[patch]` No test distinguished an *absent* `err`/`errDesc` key from a present-but-empty one. Added `test_camera_status_missing_error_keys_decode_to_none`.
  - `[low]` `[patch]` Two new test docstrings tripped `ruff` (`E501` line length, `D205`/`D209` docstring formatting) once added; reformatted to pass.

Rejected, with reasons: `async_get_camera_status()` raising the same `SecuritySpyConnectError` for a response-shape mismatch as for a network failure (matches the pre-existing `_capture_entries` precedent this story extends, not a new defect); the `last_error`/`error` naming split between `Camera` and `CameraStatus` (explicit, justified spec design decision, not a bug); no consistency check for `camStatus` entry count (the endpoint carries no separate declared count to check against, unlike `systemInfo`'s `camera-count`); `cert_expiry_days` rejecting a fractional day count via `_as_int`'s strict-integer rule (pre-existing `_as_int` behavior used library-wide, speculative for this field's actual wire shape); `CameraStatus` carrying no camera name (explicitly scoped out by the spec's field list); the `{str(key): item for key, item in entry.items()}` type-checker workaround being duplicated from `_capture_entries` (cosmetic, matches existing convention); `data_rate`'s unit being undocumented (already disclosed honestly in the docstring; a downstream HA-sensor unit-label question belongs to a later epic, not this story); duplicate `num` entries in a `camStatus` response producing duplicate `CameraStatus` tuple entries rather than being deduped like `ServerInfo.cameras` (no AC requires dict semantics here; a per-entry tuple is a reasonable and undocumented-either-way choice).

## Design Notes

**`cert_expiry_days` is not guarded by the non-negative rule.** A negative day count is what an *already-expired* certificate reports, and that is exactly the diagnosable state the field exists to carry -- clamping it to `None` would hide the more urgent case. `cpu_usage`, `memory_pressure`, `current_fps`, and `data_rate` have no such legitimate negative reading, so those do fall back to `None` on a negative value, following `ServerInfo.from_api`'s existing `camera_count < 0` precedent (models.py ~line 700).

**Zero is the "no error" sentinel on both error surfaces, and the wire proves it.** The single live `++camStatus` capture in the repo (research addendum §8.12) shows `"err":0` on a camera that is enabled, online and open -- so the healthy state is a numeric zero, not the empty string the I/O matrix anticipated. `_as_error_code()` therefore collapses every zero spelling to `None` before a code reaches a consumer, and `Camera.last_error` uses the same helper because research §10 files the two keys as one error surface. This is what makes the documented `if status.error is not None` idiom mean "actually erroring"; decoding with plain `_as_str` would have made it mean "is a camera".

**A description is decoded with its code, never on its own.** Once zero became the "no error" sentinel, decoding `errDesc`/`last-error-description` independently left a third state the API has no meaning for: no code, but a description. A consumer surfacing the description directly -- the obvious shape for an HA "last error" attribute -- would then show a stale fault on a camera the library itself calls healthy. Both fields are therefore `None` whenever their code is.

**`CameraStatus.error`/`error_description` mirror `Camera.last_error`/`last_error_description`.** The `camStatus` wire keys are `err`/`errDesc`; naming the decoded fields to match the sibling pair already established on `Camera` in this same story keeps the two error surfaces recognizable as the same concept without duplicating a name.

## Verification

**Commands:**
- `cd aiosecurityspy && uv run ruff check . && uv run ruff format --check .` -- expected: zero findings
- `cd aiosecurityspy && uv run mypy --strict src tests` -- expected: no issues
- `cd aiosecurityspy && uv run pytest -q` -- expected: all pass, every pre-existing test included, new tests covering the I/O matrix above


## Auto Run Result

Status: done — follow-up review pass (no implementation loopback; the story's code was already in place).

**Change made this pass.** Six review patches on top of the existing implementation, one of which is a public-behavior change: an error *description* is now decoded together with its error code on both error surfaces, so `CameraStatus.error_description` and `Camera.last_error_description` are `None` whenever their code is. The rest correct a load-bearing documentation contradiction, close a test that asserted less than it claimed, and fold whitespace-only wire values into the sentinels they obviously are.

**Files changed:**
- `aiosecurityspy/src/aiosecurityspy/models.py` — pair each error description with its code; strip whitespace-only error codes and `new-version`; docstrings for the pairing rule.
- `aiosecurityspy/src/aiosecurityspy/const.py` — correct the `ENDPOINT_CAM_STATUS` provenance note to match the HAR-capture evidence the decoding rules rest on.
- `aiosecurityspy/src/aiosecurityspy/client.py` — the `[ASSUMPTION]` block now states accurately what a stub can and cannot settle about the `format=json` question.
- `aiosecurityspy/tests/test_models.py` — six new regression tests: description-never-outlives-code (both surfaces, every no-error spelling), description-survives-a-real-code, whitespace error code, whitespace `new-version`.
- `aiosecurityspy/tests/test_client.py` — assert the `++camStatus` call sends no query parameters; drop a build-then-string-replace test body.
- `aiosecurityspy/README.md`, `aiosecurityspy/CHANGELOG.md` — document the code/description pairing rule.

**Review findings breakdown:** 6 patches applied (medium 3, low 3), 0 deferred, 11 rejected (5 medium, 6 low) — see the triage log for each rejection's reason. No intent gaps and no spec defects: the intent contract held under both reviewers.

**Verification:** `uv run ruff check .` (all checks passed), `uv run ruff format --check .` (23 files already formatted), `uv run mypy --strict src tests` (no issues in 21 source files), `uv run pytest -q` (780 passed). Run from `aiosecurityspy/`, per the repo's two-suite note.

**Residual risks:** The `++camStatus` shape and the `format=json` question are still settled only by one HAR capture of one server — the `[ASSUMPTION]` markers record this, and a live-server check remains the only thing that can close them. The code/description pairing assumes a description without a code carries no information the library should surface; if a server is ever found that reports a meaningful description alongside a zero code, that is a spec decision to revisit, not a bug to patch.
