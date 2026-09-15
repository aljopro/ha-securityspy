"""Setup and unload coverage, including the AD-6 exception-mapping seam."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from aiosecurityspy import (
    PERM_LIVEVIDEO,
    PERM_SCHED,
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

from custom_components.securityspy import async_remove_config_entry_device
from custom_components.securityspy.const import (
    CONF_CREATE_CAMERA_ENTITIES,
    DOMAIN,
    LIGHT_POLL_INTERVAL,
    RECONCILE_INTERVAL,
)
from custom_components.securityspy.coordinator import SecuritySpyDataUpdateCoordinator
from custom_components.securityspy.permissions import issue_id

from .conftest import (
    MOCK_USER_INPUT,
    SERVER_NAME,
    SERVER_UUID,
    https_input,
    make_camera,
    make_camera_status,
    make_server_info,
    make_server_info_with_cameras,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import issue_registry as ir


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
    """`ConfigEntryAuthFailed` marks the entry as needing attention and starts reauth.

    Story 2.8 added ``async_step_reauth``, so this unchanged setup-time mapping
    now opens the reauth flow at once. The AD-18 counter covers failures
    after setup only.
    """
    mock_client.async_get_server_info.side_effect = SecuritySpyAuthError("192.168.1.20", 8000, 403)
    entry = _add_entry(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert entry.error_reason_translation_key == "invalid_auth"
    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == entry.entry_id


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

    `coordinator.data.server is entry.runtime_data.server` proves the
    constructor seeded from the one server `__init__.py` already fetched, with
    no divergent second fetch: had `async_start` re-fetched, `coordinator.data`
    could in principle wrap a *different* `ServerInfo` object than the one
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
    assert entry.runtime_data.coordinator.data.server is entry.runtime_data.server
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


async def test_setup_starts_the_relay_and_unload_stops_it(
    hass: HomeAssistant, mock_client: MagicMock, mock_relay: MagicMock
) -> None:
    """The relay is built from the fetched server, started once, and stopped on unload."""
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_client.create_rtsp_relay.assert_called_once_with(entry.runtime_data.server)
    mock_relay.async_start.assert_awaited_once()
    assert entry.runtime_data.relay is mock_relay
    mock_relay.async_stop.assert_not_awaited()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    mock_relay.async_stop.assert_awaited_once()


async def test_setup_skips_the_relay_while_camera_entities_are_off(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """With the option off, no relay exists to hand out a stream address."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        options={CONF_CREATE_CAMERA_ENTITIES: False},
        unique_id=SERVER_UUID,
        title=SERVER_NAME,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    mock_client.create_rtsp_relay.assert_not_called()
    assert entry.runtime_data.relay is None


async def test_setup_skips_the_relay_without_an_rtsp_port(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """A server publishing no RTSP port gets no relay, and setup still succeeds."""
    mock_client.async_get_server_info.return_value = make_server_info(rtsp_port=None)
    entry = _add_entry(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    mock_client.create_rtsp_relay.assert_not_called()
    assert entry.runtime_data.relay is None


async def test_setup_tolerates_a_relay_that_cannot_bind(
    hass: HomeAssistant,
    mock_client: MagicMock,  # noqa: ARG001 - keeps the client patched for setup
    mock_relay: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A bind failure is one detail-free warning, no relay, and a loaded entry."""
    mock_relay.async_start.side_effect = OSError("[Errno 48] Address already in use")
    entry = _add_entry(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.relay is None
    warnings = [record for record in caplog.records if "relay" in record.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelname == "WARNING"
    assert "Errno" not in warnings[0].getMessage()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    mock_relay.async_stop.assert_not_awaited()


async def test_missing_permission_issues_survive_unload_and_go_with_the_entry(
    hass: HomeAssistant, mock_client: MagicMock, issue_registry: ir.IssueRegistry
) -> None:
    """Unload keeps the issue for a reload to re-evaluate; removing the entry deletes it."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway", permissions=PERM_SCHED),)
    )
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    live_video_issue = issue_id(entry.entry_id, "live_video")
    assert issue_registry.async_get_issue(DOMAIN, live_video_issue) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, live_video_issue) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not [key for key in issue_registry.issues if key[0] == DOMAIN]


async def test_missing_permission_issues_are_scoped_per_entry(
    hass: HomeAssistant, mock_client: MagicMock, issue_registry: ir.IssueRegistry
) -> None:
    """One server's setup or removal never clears another server's issues."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway", permissions=PERM_SCHED),)
    )
    entry_a = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry_a.entry_id)
    await hass.async_block_till_done()
    issue_a = issue_id(entry_a.entry_id, "live_video")
    assert issue_registry.async_get_issue(DOMAIN, issue_a) is not None

    other_uuid = "11111111-2222-3333-4444-555555555555"
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(
        uuid=other_uuid,
        name="Second Server",
        cameras=(make_camera(1, "Garden", permissions=PERM_LIVEVIDEO),),
    )
    entry_b = MockConfigEntry(
        domain=DOMAIN,
        data={**MOCK_USER_INPUT, CONF_HOST: "192.168.1.21"},
        unique_id=other_uuid,
        title="Second Server",
    )
    entry_b.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry_b.entry_id)
    await hass.async_block_till_done()
    assert entry_b.state is ConfigEntryState.LOADED
    assert issue_registry.async_get_issue(DOMAIN, issue_a) is not None

    await hass.config_entries.async_remove(entry_b.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_a) is not None

    await hass.config_entries.async_remove(entry_a.entry_id)
    await hass.async_block_till_done()
    assert issue_registry.async_get_issue(DOMAIN, issue_a) is None


async def test_remove_config_entry_device_only_allows_cameras_absent_from_the_inventory(
    hass: HomeAssistant, mock_client: MagicMock, device_registry: dr.DeviceRegistry
) -> None:
    """True for a camera that left the inventory; False for the hub and a present camera."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras()
    # Camera 1 offline: present-but-offline must still be refused.
    mock_client.async_get_camera_status.return_value = (make_camera_status(1, online=False),)
    entry = _add_entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hub = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    camera_1 = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")})
    camera_2 = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_2")})
    assert hub is not None
    assert camera_1 is not None
    assert camera_2 is not None
    assert not await async_remove_config_entry_device(hass, entry, camera_2)

    mock_client.async_get_server_info.return_value = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"),)
    )
    async_fire_time_changed(hass, dt_util.utcnow() + RECONCILE_INTERVAL)
    await hass.async_block_till_done()

    assert await async_remove_config_entry_device(hass, entry, camera_2)
    assert not await async_remove_config_entry_device(hass, entry, camera_1)
    assert not await async_remove_config_entry_device(hass, entry, hub)

    # During an outage the held inventory is stale, so nothing is removable.
    mock_client.async_get_camera_status.side_effect = SecuritySpyConnectError(
        "192.168.1.20", 8000, "timeout"
    )
    async_fire_time_changed(hass, dt_util.utcnow() + LIGHT_POLL_INTERVAL)
    await hass.async_block_till_done()
    assert not await async_remove_config_entry_device(hass, entry, camera_2)


async def test_remove_config_entry_device_refuses_while_the_entry_is_not_loaded(
    hass: HomeAssistant, mock_client: MagicMock, device_registry: dr.DeviceRegistry
) -> None:
    """With no loaded coordinator there is no inventory to prove a device stale."""
    mock_client.async_get_server_info.return_value = make_server_info_with_cameras()
    entry = _add_entry(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{SERVER_UUID}_9")}
    )

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not await async_remove_config_entry_device(hass, entry, device)
