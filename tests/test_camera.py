"""Camera entity coverage: one test per row of the story's I/O matrix.

Entries are set up through `hass.config_entries.async_setup`, exactly as Home
Assistant does it, and the stream and still are requested through Home
Assistant's own camera helpers, so nothing here constructs an entity directly.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

import pytest
from aiosecurityspy import (
    CameraImage,
    SecuritySpyAuthError,
    SecuritySpyConnectError,
    SecuritySpyPermissionError,
)
from homeassistant.components.camera import (
    CameraEntityFeature,
    async_get_stream_source,
)
from homeassistant.components.camera.helper import get_camera_from_entity_id
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.const import CONF_CREATE_CAMERA_ENTITIES, DOMAIN

from .conftest import (
    MOCK_USER_INPUT,
    RELAY_URL,
    SERVER_NAME,
    SERVER_UUID,
    make_server_info_with_cameras,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    from custom_components.securityspy.camera import SecuritySpyCamera

IMAGE_BYTES = b"\xff\xd8\xff\xe0jpeg"
CAMERA_NUMBERS = (1, 2)


@pytest.fixture(autouse=True)
def two_cameras(mock_client: MagicMock) -> None:
    """Serve the two-camera inventory from the "Fresh setup" row."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras()


def _add_entry(hass: HomeAssistant, *, create_cameras: bool | None = None) -> MockConfigEntry:
    options = {} if create_cameras is None else {CONF_CREATE_CAMERA_ENTITIES: create_cameras}
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        options=options,
        unique_id=SERVER_UUID,
        title=SERVER_NAME,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _entity_id(entity_registry: er.EntityRegistry, number: int) -> str | None:
    return entity_registry.async_get_entity_id("camera", DOMAIN, f"{SERVER_UUID}_{number}_camera")


def _camera(entity_registry: er.EntityRegistry, number: int = 1) -> str:
    entity_id = _entity_id(entity_registry, number)
    assert entity_id is not None
    return entity_id


def _entity(hass: HomeAssistant, entity_id: str) -> SecuritySpyCamera:
    camera: SecuritySpyCamera = get_camera_from_entity_id(hass, entity_id)  # type: ignore[assignment]
    return camera


async def _set_option(hass: HomeAssistant, entry: MockConfigEntry, *, value: bool) -> None:
    """Change the option the way a user does: through the options flow."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CREATE_CAMERA_ENTITIES: value}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_fresh_setup(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_relay: MagicMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Each camera gets an enabled streaming entity on its device, and nothing is fetched."""
    entry = _add_entry(hass)

    await _setup(hass, entry)

    for number in CAMERA_NUMBERS:
        entity_id = _camera(entity_registry, number)
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.disabled_by is None
        device = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_{number}")})
        assert device is not None
        assert registry_entry.device_id == device.id
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.attributes["supported_features"] == CameraEntityFeature.STREAM
        assert state.attributes["friendly_name"] == device.name
    mock_client.create_rtsp_relay.assert_called_once_with(entry.runtime_data.server)
    mock_relay.async_start.assert_awaited_once()
    mock_relay.stream_url.assert_not_called()
    mock_client.async_get_camera_image.assert_not_called()


async def test_stream_requested(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched for setup
    mock_relay: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """The stream source is the relay's credential-free address."""
    entry = _add_entry(hass)
    await _setup(hass, entry)

    source = await async_get_stream_source(hass, _camera(entity_registry, 2))

    assert source == RELAY_URL
    mock_relay.stream_url.assert_called_once_with(2)


async def test_still_image(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """The still comes from the library, scaled by the requested width."""
    mock_client.async_get_camera_image.return_value = CameraImage(
        data=IMAGE_BYTES, content_type="image/jpeg"
    )
    entry = _add_entry(hass)
    await _setup(hass, entry)

    image = await _entity(hass, _camera(entity_registry)).async_camera_image(width=320)

    assert image == IMAGE_BYTES
    mock_client.async_get_camera_image.assert_awaited_once_with(
        entry.runtime_data.coordinator.data.server, 1, width=320
    )


@pytest.mark.parametrize(
    "error",
    [
        SecuritySpyConnectError("192.168.1.20", 8000, "timeout"),
        SecuritySpyAuthError("192.168.1.20", 8000, 401),
        ValueError("width must be an integer of at least 1"),
    ],
    ids=["connect", "auth", "bad-width"],
)
async def test_image_failure(
    hass: HomeAssistant,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
    error: Exception,
) -> None:
    """A library failure yields no image rather than an exception."""
    mock_client.async_get_camera_image.side_effect = error
    entry = _add_entry(hass)
    await _setup(hass, entry)

    assert await _entity(hass, _camera(entity_registry)).async_camera_image() is None


async def test_no_rtsp(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Without an RTSP port the entities remain, but offer no stream and no relay exists."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(rtsp_port=None)
    entry = _add_entry(hass)
    await _setup(hass, entry)

    entity_id = _camera(entity_registry)
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["supported_features"] == CameraEntityFeature(0)
    assert await _entity(hass, entity_id).stream_source() is None
    mock_client.create_rtsp_relay.assert_not_called()
    assert entry.runtime_data.relay is None


async def test_relay_bind_fails(
    hass: HomeAssistant,
    mock_relay: MagicMock,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A relay that cannot bind leaves setup working, streamless, with one bare warning."""
    mock_relay.async_start.side_effect = OSError("[Errno 48] address already in use 127.0.0.1")
    entry = _add_entry(hass)
    await _setup(hass, entry)

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(_camera(entity_registry))
    assert state is not None
    assert state.attributes["supported_features"] == CameraEntityFeature(0)
    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "relay" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert "Errno" not in warnings[0].getMessage()
    assert warnings[0].exc_info is None


@pytest.mark.parametrize(
    "error",
    [
        SecuritySpyPermissionError("live video", 1),
        ValueError("camera_number"),
        RuntimeError("relay is not started"),
    ],
    ids=["permission", "value", "stopped"],
)
async def test_unknown_camera(
    hass: HomeAssistant,
    mock_relay: MagicMock,
    entity_registry: er.EntityRegistry,
    error: Exception,
) -> None:
    """A camera the relay does not serve has no stream source."""
    mock_relay.stream_url.side_effect = error
    entry = _add_entry(hass)
    await _setup(hass, entry)

    assert await async_get_stream_source(hass, _camera(entity_registry)) is None


async def test_option_off(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_relay: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Turning the option off reloads, removes the entities, and builds no new relay."""
    entry = _add_entry(hass)
    await _setup(hass, entry)
    assert _entity_id(entity_registry, 1) is not None
    mock_client.create_rtsp_relay.reset_mock()

    await _set_option(hass, entry, value=False)

    assert entry.state is ConfigEntryState.LOADED
    mock_relay.async_stop.assert_awaited_once()
    mock_client.create_rtsp_relay.assert_not_called()
    assert entry.runtime_data.relay is None
    for number in CAMERA_NUMBERS:
        assert _entity_id(entity_registry, number) is None
    assert not hass.states.async_entity_ids("camera")


async def test_option_back_on(
    hass: HomeAssistant, mock_client: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Turning the option back on restores the entities under their original unique ids."""
    entry = _add_entry(hass, create_cameras=False)
    await _setup(hass, entry)
    assert _entity_id(entity_registry, 1) is None
    mock_client.create_rtsp_relay.assert_not_called()

    await _set_option(hass, entry, value=True)

    for number in CAMERA_NUMBERS:
        entity_id = _entity_id(entity_registry, number)
        assert entity_id is not None
        assert hass.states.get(entity_id) is not None
    mock_client.create_rtsp_relay.assert_called_once()


async def test_unload(
    hass: HomeAssistant, mock_relay: MagicMock, entity_registry: er.EntityRegistry
) -> None:
    """Unloading the entry stops the relay."""
    entry = _add_entry(hass)
    await _setup(hass, entry)
    assert _entity_id(entity_registry, 1) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    mock_relay.async_stop.assert_awaited_once()


async def test_no_credential_reaches_the_log(
    hass: HomeAssistant,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup, image failures and an unreachable server log no password in any form (AD-13)."""
    caplog.set_level(logging.DEBUG)
    password = MOCK_USER_INPUT[CONF_PASSWORD]
    basic = base64.b64encode(f"{MOCK_USER_INPUT[CONF_USERNAME]}:{password}".encode()).decode()

    entry = _add_entry(hass)
    await _setup(hass, entry)
    camera = _entity(hass, _camera(entity_registry))
    mock_client.async_get_camera_image.side_effect = SecuritySpyConnectError(
        "192.168.1.20", 8000, "timeout"
    )
    assert await camera.async_camera_image() is None
    mock_client.async_get_camera_image.side_effect = SecuritySpyAuthError("192.168.1.20", 8000, 401)
    assert await camera.async_camera_image() is None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    mock_client.async_get_server_info.side_effect = SecuritySpyConnectError(
        "192.168.1.20", 8000, "unreachable"
    )
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert "SecuritySpyAuthError" in caplog.text
    assert password not in caplog.text
    assert basic not in caplog.text
