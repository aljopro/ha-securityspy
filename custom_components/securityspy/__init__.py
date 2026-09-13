"""The SecuritySpy integration.

Setup owns the one exception-mapping seam required by AD-6: library-typed
errors become Home Assistant config-entry failures here and nowhere else, so a
future coordinator or platform never re-decides what a connect error means.

The coordinator (``coordinator.py``) and the device-identity builders
(``entity.py``) exist as of story 2.3, and setup starts the coordinator here
before forwarding platform setups. Story 2.4 adds the first entity classes
and platform module (``sensor.py``), so :data:`PLATFORMS` is no longer empty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
from homeassistant.config_entries import ConfigEntry
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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import SecuritySpyDataUpdateCoordinator

_LOGGER: Final = logging.getLogger(__name__)

if TYPE_CHECKING:
    from aiosecurityspy import ServerInfo
    from homeassistant.core import HomeAssistant

#: Story 2.4 adds the first platform: diagnostic sensors for hub and camera
#: health.
PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class SecuritySpyRuntimeData:
    """Everything the integration owns for one config entry.

    Stored on ``entry.runtime_data`` rather than ``hass.data[DOMAIN]``, which
    the Bronze ``runtime-data`` rule forbids (AD-12).
    """

    client: SecuritySpyClient
    server: ServerInfo
    coordinator: SecuritySpyDataUpdateCoordinator


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
    entry.runtime_data = SecuritySpyRuntimeData(
        client=client, server=server, coordinator=coordinator
    )

    # Registers devices from the server already fetched above -- no second
    # fetch (see coordinator.async_start's own docstring) -- and schedules the
    # periodic reconciliation timer that keeps them current without a reload.
    await coordinator.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
