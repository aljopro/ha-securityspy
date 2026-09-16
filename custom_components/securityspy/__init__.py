"""The SecuritySpy integration.

Setup owns the one exception-mapping seam required by AD-6: library-typed
errors become Home Assistant config-entry failures here and nowhere else, so a
future coordinator or platform never re-decides what a connect error means.

The coordinator (``coordinator.py``) and the device-identity builders
(``entity.py``) exist as of story 2.3, and setup starts the coordinator here
before forwarding platform setups. Story 2.4 adds the first entity classes
and platform module (``sensor.py``), so :data:`PLATFORMS` is no longer empty.
Story 2.6 adds the ``camera`` platform and the library RTSP relay it streams
through, so no credential-bearing URL ever leaves the library (AD-13).
Story 2.7 adds the shared permission gate (``permissions.py``): platforms ask it
before creating a permission-dependent entity, and setup turns its recorded
denials into repair issues once every platform has been forwarded.
Story 3.1 adds ``async_remove_config_entry_device``: reconciliation no longer
removes devices, so a camera that leaves the inventory is deleted by the user.
Story 3.2 adds ``_async_start_stream``: the Event Stream is built here, right
alongside the RTSP relay it mirrors in shape, and its lifecycle callbacks are
pointed at the coordinator (``coordinator.py`` owns what each one does).
Connecting is non-blocking (``connect()`` schedules the reader and returns),
so a server that is unreachable at startup does not delay setup -- the same
``ConfigEntryNotReady`` retry above already covers that case for the initial
fetch, and the stream's own indefinite backoff covers every later one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, timezone
from typing import TYPE_CHECKING, Final

from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyCertificateError,
    SecuritySpyClient,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyPermissionError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CREATE_CAMERA_ENTITIES, DOMAIN
from .coordinator import SecuritySpyDataUpdateCoordinator
from .permissions import PermissionGate, issue_id

_LOGGER: Final = logging.getLogger(__name__)

if TYPE_CHECKING:
    from aiosecurityspy import RtspRelay, SecuritySpyEventStream, ServerInfo, StreamEvent
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr

#: Story 2.4 added the first platform: diagnostic sensors for hub and camera
#: health. Story 2.5 adds a single hub-level update entity, and story 2.6 the
#: live video camera entities.
PLATFORMS: list[Platform] = [Platform.CAMERA, Platform.SENSOR, Platform.UPDATE]


@dataclass
class SecuritySpyRuntimeData:
    """Everything the integration owns for one config entry.

    Stored on ``entry.runtime_data`` rather than ``hass.data[DOMAIN]``, which
    the Bronze ``runtime-data`` rule forbids (AD-12).
    """

    client: SecuritySpyClient
    server: ServerInfo
    coordinator: SecuritySpyDataUpdateCoordinator
    #: The one permission gate every platform consults (story 2.7).
    permission_gate: PermissionGate
    #: The connected (or reconnecting) Event Stream (story 3.2). Always
    #: present -- unlike the relay, nothing makes the stream optional.
    stream: SecuritySpyEventStream
    #: The started RTSP relay, or ``None`` when camera entities are off, the
    #: server publishes no RTSP port, or the relay could not bind.
    relay: RtspRelay | None = None


#: Typed config entry. Every function that takes an entry uses this alias, so
#: ``entry.runtime_data`` is statically known to be a
#: :class:`SecuritySpyRuntimeData`.
type SecuritySpyConfigEntry = ConfigEntry[SecuritySpyRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SecuritySpyConfigEntry) -> bool:
    """Set up SecuritySpy from a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set up.

    Raises:
        ConfigEntryNotReady: The server could not be reached. Home Assistant
            retries with backoff.
        ConfigEntryAuthFailed: The stored credentials were rejected.
        ConfigEntryError: The server is permanently incompatible; retrying
            cannot help.

    Returns:
        ``True`` once the entry is usable.

    """
    try:
        # Both TLS choices are read from the entry and applied here, to the
        # session and to the client alike. Every later connection -- including
        # the event stream Epic 3 spawns from this client -- inherits them from
        # the client rather than re-reading the entry, so there is one place
        # they are decided. Read inside the guard: a key missing from stored
        # data is the same class of problem as a value the client rejects, and
        # a bare `KeyError` traceback would be a worse report of it.
        verify_ssl: bool = entry.data[CONF_VERIFY_SSL]
        use_https: bool = entry.data[CONF_SSL]
        if use_https and not verify_ssl:
            # The only ongoing record of the choice. Every request -- and the
            # Epic 3 event stream -- carries the HTTP Basic credential to
            # whatever answers this address, so a setting flipped once during
            # troubleshooting should not stay silent. No credential is logged.
            #
            # Gated on HTTPS as well: nothing in the form couples the two
            # toggles, so a plain-HTTP entry can carry verification off. There
            # is no certificate to check on such a connection, and the form
            # already says the flag is "only used when Connect over HTTPS is
            # on" -- warning about it anyway would describe a risk the entry
            # does not run, and teach the reader to ignore the line that
            # matters when it does.
            _LOGGER.warning(
                "Certificate verification is disabled for the SecuritySpy server at %s:%s; "
                "its identity is not being checked on any connection",
                entry.data[CONF_HOST],
                entry.data[CONF_PORT],
            )
        client = SecuritySpyClient(
            # inject-websession (Platinum): the integration never builds a
            # session. Home Assistant keeps one per verification setting, each
            # with an SSL context built off the event loop.
            async_get_clientsession(hass, verify_ssl=verify_ssl),
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            use_https=use_https,
            # The per-request `ssl=` flag must agree with the session's
            # connector: `ssl=True` resolves by deferring to it.
            verify_ssl=verify_ssl,
        )
    except (KeyError, TypeError, ValueError) as err:
        # Stored data the client cannot use -- a hand-edited entry, a restore
        # from a future schema, or an entry written before a field existed.
        # Retrying cannot help, so it is permanent. `KeyError` is included
        # because a missing key is exactly that condition, and it is not a
        # `ValueError`: without this it would escape as a raw traceback.
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="invalid_stored_data"
        ) from err

    # test-before-setup (Bronze): prove the server is usable before any entity
    # or listener exists, and map the failure exactly once (AD-6).
    try:
        server = await client.async_get_server_info()
    except SecuritySpyAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from err
    except SecuritySpyPermissionError as err:
        # The credentials are correct but the account lacks a permission
        # `async_get_server_info` needs -- re-authenticating cannot fix this,
        # so it is a permanent `ConfigEntryError`, not `ConfigEntryAuthFailed`
        # (which would send the user through a reauth flow that changes
        # nothing) and not `ConfigEntryNotReady` (which would retry forever).
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="permission_denied"
        ) from err
    except SecuritySpyUnsupportedVersionError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="unsupported_version"
        ) from err
    except SecuritySpyCertificateError as err:
        # Must precede the `SecuritySpyConnectError` clause it subclasses, or the
        # certificate-specific message is unreachable. `NotReady` rather than
        # `ConfigEntryError` because one of the two causes self-heals: an expired
        # certificate is fixed by renewal without anyone touching Home Assistant,
        # and `NotReady` picks that up on its own. The other cause -- a name the
        # certificate was not issued for, which the user-facing string names as
        # the likelier one -- is permanent, but its repair is story 2.9's
        # reconfigure flow; a permanent error here would strand the entry until a
        # manual reload without bringing that repair any closer.
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="invalid_certificate"
        ) from err
    except SecuritySpyConnectError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="cannot_connect"
        ) from err
    except SecuritySpyError as err:
        # A typed library failure this story does not model. Treated as transient
        # so Home Assistant retries rather than stranding the entry on a failure
        # nobody has classified yet.
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="unknown") from err

    coordinator = SecuritySpyDataUpdateCoordinator(hass, entry, client, server)
    relay = await _async_start_relay(entry, client, server)

    # Registers devices from the server already fetched above -- no second
    # fetch (see coordinator.async_start's own docstring) -- and schedules the
    # periodic reconciliation timer that keeps them current without a reload.
    # Deliberately before `_async_start_stream`: `async_handle_stream_connected`
    # skips reconciling on the stream's first connect on the strength of the
    # registry already being synced, which is only true if this has already
    # run -- `async_start` itself never awaits anything, but the stream's own
    # reader does, so starting the stream first would leave that ordering an
    # accident of scheduling rather than a fact the code establishes.
    await coordinator.async_start()

    stream = await _async_start_stream(entry, client, server, coordinator)
    entry.runtime_data = SecuritySpyRuntimeData(
        client=client,
        server=server,
        coordinator=coordinator,
        permission_gate=PermissionGate(coordinator, entry.entry_id),
        stream=stream,
        relay=relay,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # After forwarding, so every platform has asked the gate: one issue per
    # denied permission lists every affected camera, and any permission no
    # longer denied has its issue cleared.
    entry.runtime_data.permission_gate.async_update_issues(hass)
    return True


async def _async_start_relay(
    entry: SecuritySpyConfigEntry, client: SecuritySpyClient, server: ServerInfo
) -> RtspRelay | None:
    """Start the RTSP relay the camera entities stream through, if one applies.

    The relay exists only while the ``create_camera_entities`` option is on, so
    turning the option off (which reloads the entry) stops it and every address
    it issued: relay addresses cannot be revoked one by one. Opening its
    listener sends nothing to SecuritySpy; an upstream connection is made only
    when a consumer plays a stream.

    Args:
        entry: The config entry being set up. The relay's stop is registered on
            its unload.
        client: The client whose credential the relay authenticates with.
        server: The permission-scoped inventory the relay serves.

    Returns:
        The started relay, or ``None`` when the option is off, the server
        publishes no RTSP port, or the local listener could not bind.

    """
    if not entry.options.get(CONF_CREATE_CAMERA_ENTITIES, True) or server.rtsp_port is None:
        return None
    # Loopback bind and library defaults: only this Home Assistant's own stream
    # worker needs to reach it.
    relay = client.create_rtsp_relay(server)
    try:
        await relay.async_start()
    except OSError:
        # No detail: the entities still offer stills, and a bind error names
        # only local addresses that would not help anyone reading the log.
        _LOGGER.warning(
            "Could not start the local live video relay; SecuritySpy camera "
            "streams are unavailable until the entry is reloaded"
        )
        return None
    entry.async_on_unload(relay.async_stop)
    return relay


async def _async_start_stream(
    entry: SecuritySpyConfigEntry,
    client: SecuritySpyClient,
    server: ServerInfo,
    coordinator: SecuritySpyDataUpdateCoordinator,
) -> SecuritySpyEventStream:
    """Build the Event Stream, wire its lifecycle into the coordinator, and connect it.

    Registered for unload before connecting, not after: `disconnect()` is
    idempotent (FR-33), so there is no harm in owning the callback a moment
    before there is anything to disconnect, and doing it first means a stream
    that somehow starts delivering before this function returns can never
    outlive the entry that owns it.

    Heartbeat and backoff tuning are left at the library's own defaults
    (AD-11): they already match this project's documented interval (loss
    within 3 missed heartbeats) and retry policy (indefinite exponential
    backoff), so restating them here would only be a second place for the two
    to drift apart.

    Args:
        entry: The config entry the stream belongs to; its unload stops the
            stream.
        client: The client the stream reads its validated connection from.
        server: The already-fetched server, whose `utc_offset` timestamps the
            stream's own events. `[ASSUMPTION]` (library-documented): no
            SecuritySpy endpoint publishes it independently of `++systemInfo`,
            so a server that omits it is treated as UTC -- the library's own
            fallback for the same gap.
        coordinator: Whose `async_handle_stream_connected`,
            `async_handle_stream_disconnected`, `async_handle_stream_reconnected`
            and `record_auth_failure` become the stream's four lifecycle
            callbacks.

    Returns:
        The connecting (or already-connected) stream.

    """
    stream = client.event_stream(
        on_event=_async_handle_stream_event,
        on_connected=coordinator.async_handle_stream_connected,
        on_disconnected=coordinator.async_handle_stream_disconnected,
        on_reconnected=coordinator.async_handle_stream_reconnected,
        on_auth_failed=coordinator.record_auth_failure,
        server_timezone=timezone(server.utc_offset) if server.utc_offset is not None else UTC,
    )
    entry.async_on_unload(stream.disconnect)
    # Non-blocking (AD-10): schedules the reader and returns rather than
    # waiting for the first handshake, so a server that is down at startup
    # does not delay `async_setup_entry` -- the stream's own indefinite
    # backoff (AD-11) keeps retrying afterwards regardless.
    await stream.connect()
    return stream


async def _async_handle_stream_event(event: StreamEvent) -> None:
    """Discard a decoded event; no consumer reads one yet.

    `on_event` is not optional on `SecuritySpyEventStream` (a stream with
    nothing to deliver events to is still a stream), but this story owns only
    the connection lifecycle (FR-31) -- Epic 4/5 are what read a `StreamEvent`
    to update observation state, and until one of them exists there is
    nothing correct to do with it here.
    """


async def async_unload_entry(hass: HomeAssistant, entry: SecuritySpyConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to unload.

    Returns:
        Whether every platform unloaded cleanly.

    """
    # No explicit coordinator shutdown call is needed here: the coordinator's
    # reconciliation timer was registered through `entry.async_on_unload` in
    # `async_start`, and `ConfigEntry._async_process_on_unload` runs those
    # callbacks unconditionally on unload -- independent of whether any
    # platform was forwarded, so an empty `PLATFORMS` does not skip it.
    # Missing-permission issues are deliberately left in place: a reload
    # re-evaluates them, and only `async_remove_entry` deletes them.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant,  # noqa: ARG001 - required integration signature
    entry: SecuritySpyConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow deleting a camera device only once its camera left the inventory.

    Gold `stale-devices`: the coordinator never removes a device itself, so
    the user can. The hub, and any camera still inventoried (online or not),
    are refused -- the next reconciliation would recreate them anyway.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry the device belongs to.
        device_entry: The device the user asked to delete.

    Returns:
        ``True`` only when the entry is loaded, the device is a camera device
        of this server, and that camera is absent from the current inventory.

    """
    if entry.state is not ConfigEntryState.LOADED:
        # Without a loaded coordinator there is no current inventory to check
        # against, so nothing can be proven stale.
        return False
    coordinator = entry.runtime_data.coordinator
    if not coordinator.last_update_success:
        # During an outage the held inventory is stale: a camera missing from
        # it may be back, so nothing can be proven stale until a poll succeeds.
        return False
    server = coordinator.data.server
    camera_number = SecuritySpyDataUpdateCoordinator._camera_number_for(  # noqa: SLF001 - one identity parser, shared with the coordinator
        device_entry, f"{server.uuid}_"
    )
    return camera_number is not None and camera_number not in server.cameras


async def async_remove_entry(hass: HomeAssistant, entry: SecuritySpyConfigEntry) -> None:
    """Delete the missing-permission issues of a removed config entry.

    Unload leaves them in place so a reload can re-evaluate them; only removal
    means nothing will. Only this entry's issues go; another server's stay.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry being removed.

    """
    for permission in PermissionGate.permission_names():
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry.entry_id, permission))
