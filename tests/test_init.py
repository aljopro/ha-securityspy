"""Setup and unload coverage, including the AD-6 exception-mapping seam."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.const import DOMAIN

from .conftest import MOCK_USER_INPUT, SERVER_NAME, SERVER_UUID

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Register a config entry shaped exactly as the config flow creates one."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        unique_id=SERVER_UUID,
        title=SERVER_NAME,
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_stores_typed_runtime_data(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """A reachable server yields a loaded entry with its client and server info."""
    entry = _add_entry(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.client is mock_client
    assert entry.runtime_data.server.uuid == SERVER_UUID


async def test_unload_entry(hass: HomeAssistant, mock_client: MagicMock) -> None:  # noqa: ARG001 - the client must stay patched for setup
    """A loaded entry unloads cleanly."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("side_effect", "expected_state", "expected_key"),
    [
        (
            SecuritySpyConnectError("192.168.1.20", 8000, "timeout"),
            ConfigEntryState.SETUP_RETRY,
            "cannot_connect",
        ),
        (
            SecuritySpyAuthError("192.168.1.20", 8000, 401),
            ConfigEntryState.SETUP_ERROR,
            "invalid_auth",
        ),
        (
            SecuritySpyUnsupportedVersionError("5.4", "6.0"),
            ConfigEntryState.SETUP_ERROR,
            "unsupported_version",
        ),
    ],
)
async def test_setup_maps_library_errors(
    hass: HomeAssistant,
    mock_client: MagicMock,
    side_effect: Exception,
    expected_state: ConfigEntryState,
    expected_key: str,
) -> None:
    """Each library error becomes the config-entry failure AD-6 assigns it.

    The state alone is not the contract: reaching `SETUP_ERROR` while showing the
    wrong message is still a mismapping, so the translation key is asserted too.
    """
    mock_client.async_get_server_info.side_effect = side_effect
    entry = _add_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is expected_state
    assert entry.error_reason_translation_key == expected_key


async def test_revoked_credentials_surface_a_translated_auth_failure(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """`ConfigEntryAuthFailed` marks the entry as needing attention, with a message.

    No reauth flow starts yet, and that is correct rather than broken: Home
    Assistant calls ``async_start_reauth_if_available``, which is a no-op while
    the flow has no ``async_step_reauth``. Story 2.8 adds that step and the
    AD-18 counter, and this mapping starts driving it with no change here.
    """
    mock_client.async_get_server_info.side_effect = SecuritySpyAuthError("192.168.1.20", 8000, 403)
    entry = _add_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_auth"
    assert not hass.config_entries.flow.async_progress()


async def test_setup_rejects_unusable_stored_data(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched so only the constructor fails
) -> None:
    """Stored connection details the client cannot use fail permanently."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_USER_INPUT, CONF_HOST: "http://nvr.example.com:8000/path"},
        unique_id=SERVER_UUID,
        title=SERVER_NAME,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.securityspy.SecuritySpyClient",
        side_effect=ValueError("host must be a bare hostname or IP address"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_stored_data"


async def test_setup_retries_on_an_unmodelled_library_error(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A typed library error outside AD-6's three classes is treated as transient."""
    mock_client.async_get_server_info.side_effect = SecuritySpyError("something unforeseen")
    entry = _add_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == "unknown"
