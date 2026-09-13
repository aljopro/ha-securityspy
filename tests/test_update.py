"""Update entity coverage: one test per row of the story's I/O matrix.

Entries are set up through `hass.config_entries.async_setup`, exactly as
Home Assistant does it, so entity creation, unique ID, and device linkage are
all exercised through the real platform-setup path rather than by
constructing the entity directly.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.update import UpdateDeviceClass, UpdateEntityFeature
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.const import DOMAIN

from .conftest import (
    MOCK_USER_INPUT,
    SERVER_NAME,
    SERVER_UUID,
    make_camera,
    make_server_info,
    make_server_info_with_cameras,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr
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


def _entity_id(entity_registry: er.EntityRegistry) -> str | None:
    return entity_registry.async_get_entity_id("update", DOMAIN, f"{SERVER_UUID}_update")


async def test_update_available(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Update offered: installed/latest versions differ, state is `on`."""
    mock_client.async_get_server_info.return_value = make_server_info(update_version="6.21")
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_ON
    assert state.attributes["installed_version"] == "6.20"
    assert state.attributes["latest_version"] == "6.21"


async def test_no_update_available(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """No update offered: `latest_version` falls back to `version`, state is `off`."""
    mock_client.async_get_server_info.return_value = make_server_info(update_version=None)
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["installed_version"] == "6.20"
    assert state.attributes["latest_version"] == "6.20"


async def test_no_install_action_offered(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """No install action: `supported_features` is the class default of zero.

    Calling `update.install` on this entity raises Home Assistant's own
    "not supported" error; no code path in this entity handles installation.
    """
    mock_client.async_get_server_info.return_value = make_server_info(update_version="6.21")
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["supported_features"] == UpdateEntityFeature(0)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "update",
            "install",
            {"entity_id": entity_id},
            blocking=True,
        )


async def test_diagnostic_category_and_firmware_device_class(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Diagnostic-categorized (the base class's own INSTALL-less fallback) and firmware-classed."""
    mock_client.async_get_server_info.return_value = make_server_info(update_version="6.21")
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry)
    assert entity_id is not None
    entity_entry = entity_registry.async_get(entity_id)
    assert entity_entry is not None
    assert entity_entry.entity_category is EntityCategory.DIAGNOSTIC

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["device_class"] == UpdateDeviceClass.FIRMWARE


async def test_exactly_one_update_entity_regardless_of_camera_count(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """The update entity is hub-only: it does not multiply per camera."""
    server = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"), make_camera(2, "Backyard")),
        update_version="6.21",
    )
    mock_client.async_get_server_info.return_value = server
    entry = _add_entry(hass)

    await _setup(hass, entry)

    update_entities = [
        registry_entry
        for registry_entry in entity_registry.entities.values()
        if registry_entry.config_entry_id == entry.entry_id and registry_entry.domain == "update"
    ]
    assert len(update_entities) == 1
    assert update_entities[0].unique_id == f"{SERVER_UUID}_update"


async def test_state_follows_a_coordinator_refresh(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """The entity reflects a later coordinator update, not just the value seeded at setup."""
    mock_client.async_get_server_info.return_value = make_server_info(update_version="6.21")
    entry = _add_entry(hass)
    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry)
    assert entity_id is not None
    assert hass.states.get(entity_id).state == STATE_ON  # type: ignore[union-attr]

    coordinator = entry.runtime_data.coordinator
    coordinator.async_set_updated_data(
        replace(coordinator.data, server=make_server_info(update_version=None))
    )
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["latest_version"] == "6.20"


async def test_unique_id_and_device_linkage(
    hass: HomeAssistant,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The update entity has the hub's permanent unique ID and is linked to the hub device."""
    mock_client.async_get_server_info.return_value = make_server_info(update_version="6.21")
    entry = _add_entry(hass)

    await _setup(hass, entry)

    entity_id = _entity_id(entity_registry)
    assert entity_id is not None
    entity_entry = entity_registry.async_get(entity_id)
    assert entity_entry is not None
    assert entity_entry.unique_id == f"{SERVER_UUID}_update"

    hub_device = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    assert hub_device is not None
    assert entity_entry.device_id == hub_device.id
