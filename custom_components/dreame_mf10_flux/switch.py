"""Validated binary controls. Copyright 2026 Gabriele Pennacchia."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FluxEntry
from .api import Property
from .coordinator import FluxCoordinator
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            FluxSwitch(coordinator, "child_lock", Property.CHILD_LOCK),
            FluxSwitch(coordinator, "rotation", Property.ROTATION),
        ]
    )


class FluxSwitch(FluxEntity, SwitchEntity):
    """A switch with a fixed, validated property binding."""

    def __init__(self, coordinator: FluxCoordinator, key: str, prop: Property) -> None:
        super().__init__(coordinator, key)
        self._key = key
        self._property = prop

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.data, self._key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.execute(properties={self._property: 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.execute(properties={self._property: 0})
