"""One state owner for each fan. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import logging
from collections.abc import Mapping
from datetime import timedelta
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AuthenticationError,
    CloudError,
    Device,
    FanState,
    FluxClient,
    Oscillation,
    Property,
    RateLimited,
)
from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN, NAME

_LOGGER = logging.getLogger(__name__)


class FluxCoordinator(DataUpdateCoordinator[FanState]):
    """Serialize device operations and publish only meaningful state changes."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: FluxClient, device: Device
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=NAME,
            always_update=False,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
        self.client = client
        self.device = device
        self._device_lock = asyncio.Lock()
        self.last_poll_ms = 0.0

    async def _read(self) -> FanState:
        started = monotonic()
        self.device, state = await self.client.snapshot(self.device.did)
        self.last_poll_ms = round((monotonic() - started) * 1000, 1)
        return state

    async def _async_update_data(self) -> FanState:
        try:
            async with self._device_lock:
                return await self._read()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="authentication_failed"
            ) from err
        except RateLimited as err:
            raise UpdateFailed("Cloud request limit reached", retry_after=err.retry_after) from err
        except CloudError as err:
            raise UpdateFailed(str(err)) from err

    async def execute(
        self,
        *,
        power: bool | None = None,
        properties: Mapping[Property, int] | None = None,
        oscillation: Oscillation | None = None,
    ) -> None:
        """Apply a logical command and confirm it with exactly one property read."""
        try:
            async with self._device_lock:
                if self.data and self.data.online is False:
                    raise HomeAssistantError(
                        translation_domain=DOMAIN, translation_key="device_offline"
                    )
                if properties:
                    await self.client.write(self.device, properties)
                if power is not None:
                    await self.client.power(self.device, power)
                if oscillation is not None:
                    await self.client.oscillate(self.device, oscillation)
                state = await self._read()
                self.async_set_updated_data(state)
        except AuthenticationError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="authentication_failed"
            ) from err
        except CloudError as err:
            # A timeout can follow a successfully accepted write. Never replay it.
            self.async_set_update_error(UpdateFailed(str(err)))
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err
