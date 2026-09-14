"""Coordinator coverage: one test per row of the story's I/O matrix.

The coordinator is constructed directly against a `MockConfigEntry` and a
mocked client, bypassing `async_setup_entry`, so behaviour is exercised
without going through the timer -- exactly what the shared sync helper was
extracted to make possible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiosecurityspy import (
    PERM_LIVEVIDEO,
    PERM_SCHED,
    SecuritySpyAuthError,
    SecuritySpyConnectError,
    SecuritySpyPermissionError,
    SecuritySpyUnsupportedVersionError,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.const import (
    AUTH_FAILURE_THRESHOLD,
    DOMAIN,
    LIGHT_POLL_INTERVAL,
    RECONCILE_INTERVAL,
)
from custom_components.securityspy.coordinator import SecuritySpyDataUpdateCoordinator

from .conftest import (
    SERVER_UUID,
    make_camera,
    make_camera_status,
    make_server_info,
    make_server_info_with_cameras,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from homeassistant.core import HomeAssistant


def _add_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Register a bare config entry to own the coordinator under test."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERVER_UUID)
    entry.add_to_hass(hass)
    return entry


def _make_coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, server: object, client: MagicMock | None = None
) -> SecuritySpyDataUpdateCoordinator:
    return SecuritySpyDataUpdateCoordinator(
        hass,
        entry,
        client or MagicMock(),
        server,  # type: ignore[arg-type]
    )


async def _start_without_a_real_timer(coordinator: SecuritySpyDataUpdateCoordinator) -> None:
    """Run `async_start` without leaving a real timer scheduled past the test.

    Every test but the two specifically about scheduling only cares about the
    initial device-registry sync; a real `async_track_time_interval` timer
    would otherwise still be pending when the test's event loop tears down,
    since nothing in these tests ever unloads the bare `MockConfigEntry`.
    """
    with patch("custom_components.securityspy.coordinator.async_track_time_interval"):
        await coordinator.async_start()


def _reconcile_method(
    coordinator: SecuritySpyDataUpdateCoordinator,
) -> Callable[[], Coroutine[None, None, None]]:
    """Return the coordinator's reconciliation callback via `getattr`.

    A plain `coordinator._async_reconcile` attribute access is flagged by
    ruff's `SLF001` (private-member-access) even from a test, so the callback
    the timer actually invokes is fetched by name instead.
    """
    method: Callable[[], Coroutine[None, None, None]] = getattr(coordinator, "_async_reconcile")  # noqa: B009
    return method


async def _reconcile_now(coordinator: SecuritySpyDataUpdateCoordinator) -> None:
    """Invoke one reconciliation pass, as the periodic timer would."""
    await _reconcile_method(coordinator)()


def _camera_devices(
    device_registry: dr.DeviceRegistry, entry: MockConfigEntry
) -> list[dr.DeviceEntry]:
    hub = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    return [
        device
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if hub is None or device.id != hub.id
    ]


async def test_fresh_setup_registers_hub_and_camera_devices(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """N cameras yield exactly one hub device and N camera devices, no re-fetch."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras()
    client = MagicMock()
    client.async_get_server_info = AsyncMock()
    coordinator = _make_coordinator(hass, entry, server, client)

    await _start_without_a_real_timer(coordinator)

    hub = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    assert hub is not None
    assert hub.entry_type is DeviceEntryType.SERVICE
    cameras = _camera_devices(device_registry, entry)
    assert len(cameras) == len(server.cameras)
    for camera in server.cameras.values():
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, f"{SERVER_UUID}_{camera.number}")}
        )
        assert device is not None
        assert device.via_device_id == hub.id
        assert device.name == camera.name
    client.async_get_server_info.assert_not_awaited()


async def test_zero_cameras_registers_hub_only(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """A camera-less server still succeeds with just the hub device."""
    entry = _add_entry(hass)
    server = make_server_info()
    coordinator = _make_coordinator(hass, entry, server)

    await _start_without_a_real_timer(coordinator)

    hub = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    assert hub is not None
    assert _camera_devices(device_registry, entry) == []


async def test_reconcile_renames_a_camera_device(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """A renamed camera updates the device name; its id and identifiers persist."""
    entry = _add_entry(hass)
    initial = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, initial, client)
    await _start_without_a_real_timer(coordinator)
    before = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")})
    assert before is not None

    renamed = make_server_info_with_cameras(cameras=(make_camera(1, "Back Yard"),))
    client.async_get_server_info = AsyncMock(return_value=renamed)
    await _reconcile_now(coordinator)

    after = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")})
    assert after is not None
    assert after.id == before.id
    assert after.identifiers == before.identifiers
    assert after.name == "Back Yard"
    assert coordinator.data.server is renamed


async def test_reconcile_adds_a_new_camera_device(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """A camera newly present in the inventory gets a new device, via the hub."""
    entry = _add_entry(hass)
    initial = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, initial, client)
    await _start_without_a_real_timer(coordinator)
    hub = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    assert hub is not None

    grown = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"), make_camera(2, "Front Door"))
    )
    client.async_get_server_info = AsyncMock(return_value=grown)
    await _reconcile_now(coordinator)

    new_device = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_2")})
    assert new_device is not None
    assert new_device.via_device_id == hub.id
    assert len(_camera_devices(device_registry, entry)) == len(grown.cameras)


async def test_reconcile_removes_a_camera_device(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """A camera no longer in the inventory has its device removed; others survive."""
    entry = _add_entry(hass)
    initial = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"), make_camera(2, "Front Door"))
    )
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, initial, client)
    await _start_without_a_real_timer(coordinator)
    hub = device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)})
    assert hub is not None

    shrunk = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client.async_get_server_info = AsyncMock(return_value=shrunk)
    await _reconcile_now(coordinator)

    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_2")}) is None
    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")}) is not None
    assert device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)}) is not None
    assert hub.id == device_registry.async_get_device(identifiers={(DOMAIN, SERVER_UUID)}).id  # type: ignore[union-attr]


async def test_reconcile_self_heals_a_manually_deleted_camera_device(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Diffing the registry (not `self.data`) recreates a manually-removed device."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)
    device = device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")})
    assert device is not None
    device_registry.async_remove_device(device.id)
    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")}) is None

    # `self.data` never changed, so a diff against it would not notice anything
    # missing -- the registry-diff strategy is what recreates the device here.
    client.async_get_server_info = AsyncMock(return_value=server)
    await _reconcile_now(coordinator)

    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")}) is not None


async def test_reconcile_removes_a_device_with_no_recognisable_camera_identifier(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """A device under this entry with no matching camera identifier is treated as stale.

    Unreachable under the sole-writer invariant in real operation (only the
    coordinator ever registers a device for this config entry), but the diff
    must still resolve *some* way if it were ever violated; removing rather
    than crashing the whole reconciliation is that answer.
    """
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    coordinator = _make_coordinator(hass, entry, server)
    await _start_without_a_real_timer(coordinator)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "not-a-camera-identifier")}
    )
    # Also cover a domain-matching, prefix-matching identifier whose suffix is
    # not purely numeric -- a different way the "no recognisable camera
    # number" branch can be reached.
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{SERVER_UUID}_abc")}
    )

    client = MagicMock()
    client.async_get_server_info = AsyncMock(return_value=server)
    coordinator.client = client
    await _reconcile_now(coordinator)

    assert (
        device_registry.async_get_device(identifiers={(DOMAIN, "not-a-camera-identifier")}) is None
    )
    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_abc")}) is None
    assert device_registry.async_get_device(identifiers={(DOMAIN, f"{SERVER_UUID}_1")}) is not None


async def test_a_reload_against_the_same_identity_does_not_duplicate_devices(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Identity keys off `server.uuid`/camera number alone, not connection details.

    A second coordinator constructed for the same entry against the same
    `server` stands in for a reload -- including one following a host/IP/port
    change, which this test cannot represent directly since neither
    `ServerInfo` nor a device's identity carries a host or IP (AD-5): proving
    that two independent instantiations of the identical identity never
    duplicate devices is the strongest statement obtainable at this layer.
    """
    entry = _add_entry(hass)
    server = make_server_info_with_cameras()
    first = _make_coordinator(hass, entry, server)
    await _start_without_a_real_timer(first)

    second = _make_coordinator(hass, entry, server)
    await _start_without_a_real_timer(second)

    assert len(dr.async_entries_for_config_entry(device_registry, entry.entry_id)) == 1 + len(
        server.cameras
    )


@pytest.mark.parametrize(
    "side_effect",
    [
        SecuritySpyConnectError("192.168.1.20", 8000, "timeout"),
        SecuritySpyAuthError("192.168.1.20", 8000, 401),
        SecuritySpyUnsupportedVersionError("5.4", "6.0"),
    ],
)
async def test_reconcile_failure_leaves_the_registry_untouched(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    caplog: pytest.LogCaptureFixture,
    side_effect: Exception,
) -> None:
    """A transient or permanent poll failure changes nothing and does not raise."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)
    before = {
        device.id for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    }

    client.async_get_server_info = AsyncMock(side_effect=side_effect)
    with caplog.at_level("DEBUG"):
        await _reconcile_now(coordinator)

    after = {
        device.id for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    }
    assert after == before
    assert coordinator.data.server is server
    assert any(
        record.levelname == "DEBUG" and "reconcil" in record.getMessage().lower()
        for record in caplog.records
    )


async def test_reconcile_survives_an_unexpected_registry_sync_failure(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A bug in the registry sync itself is logged loudly, not left to crash the timer."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)

    client.async_get_server_info = AsyncMock(return_value=server)
    with (
        patch.object(coordinator, "_sync_device_registry", side_effect=RuntimeError("boom")),
        caplog.at_level("ERROR"),
    ):
        await _reconcile_now(coordinator)  # must not raise

    assert coordinator.data.server is server  # unchanged: the failed sync must not be published
    assert any(
        record.levelname == "ERROR" and "unexpected" in record.getMessage().lower()
        for record in caplog.records
    )


def _light_poll_method(
    coordinator: SecuritySpyDataUpdateCoordinator,
) -> Callable[[], Coroutine[None, None, None]]:
    """Return the coordinator's light-poll callback via `getattr` (see `_reconcile_method`)."""
    method: Callable[[], Coroutine[None, None, None]] = getattr(  # noqa: B009
        coordinator, "_async_poll_light_status"
    )
    return method


async def _poll_light_status_now(coordinator: SecuritySpyDataUpdateCoordinator) -> None:
    """Invoke one light-poll pass, as the periodic timer would."""
    await _light_poll_method(coordinator)()


async def test_unload_cancels_both_reconciliation_timers(hass: HomeAssistant) -> None:
    """Both timers' unsubs, registered via `entry.async_on_unload`, are called on unload."""
    entry = _add_entry(hass)
    server = make_server_info()
    unsubs = [MagicMock(), MagicMock()]
    with patch(
        "custom_components.securityspy.coordinator.async_track_time_interval",
        side_effect=unsubs,
    ):
        coordinator = _make_coordinator(hass, entry, server)
        await coordinator.async_start()

    entry.mock_state(hass, ConfigEntryState.LOADED)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    for unsub in unsubs:
        unsub.assert_called_once()


async def test_reconciliation_is_scheduled_with_the_right_callback_and_interval(
    hass: HomeAssistant,
) -> None:
    """The heavy timer is `_async_reconcile` on `RECONCILE_INTERVAL`."""
    entry = _add_entry(hass)
    server = make_server_info()
    coordinator = _make_coordinator(hass, entry, server)

    with patch(
        "custom_components.securityspy.coordinator.async_track_time_interval"
    ) as track_time_interval:
        await coordinator.async_start()

    args, _kwargs = track_time_interval.call_args_list[0]
    assert args[0] is hass
    assert args[1] == _reconcile_method(coordinator)
    assert args[2] == RECONCILE_INTERVAL


async def test_light_poll_is_scheduled_with_the_right_callback_and_interval(
    hass: HomeAssistant,
) -> None:
    """The light timer is `_async_poll_light_status` on `LIGHT_POLL_INTERVAL`."""
    entry = _add_entry(hass)
    server = make_server_info()
    coordinator = _make_coordinator(hass, entry, server)

    with patch(
        "custom_components.securityspy.coordinator.async_track_time_interval"
    ) as track_time_interval:
        await coordinator.async_start()

    args, _kwargs = track_time_interval.call_args_list[1]
    assert args[0] is hass
    assert args[1] == _light_poll_method(coordinator)
    assert args[2] == LIGHT_POLL_INTERVAL


async def test_light_poll_merges_fresh_camera_statuses(hass: HomeAssistant) -> None:
    """A successful light poll replaces `camera_statuses`, keeping `server` as-is."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)

    status = make_camera_status(1, error="e/network", error_description="Network error")
    client.async_get_camera_status = AsyncMock(return_value=(status,))
    await _poll_light_status_now(coordinator)

    assert coordinator.data.server is server
    assert coordinator.data.camera_statuses == {1: status}


async def test_light_poll_transient_failure_leaves_data_untouched(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A transient light-poll failure changes nothing and does not raise."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)
    before = coordinator.data

    client.async_get_camera_status = AsyncMock(
        side_effect=SecuritySpyConnectError("192.168.1.20", 8000, "timeout")
    )
    with caplog.at_level("DEBUG"):
        await _poll_light_status_now(coordinator)

    assert coordinator.data is before
    assert any(
        record.levelname == "DEBUG" and "light" in record.getMessage().lower()
        for record in caplog.records
    )


async def test_heavy_reconcile_preserves_camera_statuses_from_the_last_light_poll(
    hass: HomeAssistant,
) -> None:
    """A heavy refresh keeps the last-known `camera_statuses`, not reset to empty."""
    entry = _add_entry(hass)
    initial = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, initial, client)
    await _start_without_a_real_timer(coordinator)

    status = make_camera_status(1, error="e/network")
    client.async_get_camera_status = AsyncMock(return_value=(status,))
    await _poll_light_status_now(coordinator)
    assert coordinator.data.camera_statuses == {1: status}

    refreshed = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client.async_get_server_info = AsyncMock(return_value=refreshed)
    await _reconcile_now(coordinator)

    assert coordinator.data.server is refreshed
    assert coordinator.data.camera_statuses == {1: status}


async def test_light_poll_drops_a_status_for_a_camera_not_in_the_current_inventory(
    hass: HomeAssistant,
) -> None:
    """A light poll never introduces a status for a camera outside `server.cameras`.

    Otherwise a status the light endpoint still reports for a camera the last
    heavy reconcile already dropped would linger for up to `RECONCILE_INTERVAL`
    (the next heavy pass), rather than being filtered at the point it arrives.
    """
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)

    status_1 = make_camera_status(1)
    status_99 = make_camera_status(99)  # not in `server.cameras`
    client.async_get_camera_status = AsyncMock(return_value=(status_1, status_99))
    await _poll_light_status_now(coordinator)

    assert set(coordinator.data.camera_statuses) == {1}


async def test_light_poll_survives_an_unexpected_failure(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """An unmodelled exception from the light poll does not kill the timer callback."""
    entry = _add_entry(hass)
    server = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, server, client)
    await _start_without_a_real_timer(coordinator)
    before = coordinator.data

    client.async_get_camera_status = AsyncMock(side_effect=RuntimeError("boom"))
    with caplog.at_level("ERROR"):
        await _poll_light_status_now(coordinator)

    assert coordinator.data is before
    assert any(record.levelname == "ERROR" for record in caplog.records)


async def test_heavy_reconcile_drops_status_for_a_camera_removed_from_inventory(
    hass: HomeAssistant,
) -> None:
    """A camera gone from `server.cameras` by the time reconcile applies loses its status entry."""
    entry = _add_entry(hass)
    initial = make_server_info_with_cameras(
        cameras=(make_camera(1, "Driveway"), make_camera(2, "Front Door"))
    )
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, initial, client)
    await _start_without_a_real_timer(coordinator)

    status_1 = make_camera_status(1, error="e/network")
    status_2 = make_camera_status(2)
    client.async_get_camera_status = AsyncMock(return_value=(status_1, status_2))
    await _poll_light_status_now(coordinator)
    assert set(coordinator.data.camera_statuses) == {1, 2}

    shrunk = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client.async_get_server_info = AsyncMock(return_value=shrunk)
    await _reconcile_now(coordinator)

    assert set(coordinator.data.camera_statuses) == {1}


async def test_camera_permissions_are_decoded_at_start_and_on_heavy_refresh(
    hass: HomeAssistant,
) -> None:
    """Each inventoried camera's permission names are published, and refreshed."""
    entry = _add_entry(hass)
    initial = make_server_info_with_cameras(cameras=(make_camera(1, "Driveway"),))
    client = MagicMock()
    coordinator = _make_coordinator(hass, entry, initial, client)

    assert coordinator.data.camera_permissions == {1: frozenset({"live_video"})}

    refreshed = make_server_info_with_cameras(
        cameras=(
            make_camera(1, "Driveway", permissions=PERM_LIVEVIDEO | PERM_SCHED),
            make_camera(2, "Front Door"),
        )
    )
    client.async_get_server_info = AsyncMock(return_value=refreshed)
    await _start_without_a_real_timer(coordinator)
    await _reconcile_now(coordinator)

    assert coordinator.data.camera_permissions == {
        1: frozenset({"live_video", "schedule"}),
        2: frozenset({"live_video"}),
    }


def _auth_error() -> SecuritySpyAuthError:
    return SecuritySpyAuthError("192.168.1.20", 8000, 401)


async def _start_with_mock_timers(
    coordinator: SecuritySpyDataUpdateCoordinator,
) -> list[MagicMock]:
    """Run `async_start` with stand-in timers, returning their two unsubs."""
    unsubs = [MagicMock(), MagicMock()]
    with patch(
        "custom_components.securityspy.coordinator.async_track_time_interval",
        side_effect=unsubs,
    ):
        await coordinator.async_start()
    return unsubs


async def test_three_consecutive_auth_failures_start_reauth_and_stop_polling(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Heavy, light, heavy auth failures: timers cancelled, reauth started, one WARNING."""
    entry = _add_entry(hass)
    client = MagicMock()
    client.async_get_server_info = AsyncMock(side_effect=_auth_error())
    client.async_get_camera_status = AsyncMock(side_effect=_auth_error())
    coordinator = _make_coordinator(hass, entry, make_server_info(), client)
    unsubs = await _start_with_mock_timers(coordinator)

    with (
        patch.object(entry, "async_start_reauth") as start_reauth,
        caplog.at_level("WARNING"),
    ):
        await _reconcile_now(coordinator)
        await _poll_light_status_now(coordinator)
        start_reauth.assert_not_called()
        for unsub in unsubs:
            unsub.assert_not_called()
        await _reconcile_now(coordinator)

    start_reauth.assert_called_once_with(hass)
    for unsub in unsubs:
        unsub.assert_called_once()
    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "hunter2" not in warnings[0].getMessage()


async def test_threshold_really_opens_a_reauth_flow(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Unpatched, reaching the threshold leaves a reauth flow in progress for the entry."""
    entry = _add_entry(hass)
    coordinator = _make_coordinator(hass, entry, make_server_info(), mock_client)
    await _start_with_mock_timers(coordinator)

    for _ in range(3):
        coordinator.record_auth_failure()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == entry.entry_id


async def test_stream_hook_counts_with_the_polls(hass: HomeAssistant) -> None:
    """Two poll failures plus one stream-reported failure reach the threshold."""
    entry = _add_entry(hass)
    client = MagicMock()
    client.async_get_server_info = AsyncMock(side_effect=_auth_error())
    client.async_get_camera_status = AsyncMock(side_effect=_auth_error())
    coordinator = _make_coordinator(hass, entry, make_server_info(), client)
    await _start_with_mock_timers(coordinator)

    with patch.object(entry, "async_start_reauth") as start_reauth:
        await _reconcile_now(coordinator)
        await _poll_light_status_now(coordinator)
        coordinator.record_auth_failure()

    start_reauth.assert_called_once_with(hass)


@pytest.mark.parametrize("successful_poll", ["heavy", "light"])
async def test_a_successful_poll_resets_the_counter(
    hass: HomeAssistant, successful_poll: str
) -> None:
    """Two failures then a success: back to zero, and two more failures still do nothing."""
    entry = _add_entry(hass)
    server = make_server_info()
    client = MagicMock()
    client.async_get_server_info = AsyncMock(side_effect=_auth_error())
    client.async_get_camera_status = AsyncMock(side_effect=_auth_error())
    coordinator = _make_coordinator(hass, entry, server, client)
    unsubs = await _start_with_mock_timers(coordinator)

    with patch.object(entry, "async_start_reauth") as start_reauth:
        await _reconcile_now(coordinator)
        await _poll_light_status_now(coordinator)
        if successful_poll == "heavy":
            client.async_get_server_info = AsyncMock(return_value=server)
            await _reconcile_now(coordinator)
        else:
            client.async_get_camera_status = AsyncMock(return_value=())
            await _poll_light_status_now(coordinator)
        assert coordinator.auth_failures == 0

        coordinator.record_auth_failure()
        coordinator.record_auth_failure()

    start_reauth.assert_not_called()
    for unsub in unsubs:
        unsub.assert_not_called()


@pytest.mark.parametrize(
    "side_effect",
    [
        SecuritySpyPermissionError("unknown"),
        SecuritySpyConnectError("192.168.1.20", 8000, "timeout"),
    ],
)
async def test_non_auth_failures_neither_count_nor_reset(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, side_effect: Exception
) -> None:
    """Permission denials and connect errors leave the counter exactly where it was."""
    entry = _add_entry(hass)
    client = MagicMock()
    client.async_get_server_info = AsyncMock(side_effect=side_effect)
    client.async_get_camera_status = AsyncMock(side_effect=side_effect)
    coordinator = _make_coordinator(hass, entry, make_server_info(), client)
    await _start_with_mock_timers(coordinator)
    coordinator.record_auth_failure()

    with patch.object(entry, "async_start_reauth") as start_reauth, caplog.at_level("DEBUG"):
        for _ in range(3):
            await _reconcile_now(coordinator)
            await _poll_light_status_now(coordinator)

    assert coordinator.auth_failures == 1
    start_reauth.assert_not_called()
    own = [r for r in caplog.records if r.name == "custom_components.securityspy"]
    assert any(record.levelname == "DEBUG" for record in own)
    assert not any(record.levelname == "WARNING" for record in own)


async def test_failures_beyond_the_threshold_do_not_start_reauth_again(
    hass: HomeAssistant,
) -> None:
    """A fourth failure -- e.g. a poll already in flight -- starts no second reauth."""
    entry = _add_entry(hass)
    coordinator = _make_coordinator(hass, entry, make_server_info())
    unsubs = await _start_with_mock_timers(coordinator)

    with patch.object(entry, "async_start_reauth") as start_reauth:
        for _ in range(5):
            coordinator.record_auth_failure()

    start_reauth.assert_called_once_with(hass)
    for unsub in unsubs:
        unsub.assert_called_once()


async def test_a_late_success_after_the_threshold_does_not_rearm_reauth(
    hass: HomeAssistant,
) -> None:
    """A poll that succeeds after reauth started cannot reset the count for a second run."""
    entry = _add_entry(hass)
    coordinator = _make_coordinator(hass, entry, make_server_info())
    await _start_with_mock_timers(coordinator)

    with patch.object(entry, "async_start_reauth") as start_reauth:
        for _ in range(3):
            coordinator.record_auth_failure()
        coordinator.record_auth_success()
        for _ in range(3):
            coordinator.record_auth_failure()

    start_reauth.assert_called_once_with(hass)
    assert coordinator.auth_failures == AUTH_FAILURE_THRESHOLD


async def test_unload_after_the_threshold_does_not_cancel_the_timers_twice(
    hass: HomeAssistant,
) -> None:
    """Timers stopped early by the threshold are not cancelled again on unload."""
    entry = _add_entry(hass)
    coordinator = _make_coordinator(hass, entry, make_server_info())
    unsubs = await _start_with_mock_timers(coordinator)
    with patch.object(entry, "async_start_reauth"):
        for _ in range(3):
            coordinator.record_auth_failure()

    entry.mock_state(hass, ConfigEntryState.LOADED)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    for unsub in unsubs:
        unsub.assert_called_once()
