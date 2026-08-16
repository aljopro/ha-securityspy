"""Config-flow coverage: one test per row of the story's I/O matrix.

`config-flow-test-coverage` (Bronze) demands 100% of `config_flow.py`,
including every abort and every error path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from aiosecurityspy import DEFAULT_PORT as LIBRARY_DEFAULT_PORT
from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.config_flow import STEP_USER_DATA_SCHEMA
from custom_components.securityspy.const import DOMAIN

from .conftest import MOCK_USER_INPUT, SERVER_NAME, SERVER_UUID, make_server_info

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

#: The flow validates once, then the freshly created entry validates again at
#: setup: `test-before-configure` and `test-before-setup` are separate rules.
EXPECTED_VALIDATION_CALLS = 2


async def _start_user_flow(hass: HomeAssistant) -> dict[str, Any]:
    """Open the user step and assert the form is shown with no error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    return dict(result)


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """The happy path: the entry is keyed on the UUID and titled with the name."""
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == SERVER_NAME
    assert result["data"] == MOCK_USER_INPUT
    assert result["result"].unique_id == SERVER_UUID
    assert mock_client.async_get_server_info.await_count == EXPECTED_VALIDATION_CALLS


def test_form_defaults_to_the_library_port() -> None:
    """The port field is pre-filled from the library's default, not a literal."""
    port = next(marker for marker in STEP_USER_DATA_SCHEMA.schema if marker.schema == CONF_PORT)
    assert port.default() == LIBRARY_DEFAULT_PORT


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (SecuritySpyConnectError("192.168.1.20", 8000, "timeout"), "cannot_connect"),
        (SecuritySpyAuthError("192.168.1.20", 8000, 401), "invalid_auth"),
        (SecuritySpyUnsupportedVersionError("5.4", "6.0"), "unsupported_version"),
        (SecuritySpyError("something unforeseen"), "unknown"),
    ],
)
async def test_request_failures_redisplay_the_form(
    hass: HomeAssistant,
    mock_client: MagicMock,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """A failed validation call maps to its own error and keeps the flow alive."""
    mock_client.async_get_server_info.side_effect = side_effect
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}
    suggestions = {
        marker.schema: marker.description["suggested_value"]
        for marker in result["data_schema"].schema  # type: ignore[union-attr]
        if marker.description is not None
    }
    # Everything typed comes back except the password: a suggested value travels
    # to the browser in the flow result, and a credential need not (AD-13).
    assert suggestions == {
        key: value for key, value in MOCK_USER_INPUT.items() if key != CONF_PASSWORD
    }
    assert CONF_PASSWORD not in suggestions


@pytest.mark.parametrize(
    "side_effect",
    [
        ValueError("host must be a bare hostname or IP address"),
        TypeError("port must be an integer"),
    ],
)
async def test_unusable_connection_details_are_rejected_before_any_call(
    hass: HomeAssistant,
    mock_client_class: MagicMock,
    mock_client: MagicMock,
    side_effect: Exception,
) -> None:
    """The client constructor rejects a bad host or port before the network."""
    mock_client_class.side_effect = side_effect
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_host"}
    assert mock_client.async_get_server_info.await_count == 0


async def test_unexpected_error_keeps_the_flow_alive(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A failure the library never wrapped still redisplays the form.

    The flow must not abort on a live call: an unwrapped transport error or a
    decoding bug becomes the generic message, not a traceback.
    """
    mock_client.async_get_server_info.side_effect = TimeoutError("no response")
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_missing_server_uuid_fails_closed(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A server with no UUID has no permanent identity, so no entry is created."""
    mock_client.async_get_server_info.return_value = make_server_info(uuid="")
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_server_uuid"}
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_recovers_after_an_error(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """A corrected resubmission after a failure still creates the entry."""
    mock_client.async_get_server_info.side_effect = SecuritySpyConnectError(
        "192.168.1.20", 8000, "timeout"
    )
    result = await _start_user_flow(hass)
    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.async_get_server_info.side_effect = None
    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERVER_UUID


async def test_same_server_at_another_address_aborts(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Identity is the UUID, so a second address for one server is a duplicate."""
    existing = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, unique_id=SERVER_UUID)
    existing.add_to_hass(hass)
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                **MOCK_USER_INPUT,
                CONF_HOST: "nvr.example.com",
                CONF_USERNAME: "someone-else",
                CONF_PASSWORD: "another-password",
            },
        )
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert mock_client.async_get_server_info.await_count == 1
