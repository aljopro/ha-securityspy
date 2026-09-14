"""Config-flow coverage: one test per row of the story's I/O matrix.

`config-flow-test-coverage` (Bronze) demands 100% of `config_flow.py`,
including every abort and every error path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from aiosecurityspy import DEFAULT_PORT as LIBRARY_DEFAULT_PORT
from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyCertificateError,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyPermissionError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.config_flow import STEP_USER_DATA_SCHEMA
from custom_components.securityspy.const import CONF_CREATE_CAMERA_ENTITIES, DOMAIN

from .conftest import (
    MOCK_HTTPS_USER_INPUT,
    MOCK_USER_INPUT,
    SERVER_NAME,
    SERVER_UUID,
    https_input,
    make_server_info,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

#: The flow validates once, then the freshly created entry validates again at
#: setup: `test-before-configure` and `test-before-setup` are separate rules.
EXPECTED_VALIDATION_CALLS = 2


@pytest.fixture
def mock_session_factory() -> Iterator[MagicMock]:
    """Patch the flow's `async_get_clientsession` so the ask can be observed.

    The verification setting selects *which* Home Assistant session is used --
    each has a connector whose SSL context was built off the event loop -- so
    the argument the flow passes here is part of the contract, not plumbing.
    """
    with patch(
        "custom_components.securityspy.config_flow.async_get_clientsession"
    ) as get_clientsession:
        yield get_clientsession


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


async def test_http_defaults_reach_the_client_unchanged(
    hass: HomeAssistant, mock_client_class: MagicMock, mock_session_factory: MagicMock
) -> None:
    """Left at their defaults, the toggles reproduce story 2.1's behaviour exactly."""
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_USER_INPUT)
    )
    await hass.async_block_till_done()

    # Without this the flow could fail and redisplay the form -- the client is
    # still constructed on that path, so the kwargs below would pass regardless.
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_client_class.call_args_list[0].kwargs["use_https"] is False
    assert mock_client_class.call_args_list[0].kwargs["verify_ssl"] is True
    assert mock_session_factory.call_args.kwargs == {"verify_ssl": True}


@pytest.mark.parametrize("verify_ssl", [True, False])
async def test_https_choices_reach_the_entry_the_client_and_the_session(
    hass: HomeAssistant,
    mock_client_class: MagicMock,
    mock_session_factory: MagicMock,
    verify_ssl: bool,  # noqa: FBT001 - parametrized flag
) -> None:
    """Both toggles persist with the entry and reach the client and its session."""
    result = await _start_user_flow(hass)
    submitted = https_input(verify_ssl=verify_ssl)

    result = dict(await hass.config_entries.flow.async_configure(result["flow_id"], submitted))
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == submitted
    assert result["data"][CONF_SSL] is True
    assert result["data"][CONF_VERIFY_SSL] is verify_ssl

    kwargs = mock_client_class.call_args_list[0].kwargs
    assert kwargs["use_https"] is True
    assert kwargs["verify_ssl"] is verify_ssl
    # The session and the per-request flag have to agree: aiohttp resolves
    # `ssl=True` by deferring to the connector this session was built with.
    assert mock_session_factory.call_args.kwargs == {"verify_ssl": verify_ssl}


async def test_certificate_mismatch_names_the_certificate(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A rejected certificate gets its own message, not the generic network one.

    The library error is a `SecuritySpyConnectError` subclass, so a mapping that
    tested the parent first would answer `cannot_connect` and send the user
    hunting for a network fault that does not exist.
    """
    mock_client.async_get_server_info.side_effect = SecuritySpyCertificateError(
        "192.168.1.20", 8001, "SSLCertVerificationError"
    )
    result = await _start_user_flow(hass)

    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_HTTPS_USER_INPUT)
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_certificate"}
    suggestions = {
        marker.schema: marker.description["suggested_value"]
        for marker in result["data_schema"].schema
        if marker.description is not None
    }
    # The toggles come back as submitted: the fix is to turn one of them off, and
    # a form that forgot them makes the user re-derive their own answer.
    assert suggestions[CONF_SSL] is True
    assert suggestions[CONF_VERIFY_SSL] is True
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_retrying_with_verification_off_succeeds(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_client_class: MagicMock,
    mock_session_factory: MagicMock,
) -> None:
    """The documented remedy works: turn verification off and the entry is created."""
    mock_client.async_get_server_info.side_effect = SecuritySpyCertificateError(
        "192.168.1.20", 8001, "SSLCertVerificationError"
    )
    result = await _start_user_flow(hass)
    result = dict(
        await hass.config_entries.flow.async_configure(result["flow_id"], MOCK_HTTPS_USER_INPUT)
    )
    assert result["errors"] == {"base": "invalid_certificate"}

    mock_client.async_get_server_info.side_effect = None
    result = dict(
        await hass.config_entries.flow.async_configure(
            result["flow_id"], https_input(verify_ssl=False)
        )
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VERIFY_SSL] is False
    assert mock_client_class.call_args_list[1].kwargs["verify_ssl"] is False
    assert mock_session_factory.call_args.kwargs == {"verify_ssl": False}


@pytest.mark.parametrize(
    ("field", "expected_default"),
    [(CONF_SSL, False), (CONF_VERIFY_SSL, True)],
)
def test_toggle_defaults(field: str, expected_default: bool) -> None:  # noqa: FBT001 - parametrized expectation
    """HTTPS is off by default and verification is on; nobody arrives at unverified."""
    marker = next(item for item in STEP_USER_DATA_SCHEMA.schema if item.schema == field)
    assert marker.default() is expected_default


def test_form_defaults_to_the_library_port() -> None:
    """The port field is pre-filled from the library's default, not a literal."""
    port = next(marker for marker in STEP_USER_DATA_SCHEMA.schema if marker.schema == CONF_PORT)
    assert port.default() == LIBRARY_DEFAULT_PORT


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (SecuritySpyConnectError("192.168.1.20", 8000, "timeout"), "cannot_connect"),
        (SecuritySpyAuthError("192.168.1.20", 8000, 401), "invalid_auth"),
        (SecuritySpyPermissionError("unknown"), "permission_denied"),
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
        for marker in result["data_schema"].schema
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


async def test_options_flow_shows_the_default(hass: HomeAssistant) -> None:
    """An entry with no stored options offers camera entities switched on."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, unique_id=SERVER_UUID)
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    schema = result["data_schema"]
    assert schema is not None
    assert schema({}) == {CONF_CREATE_CAMERA_ENTITIES: True}


@pytest.mark.parametrize("value", [False, True])
async def test_options_flow_saves_and_reloads(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched for the reload
    value: bool,  # noqa: FBT001 - parametrized flag
) -> None:
    """A submitted option is stored and the entry reloads to apply it."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        options={CONF_CREATE_CAMERA_ENTITIES: not value},
        unique_id=SERVER_UUID,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(
        hass.config_entries,
        "async_schedule_reload",
        wraps=hass.config_entries.async_schedule_reload,
    ) as schedule_reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_CREATE_CAMERA_ENTITIES: value}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_CREATE_CAMERA_ENTITIES: value}
    schedule_reload.assert_called_once_with(entry.entry_id)
