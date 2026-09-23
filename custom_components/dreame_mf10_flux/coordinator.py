"""One state owner for each fan. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import NoReturn

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
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
from .usage import FluxUsage

_LOGGER = logging.getLogger(__name__)
_CONFIRMATION_DELAYS = (0, 0.5, 1.0)
_COMMAND_FIELDS = {
    Property.MODE: "mode",
    Property.SPEED: "speed",
    Property.ROTATION: "rotation",
    Property.CHILD_LOCK: "child_lock",
    Property.DISPLAY: "display",
    Property.OFF_TIMER: "off_timer",
}


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
        self.last_successful_update: datetime | None = None
        self.consecutive_update_failures = 0
        self.last_command_ms: float | None = None
        self.last_command_success: bool | None = None
        self.last_command_error: str | None = None
        self.commands = 0
        self.command_failures = 0
        self.consecutive_command_failures = 0
        self.usage = FluxUsage(hass, entry.entry_id, self.update_interval.total_seconds() * 2 + 30)

    async def _read(self) -> FanState:
        started = monotonic()
        try:
            device, state = await self.client.snapshot(self.device.did)
        except CloudError:
            self.usage.unavailable()
            self.consecutive_update_failures += 1
            raise
        finally:
            self.last_poll_ms = round((monotonic() - started) * 1000, 1)
        self.last_successful_update = datetime.now(UTC)
        self.consecutive_update_failures = 0
        if (device.name, device.firmware) != (self.device.name, self.device.firmware):
            registry = dr.async_get(self.hass)
            if registered := registry.async_get_device_by_identifier(
                (DOMAIN, device.did), self.config_entry.entry_id
            ):
                registry.async_update_device(
                    registered.id, name=device.name or NAME, sw_version=device.firmware
                )
        self.device = device
        self.usage.observe(state.power if state.online is not False else None)
        return state

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.usage.async_shutdown()

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
        ensure_on: bool = False,
        properties: Mapping[Property, int] | None = None,
        oscillation: Oscillation | None = None,
    ) -> None:
        """Serialize state-dependent decisions, writes and bounded confirmation reads."""
        async with self._device_lock:
            started = monotonic()
            self.commands += 1
            try:
                await self._execute_command(power, ensure_on, properties or {}, oscillation)
            except HomeAssistantError as err:
                self.last_command_success = False
                self.last_command_error = err.translation_key
                self.command_failures += 1
                self.consecutive_command_failures += 1
                raise
            else:
                self.last_command_success = True
                self.last_command_error = None
                self.consecutive_command_failures = 0
            finally:
                self.last_command_ms = round((monotonic() - started) * 1000, 1)

    async def _execute_command(
        self,
        power: bool | None,
        ensure_on: bool,
        properties: Mapping[Property, int],
        oscillation: Oscillation | None,
    ) -> None:
        if self.data and self.data.online is False:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="device_offline")
        expected: dict[str, object] = {
            _COMMAND_FIELDS[prop]: value for prop, value in properties.items()
        }
        if ensure_on:
            expected["power"] = True
            power = True if self.data.power is not True else None
        elif power is not None:
            expected["power"] = power
        if oscillation is not None:
            expected["oscillation"] = oscillation
        try:
            if properties:
                await self.client.write(self.device, properties)
            if power is not None:
                await self.client.power(self.device, power)
            if oscillation is not None:
                await self.client.oscillate(self.device, oscillation)
        except CloudError as err:
            await self._command_error(err, reconcile=True)

        for delay in _CONFIRMATION_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            try:
                state = await self._read()
            except CloudError as err:
                await self._command_error(err)
            self.async_set_updated_data(state)
            if all(getattr(state, key) == value for key, value in expected.items()):
                return
            if state.online is False:
                break
        # The cloud is reachable: preserve the actual state, including partial changes.
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="command_failed")

    async def _command_error(self, err: CloudError, *, reconcile: bool = False) -> NoReturn:
        """Refresh uncertain writes once, without resending any command."""
        if reconcile and not isinstance(err, (AuthenticationError, RateLimited)):
            try:
                self.async_set_updated_data(await self._read())
            except CloudError as read_error:
                err = read_error
            else:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                ) from err
        self.async_set_update_error(
            UpdateFailed(str(err), retry_after=err.retry_after)
            if isinstance(err, RateLimited)
            else UpdateFailed(str(err))
        )
        if isinstance(err, AuthenticationError):
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="authentication_failed"
            ) from err
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_failed"
        ) from err
