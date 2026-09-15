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

Story 2.8 adds AD-18's consecutive-auth-failure counter. Both polls feed it,
and so will Epic 3's stream through the public `record_auth_failure` /
`record_auth_success` hooks. On the `AUTH_FAILURE_THRESHOLD`-th consecutive
failure the coordinator stops both timers and starts reauth.

Story 3.1 makes a failed poll visible instead of silently keeping stale data:
either poll failing flips `last_update_success` to False, so every entity goes
unavailable until the next successful poll restores it through
`async_set_updated_data`. It also adds the `stream_connected` flag the push
availability layer reads (Story 3.2 wires the stream that sets it), and stops
reconciliation from removing devices: a camera that leaves the inventory keeps
its device, and history, until the user deletes it through
`async_remove_config_entry_device`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from aiosecurityspy import SecuritySpyAuthError, SecuritySpyError
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import AUTH_FAILURE_THRESHOLD, DOMAIN, LIGHT_POLL_INTERVAL, RECONCILE_INTERVAL
from .entity import camera_device_info, hub_device_info

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
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
        #: Consecutive `SecuritySpyAuthError`s across every plane (AD-18).
        #: Starts at zero on every setup, so a reload after reauth begins clean.
        self.auth_failures = 0
        #: The two timers' cancel callbacks, kept so reaching the threshold can
        #: stop polling without waiting for an unload.
        self._timer_unsubs: list[Callable[[], None]] = []
        #: Latched when the threshold starts reauth; freezes the counter.
        self._reauth_started = False
        #: Whether the Event Stream is currently connected -- the fourth
        #: availability layer, read only by push-derived entities. False until
        #: Story 3.2 wires the stream: no stream exists yet, so claiming it is
        #: healthy would make a push-derived entity look live when nothing
        #: could be feeding it.
        self.stream_connected = False

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
        self._timer_unsubs = [
            async_track_time_interval(self.hass, self._async_reconcile, RECONCILE_INTERVAL),
            async_track_time_interval(
                self.hass, self._async_poll_light_status, LIGHT_POLL_INTERVAL
            ),
        ]
        # One idempotent cancel registered for unload, rather than the raw
        # unsubs: the threshold may already have cancelled the timers, and
        # calling a timer's unsub twice is not safe.
        self.config_entry.async_on_unload(self._cancel_timers)

    @callback
    def _cancel_timers(self) -> None:
        """Stop both poll timers; safe to call any number of times."""
        unsubs, self._timer_unsubs = self._timer_unsubs, []
        for unsub in unsubs:
            unsub()

    @callback
    def async_set_stream_connected(self, connected: bool) -> None:  # noqa: FBT001 - mirrors the stream's own connected/disconnected callbacks
        """Record the Event Stream's health, notifying listeners on a change.

        A repeated report of the same state is a no-op, so a stream that
        reconnects without ever having dropped does not rewrite every entity.

        Args:
            connected: Whether the stream is connected now.

        """
        if connected == self.stream_connected:
            return
        self.stream_connected = connected
        self.async_update_listeners()

    @callback
    def _async_mark_poll_failed(self) -> None:
        """Mark the coordinator's last update as failed, once per outage.

        Listeners are notified only on the True-to-False transition: a
        second failing poll changes no entity's availability, so writing every
        state again would be pure noise. The next successful poll restores
        `last_update_success` through `async_set_updated_data`.
        """
        if not self.last_update_success:
            return
        self.last_update_success = False
        self.async_update_listeners()

    @callback
    def record_auth_failure(self) -> None:
        """Count one rejected credential, starting reauth at the threshold.

        Public so Epic 3's event stream can report its own auth failures into
        the same counter the polls use (AD-18). Only the call that *reaches*
        the threshold acts: later calls -- a poll already in flight when the
        timers stopped, or the stream -- do not start a second reauth.
        """
        if self._reauth_started:
            return
        self.auth_failures += 1
        if self.auth_failures < AUTH_FAILURE_THRESHOLD:
            return
        self._reauth_started = True
        # Stop polling first: a dead password retried every 30 seconds could
        # also trip an account lockout on the server.
        self._cancel_timers()
        LOGGER.warning(
            "SecuritySpy rejected the stored credentials %d times in a row; "
            "polling stopped until they are entered again",
            AUTH_FAILURE_THRESHOLD,
        )
        # What `ConfigEntryAuthFailed` does internally; a timer callback cannot
        # raise that, so the flow is started directly.
        self.config_entry.async_start_reauth(self.hass)

    @callback
    def record_auth_success(self) -> None:
        """Reset the counter after any request the server authenticated.

        Ignored once reauth has started: a poll already in flight when the
        timers stopped must not re-arm the counter, or a later failure run
        would start a second reauth. Only the reload that finishes reauth
        builds a fresh coordinator with a fresh count.
        """
        if self._reauth_started:
            return
        self.auth_failures = 0

    async def _async_reconcile(self, _now: datetime | None = None) -> None:
        """Re-fetch the server and reconcile the device registry from it.

        On failure, the registry and `self.data` are left untouched, the
        failure is logged once at `DEBUG`, and `last_update_success` goes
        False so entities report unavailable rather than stale; the next
        scheduled attempt simply retries. A
        `SecuritySpyAuthError` additionally counts towards reauth, and a
        successful fetch resets that count.

        Args:
            _now: The time the timer fired, per `async_track_time_interval`'s
                callback signature. Unused: the reconciliation does not care
                when it runs, only that it did.

        """
        try:
            server = await self.client.async_get_server_info()
        except SecuritySpyError as err:
            # Every library error is logged the same way and retried on the
            # next tick. Only an auth rejection also counts: a permission
            # denial means the password *worked*, and a connect error says
            # nothing about the password at all.
            LOGGER.debug("Periodic reconciliation failed: %s", err)
            if isinstance(err, SecuritySpyAuthError):
                self.record_auth_failure()
            self._async_mark_poll_failed()
            return
        except Exception:
            # Same guard as the light poll: an unexpected failure must not kill
            # this periodic callback, and the server did not answer usefully,
            # so entities go unavailable exactly as for a library error.
            LOGGER.exception("Unexpected error while reconciling the server")
            self._async_mark_poll_failed()
            return

        self.record_auth_success()
        try:
            # Sync before publishing: a listener must never observe
            # `self.data` ahead of the device registry it describes.
            self._sync_device_registry(server)
        except Exception:
            # An unexpected failure writing to the device registry -- not one
            # of this story's typed library errors -- must not kill this
            # periodic callback for every future cycle; log loudly and let the
            # next scheduled attempt retry. Availability is not touched: the
            # server did answer, so its entities are not stale.
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

        On failure, `self.data` is left untouched, the failure is logged once
        at `DEBUG` and `last_update_success` goes False, exactly mirroring
        `_async_reconcile`'s own failure handling -- the next scheduled attempt
        simply retries, and an auth rejection counts towards reauth in the same
        shared counter.

        Args:
            _now: The time the timer fired, per `async_track_time_interval`'s
                callback signature. Unused: the poll does not care when it
                runs, only that it did.

        """
        try:
            statuses = await self.client.async_get_camera_status()
        except SecuritySpyError as err:
            LOGGER.debug("Periodic light status poll failed: %s", err)
            if isinstance(err, SecuritySpyAuthError):
                self.record_auth_failure()
            self._async_mark_poll_failed()
            return
        except Exception:
            # Mirrors `_async_reconcile`'s own guard: an unexpected failure
            # here must not kill this periodic callback for every future
            # cycle; log loudly and let the next scheduled attempt retry.
            LOGGER.exception("Unexpected error while polling light camera status")
            self._async_mark_poll_failed()
            return

        self.record_auth_success()
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
        """Create or update the hub and every inventoried camera device.

        `async_get_or_create` runs for every camera on every pass, so a device
        deleted out-of-band (e.g. by hand in the HA UI) while its camera is
        still inventoried is self-healingly recreated on the next
        reconciliation rather than staying missing forever. Devices are never
        removed here: a camera that leaves the inventory may be disabled,
        de-permissioned or deleted, which this integration cannot tell apart,
        so its device and history stay until the user removes it
        (`async_remove_config_entry_device`); its entities report unavailable.

        Args:
            server: The server state to register devices from.

        """
        registry = dr.async_get(self.hass)
        entry_id = self.config_entry.entry_id

        registry.async_get_or_create(config_entry_id=entry_id, **hub_device_info(server))

        for camera in server.cameras.values():
            registry.async_get_or_create(
                config_entry_id=entry_id, **camera_device_info(server, camera)
            )

    @staticmethod
    def _camera_number_for(device: dr.DeviceEntry, prefix: str) -> int | None:
        """Extract the camera number encoded in one of a device's identifiers.

        Args:
            device: A device registered under this config entry.
            prefix: `"{server.uuid}_"`, the camera-identifier prefix.

        Returns:
            The camera number, or `None` when no identifier of this device
            matches the expected `(DOMAIN, "{uuid}_{number}")` shape -- under
            the sole-writer invariant, normally only the hub device.

        """
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier.startswith(prefix):
                suffix = identifier.removeprefix(prefix)
                if suffix.isdigit():
                    return int(suffix)
        return None
