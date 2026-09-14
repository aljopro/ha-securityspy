"""Permission gate unit coverage (story 2.7).

The gate is built against a bare coordinator seeded with fixture cameras, so
its answers and the issues it syncs are exercised without platform setup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from aiosecurityspy import PERM_LIVEVIDEO, PERM_SCHED, PERMISSION_NAMES
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.securityspy.const import DOMAIN
from custom_components.securityspy.coordinator import SecuritySpyDataUpdateCoordinator
from custom_components.securityspy.permissions import PermissionGate, issue_id

from .conftest import SERVER_UUID, make_camera, make_server_info_with_cameras

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

ENTRY_ID = "entry_a"
LIVE_VIDEO_ISSUE = issue_id(ENTRY_ID, "live_video")


def _gate(hass: HomeAssistant, *masks: int) -> PermissionGate:
    """Build a gate over cameras numbered from 1, one per permission mask."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERVER_UUID, entry_id=ENTRY_ID)
    entry.add_to_hass(hass)
    server = make_server_info_with_cameras(
        cameras=tuple(
            make_camera(number, f"Camera {number}", permissions=mask)
            for number, mask in enumerate(masks, start=1)
        )
    )
    coordinator = SecuritySpyDataUpdateCoordinator(hass, entry, MagicMock(), server)
    return PermissionGate(coordinator, ENTRY_ID)


async def test_unknown_permission_name_is_refused(hass: HomeAssistant) -> None:
    """A misspelt name raises rather than silently denying every camera."""
    gate = _gate(hass, PERM_LIVEVIDEO)

    with pytest.raises(ValueError, match="live_vidoe"):
        gate.permitted(1, "live_vidoe")


async def test_absent_camera_is_denied_and_recorded(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """A camera missing from the inventory is denied and listed by number."""
    gate = _gate(hass, PERM_LIVEVIDEO)

    assert gate.permitted(99, "live_video") is False
    gate.async_update_issues(hass)

    issue = issue_registry.async_get_issue(DOMAIN, LIVE_VIDEO_ISSUE)
    assert issue is not None
    assert issue.translation_placeholders == {"permission": "live_video", "cameras": "camera 99"}


async def test_denials_are_deduplicated_and_sorted(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Asking twice lists a camera once, in camera-number order."""
    gate = _gate(hass, PERM_LIVEVIDEO, PERM_SCHED, PERM_SCHED)

    assert gate.permitted(1, "live_video") is True
    for number in (3, 2, 3):
        assert gate.permitted(number, "live_video") is False
    gate.async_update_issues(hass)

    issue = issue_registry.async_get_issue(DOMAIN, LIVE_VIDEO_ISSUE)
    assert issue is not None
    assert issue.translation_placeholders == {
        "permission": "live_video",
        "cameras": "Camera 2, Camera 3",
    }
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable is False
    assert issue.translation_key == "missing_permission"


async def test_issues_are_created_and_deleted(
    hass: HomeAssistant, issue_registry: ir.IssueRegistry
) -> None:
    """Only denied permissions keep an issue; every other one is cleared."""
    for permission in PERMISSION_NAMES.values():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id(ENTRY_ID, permission),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_permission",
        )
    gate = _gate(hass, PERM_LIVEVIDEO)

    assert gate.permitted(1, "schedule") is False
    gate.async_update_issues(hass)

    remaining = {issue_id for (domain, issue_id) in issue_registry.issues if domain == DOMAIN}
    assert remaining == {issue_id(ENTRY_ID, "schedule")}
