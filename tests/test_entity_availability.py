"""Layered entity availability (story 3.1, FR-30, Silver `entity-unavailable`).

Every row of the story's I/O matrix is driven through a real entry setup with
the mocked client, advancing time with `async_fire_time_changed` so the
coordinator's own timers run, and asserting on entity *state* -- the thing a
user and an automation actually see.
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from typing import TYPE_CHECKING

from aiosecurityspy import SecuritySpyConnectError
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.securityspy import PLATFORMS, camera, sensor, update
from custom_components.securityspy.const import DOMAIN, LIGHT_POLL_INTERVAL, RECONCILE_INTERVAL
from custom_components.securityspy.sensor import CAMERA_SENSORS, SecuritySpyCameraSensor

from .conftest import (
    MOCK_USER_INPUT,
    SERVER_NAME,
    SERVER_UUID,
    make_camera,
    make_camera_status,
    make_server_info_with_cameras,
)

if TYPE_CHECKING:
    from datetime import timedelta
    from unittest.mock import MagicMock

    import pytest
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

HUB_UNIQUE_ID = f"{SERVER_UUID}_cpu_usage"
CAM_1_UNIQUE_ID = f"{SERVER_UUID}_1_current_fps"
CAM_2_UNIQUE_ID = f"{SERVER_UUID}_2_current_fps"


class _PushDerivedCameraSensor(SecuritySpyCameraSensor):
    """A stand-in push-derived entity; no real one exists until Story 3.2."""

    _attr_push_derived = True


async def _setup(hass: HomeAssistant, mock_client: MagicMock) -> MockConfigEntry:
    """Set up an entry against a two-camera server."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras()
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_USER_INPUT, unique_id=SERVER_UUID, title=SERVER_NAME
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _unavailable(hass: HomeAssistant, entity_registry: er.EntityRegistry, unique_id: str) -> bool:
    """Return whether the sensor with this unique id currently reads unavailable."""
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state == STATE_UNAVAILABLE


async def _advance(hass: HomeAssistant, interval: timedelta) -> None:
    """Fire the coordinator's timers as if `interval` had elapsed."""
    async_fire_time_changed(hass, dt_util.utcnow() + interval)
    await hass.async_block_till_done()


async def test_an_unreachable_server_makes_every_entity_unavailable_until_it_answers(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A failing light poll marks hub and camera entities unavailable; success restores them."""
    await _setup(hass, mock_client)
    unique_ids = (HUB_UNIQUE_ID, CAM_1_UNIQUE_ID, CAM_2_UNIQUE_ID)
    assert not any(_unavailable(hass, entity_registry, uid) for uid in unique_ids)

    mock_client.async_get_camera_status.side_effect = SecuritySpyConnectError(
        "192.168.1.20", 8000, "timeout"
    )
    await _advance(hass, LIGHT_POLL_INTERVAL)
    assert all(_unavailable(hass, entity_registry, uid) for uid in unique_ids)

    mock_client.async_get_camera_status.side_effect = None
    await _advance(hass, LIGHT_POLL_INTERVAL)
    assert not any(_unavailable(hass, entity_registry, uid) for uid in unique_ids)


async def test_a_failed_reconcile_makes_every_entity_unavailable(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A failing heavy poll marks every entity unavailable.

    Invoked directly rather than by advancing time: `RECONCILE_INTERVAL` is a
    multiple of `LIGHT_POLL_INTERVAL`, so the light poll fires on the same tick
    and its success would (correctly) restore availability before the assert.
    """
    entry = await _setup(hass, mock_client)
    reconcile = getattr(entry.runtime_data.coordinator, "_async_reconcile")  # noqa: B009

    mock_client.async_get_server_info.side_effect = SecuritySpyConnectError(
        "192.168.1.20", 8000, "timeout"
    )
    await reconcile()
    await hass.async_block_till_done()
    for uid in (HUB_UNIQUE_ID, CAM_1_UNIQUE_ID, CAM_2_UNIQUE_ID):
        assert _unavailable(hass, entity_registry, uid)

    mock_client.async_get_server_info.side_effect = None
    await _advance(hass, RECONCILE_INTERVAL)
    assert not _unavailable(hass, entity_registry, HUB_UNIQUE_ID)


async def test_an_unexpected_poll_error_makes_every_entity_unavailable(
    hass: HomeAssistant,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A non-library exception is logged and treated as an outage."""
    await _setup(hass, mock_client)

    mock_client.async_get_camera_status.side_effect = RuntimeError("boom")
    await _advance(hass, LIGHT_POLL_INTERVAL)

    for uid in (HUB_UNIQUE_ID, CAM_1_UNIQUE_ID, CAM_2_UNIQUE_ID):
        assert _unavailable(hass, entity_registry, uid)
    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_an_offline_camera_is_unavailable_alone(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Camera 1 offline leaves the hub and camera 2 available."""
    await _setup(hass, mock_client)

    mock_client.async_get_camera_status.return_value = (
        make_camera_status(1, online=False),
        make_camera_status(2, online=True),
    )
    await _advance(hass, LIGHT_POLL_INTERVAL)

    assert _unavailable(hass, entity_registry, CAM_1_UNIQUE_ID)
    assert not _unavailable(hass, entity_registry, CAM_2_UNIQUE_ID)
    assert not _unavailable(hass, entity_registry, HUB_UNIQUE_ID)


async def test_a_camera_with_no_status_falls_back_to_its_connected_flag(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Without a light-poll status, `Camera.connected=False` makes the camera unavailable."""
    disconnected = replace(make_camera(2, "Front Door"), connected=False)
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"), disconnected)
    )
    entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_USER_INPUT, unique_id=SERVER_UUID, title=SERVER_NAME
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.coordinator.data.camera_statuses == {}
    assert _unavailable(hass, entity_registry, CAM_2_UNIQUE_ID)
    assert not _unavailable(hass, entity_registry, CAM_1_UNIQUE_ID)


async def test_a_camera_leaving_the_inventory_is_unavailable_and_keeps_its_device(
    hass: HomeAssistant,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Camera 2 dropping out of `++systemInfo` goes unavailable; its device stays."""
    await _setup(hass, mock_client)

    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"),)
    )
    await _advance(hass, RECONCILE_INTERVAL)

    assert _unavailable(hass, entity_registry, CAM_2_UNIQUE_ID)
    assert not _unavailable(hass, entity_registry, CAM_1_UNIQUE_ID)
    assert not _unavailable(hass, entity_registry, HUB_UNIQUE_ID)
    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_2")}) is not None


async def test_stream_health_gates_only_push_derived_entities(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """A down stream leaves poll-derived entities available but not push-derived ones."""
    entry = await _setup(hass, mock_client)
    coordinator = entry.runtime_data.coordinator
    push_entity = _PushDerivedCameraSensor(coordinator, 1, CAMERA_SENSORS[0])
    assert bool(coordinator.stream_connected) is False

    assert not _unavailable(hass, entity_registry, CAM_1_UNIQUE_ID)
    assert bool(push_entity.available) is False

    coordinator.async_set_stream_connected(True)  # noqa: FBT003 - the flag under test
    assert bool(push_entity.available) is True
    assert not _unavailable(hass, entity_registry, CAM_1_UNIQUE_ID)


def test_no_platform_class_overrides_available() -> None:
    """Availability lives in `entity.py` alone; platforms never redefine it."""
    modules = (camera, sensor, update)
    # A new platform must be added to `modules`, or this guard silently skips it.
    assert {platform.value for platform in PLATFORMS} == {
        module.__name__.rsplit(".", 1)[-1] for module in modules
    }
    for module in modules:
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__:
                assert "available" not in vars(cls), f"{module.__name__}.{name} overrides available"
