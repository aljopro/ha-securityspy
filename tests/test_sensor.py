"""Sensor coverage: one test per row of the story's I/O matrix.

Entries are set up through `hass.config_entries.async_setup`, exactly as
Home Assistant does it, so sensor creation, unique IDs, device linkage, and
diagnostic categorization are all exercised through the real platform-setup
path rather than by constructing entities directly.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from aiosecurityspy import SecuritySpyConnectError, ServerInfo
from homeassistant.const import STATE_UNKNOWN, EntityCategory
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.securityspy.const import DOMAIN, LIGHT_POLL_INTERVAL

from .conftest import (
    MOCK_USER_INPUT,
    SERVER_NAME,
    SERVER_UUID,
    make_camera,
    make_camera_status,
    make_server_info,
    make_server_info_with_cameras,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er


def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_USER_INPUT, unique_id=SERVER_UUID, title=SERVER_NAME
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(entity_registry: er.EntityRegistry, unique_id: str) -> str | None:
    return entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)


def _fire_light_poll(hass: HomeAssistant) -> None:
    """Advance time past `LIGHT_POLL_INTERVAL` to fire the light-poll timer."""
    async_fire_time_changed(hass, dt_util.utcnow() + LIGHT_POLL_INTERVAL)


def _with_hub_health(
    server: ServerInfo,
    *,
    cpu_usage: float | None = None,
    cert_expiry_days: int | None = None,
) -> ServerInfo:
    """Return a copy of `server` with the given hub-health fields set.

    `make_server_info_with_cameras` does not itself accept the health kwargs
    (it composes the base `make_server_info` builder without them), so this
    applies `dataclasses.replace` on top instead of widening that builder's
    already-established signature.
    """
    updates: dict[str, float | int] = {}
    if cpu_usage is not None:
        updates["cpu_usage"] = cpu_usage
    if cert_expiry_days is not None:
        updates["cert_expiry_days"] = cert_expiry_days
    return replace(server, **updates)


async def test_hub_and_camera_sensors_read_fresh_heavy_values(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Fresh setup: hub CPU sensor and camera FPS sensor read the seeded values."""
    server = _with_hub_health(
        make_server_info_with_cameras(cameras=(make_camera(1, "Driveway", current_fps=15.0),)),
        cpu_usage=42.0,
    )
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    cpu_entity_id = _entity_id(entity_registry, f"{SERVER_UUID}_cpu_usage")
    assert cpu_entity_id is not None
    state = hass.states.get(cpu_entity_id)
    assert state is not None
    assert state.state == "42.0"

    fps_entity_id = _entity_id(entity_registry, f"{SERVER_UUID}_1_current_fps")
    assert fps_entity_id is not None
    fps_state = hass.states.get(fps_entity_id)
    assert fps_state is not None
    assert fps_state.state == "15.0"


async def test_field_not_reported_renders_unknown(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """`cert_expiry_days=None` renders as HA's own unknown state."""
    server = make_server_info()
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry, f"{SERVER_UUID}_cert_expiry_days")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNKNOWN


async def test_cert_already_expired_is_not_clamped_or_hidden(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A negative `cert_expiry_days` (already expired) is reported as-is."""
    server = _with_hub_health(make_server_info(), cert_expiry_days=-3)
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry, f"{SERVER_UUID}_cert_expiry_days")
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "-3"


async def test_light_poll_updates_last_error_without_touching_heavy_fields(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A successful light poll updates `last_error`; FPS/data-rate stay at the last heavy value."""
    server = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway", current_fps=15.0, data_rate=500.0),)
    )
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)
    await _setup(hass, entry)

    mock_client.async_get_camera_status = AsyncMock(
        return_value=(make_camera_status(1, error="e/network", error_description="Network error"),)
    )
    _fire_light_poll(hass)
    await hass.async_block_till_done()

    last_error_id = _entity_id(entity_registry, f"{SERVER_UUID}_1_last_error")
    assert last_error_id is not None
    state = hass.states.get(last_error_id)
    assert state is not None
    assert state.state == "e/network"
    assert state.attributes["last_error_description"] == "Network error"

    fps_id = _entity_id(entity_registry, f"{SERVER_UUID}_1_current_fps")
    assert fps_id is not None
    fps_state = hass.states.get(fps_id)
    assert fps_state is not None
    assert fps_state.state == "15.0"

    data_rate_id = _entity_id(entity_registry, f"{SERVER_UUID}_1_data_rate")
    assert data_rate_id is not None
    data_rate_state = hass.states.get(data_rate_id)
    assert data_rate_state is not None
    assert data_rate_state.state == "500.0"


async def test_light_poll_transient_failure_leaves_last_error_untouched(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A transient light-poll failure does not clear or change `last_error`."""
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)
    await _setup(hass, entry)

    mock_client.async_get_camera_status = AsyncMock(
        return_value=(make_camera_status(1, error="e/network"),)
    )
    _fire_light_poll(hass)
    await hass.async_block_till_done()

    mock_client.async_get_camera_status = AsyncMock(
        side_effect=SecuritySpyConnectError("192.168.1.20", 8000, "timeout")
    )
    _fire_light_poll(hass)
    await hass.async_block_till_done()

    last_error_id = _entity_id(entity_registry, f"{SERVER_UUID}_1_last_error")
    assert last_error_id is not None
    state = hass.states.get(last_error_id)
    assert state is not None
    assert state.state == "e/network"


async def test_zero_cameras_creates_only_hub_sensors(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A camera-less server gets hub sensors only; setup succeeds."""
    server = make_server_info()
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    assert _entity_id(entity_registry, f"{SERVER_UUID}_cpu_usage") is not None
    camera_sensor_unique_ids = [
        registry_entry.unique_id
        for registry_entry in entity_registry.entities.values()
        if registry_entry.config_entry_id == entry.entry_id
        and registry_entry.unique_id.removeprefix(f"{SERVER_UUID}_").split("_")[0].isdigit()
    ]
    assert camera_sensor_unique_ids == []


async def test_every_sensor_is_diagnostic_categorized_with_unique_id_and_device(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Every created sensor is diagnostic-categorized, uniquely identified, and device-linked."""
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    sensors = [
        registry_entry
        for registry_entry in entity_registry.entities.values()
        if registry_entry.config_entry_id == entry.entry_id and registry_entry.domain == "sensor"
    ]
    expected_count = 4 + 3  # 4 hub sensors + 3 camera sensors for one camera
    assert len(sensors) == expected_count
    for sensor in sensors:
        assert sensor.entity_category is EntityCategory.DIAGNOSTIC
        assert sensor.device_id is not None
        assert sensor.unique_id.startswith(f"{SERVER_UUID}_")


async def test_multiple_cameras_each_get_their_own_full_set_of_sensors(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """N cameras produce N independent camera-sensor sets, not a shared or de-duplicated one."""
    server = make_server_info_with_cameras(
        cameras=(
            make_camera(1, "Driveway"),
            make_camera(2, "Backyard"),
            make_camera(3, "Front Door"),
        )
    )
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    sensors = [
        registry_entry
        for registry_entry in entity_registry.entities.values()
        if registry_entry.config_entry_id == entry.entry_id and registry_entry.domain == "sensor"
    ]
    sensors_per_camera = 3
    expected_count = 4 + sensors_per_camera * 3  # 4 hub sensors + per-camera sensors, 3 cameras
    assert len(sensors) == expected_count
    assert len({sensor.unique_id for sensor in sensors}) == expected_count
    for camera_number in (1, 2, 3):
        camera_sensor_ids = {
            sensor.unique_id
            for sensor in sensors
            if sensor.unique_id.startswith(f"{SERVER_UUID}_{camera_number}_")
        }
        assert len(camera_sensor_ids) == sensors_per_camera


async def test_camera_removed_before_setup_gets_no_sensor_entities(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A camera number never present in `server.cameras` at setup time gets no sensors.

    Mirrors story 2.3's "no device, no entity" rule -- not a new permission
    gate (story 2.7's job) -- by simply never asking for camera 99's sensors.
    """
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    assert _entity_id(entity_registry, f"{SERVER_UUID}_99_current_fps") is None
