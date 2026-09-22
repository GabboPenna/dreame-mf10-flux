"""Blade movement selection. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FluxEntry
from .api import Oscillation
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluxOscillation(entry.runtime_data.coordinator, "oscillation")])


class FluxOscillation(FluxEntity, SelectEntity):
    """Six mutually consistent oscillation combinations."""

    _attr_options = list(Oscillation)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.oscillation

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.execute(oscillation=Oscillation(option))
