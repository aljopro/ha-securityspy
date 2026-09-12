"""Setup and unload coverage, including the AD-6 exception-mapping seam."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from aiosecurityspy import (
    SecuritySpyAuthError,
    SecuritySpyCertificateError,
    SecuritySpyConnectError,
    SecuritySpyError,
    SecuritySpyPermissionError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SSL, CONF_VERIFY_SSL
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.securityspy.const import DOMAIN, RECONCILE_INTERVAL
from custom_components.securityspy.coordinator import SecuritySpyDataUpdateCoordinator

from .conftest import MOCK_USER_INPUT, SERVER_NAME, SERVER_UUID, https_input

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _add_entry(hass: HomeAssistant, data: dict[str, Any] | None = None) -> MockConfigEntry:
    """Register a config entry shaped exactly as the config flow creates one.

    Args:
        hass: The Home Assistant instance.
        data: Entry data, defaulting to the plain-HTTP payload.

    Returns:
        The registered entry.

    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT if data is None else data,
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
            SecuritySpyPermissionError("unknown"),
            ConfigEntryState.SETUP_ERROR,
            "permission_denied",
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


@pytest.mark.parametrize(
    ("data", "use_https", "verify_ssl"),
    [
        (MOCK_USER_INPUT, False, True),
        (https_input(), True, True),
        (https_input(verify_ssl=False), True, False),
    ],
    ids=["http", "https-verified", "https-unverified"],
)
async def test_setup_applies_the_stored_tls_choices(
    hass: HomeAssistant,
    mock_client_class: MagicMock,
    data: dict[str, Any],
    use_https: bool,  # noqa: FBT001 - parametrized flag
    verify_ssl: bool,  # noqa: FBT001 - parametrized flag
) -> None:
    """Setup hands both stored flags to the client and to the session it uses.

    The client is what Epic 3 spawns the event stream from, so a flag that
    reached the entry but not the client would give the stream a different
    transport than the one the user chose. The plain-HTTP row is here so a
    hard-coded `use_https=True` cannot pass: it is the default a regression
    would land on.
    """
    entry = _add_entry(hass, data)

    with patch(
        "custom_components.securityspy.async_get_clientsession"
    ) as get_clientsession:  # the argument selects the session, so it is contract
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    kwargs = mock_client_class.call_args.kwargs
    assert kwargs["use_https"] is use_https
    assert kwargs["verify_ssl"] is verify_ssl
    assert get_clientsession.call_args.kwargs == {"verify_ssl": verify_ssl}


async def test_setup_warns_while_verification_is_disabled(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched so setup succeeds
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Disabling verification leaves a record every time the entry loads.

    The form describes the cost at decision time; nothing else would ever
    mention it again, and the HTTP Basic credential rides on every request the
    unverified connection makes.
    """
    entry = _add_entry(hass, https_input(verify_ssl=False))

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert any("verification is disabled" in record.getMessage() for record in warnings)
    assert not any(MOCK_USER_INPUT[CONF_PASSWORD] in record.getMessage() for record in warnings)


async def test_setup_does_not_warn_about_verification_on_a_plain_http_entry(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched so setup succeeds
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verification off without HTTPS is not a risk, and must not be reported as one.

    Nothing in the form couples the two toggles, so this entry is submittable.
    There is no certificate on a plain-HTTP connection, so the warning would
    describe something the entry never does -- and a warning that cries wolf on
    a safe configuration is what teaches the reader to skip it on the unsafe one.
    """
    entry = _add_entry(hass, {**MOCK_USER_INPUT, CONF_VERIFY_SSL: False})

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert not any(
        "verification is disabled" in record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING"
    )


async def test_setup_rejects_stored_data_missing_a_field(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched so only the read fails
) -> None:
    """An entry written before a field existed fails with a translated message.

    A missing key is a `KeyError`, not the `ValueError` the client raises for a
    value it dislikes, so without the guard it would escape `async_setup_entry`
    as a raw traceback -- the one outcome the stored-data path promises not to
    produce.
    """
    entry = _add_entry(
        hass, {key: value for key, value in MOCK_USER_INPUT.items() if key != CONF_SSL}
    )

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_stored_data"


async def test_setup_names_a_certificate_failure(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A certificate rejected at setup retries, with the certificate-specific message.

    Order is the whole risk here: the library error subclasses
    `SecuritySpyConnectError`, so a clause placed after its parent would make
    this message unreachable and nothing would fail loudly.
    """
    mock_client.async_get_server_info.side_effect = SecuritySpyCertificateError(
        "192.168.1.20", 8001, "SSLCertVerificationError"
    )
    entry = _add_entry(hass, https_input())

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # `NotReady`, not a permanent error: an expired certificate renews itself and
    # the entry recovers without anyone touching Home Assistant.
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert entry.error_reason_translation_key == "invalid_certificate"


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


async def test_setup_constructs_and_starts_the_coordinator(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Setup builds the coordinator, starts it, and stores it on runtime_data.

    `coordinator.data is entry.runtime_data.server` proves the constructor
    seeded from the one server `__init__.py` already fetched, with no
    divergent second fetch: had `async_start` re-fetched, `coordinator.data`
    could in principle be a *different* `ServerInfo` object than the one
    stored as `.server`, even if the two compared equal.
    """
    entry = _add_entry(hass)

    with patch(
        "custom_components.securityspy.SecuritySpyDataUpdateCoordinator.async_start",
        autospec=True,
    ) as async_start:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert isinstance(entry.runtime_data.coordinator, SecuritySpyDataUpdateCoordinator)
    async_start.assert_awaited_once()
    assert entry.runtime_data.coordinator.data is entry.runtime_data.server
    # Only the one `test-before-setup` call: the coordinator's own startup
    # path must not add a second.
    assert mock_client.async_get_server_info.await_count == 1


async def test_unload_cancels_the_coordinators_reconciliation_timer(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched for setup
) -> None:
    """Unloading the entry cancels the coordinator's periodic timer.

    Asserted through the real `async_track_time_interval` unsub rather than a
    mock: `_async_process_on_unload` runs the callback registered in
    `async_start` regardless of `PLATFORMS` being empty, and cancelling that
    unsub is what stops the timer from firing after unload.
    """
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator

    with patch.object(
        coordinator,
        "_async_reconcile",
        wraps=getattr(coordinator, "_async_reconcile"),  # noqa: B009
    ) as reconcile:
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        async_fire_time_changed(hass, dt_util.utcnow() + RECONCILE_INTERVAL * 2)
        await hass.async_block_till_done()

    reconcile.assert_not_called()
