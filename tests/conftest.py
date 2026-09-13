"""Shared fixtures for the SecuritySpy integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final
from unittest.mock import MagicMock, patch

import pytest
from aiosecurityspy import Camera, CameraStatus, ServerInfo
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)

if TYPE_CHECKING:
    from collections.abc import Generator

SERVER_UUID: Final = "1D3A5C7E-9B21-4F60-8A44-0C2E6F1B7D93"
SERVER_NAME: Final = "nvr"

#: The six fields the user step collects, and the only six an entry stores.
#: Defaults: plain HTTP, verification on -- the shape the form offers unchanged.
MOCK_USER_INPUT: Final[dict[str, Any]] = {
    CONF_HOST: "192.168.1.20",
    CONF_PORT: 8000,
    CONF_USERNAME: "homeassistant",
    CONF_PASSWORD: "hunter2",
    CONF_SSL: False,
    CONF_VERIFY_SSL: True,
}

#: The same server reached over TLS on SecuritySpy's HTTPS port. Derived from
#: `MOCK_USER_INPUT` so a new field cannot be added to one payload only.
MOCK_HTTPS_USER_INPUT: Final[dict[str, Any]] = {
    **MOCK_USER_INPUT,
    CONF_PORT: 8001,
    CONF_SSL: True,
}


def https_input(*, verify_ssl: bool = True) -> dict[str, Any]:
    """Return the HTTPS payload, optionally with verification turned off.

    Args:
        verify_ssl: Whether the submitted form asks for certificate
            verification. The interesting case is ``False``: it is the retry a
            user makes after a certificate mismatch.

    Returns:
        A submittable copy of the HTTPS payload.

    """
    return {**MOCK_HTTPS_USER_INPUT, CONF_VERIFY_SSL: verify_ssl}


def make_server_info(  # noqa: PLR0913 - each kwarg is a distinct optional health field, non-breaking to add
    uuid: str = SERVER_UUID,
    name: str = SERVER_NAME,
    *,
    cpu_usage: float | None = None,
    memory_pressure: float | None = None,
    cert_expiry_days: int | None = None,
    update_version: str | None = None,
) -> ServerInfo:
    """Build a ``ServerInfo`` without going near the wire."""
    return ServerInfo(
        uuid=uuid,
        name=name,
        version="6.20",
        version_info=(6, 20),
        camera_count=0,
        cpu_usage=cpu_usage,
        memory_pressure=memory_pressure,
        cert_expiry_days=cert_expiry_days,
        update_version=update_version,
    )


def make_camera(  # noqa: PLR0913 - each kwarg is a distinct optional health field, non-breaking to add
    number: int,
    name: str,
    *,
    enabled: bool = True,
    current_fps: float | None = None,
    data_rate: float | None = None,
    last_error: str | None = None,
    last_error_description: str | None = None,
) -> Camera:
    """Build a ``Camera`` without going near the wire."""
    return Camera(
        number=number,
        name=name,
        connected=True,
        enabled=enabled,
        permissions=0,
        current_fps=current_fps,
        data_rate=data_rate,
        last_error=last_error,
        last_error_description=last_error_description,
    )


def make_camera_status(  # noqa: PLR0913 - each kwarg mirrors a distinct `CameraStatus` field
    number: int,
    *,
    enabled: bool = True,
    online: bool = True,
    open: bool = True,  # noqa: A002 - matches the library's own `CameraStatus.open` field name
    error: str | None = None,
    error_description: str | None = None,
) -> CameraStatus:
    """Build a ``CameraStatus`` without going near the wire."""
    return CameraStatus(
        number=number,
        enabled=enabled,
        online=online,
        open=open,
        error=error,
        error_description=error_description,
    )


def make_server_info_with_cameras(
    uuid: str = SERVER_UUID,
    name: str = SERVER_NAME,
    cameras: tuple[Camera, ...] = (),
    *,
    update_version: str | None = None,
) -> ServerInfo:
    """Build a ``ServerInfo`` carrying the given cameras, keyed by number.

    Args:
        uuid: The server's identity.
        name: The server's display name.
        cameras: The cameras to inventory; defaults to two, matching the
            "N cameras" row of the story's I/O matrix.
        update_version: The offered update version, if any.

    Returns:
        A `ServerInfo` with `cameras` populated from the given entries.

    """
    entries = cameras or (
        make_camera(1, "Driveway"),
        make_camera(2, "Front Door"),
    )
    return ServerInfo(
        uuid=uuid,
        name=name,
        version="6.20",
        version_info=(6, 20),
        camera_count=len(entries),
        cameras={camera.number: camera for camera in entries},
        update_version=update_version,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Load `custom_components/` in every test; required for custom integrations.

    The parameter is requested purely for its side effect: it is what makes
    Home Assistant willing to load an integration from `custom_components/`.
    """


@pytest.fixture
def mock_client_class() -> Generator[MagicMock]:
    """Patch `SecuritySpyClient` at both import sites with one shared mock.

    The config flow and `async_setup_entry` each import the class by name, so
    both bindings have to be replaced; sharing a single mock keeps a test's
    `side_effect` in force across a flow that ends by setting the entry up.
    """
    with (
        patch(
            "custom_components.securityspy.config_flow.SecuritySpyClient", autospec=True
        ) as client_class,
        patch("custom_components.securityspy.SecuritySpyClient", new=client_class),
    ):
        client_class.return_value.async_get_server_info.return_value = make_server_info()
        # Empty by default: most tests do not care about the light poll, and
        # an empty tuple is the non-breaking default `SecuritySpyData` itself
        # starts with.
        client_class.return_value.async_get_camera_status.return_value = ()
        yield client_class


@pytest.fixture
def mock_client(mock_client_class: MagicMock) -> MagicMock:
    """Return the mocked client instance the patched class hands out."""
    instance: MagicMock = mock_client_class.return_value
    return instance
