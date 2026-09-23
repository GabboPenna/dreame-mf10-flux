"""Temperature and observed operating hours. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FluxEntry
from .coordinator import FluxCoordinator
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            FluxTemperature(coordinator, "temperature"),
            FluxUsageSensor(coordinator, "operating_hours", daily=False),
            FluxUsageSensor(coordinator, "operating_hours_today", daily=True),
        ]
    )


class FluxTemperature(FluxEntity, SensorEntity):
    """Ambient temperature without inventing a reading for unsupported responses."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.temperature


class FluxUsageSensor(FluxEntity, SensorEntity):
    """Persistent observed runtime; the total remains readable during an outage."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: FluxCoordinator, key: str, *, daily: bool) -> None:
        super().__init__(coordinator, key)
        self._daily = daily

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.usage.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self.coordinator.usage.loaded

    @property
    def native_value(self) -> float:
        usage = self.coordinator.usage
        return (usage.today_seconds if self._daily else usage.total_seconds) / 3600

    @property
    def extra_state_attributes(self) -> dict:
        usage = self.coordinator.usage
        attributes = {"tracking_started_at": usage.started_at}
        if self._daily:
            attributes["date"] = usage.day
        return attributes
