"""Shared entity identity and availability. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import FluxCoordinator


class FluxEntity(CoordinatorEntity[FluxCoordinator]):
    """A translated entity backed by the same immutable fan snapshot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FluxCoordinator, key: str) -> None:
        super().__init__(coordinator, context=key)
        device = coordinator.device
        self._attr_unique_id = f"{device.did}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.did)},
            manufacturer="Dreame",
            name=device.name or NAME,
            model="MF10",
            model_id=device.model,
            sw_version=device.firmware,
        )
        if device.mac:
            self._attr_device_info["connections"] = {(CONNECTION_NETWORK_MAC, device.mac)}

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.online is not False
