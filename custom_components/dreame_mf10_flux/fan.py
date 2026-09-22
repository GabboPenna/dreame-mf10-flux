"""Native fan controls. Copyright 2026 Gabriele Pennacchia."""

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FluxEntry
from .api import Mode, Oscillation, Property
from .api.models import speed_from_percentage
from .entity import FluxEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: FluxEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([FluxFan(entry.runtime_data.coordinator, "fan")])


class FluxFan(FluxEntity, FanEntity):
    """Ten speed levels and stable preset values for automations."""

    _attr_name = None
    _attr_supported_features = (
        FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.OSCILLATE
    )
    _attr_speed_count = 10
    _attr_preset_modes = [mode.name.lower() for mode in Mode]

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.power

    @property
    def percentage(self) -> int | None:
        state = self.coordinator.data
        if state.power is False:
            return 0
        return state.speed * 10 if state.speed is not None else None

    @property
    def preset_mode(self) -> str | None:
        mode = self.coordinator.data.mode
        return mode.name.lower() if mode is not None else None

    @property
    def oscillating(self) -> bool | None:
        value = self.coordinator.data.oscillation
        return value != Oscillation.OFF if value is not None else None

    async def async_turn_on(
        self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any
    ) -> None:
        properties: dict[Property, int] = {}
        if percentage is not None:
            speed = speed_from_percentage(percentage)
            if speed == 0:
                await self.async_turn_off()
                return
            properties = {Property.MODE: Mode.MANUAL.value, Property.SPEED: speed}
        if preset_mode is not None:
            properties[Property.MODE] = Mode[preset_mode.upper()].value
        await self.coordinator.execute(power=True, properties=properties)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.execute(power=False)

    async def async_set_percentage(self, percentage: int) -> None:
        speed = speed_from_percentage(percentage)
        if speed == 0:
            await self.async_turn_off()
        else:
            await self.coordinator.execute(
                power=True if not self.is_on else None,
                properties={Property.MODE: Mode.MANUAL.value, Property.SPEED: speed},
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.coordinator.execute(properties={Property.MODE: Mode[preset_mode.upper()].value})

    async def async_oscillate(self, oscillating: bool) -> None:
        value = Oscillation.BOTH if oscillating else Oscillation.OFF
        await self.coordinator.execute(oscillation=value)
