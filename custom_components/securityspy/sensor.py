"""Diagnostic sensors for server and per-camera health (story 2.4).

Every sensor here is `entity_category=EntityCategory.DIAGNOSTIC` -- none is a
primary control (the Boundaries & Constraints this story's spec settles).
Hub sensors (`cpu_usage`, `memory_pressure`, `camera_count`,
`cert_expiry_days`) read `coordinator.data.server`, refreshed on the existing,
slow `RECONCILE_INTERVAL` heavy poll. Per-camera `current_fps`/`data_rate`
read the same heavy `server.cameras` mapping (the light endpoint cannot
provide them); per-camera `last_error` reads `coordinator.data.camera_statuses`
instead, refreshed on the new, fast `LIGHT_POLL_INTERVAL` light poll -- the one
field both endpoints provide, so the epic's "prefer light where a value
exists there" rule picks the faster source.

Descriptions are built as tuples, per `docs/ha-integration-reference.md`'s
AD-9 pattern: one descriptor per field, with a `value_fn` doing the lookup, so
there are no copy-pasted per-field entity subclasses -- one hub sensor class
and one camera sensor class serve every descriptor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime

from .entity import SecuritySpyCameraEntity, SecuritySpyHubEntity

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from . import SecuritySpyConfigEntry
    from .coordinator import SecuritySpyData, SecuritySpyDataUpdateCoordinator

#: This platform's entities only ever read from `coordinator.data`, already
#: kept current by the coordinator's own timers; there is nothing for a
#: per-entity refresh to parallelize.
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class SecuritySpyHubSensorEntityDescription(SensorEntityDescription):
    """Describes one hub-level diagnostic sensor.

    Attributes:
        value_fn: Reads this sensor's native value from `SecuritySpyData`.

    """

    value_fn: Callable[[SecuritySpyData], StateType]


@dataclass(frozen=True, kw_only=True)
class SecuritySpyCameraSensorEntityDescription(SensorEntityDescription):
    """Describes one per-camera diagnostic sensor.

    Attributes:
        value_fn: Reads this sensor's native value from `SecuritySpyData` and
            the camera number it describes.
        extra_state_attributes_fn: Optional extra state attributes, read the
            same way. `None` (the default) means no extra attributes.

    """

    value_fn: Callable[[SecuritySpyData, int], StateType]
    extra_state_attributes_fn: Callable[[SecuritySpyData, int], Mapping[str, Any]] | None = None


def _camera_fps(data: SecuritySpyData, camera_number: int) -> float | None:
    camera = data.server.cameras.get(camera_number)
    return camera.current_fps if camera is not None else None


def _camera_data_rate(data: SecuritySpyData, camera_number: int) -> float | None:
    camera = data.server.cameras.get(camera_number)
    return camera.data_rate if camera is not None else None


def _camera_last_error(data: SecuritySpyData, camera_number: int) -> str | None:
    status = data.camera_statuses.get(camera_number)
    return status.error if status is not None else None


def _camera_last_error_attributes(data: SecuritySpyData, camera_number: int) -> Mapping[str, Any]:
    status = data.camera_statuses.get(camera_number)
    return {"last_error_description": status.error_description if status is not None else None}


HUB_SENSORS: tuple[SecuritySpyHubSensorEntityDescription, ...] = (
    SecuritySpyHubSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.server.cpu_usage,
    ),
    SecuritySpyHubSensorEntityDescription(
        key="memory_pressure",
        translation_key="memory_pressure",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.server.memory_pressure,
    ),
    SecuritySpyHubSensorEntityDescription(
        key="camera_count",
        translation_key="camera_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.server.camera_count,
    ),
    SecuritySpyHubSensorEntityDescription(
        key="cert_expiry_days",
        translation_key="cert_expiry_days",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.server.cert_expiry_days,
    ),
)

CAMERA_SENSORS: tuple[SecuritySpyCameraSensorEntityDescription, ...] = (
    SecuritySpyCameraSensorEntityDescription(
        key="current_fps",
        translation_key="current_fps",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="fps",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_camera_fps,
    ),
    SecuritySpyCameraSensorEntityDescription(
        key="data_rate",
        translation_key="data_rate",
        entity_category=EntityCategory.DIAGNOSTIC,
        # No `native_unit_of_measurement`: the library's own `data_rate`
        # docstring says the unit is not documented by SecuritySpy and is
        # carried through as-is -- inventing one here would be a guess.
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_camera_data_rate,
    ),
    SecuritySpyCameraSensorEntityDescription(
        key="last_error",
        translation_key="last_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_camera_last_error,
        extra_state_attributes_fn=_camera_last_error_attributes,
    ),
)


class SecuritySpyHubSensor(SecuritySpyHubEntity, SensorEntity):
    """One hub-level diagnostic sensor, described by `SecuritySpyHubSensorEntityDescription`."""

    entity_description: SecuritySpyHubSensorEntityDescription

    def __init__(
        self,
        coordinator: SecuritySpyDataUpdateCoordinator,
        description: SecuritySpyHubSensorEntityDescription,
    ) -> None:
        """Initialize the sensor from its description.

        Args:
            coordinator: The coordinator supplying `SecuritySpyData`.
            description: The field this sensor reads.

        """
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return this sensor's current value, or `None` if unavailable."""
        return self.entity_description.value_fn(self.coordinator.data)


class SecuritySpyCameraSensor(SecuritySpyCameraEntity, SensorEntity):
    """One per-camera diagnostic sensor, described by `SecuritySpyCameraSensorEntityDescription`."""

    entity_description: SecuritySpyCameraSensorEntityDescription

    def __init__(
        self,
        coordinator: SecuritySpyDataUpdateCoordinator,
        camera_number: int,
        description: SecuritySpyCameraSensorEntityDescription,
    ) -> None:
        """Initialize the sensor from its description.

        Args:
            coordinator: The coordinator supplying `SecuritySpyData`.
            camera_number: The camera this sensor describes.
            description: The field this sensor reads.

        """
        super().__init__(coordinator, camera_number, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        """Return this sensor's current value, or `None` if unavailable."""
        return self.entity_description.value_fn(self.coordinator.data, self.camera_number)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return this sensor's extra state attributes, if it defines any."""
        attrs_fn = self.entity_description.extra_state_attributes_fn
        if attrs_fn is None:
            return None
        return attrs_fn(self.coordinator.data, self.camera_number)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001 - required platform signature
    entry: SecuritySpyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up hub and per-camera diagnostic sensors from the coordinator.

    A camera absent from `coordinator.data.server.cameras` at this moment gets
    no sensor entities -- mirrors story 2.3's "no device, no entity" rule,
    not a new permission gate (that is story 2.7's job).

    Args:
        hass: The Home Assistant instance.
        entry: The config entry to set sensors up for.
        async_add_entities: Callback to register the new entities.

    """
    coordinator = entry.runtime_data.coordinator

    entities: list[SecuritySpyHubSensor | SecuritySpyCameraSensor] = [
        SecuritySpyHubSensor(coordinator, description) for description in HUB_SENSORS
    ]
    for camera_number in coordinator.data.server.cameras:
        entities.extend(
            SecuritySpyCameraSensor(coordinator, camera_number, description)
            for description in CAMERA_SENSORS
        )

    async_add_entities(entities)
