"""The one shared permission gate every platform consults (story 2.7).

A platform asks :meth:`PermissionGate.permitted` before creating an entity that
needs a per-camera SecuritySpy permission. The gate answers from the decoded
names on coordinator data and records each denial, so setup can raise one
repair issue per missing permission naming every affected camera -- something
no single platform, seeing only its own entities, could do.

No permission rule lives in a platform, and no mask is decoded here: the names
come from the library (AD-2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from aiosecurityspy import PERMISSION_NAMES
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import SecuritySpyDataUpdateCoordinator

#: Issue ids are this prefix, the config entry id, and the permission name.
MISSING_PERMISSION_ISSUE_PREFIX: Final = "missing_permission_"

#: Every name the library decodes, so a typo is refused rather than denying all.
_PERMISSION_NAMES: Final = frozenset(PERMISSION_NAMES.values())


def issue_id(entry_id: str, permission: str) -> str:
    """Return the repair issue id for one entry's missing permission.

    Ids are scoped per config entry so two SecuritySpy servers never clear or
    overwrite each other's issues.

    Args:
        entry_id: The config entry the issue belongs to.
        permission: A name from :data:`aiosecurityspy.PERMISSION_NAMES`.

    Returns:
        The issue id.

    """
    return f"{MISSING_PERMISSION_ISSUE_PREFIX}{entry_id}_{permission}"


class PermissionGate:
    """Answers permission questions and remembers what it denied."""

    def __init__(self, coordinator: SecuritySpyDataUpdateCoordinator, entry_id: str) -> None:
        """Initialize the gate.

        Args:
            coordinator: The coordinator whose data carries the decoded
                per-camera permissions and the camera names.
            entry_id: The config entry whose issues this gate owns.

        """
        self._coordinator = coordinator
        self._entry_id = entry_id
        self._denials: dict[str, set[int]] = {}

    @staticmethod
    def permission_names() -> frozenset[str]:
        """Return every permission name the library decodes."""
        return _PERMISSION_NAMES

    def permitted(self, camera_number: int, permission: str) -> bool:
        """Return whether the account holds ``permission`` on a camera.

        A denial is recorded for :meth:`async_update_issues`; asking twice
        records it once.

        Args:
            camera_number: The camera the entity would belong to.
            permission: A name from :data:`aiosecurityspy.PERMISSION_NAMES`.

        Raises:
            ValueError: ``permission`` is not a name the library decodes. A
                misspelling would otherwise silently deny every camera.

        Returns:
            ``True`` when the camera is inventoried and grants the permission;
            ``False`` otherwise, including for a camera that is absent.

        """
        if permission not in _PERMISSION_NAMES:
            message = f"unknown permission name {permission!r}"
            raise ValueError(message)
        granted = self._coordinator.data.camera_permissions.get(camera_number, frozenset())
        if permission in granted:
            return True
        self._denials.setdefault(permission, set()).add(camera_number)
        return False

    def async_update_issues(self, hass: HomeAssistant) -> None:
        """Raise one issue per denied permission and clear this entry's others.

        Args:
            hass: The Home Assistant instance.

        """
        cameras = self._coordinator.data.server.cameras
        for permission in _PERMISSION_NAMES:
            permission_issue_id = issue_id(self._entry_id, permission)
            denied = self._denials.get(permission)
            if not denied:
                ir.async_delete_issue(hass, DOMAIN, permission_issue_id)
                continue
            # An absent camera has no name this integration may learn elsewhere
            # (DW-5), so it is named by number rather than dropped.
            names = [
                cameras[number].name if number in cameras else f"camera {number}"
                for number in sorted(denied)
            ]
            ir.async_create_issue(
                hass,
                DOMAIN,
                permission_issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="missing_permission",
                translation_placeholders={
                    "permission": permission,
                    "cameras": ", ".join(names),
                },
            )
