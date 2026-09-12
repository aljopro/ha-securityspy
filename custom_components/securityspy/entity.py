"""Device identity builders, per AD-5.

Pure, synchronous functions with no Home Assistant I/O and no entity classes --
this module exists so the coordinator and every future platform compute device
identity from exactly one place. `common-modules` (Bronze) requires a module
named `entity.py` to exist under this name once platforms arrive; this story
gives it real content ahead of that (no entity class yet -- that starts in
story 2.4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN

if TYPE_CHECKING:
    from aiosecurityspy import Camera, ServerInfo


def hub_device_info(server: ServerInfo) -> DeviceInfo:
    """Return the `DeviceInfo` for the SecuritySpy server hub device.

    Identity is `server.uuid` alone (AD-5) -- never hostname, IP, or a
    fabricated MAC. `entry_type=SERVICE` marks it as software running on a
    Mac, not a physical appliance.

    Args:
        server: The server whose hub device is being described.

    Returns:
        The hub's device identity.

    """
    return DeviceInfo(
        identifiers={(DOMAIN, server.uuid)},
        entry_type=DeviceEntryType.SERVICE,
        name=server.name,
        manufacturer="Ben Software",
        sw_version=server.version,
    )


def camera_device_info(server: ServerInfo, camera: Camera) -> DeviceInfo:
    """Return the `DeviceInfo` for one camera device, linked to the hub.

    Identity is `server.uuid` combined with `camera.number` (AD-5) -- never
    the camera's user-editable name. No `sw_version` (SecuritySpy does not
    report one per camera) and no `model` (the library's `Camera` model has
    no model field to report).

    Args:
        server: The server the camera belongs to, for its hub link.
        camera: The camera whose device is being described.

    Returns:
        The camera's device identity.

    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"{server.uuid}_{camera.number}")},
        via_device=(DOMAIN, server.uuid),
        name=camera.name,
        manufacturer="Ben Software",
    )
