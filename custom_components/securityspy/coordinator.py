"""The single coordinator (AD-4), sole writer of the device registry.

No push stream exists yet (that is Epic 3), so this coordinator is a
deliberately smaller slice of the eventual, stream-fed design described in
``docs/ha-integration-reference.md``: it is seeded once from the ``ServerInfo``
``__init__.py`` already fetched, registers devices from that seed, and then
only re-fetches on its own slow periodic timer. Only the coordinator ever
writes to the device registry (AD-12): platforms and entities read from it,
never through it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Final

from aiosecurityspy import SecuritySpyError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, RECONCILE_INTERVAL
from .entity import camera_device_info, hub_device_info

if TYPE_CHECKING:
    from datetime import datetime

    from aiosecurityspy import SecuritySpyClient, ServerInfo
    from homeassistant.core import HomeAssistant

    from . import SecuritySpyConfigEntry

LOGGER: Final = logging.getLogger(__package__)


class SecuritySpyDataUpdateCoordinator(DataUpdateCoordinator["ServerInfo"]):
    """Owns the device registry sync and the reconciliation timer.

    ``update_interval=None`` (AD-4): this coordinator is not base-class polled.
    The only interval-driven behaviour it has is the reconciliation timer it
    schedules itself in :meth:`async_start`.
    """

    config_entry: SecuritySpyConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SecuritySpyConfigEntry,
        client: SecuritySpyClient,
        server: ServerInfo,
    ) -> None:
        """Initialize the coordinator, seeded with the already-fetched server.

        Args:
            hass: The Home Assistant instance.
            entry: The config entry this coordinator belongs to.
            client: The library client used for the periodic re-fetch.
            server: The `ServerInfo` `__init__.py` already fetched for
                `test-before-setup`. Assigned directly to `self.data` rather
                than through `async_set_updated_data`: there are no listeners
                yet at construction time, so there is nothing for that method's
                notification to reach, and calling it would misreport this as
                an *update* rather than the coordinator's initial state.

        """
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.client = client
        self.data = server

    async def async_start(self) -> None:
        """Register devices from the already-seeded data, then start polling.

        Does **not** call `client.async_get_server_info()` again: `self.data`
        is already the server `__init__.py` fetched moments earlier for
        `test-before-setup`, so re-fetching here would be a wasted network
        round-trip on every startup and risks `entry.runtime_data.server`
        silently diverging from `coordinator.data` if the account's camera
        inventory changed in the moment between two back-to-back calls. Only
        the periodic timer's `_async_reconcile` re-fetches.
        """
        self._sync_device_registry(self.data)
        self.config_entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_reconcile, RECONCILE_INTERVAL)
        )

    async def _async_reconcile(self, _now: datetime | None = None) -> None:
        """Re-fetch the server and reconcile the device registry from it.

        On failure, the registry is left untouched and the failure is logged
        once at `DEBUG` -- this story does not escalate a poll failure (auth
        counting and reauth are story 2.8's job); the next scheduled attempt
        simply retries.

        Args:
            _now: The time the timer fired, per `async_track_time_interval`'s
                callback signature. Unused: the reconciliation does not care
                when it runs, only that it did.

        """
        try:
            server = await self.client.async_get_server_info()
        except SecuritySpyError as err:
            # SecuritySpyConnectError, SecuritySpyAuthError and
            # SecuritySpyUnsupportedVersionError are all subclasses of this and
            # every branch takes the same action here -- this story does not
            # escalate any of them (auth counting and reauth are story 2.8's
            # job); the next scheduled attempt simply retries.
            LOGGER.debug("Periodic reconciliation failed: %s", err)
            return

        try:
            # Sync before publishing: a listener (the first arrives in story
            # 2.4) must never observe `self.data` ahead of the device registry
            # it describes.
            self._sync_device_registry(server)
        except Exception:
            # An unexpected failure writing to the device registry -- not one
            # of this story's typed library errors -- must not kill this
            # periodic callback for every future cycle; log loudly and let the
            # next scheduled attempt retry, same as a poll failure above.
            LOGGER.exception("Unexpected error while reconciling the device registry")
            return

        self.async_set_updated_data(server)

    def _sync_device_registry(self, server: ServerInfo) -> None:
        """Create/update the hub and every camera device, then drop stale ones.

        Diffs `server.cameras` against the registry's own current devices for
        this config entry -- not against `self.data.cameras` -- so a device
        deleted out-of-band (e.g. by hand in the HA UI) is self-healingly
        recreated on the next reconciliation rather than staying missing
        forever, and a camera genuinely removed from the inventory is the only
        thing that gets its device removed.

        Args:
            server: The server state to register devices from.

        """
        registry = dr.async_get(self.hass)
        entry_id = self.config_entry.entry_id

        hub_entry = registry.async_get_or_create(
            config_entry_id=entry_id, **hub_device_info(server)
        )

        for camera in server.cameras.values():
            registry.async_get_or_create(
                config_entry_id=entry_id, **camera_device_info(server, camera)
            )

        known_numbers = set(server.cameras)
        prefix = f"{server.uuid}_"
        for device in dr.async_entries_for_config_entry(registry, entry_id):
            if device.id == hub_entry.id:
                continue
            camera_number = self._camera_number_for(device, prefix)
            if camera_number is None or camera_number not in known_numbers:
                registry.async_remove_device(device.id)

    @staticmethod
    def _camera_number_for(device: dr.DeviceEntry, prefix: str) -> int | None:
        """Extract the camera number encoded in one of a device's identifiers.

        Args:
            device: A device registered under this config entry.
            prefix: `"{server.uuid}_"`, the camera-identifier prefix.

        Returns:
            The camera number, or `None` when no identifier of this device
            matches the expected `(DOMAIN, "{uuid}_{number}")` shape -- under
            the sole-writer invariant this only happens for the hub device
            itself (already excluded by the caller), never for a malformed
            camera device.

        """
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier.startswith(prefix):
                suffix = identifier.removeprefix(prefix)
                if suffix.isdigit():
                    return int(suffix)
        return None
