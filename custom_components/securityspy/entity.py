"""Device identity builders, per AD-5, and the first entity base classes.

The device-identity functions are pure and synchronous, with no Home
Assistant I/O and no entity classes -- this module exists so the coordinator
and every platform compute device identity from exactly one place.
`common-modules` (Bronze) requires a module named `entity.py` to exist under
this name once platforms arrive; story 2.3 gave it real content ahead of that.

Story 2.4 adds the first entity classes: `SecuritySpyHubEntity` and
`SecuritySpyCameraEntity`, both `CoordinatorEntity` base classes reused by
every diagnostic sensor.

Story 3.1 adds `SecuritySpyEntity`, the one place `available` is defined
(Silver `entity-unavailable`, FR-30). It layers, in order: the coordinator's
last poll succeeded; for camera entities, the camera is still in the inventory
and is online; and, for push-derived entities only, the Event Stream is
connected. No platform overrides it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from aiosecurityspy import Camera, ServerInfo

    from .coordinator import SecuritySpyDataUpdateCoordinator


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


class SecuritySpyEntity(CoordinatorEntity["SecuritySpyDataUpdateCoordinator"]):
    """Base class for every SecuritySpy entity; owns availability.

    Attributes:
        _attr_push_derived: Whether this entity's state comes from the Event
            Stream. Such an entity additionally requires
            `coordinator.stream_connected`, since a dropped stream means its
            state can no longer advance. Poll-derived entities ignore stream
            health: their data comes from the polls whether or not the stream
            is up.

    """

    _attr_has_entity_name = True
    _attr_push_derived: bool = False

    @property
    def available(self) -> bool:
        """Return whether the last poll succeeded and, if push-derived, the stream is up."""
        if not super().available:
            return False
        return not self._attr_push_derived or self.coordinator.stream_connected


class SecuritySpyHubEntity(SecuritySpyEntity):
    """Base class for entities attached to the SecuritySpy server hub device.

    `_attr_has_entity_name = True` (inherited) so each entity's own name (set
    by a subclass's entity description) is combined with the device's name by
    Home Assistant rather than repeated in full.
    """

    def __init__(self, coordinator: SecuritySpyDataUpdateCoordinator, key: str) -> None:
        """Initialize the hub entity.

        Args:
            coordinator: The coordinator supplying `SecuritySpyData`.
            key: The entity description key, combined with the server's
                `uuid` for a permanent unique id (the epic's scheme).

        """
        super().__init__(coordinator)
        server = coordinator.data.server
        self._attr_unique_id = f"{server.uuid}_{key}"
        self._attr_device_info = hub_device_info(server)


class SecuritySpyCameraEntity(SecuritySpyEntity):
    """Base class for entities attached to one camera device.

    Adds the two camera layers to `SecuritySpyEntity.available`: the camera
    must still be in the inventory, and must be online.
    """

    def __init__(
        self, coordinator: SecuritySpyDataUpdateCoordinator, camera_number: int, key: str
    ) -> None:
        """Initialize the camera entity.

        Args:
            coordinator: The coordinator supplying `SecuritySpyData`.
            camera_number: The camera this entity describes, per the current
                `coordinator.data.server.cameras` inventory at entity-setup
                time.
            key: The entity description key, combined with the server's
                `uuid` and the camera number for a permanent unique id (the
                epic's scheme).

        """
        super().__init__(coordinator)
        server = coordinator.data.server
        camera = server.cameras[camera_number]
        self.camera_number = camera_number
        self._attr_unique_id = f"{server.uuid}_{camera_number}_{key}"
        self._attr_device_info = camera_device_info(server, camera)

    @property
    def available(self) -> bool:
        """Return whether the base layers pass and this camera is present and online.

        Online comes from the light poll's `CameraStatus.online` when a status
        exists, since that is refreshed far more often; before the first light
        poll, or for a camera it has not reported, the heavy poll's
        `Camera.connected` is the only signal there is.
        """
        if not super().available:
            return False
        data = self.coordinator.data
        camera = data.server.cameras.get(self.camera_number)
        if camera is None:
            return False
        status = data.camera_statuses.get(self.camera_number)
        return status.online if status is not None else camera.connected
