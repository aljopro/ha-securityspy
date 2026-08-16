"""The SecuritySpy integration.

Setup owns the one exception-mapping seam required by AD-6: library-typed
errors become Home Assistant config-entry failures here and nowhere else, so a
future coordinator or platform never re-decides what a connect error means.

No coordinator, platform or entity exists yet -- :data:`PLATFORMS` is
deliberately empty until story 2.3 introduces them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyClient,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

if TYPE_CHECKING:
    from aiosecurityspy import ServerInfo
    from homeassistant.core import HomeAssistant

#: Empty until story 2.3 adds the coordinator and the first platforms. Forwarding
#: an empty list is a no-op, so the setup/unload shape is already the final one.
PLATFORMS: list[Platform] = []


@dataclass
class SecuritySpyRuntimeData:
    """Everything the integration owns for one config entry.

    Stored on ``entry.runtime_data`` rather than ``hass.data[DOMAIN]``, which
    the Bronze ``runtime-data`` rule forbids (AD-12).
    """

    client: SecuritySpyClient
    server: ServerInfo


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
        client = SecuritySpyClient(
            # inject-websession (Platinum): the integration never builds a session.
            async_get_clientsession(hass),
            entry.data[CONF_HOST],
            entry.data[CONF_PORT],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
        )
    except (TypeError, ValueError) as err:
        # Stored data the client cannot use -- a hand-edited entry, or a restore
        # from a future schema. Retrying cannot help, so it is permanent.
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
    except SecuritySpyUnsupportedVersionError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="unsupported_version"
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

    entry.runtime_data = SecuritySpyRuntimeData(client=client, server=server)
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
    # The client owns no task, socket or timer of its own -- the session belongs
    # to Home Assistant -- so unloading the platforms is the whole job for now.
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
