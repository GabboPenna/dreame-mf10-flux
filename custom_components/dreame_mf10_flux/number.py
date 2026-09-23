"""Native sleep timer. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FluxEntry
from .api import Property
from .api.models import bounded_int
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluxOffTimer(entry.runtime_data.coordinator, "off_timer")])


class FluxOffTimer(FluxEntity, NumberEntity):
    """Hours reported by the device, without fabricating a remaining countdown."""

    _attr_native_min_value = 0
    _attr_native_max_value = 8
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_mode = NumberMode.BOX

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.off_timer is not None

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.off_timer

    async def async_set_native_value(self, value: float) -> None:
        if (hours := bounded_int(value, 0, 8)) is None:
            raise ValueError("Auto-off timer requires whole hours from 0 to 8")
        await self.coordinator.execute(properties={Property.OFF_TIMER: hours})
