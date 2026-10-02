"""Persistent, per-fan seasonal suspension. Copyright 2026 Gabriele Pennacchia."""

from dataclasses import asdict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import Device
from .const import DOMAIN


class FluxSeason:
    """Keep enough device identity to start a stored fan without cloud access."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.store = Store(hass, 1, f"{DOMAIN}.{entry_id}.season")
        self.paused = False
        self.device: Device | None = None

    async def async_load(self, did: str) -> None:
        if data := await self.store.async_load():
            device = Device(**data["device"])
            if device.did != did:
                raise ValueError("Seasonal storage belongs to another device")
            self.device = device
            self.paused = data["paused"] is True

    async def async_save(self, paused: bool, device: Device) -> None:
        await self.store.async_save({"paused": paused, "device": asdict(device)})
        self.paused = paused
        self.device = device
