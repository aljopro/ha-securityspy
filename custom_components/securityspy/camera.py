"""Live video camera entities for SecuritySpy (story 2.6).

One `Camera` per camera in the permission-scoped inventory, attached to its
camera device and named after it. The stream source is the library RTSP
relay's credential-free address, and the still image comes from the library's
header-authenticated snapshot call -- this module builds no URL and never sees
a credential (AD-2, AD-13).

Nothing here polls or preloads: Home Assistant asks for a stream or a still
only when something is watching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from aiosecurityspy import SecuritySpyError, SecuritySpyPermissionError
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.helpers import entity_registry as er

from .const import CONF_CREATE_CAMERA_ENTITIES
from .entity import SecuritySpyCameraEntity

if TYPE_CHECKING:
    from aiosecurityspy import RtspRelay, SecuritySpyClient
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import SecuritySpyConfigEntry
    from .coordinator import SecuritySpyDataUpdateCoordinator

_LOGGER: Final = logging.getLogger(__name__)

#: Streams and stills are fetched on demand, one request per viewer; there is
#: no per-entity refresh to parallelize.
PARALLEL_UPDATES = 0

#: Entity description key, giving the unique id `{uuid}_{number}_camera`.
CAMERA_KEY: Final = "camera"


class SecuritySpyCamera(SecuritySpyCameraEntity, Camera):
    """Live video and stills for one SecuritySpy camera.

    `_attr_name = None` so the entity takes the camera device's name: it is
    the device's main feature.
    """

    _attr_name = None

    def __init__(
        self,
        coordinator: SecuritySpyDataUpdateCoordinator,
        camera_number: int,
        client: SecuritySpyClient,
        relay: RtspRelay | None,
    ) -> None:
        """Initialize the camera entity.

        Args:
            coordinator: The coordinator supplying `SecuritySpyData`.
            camera_number: The camera this entity shows.
            client: The client that fetches still images.
            relay: The started RTSP relay, or `None` when streaming is
                unavailable.

        """
        super().__init__(coordinator, camera_number, CAMERA_KEY)
        # `Camera` keeps its own state (access tokens, stream handle) and the
        # coordinator base's init does not chain to it.
        Camera.__init__(self)
        self._client = client
        self._relay = relay
        self._attr_supported_features = (
            CameraEntityFeature.STREAM if relay is not None else CameraEntityFeature(0)
        )

    async def stream_source(self) -> str | None:
        """Return the relay's credential-free address for this camera.

        Returns:
            The relay URL, or `None` when there is no relay, the relay does
            not serve this camera (for example one added after it was built),
            or the relay has already stopped during an unload or reload.

        """
        if self._relay is None:
            return None
        try:
            return self._relay.stream_url(self.camera_number)
        except SecuritySpyPermissionError, ValueError, RuntimeError:
            return None

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,  # noqa: ARG002 - SecuritySpy scales by width only
    ) -> bytes | None:
        """Return a current still image from SecuritySpy's snapshot endpoint.

        Args:
            width: The requested width in pixels, if any.
            height: The requested height; unused, the server keeps the aspect.

        Returns:
            The image bytes, or `None` when the library could not fetch one.

        """
        try:
            image = await self._client.async_get_camera_image(
                self.coordinator.data.server, self.camera_number, width=width
            )
        except (SecuritySpyError, ValueError) as err:
            # `ValueError` is the library refusing a width below 1, which a
            # caller can request through the image proxy's query string.
            # Class name only: the message is the library's, and a log line is
            # no place to find out whether it quotes anything sensitive.
            _LOGGER.debug(
                "Could not fetch a still image for camera %s: %s",
                self.camera_number,
                type(err).__name__,
            )
            return None
        return image.data


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SecuritySpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one camera entity per camera, or clear them when the option is off.

    Registry entries are removed rather than left orphaned, so turning the
    option off leaves nothing behind. Turning it back on recreates them under
    the same unique ids.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set cameras up for.
        async_add_entities: Callback to register the new entities.

    """
    if not entry.options.get(CONF_CREATE_CAMERA_ENTITIES, True):
        entity_registry = er.async_get(hass)
        for registry_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
            if registry_entry.domain == "camera":
                entity_registry.async_remove(registry_entry.entity_id)
        return

    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    async_add_entities(
        SecuritySpyCamera(coordinator, camera_number, runtime_data.client, runtime_data.relay)
        for camera_number in coordinator.data.server.cameras
    )
