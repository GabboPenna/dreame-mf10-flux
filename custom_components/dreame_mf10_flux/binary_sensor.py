"""Cloud-reported connectivity. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FluxEntry
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluxConnectivity(entry.runtime_data.coordinator, "connectivity")])


class FluxConnectivity(FluxEntity, BinarySensorEntity):
    """Show a confirmed offline binding as disconnected, rather than unavailable."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return CoordinatorEntity.available.fget(self)

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.online
