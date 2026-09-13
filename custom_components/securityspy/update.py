"""The single hub-level update entity for SecuritySpy (story 2.5).

One `UpdateEntity`, attached to the hub device via the existing
`SecuritySpyHubEntity` base class (story 2.4) -- no per-camera update entity,
no install action. `installed_version` and `latest_version` read
`coordinator.data.server`, already kept current by the existing heavy
`RECONCILE_INTERVAL` poll (the only endpoint that reports `new-version`); no
new poll cadence is added here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.update import UpdateDeviceClass, UpdateEntity

from .entity import SecuritySpyHubEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import SecuritySpyConfigEntry
    from .coordinator import SecuritySpyDataUpdateCoordinator

#: This entity only ever reads from `coordinator.data`, already kept current
#: by the coordinator's own timers; there is nothing for a per-entity refresh
#: to parallelize.
PARALLEL_UPDATES = 0


class SecuritySpyUpdateEntity(SecuritySpyHubEntity, UpdateEntity):
    """Reports whether a SecuritySpy update is available on the hub server.

    No `supported_features` override: the class default `UpdateEntityFeature(0)`
    already means no install action is offered, matching this entity's
    read-only, diagnostic-only nature. No `entity_category` override either --
    `UpdateEntity` itself falls back to `EntityCategory.DIAGNOSTIC` for any
    update entity without `UpdateEntityFeature.INSTALL`.
    """

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_translation_key = "update"

    def __init__(self, coordinator: SecuritySpyDataUpdateCoordinator) -> None:
        """Initialize the update entity.

        Args:
            coordinator: The coordinator supplying `SecuritySpyData`.

        """
        super().__init__(coordinator, "update")

    @property
    def installed_version(self) -> str:
        """Return the currently installed SecuritySpy version."""
        return self.coordinator.data.server.version

    @property
    def latest_version(self) -> str:
        """Return the latest known SecuritySpy version.

        Falls back to `installed_version` when no update is offered
        (`update_version is None`), so the base class's own `state`
        computation reads `STATE_OFF` ("up to date") rather than `unknown`.
        This is a HA-side normalization of the library's `None`-means-no-update
        convention, not a change to the library's own semantics.
        """
        server = self.coordinator.data.server
        return server.update_version or server.version


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: SecuritySpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the single hub update entity from the coordinator.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set the update entity up for.
        async_add_entities: Callback to register the new entity.

    """
    coordinator = entry.runtime_data.coordinator
    async_add_entities([SecuritySpyUpdateEntity(coordinator)])
