"""The single coordinator (AD-4), sole writer of the device registry.

No push stream exists yet (that is Epic 3), so this coordinator is a
deliberately smaller slice of the eventual, stream-fed design described in
``docs/ha-integration-reference.md``: it is seeded once from the ``ServerInfo``
``__init__.py`` already fetched, registers devices from that seed, and then
only re-fetches on its own slow periodic timer. Only the coordinator ever
writes to the device registry (AD-12): platforms and entities read from it,
never through it.

Story 2.4 adds a second, faster timer alongside the original reconciliation
one: `_async_poll_light_status` refreshes per-camera `last_error` from the
cheap ``++camStatus`` endpoint on `LIGHT_POLL_INTERVAL`, while the original
`_async_reconcile` timer keeps re-fetching the heavy ``++systemInfo`` endpoint
on `RECONCILE_INTERVAL` for everything the light endpoint cannot provide.
`SecuritySpyData` wraps both results so entities (the first arrive in this
story) can read either without the coordinator's generic type having to be a
bare `ServerInfo`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from aiosecurityspy import SecuritySpyError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, LIGHT_POLL_INTERVAL, RECONCILE_INTERVAL
from .entity import camera_device_info, hub_device_info

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from aiosecurityspy import CameraStatus, SecuritySpyClient, ServerInfo
    from homeassistant.core import HomeAssistant

    from . import SecuritySpyConfigEntry

LOGGER: Final = logging.getLogger(__package__)


@dataclass(frozen=True)
class SecuritySpyData:
    """Everything the coordinator publishes to its listeners.

    Wraps `server` (the last successful heavy `++systemInfo` fetch) alongside
    `camera_statuses` (the last successful light `++camStatus` fetch, keyed by
    camera number) because `last_error` must come from the light poll (the
    epic's own "prefer light" requirement) while every other health field only
    exists on `server`. This is the smallest wrapper that satisfies that real
    need -- not `visible_camera_views()`, which intersects against permission
    membership (story 2.7's job, not this one's).
    """

    server: ServerInfo
    camera_statuses: Mapping[int, CameraStatus]
    #: Each inventoried camera's decoded permission names, keyed by camera
    #: number and rebuilt from `server` on every heavy refresh. Story 2.7's
    #: `PermissionGate` reads this; no platform decodes a mask itself.
    camera_permissions: Mapping[int, frozenset[str]]


def _camera_permissions(server: ServerInfo) -> Mapping[int, frozenset[str]]:
    """Map every inventoried camera to its decoded permission names.

    Args:
        server: The server whose `cameras` to read.

    Returns:
        A read-only mapping of camera number to the library's
        `Camera.permission_names`.

    """
    return MappingProxyType(
        {number: camera.permission_names for number, camera in server.cameras.items()}
    )


class SecuritySpyDataUpdateCoordinator(DataUpdateCoordinator[SecuritySpyData]):
    """Owns the device registry sync and the two reconciliation timers.

    ``update_interval=None`` (AD-4): this coordinator is not base-class polled.
    The only interval-driven behaviour it has are the two timers it schedules
    itself in :meth:`async_start`.
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
            client: The library client used for the periodic re-fetches.
            server: The `ServerInfo` `__init__.py` already fetched for
                `test-before-setup`. Wrapped in `SecuritySpyData` and assigned
                directly to `self.data` rather than through
                `async_set_updated_data`: there are no listeners yet at
                construction time, so there is nothing for that method's
                notification to reach, and calling it would misreport this as
                an *update* rather than the coordinator's initial state.

        """
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=None)
        self.client = client
        self.data = SecuritySpyData(
            server=server,
            camera_statuses=MappingProxyType({}),
            camera_permissions=_camera_permissions(server),
        )

    async def async_start(self) -> None:
        """Register devices from the already-seeded data, then start polling.

        Does **not** call `client.async_get_server_info()` again: `self.data`
        is already the server `__init__.py` fetched moments earlier for
        `test-before-setup`, so re-fetching here would be a wasted network
        round-trip on every startup and risks `entry.runtime_data.server`
        silently diverging from `coordinator.data` if the account's camera
        inventory changed in the moment between two back-to-back calls. Only
        the periodic timers re-fetch.
        """
        self._sync_device_registry(self.data.server)
        self.config_entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_reconcile, RECONCILE_INTERVAL)
        )
        self.config_entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_poll_light_status, LIGHT_POLL_INTERVAL)
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
            # Sync before publishing: a listener must never observe
            # `self.data` ahead of the device registry it describes.
            self._sync_device_registry(server)
        except Exception:
            # An unexpected failure writing to the device registry -- not one
            # of this story's typed library errors -- must not kill this
            # periodic callback for every future cycle; log loudly and let the
            # next scheduled attempt retry, same as a poll failure above.
            LOGGER.exception("Unexpected error while reconciling the device registry")
            return

        # Preserve the last-known `camera_statuses` across a heavy refresh --
        # they are the light poll's responsibility, and a heavy-only refresh
        # must not reset them to empty.
        self.async_set_updated_data(
            replace(
                self.data,
                server=server,
                camera_statuses=self._pruned_statuses(server),
                camera_permissions=_camera_permissions(server),
            )
        )

    async def _async_poll_light_status(self, _now: datetime | None = None) -> None:
        """Re-fetch per-camera health from the cheap ``++camStatus`` endpoint.

        On failure, `self.data` is left untouched and the failure is logged
        once at `DEBUG`, exactly mirroring `_async_reconcile`'s own failure
        handling -- the next scheduled attempt simply retries.

        Args:
            _now: The time the timer fired, per `async_track_time_interval`'s
                callback signature. Unused: the poll does not care when it
                runs, only that it did.

        """
        try:
            statuses = await self.client.async_get_camera_status()
        except SecuritySpyError as err:
            LOGGER.debug("Periodic light status poll failed: %s", err)
            return
        except Exception:
            # Mirrors `_async_reconcile`'s own guard: an unexpected failure
            # here must not kill this periodic callback for every future
            # cycle; log loudly and let the next scheduled attempt retry.
            LOGGER.exception("Unexpected error while polling light camera status")
            return

        # Filtered to the current inventory, same as `_pruned_statuses` does
        # for a heavy refresh -- otherwise a status for a camera that has
        # already left `server.cameras` would linger here until the next
        # heavy reconcile, up to `RECONCILE_INTERVAL` later.
        known_numbers = set(self.data.server.cameras)
        by_number = MappingProxyType(
            {status.number: status for status in statuses if status.number in known_numbers}
        )
        self.async_set_updated_data(replace(self.data, camera_statuses=by_number))

    def _pruned_statuses(self, server: ServerInfo) -> Mapping[int, CameraStatus]:
        """Drop any status entry for a camera no longer in `server.cameras`.

        A camera can leave the inventory between a light poll applying and the
        next heavy reconcile; without this, its stale status would linger in
        `self.data.camera_statuses` with no device or entity left to read it.

        Args:
            server: The freshly re-fetched server, whose `cameras` is the new
                authoritative inventory.

        Returns:
            `self.data.camera_statuses`, filtered to cameras still present.

        """
        known_numbers = set(server.cameras)
        return MappingProxyType(
            {
                number: status
                for number, status in self.data.camera_statuses.items()
                if number in known_numbers
            }
        )

    def _sync_device_registry(self, server: ServerInfo) -> None:
        """Create/update the hub and every camera device, then drop stale ones.

        Diffs `server.cameras` against the registry's own current devices for
        this config entry -- not against `self.data.server.cameras` -- so a
        device deleted out-of-band (e.g. by hand in the HA UI) is
        self-healingly recreated on the next reconciliation rather than
        staying missing forever, and a camera genuinely removed from the
        inventory is the only thing that gets its device removed.

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
