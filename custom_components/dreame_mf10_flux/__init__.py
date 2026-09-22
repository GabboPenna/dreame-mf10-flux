"""Dreame MF10 Flux for Home Assistant. Copyright 2026 Gabriele Pennacchia."""

import hashlib
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthenticationError, CloudError, FluxClient
from .const import CONF_DEVICE_ID, CONF_REGION, DOMAIN, PLATFORMS
from .coordinator import FluxCoordinator


@dataclass(slots=True)
class AccountSession:
    """Reference-counted account transport; Home Assistant owns the HTTP session."""

    client: FluxClient
    users: int = 0


@dataclass(slots=True)
class FluxRuntime:
    """Resources owned by a configuration entry."""

    coordinator: FluxCoordinator
    account_key: str


type FluxEntry = ConfigEntry[FluxRuntime]


async def async_setup_entry(hass: HomeAssistant, entry: FluxEntry) -> bool:
    """Authenticate, fetch a snapshot, then create the device entities."""
    credentials = (entry.data[CONF_REGION], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    key = hashlib.sha256("\0".join(credentials).encode()).hexdigest()
    accounts: dict[str, AccountSession] = hass.data.setdefault(DOMAIN, {})
    if key not in accounts:
        region, username, password = credentials
        accounts[key] = AccountSession(
            FluxClient(async_get_clientsession(hass), username, password, region)
        )
    account = accounts[key]
    account.users += 1
    try:
        device = await account.client.device(entry.data[CONF_DEVICE_ID])
        coordinator = FluxCoordinator(hass, entry, account.client, device)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = FluxRuntime(coordinator, key)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except AuthenticationError as err:
        _release(hass, key)
        raise ConfigEntryAuthFailed from err
    except CloudError as err:
        _release(hass, key)
        raise ConfigEntryNotReady(str(err)) from err
    except BaseException:
        _release(hass, key)
        raise
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


def _release(hass: HomeAssistant, key: str) -> None:
    accounts: dict[str, AccountSession] = hass.data[DOMAIN]
    account = accounts[key]
    account.users -= 1
    if not account.users:
        del accounts[key]


async def _options_updated(hass: HomeAssistant, entry: FluxEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FluxEntry) -> bool:
    """Remove listeners and release the account when its last fan is unloaded."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    _release(hass, entry.runtime_data.account_key)
    return True
