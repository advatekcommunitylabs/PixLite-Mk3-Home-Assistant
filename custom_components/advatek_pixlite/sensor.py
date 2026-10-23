"""Controller health, playback, and per-output measurements."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
import math
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)

from .entity import PixLiteEntity, value_at
from .file_names import display_name

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import PixLiteCoordinator

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PixLiteSensorEntityDescription(SensorEntityDescription):
    """Describe a value in a controller polling snapshot."""

    path: str
    divisor: int = 1
    channel: int | None = None


SENSORS: tuple[PixLiteSensorEntityDescription, ...] = (
    PixLiteSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        path="statistic.dev.temp.current",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PixLiteSensorEntityDescription(
        key="cpu",
        translation_key="cpu",
        path="statistic.dev.cpu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PixLiteSensorEntityDescription(
        key="output_rate",
        translation_key="output_rate",
        path="statistic.pixData.outFrmRate",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PixLiteSensorEntityDescription(
        key="input_rate",
        translation_key="input_rate",
        path="statistic.pixData.inFrmRate",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    PixLiteSensorEntityDescription(
        key="mode", translation_key="mode", path="status.mode"
    ),
    PixLiteSensorEntityDescription(
        key="file",
        translation_key="file",
        path="status.params.file",
        entity_registry_enabled_default=False,
    ),
    PixLiteSensorEntityDescription(
        key="playlist_item",
        translation_key="playlist_item",
        path="status.state.item",
        entity_registry_enabled_default=False,
    ),
    PixLiteSensorEntityDescription(
        key="playlist_item_type",
        translation_key="playlist_item_type",
        path="status.state.op",
        entity_registry_enabled_default=False,
    ),
    PixLiteSensorEntityDescription(
        key="playlist_item_file",
        translation_key="playlist_item_file",
        path="status.state.file",
        entity_registry_enabled_default=False,
    ),
)

BANK_VOLTAGE = PixLiteSensorEntityDescription(
    key="bank_voltage",
    translation_key="bank_voltage",
    path="statistic.dev.bankVolt",
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
    divisor=1000,
)

OUTPUT_SENSORS: tuple[PixLiteSensorEntityDescription, ...] = (
    PixLiteSensorEntityDescription(
        key="current",
        translation_key="output_current",
        path="statistic.pixPwrOuts.current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        divisor=1000,
    ),
    PixLiteSensorEntityDescription(
        key="status",
        translation_key="output_status",
        path="statistic.pixPwrOuts.stat",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    PixLiteSensorEntityDescription(
        key="voltage",
        translation_key="output_voltage",
        path="statistic.pixPwrOuts.voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        divisor=1000,
    ),
)


def sensor_descriptions(
    device: Mapping[str, Any],
) -> tuple[PixLiteSensorEntityDescription, ...]:
    """Describe the sensors supported by the controller's hardware."""
    descriptions = list(SENSORS)
    for index in range(device.get("pwrBanksIn", 0)):
        descriptions.append(
            replace(
                BANK_VOLTAGE,
                key=f"bank_{index + 1}_voltage",
                path=f"{BANK_VOLTAGE.path}.{index}",
                channel=index + 1,
            )
        )
    if device.get("pwrOut"):
        for index in range(device.get("pixPorts", 0)):
            descriptions.extend(
                replace(
                    description,
                    key=f"output_{index + 1}_{description.key}",
                    path=f"{description.path}.{index}",
                    channel=index + 1,
                )
                for description in OUTPUT_SENSORS
                if description.key != "voltage" or device.get("pwrPixVolts")
            )
    return tuple(descriptions)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[PixLiteCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the controller's supported measurement entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        PixLiteSensor(coordinator, description)
        for description in sensor_descriptions(coordinator.client.constants["dev"])
    )


class PixLiteSensor(PixLiteEntity, SensorEntity):
    """Expose one controller value through the sensor platform."""

    entity_description: PixLiteSensorEntityDescription

    def __init__(
        self,
        coordinator: PixLiteCoordinator,
        description: PixLiteSensorEntityDescription,
    ) -> None:
        """Initialize a measurement with a stable controller-based identity."""
        super().__init__(coordinator, description.key, None)
        self.entity_description = description
        if description.channel is not None:
            self._attr_translation_placeholders = {"channel": str(description.channel)}

    @property
    def native_value(self) -> int | float | str | None:
        """Return the current value in Home Assistant's native units."""
        description = self.entity_description
        value = value_at(self.coordinator.data, description.path)
        if value is None:
            return None
        if description.native_unit_of_measurement is None:
            if description.key in ("file", "playlist_item_file") and isinstance(
                value, str
            ):
                return display_name(value)
            return (
                value
                if isinstance(value, (str, int)) and not isinstance(value, bool)
                else None
            )
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            return None
        return value / description.divisor
