---
title: "Home Assistant Integration Development — Engineering Reference"
status: living
created: 2026-08-09
updated: 2026-08-09
verified_against: "developers.home-assistant.io, August 2026 (HA 2026.8)"
---

# Home Assistant Integration Development — Engineering Reference

Working reference for engineers building `ha-securityspy`. Every pattern here is written the way **this project's** architecture spine requires it, not generically — so code copied from here already complies with the ADs. Where a pattern is a quality-scale rule, the rule name is given so CI failures are traceable.

Upstream source of truth: <https://developers.home-assistant.io>. Verify against it when something here looks stale.

---

## 1. File structure and manifest

```
custom_components/securityspy/
  __init__.py          # setup/unload, runtime_data, exception mapping
  manifest.json
  coordinator.py       # the single coordinator
  config_flow.py
  entity.py            # base entities: device_info + availability
  const.py
  diagnostics.py
  repairs.py
  services.py
  sensor.py binary_sensor.py event.py image.py switch.py select.py number.py camera.py update.py
  strings.json
  icons.json
  translations/en.json
```

`common-modules` (Bronze) is why `coordinator.py` and `entity.py` have those exact names — hassfest checks for them.

### manifest.json

```json
{
  "domain": "securityspy",
  "name": "SecuritySpy",
  "codeowners": ["@jensenchappell"],
  "config_flow": true,
  "documentation": "https://github.com/<owner>/ha-securityspy",
  "integration_type": "hub",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/<owner>/ha-securityspy/issues",
  "quality_scale": "bronze",
  "requirements": ["aiosecurityspy==0.1.0"],
  "version": "0.1.0"
}
```

Key notes for this project:

- **`version` is required for custom integrations** (it is forbidden for core ones). HACS reads it.
- **`integration_type: "hub"`** — a SecuritySpy Server is a gateway to multiple cameras. This is what makes the hub/camera device hierarchy idiomatic.
- **`iot_class: "local_push"`** — we have a real push stream. This is also the justification for exempting `appropriate-polling`.
- **`requirements`** pins the library exactly (AD-14). Never vendor the library into the integration.

---

## 2. Runtime data and setup (`runtime-data`, `test-before-setup`)

`hass.data[DOMAIN]` is forbidden by the Bronze `runtime-data` rule and is machine-validated. Use a typed config entry alias.

```python
# const.py
DOMAIN = "securityspy"

# coordinator.py
type SecuritySpyConfigEntry = ConfigEntry[SecuritySpyRuntimeData]

@dataclass
class SecuritySpyRuntimeData:
    """Everything the integration owns for one config entry."""
    coordinator: SecuritySpyDataUpdateCoordinator
    client: SecuritySpyClient
```

```python
# __init__.py
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR, Platform.CAMERA, Platform.EVENT, Platform.IMAGE,
    Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.UPDATE,
]

async def async_setup_entry(hass: HomeAssistant, entry: SecuritySpyConfigEntry) -> bool:
    """Set up SecuritySpy from a config entry."""
    session = async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL])
    client = SecuritySpyClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,                      # AD-2 / Platinum inject-websession
    )

    # test-before-setup: fail fast with the right exception type (AD-6)
    try:
        server = await client.async_get_server_info()
    except SecuritySpyAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except SecuritySpyUnsupportedVersionError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="unsupported_version"
        ) from err
    except SecuritySpyConnectError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err

    coordinator = SecuritySpyDataUpdateCoordinator(hass, entry, client, server)
    await coordinator.async_start()           # hydrate + open stream, non-blocking for FR-2

    entry.runtime_data = SecuritySpyRuntimeData(coordinator=coordinator, client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SecuritySpyConfigEntry) -> bool:
    """Unload a config entry — config-entry-unloading (Silver), FR-33."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.coordinator.async_shutdown()
    return unload_ok
```

**`async_on_unload`** is the mechanism that makes FR-33 ("no task, connection, or timer survives unload") achievable — register every listener and timer through it rather than tracking them by hand.

### Services (`action-setup`)

Bronze requires service actions to be registered in `async_setup`, **not** `async_setup_entry`, so they exist even when no entry is loaded and can raise a clear error instead of silently not existing.

```python
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)     # services.py
    return True
```

---

## 3. The coordinator — push-fed, no interval (AD-4)

This is the pattern the architecture mandates and it is explicitly supported upstream: *"you can still use the data update coordinator if you want by not passing polling parameters `update_method` and `update_interval`,"* then calling `async_set_updated_data(data)` when new data arrives.

```python
class SecuritySpyDataUpdateCoordinator(DataUpdateCoordinator[SecuritySpyData]):
    """Single coordinator per config entry. Sole writer of SecuritySpyData (AD-15)."""

    config_entry: SecuritySpyConfigEntry

    def __init__(self, hass, entry, client, server) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,          # AD-4: push-fed, we schedule our own polls
        )
        self.client = client
        self.server = server
        self._auth_failures = 0            # AD-18: one counter, both planes

    async def async_start(self) -> None:
        """Hydrate from the poll plane, then open the push plane."""
        await self._async_reconcile()                       # FR-2: correct before first event
        self.client.stream.subscribe(self._handle_event)
        self.client.stream.on_reconnected(self._handle_reconnected)
        await self.client.stream.async_connect()

    @callback
    def _handle_event(self, event: SecuritySpyEvent) -> None:
        """Push plane. May only ADVANCE state (AD-1/AD-16)."""
        new_data = merge_push(self.data, event)             # AD-16: the one merge function
        self.async_set_updated_data(new_data)
```

**Do not** call `async_set_updated_data` from an entity, a platform, or a service. The coordinator is the sole writer (AD-15).

### Entities subscribe, they do not fetch

```python
class SecuritySpyCameraEntity(CoordinatorEntity[SecuritySpyDataUpdateCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator, camera_number: int, description) -> None:
        super().__init__(coordinator)
        self._camera_number = camera_number
        self.entity_description = description
        uuid = coordinator.server.uuid
        self._attr_unique_id = f"{uuid}_{camera_number}_{description.key}"   # AD-5
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{uuid}_{camera_number}")},
            via_device=(DOMAIN, uuid),
            name=self.camera.name,
            manufacturer="Ben Software",
            model=self.camera.model,
        )

    @property
    def camera(self) -> CameraData:
        return self.coordinator.data.cameras[self._camera_number]   # int keys (AD-15)
```

`CoordinatorEntity` handles `entity-event-setup` (Bronze) for you — it subscribes in `async_added_to_hass` and unsubscribes on removal. Hand-rolling subscriptions is how that rule gets violated.

### PARALLEL_UPDATES

Every platform module needs the constant (Silver `parallel-updates`). Since all reads come from the coordinator, `0` (unlimited) is right for read-only platforms; write platforms may use `1` to serialize commands.

```python
PARALLEL_UPDATES = 0
```

> **CI note:** the `parallel-updates` check moved from hassfest to the Home Assistant **pylint plugin** in HA 2026.6. A hassfest-only CI job will not catch it — wire both (AD-14).

---

## 4. Devices and entity naming (`has-entity-name`, `entity-unique-id`)

`has_entity_name = True` is mandatory for new integrations and is effectively permanent — changing it later orphans user customizations (NFR-18).

The rule: **the entity's `name` describes only the data point**, never the device.

```python
# Hub device — the SecuritySpy Server (AD-5)
DeviceInfo(
    identifiers={(DOMAIN, server.uuid)},
    entry_type=DeviceEntryType.SERVICE,     # software on a Mac, not an appliance
    name=server.name,
    manufacturer="Ben Software",
    sw_version=server.version,
    configuration_url=f"https://{host}:{port}/",
)
```

Naming outcomes with `has_entity_name = True`:

| Entity `name` | Result |
|---|---|
| `None` | friendly name is the device name — use for the *main* feature (e.g. the camera entity) |
| `translation_key="last_human_seen"` | friendly name is `"Driveway Last human seen"`, entity ID `sensor.driveway_last_human_seen` |

**Never hardcode `_attr_name` strings.** Use `translation_key` plus `strings.json` — that satisfies Gold `entity-translations` for free and is what FR-20 means by "no hardcoded names."

```python
@dataclass(frozen=True, kw_only=True)
class SecuritySpySensorEntityDescription(SensorEntityDescription):
    """Describes a SecuritySpy sensor."""
    value_fn: Callable[[CameraData], datetime | None]


OBSERVATION_SENSORS: tuple[SecuritySpySensorEntityDescription, ...] = tuple(
    SecuritySpySensorEntityDescription(
        key=f"last_{object_class}_seen",
        translation_key=f"last_{object_class}_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=partial(_last_seen, object_class=object_class),
    )
    # parameterized over classes, never copy-pasted (AD-9)
    for object_class in BUILT_IN_OBJECT_CLASSES
)
```

### Entity categories and defaults

```python
_attr_entity_category = EntityCategory.CONFIG        # arming, triggers, sensitivity, enable
_attr_entity_category = EntityCategory.DIAGNOSTIC    # cpu, fps, data rate, cert expiry
_attr_entity_registry_enabled_default = False        # camera/live video (FR-22 → protects ONVIF)
```

---

## 5. Config flow (`config-flow`, `unique-config-entry`, `test-before-configure`)

Unique ID must be stable and **must not** be an IP, hostname, or user-editable name — which is exactly why AD-5 uses the server UUID.

```python
class SecuritySpyConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                server = await _async_validate(self.hass, user_input)   # test-before-configure
            except SecuritySpyConnectError:
                errors["base"] = "cannot_connect"
            except SecuritySpyAuthError:
                errors["base"] = "invalid_auth"
            except SecuritySpyUnsupportedVersionError:
                errors["base"] = "unsupported_version"
            else:
                await self.async_set_unique_id(server.uuid)             # AD-5
                self._abort_if_unique_id_configured()                   # unique-config-entry
                return self.async_create_entry(title=server.name, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
```

### Reauth (Silver `reauthentication-flow`, FR-27)

Triggered by raising `ConfigEntryAuthFailed` — but only after AD-18's counter reaches 3, never on the first 401.

```python
    async def async_step_reauth(self, entry_data) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            entry = self._get_reauth_entry()
            ...validate...
            return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(step_id="reauth_confirm", data_schema=REAUTH_SCHEMA)
```

### Reconfigure (Gold `reconfiguration-flow`, FR-29)

`_abort_if_unique_id_mismatch()` is what guarantees FR-29's "preserves devices, entities, and history" — it stops a user from repointing an entry at a *different* server.

```python
    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            server = await _async_validate(self.hass, user_input)
            await self.async_set_unique_id(server.uuid)
            self._abort_if_unique_id_mismatch(reason="wrong_server")
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data_updates=user_input
            )
        return self.async_show_form(step_id="reconfigure", data_schema=...)
```

### Options flow (tuning — FR-8)

Options hold Detection Threshold, Debounce, motion timeout, lookback, and per-camera overrides. Changes must apply **without a restart**, via an update listener that reconfigures the reducer rather than reloading the entry.

### Test coverage

`config-flow-test-coverage` demands **100 %** coverage of `config_flow.py` including every abort and error path. The PRD addendum calls this the single biggest Bronze cost — budget for it in Epic 2, not at the end.

---

## 6. Availability, errors, and logging

### Availability (Silver `entity-unavailable`, FR-30, AD-17)

Computed once in the base entity. Platforms never override it.

```python
    @property
    def available(self) -> bool:
        data = self.coordinator.data
        if not self.coordinator.last_update_success:
            return False                                  # layer 1: server unreachable
        camera = data.cameras.get(self._camera_number)
        if camera is None or not camera.online:
            return False                                  # layer 2: this camera offline
        return True

# Push-derived entities (presence, motion) additionally require stream health — layer 3.
```

### Exceptions

| Situation | Raise | Effect |
|---|---|---|
| Transient connect failure at setup | `ConfigEntryNotReady` | HA retries with backoff |
| Auth failed (after 3, AD-18) | `ConfigEntryAuthFailed` | starts reauth flow |
| Permanently incompatible (old SecuritySpy) | `ConfigEntryError` | stops, tells the user |
| User gave bad service input | `ServiceValidationError` | Silver `action-exceptions` |
| Service failed operationally | `HomeAssistantError` | Silver `action-exceptions` |

All with `translation_domain` / `translation_key` (Gold `exception-translations`).

### Logging (Silver `log-when-unavailable`, FR-32)

Loss once at ERROR, retries at DEBUG, recovery once at WARNING. A multi-hour outage must not produce proportional log volume — hold a `_logged_unavailable` flag.

---

## 7. Diagnostics, repairs, and the credential hazard

### Diagnostics (Gold, FR-42)

**Everything** exits through the library's anonymizer (AD-13). SecuritySpy's settings JSON returns camera passwords in plaintext, so this is a live hazard, not a formality.

```python
TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, "auth", "token"}

async def async_get_config_entry_diagnostics(hass, entry: SecuritySpyConfigEntry) -> dict:
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "data": anonymize(entry.runtime_data.coordinator.data),   # library-owned
    }
```

**Never log settings payloads, at any level.**

### Repairs (Gold `repair-issues`, FR-28 / FR-45)

Two uses in this project: a missing SecuritySpy permission (naming the exact permission), and the default-install trap where per-class triggers are off so the Observation Record would sit empty forever.

```python
ir.async_create_issue(
    hass, DOMAIN, f"missing_permission_{permission}",
    is_fixable=False, severity=ir.IssueSeverity.WARNING,
    translation_key="missing_permission",
    translation_placeholders={"permission": permission, "camera": camera.name},
)
```

---

## 8. Testing

Use `pytest-homeassistant-custom-component` (actively maintained; tracks current HA, requires Python 3.14).

```
pytest-homeassistant-custom-component
```

```python
# conftest.py
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Required for custom integrations to load in tests."""
    yield


async def test_setup_entry(hass: HomeAssistant, mock_client) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_DATA, unique_id="uuid-1")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
```

Targets: **100 %** on `config_flow.py` (Bronze), **> 95 %** across all modules before announcement (Silver, FR-39). Use snapshot tests (`syrupy`) for entity/device registry shape — they catch accidental unique-ID or naming changes, which NFR-18 says are unforgivable.

Library tests are separate and must import **no** Home Assistant, using recorded protocol fixtures — including a CR-framed stream fixture, since that framing is the likeliest bug in the whole project.

---

## 9. Quality scale rule sets

Declared in `quality_scale.yaml`; every rule is `done`, `exempt` (with a comment), or `todo`.

**Bronze (release gate, FR-38):** `action-setup`, `appropriate-polling`, `brands`, `common-modules`, `config-flow`, `config-flow-test-coverage`, `dependency-transparency`, `docs-actions`, `docs-conditions`, `docs-high-level-description`, `docs-installation-instructions`, `docs-removal-instructions`, `docs-triggers`, `entity-event-setup`, `entity-unique-id`, `has-entity-name`, `runtime-data`, `test-before-configure`, `test-before-setup`, `unique-config-entry`

**Silver (announcement gate, FR-39):** `action-exceptions`, `config-entry-unloading`, `docs-configuration-parameters`, `docs-installation-parameters`, `entity-unavailable`, `integration-owner`, `log-when-unavailable`, `parallel-updates`, `reauthentication-flow`, `test-coverage`

**Gold rules we honor without committing to the tier:** `devices`, `diagnostics`, `entity-category`, `entity-device-class`, `entity-disabled-by-default`, `entity-translations`, `icon-translations`, `exception-translations`, `reconfiguration-flow`, `repair-issues`, `dynamic-devices`, `stale-devices`, and the `docs-*` family. `dynamic-devices` and `stale-devices` are cheap now and expensive to retrofit (AD-12).

**Platinum (kept reachable via library design, FR-41):** `async-dependency`, `inject-websession`, `strict-typing`.

> The quality scale is formally a *core*-integration mechanism. For a custom integration the honest claim is **"meets the rule set as verified by our own tooling in CI,"** never "certified."

---

## 10. Quick links

| Topic | URL |
|---|---|
| Developer docs home | <https://developers.home-assistant.io> |
| Fetching data / coordinator | <https://developers.home-assistant.io/docs/integration_fetching_data> |
| Config flow handler | <https://developers.home-assistant.io/docs/config_entries_config_flow_handler> |
| Entity fundamentals | <https://developers.home-assistant.io/docs/core/entity/> |
| Device & entity registry | <https://developers.home-assistant.io/docs/device_registry_index> |
| Manifest reference | <https://developers.home-assistant.io/docs/creating_integration_manifest> |
| Quality scale rules | <https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/> |
| Diagnostics | <https://developers.home-assistant.io/docs/core/integration_diagnostics> |
| Repairs | <https://developers.home-assistant.io/docs/core/platform/repairs> |
| Handling setup failures | <https://developers.home-assistant.io/docs/integration_setup_failures> |
