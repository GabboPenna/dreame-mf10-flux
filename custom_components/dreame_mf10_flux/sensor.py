"""Temperature telemetry. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FluxEntry
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluxTemperature(entry.runtime_data.coordinator, "temperature")])


class FluxTemperature(FluxEntity, SensorEntity):
    """Ambient temperature without inventing a reading for unsupported responses."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.temperature
