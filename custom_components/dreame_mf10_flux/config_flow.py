"""Account setup and recovery. Copyright 2026 Gabriele Pennacchia."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthenticationError, CloudError, Device, FluxClient, RateLimited
from .api.client import REGIONS
from .const import CONF_DEVICE_ID, CONF_POLL_INTERVAL, CONF_REGION, DEFAULT_POLL_INTERVAL, DOMAIN


def account_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Use selectors so the UI follows the user's language and device."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")
            ): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_REGION, default=defaults.get(CONF_REGION, "eu")
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=list(REGIONS), translation_key="region")
            ),
        }
    )


class FluxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one fan per entry and validate the device on reauthentication."""

    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._devices: tuple[Device, ...] = ()

    async def _validate(self, user_input: dict[str, Any]) -> str | None:
        self._credentials = {
            CONF_USERNAME: user_input[CONF_USERNAME].strip(),
            CONF_PASSWORD: user_input[CONF_PASSWORD],
            CONF_REGION: user_input[CONF_REGION],
        }
        client = FluxClient(
            async_get_clientsession(self.hass),
            self._credentials[CONF_USERNAME],
            self._credentials[CONF_PASSWORD],
            self._credentials[CONF_REGION],
        )
        try:
            self._devices = await client.devices(force=True)
        except AuthenticationError:
            return "invalid_auth"
        except RateLimited:
            return "rate_limited"
        except CloudError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            error = await self._validate(user_input)
            if error:
                errors["base"] = error
            else:
                configured = {entry.unique_id for entry in self._async_current_entries()}
                self._devices = tuple(d for d in self._devices if d.did not in configured)
                if not self._devices:
                    return self.async_abort(reason="no_devices")
                if len(self._devices) == 1:
                    return await self._create(self._devices[0])
                return await self.async_step_device()
        return self.async_show_form(
            step_id="user", data_schema=account_schema(user_input), errors=errors
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            device = next((d for d in self._devices if d.did == user_input[CONF_DEVICE_ID]), None)
            if device is None:
                return self.async_abort(reason="no_devices")
            return await self._create(device)
        options = [
            {"value": d.did, "label": f"{d.name} ({index + 1})"}
            for index, d in enumerate(self._devices)
        ]
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    async def _create(self, device: Device) -> ConfigFlowResult:
        await self.async_set_unique_id(device.did)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=device.name, data=self._credentials | {CONF_DEVICE_ID: device.did}
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            error = await self._validate(user_input)
            if error:
                errors["base"] = error
            elif not any(d.did == entry.data[CONF_DEVICE_ID] for d in self._devices):
                errors["base"] = "wrong_account"
            else:
                self._update_account_entries(entry)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=account_schema(dict(entry.data)), errors=errors
        )

    @callback
    def _update_account_entries(self, entry: ConfigEntry) -> None:
        """Recover verified fans on the same account without touching other accounts."""
        identity = (entry.data[CONF_USERNAME].strip().casefold(), entry.data[CONF_REGION])
        new_identity = (self._credentials[CONF_USERNAME].casefold(), self._credentials[CONF_REGION])
        verified = {device.did for device in self._devices}
        entries = [entry]
        if identity == new_identity:
            entries.extend(
                other
                for other in self._async_current_entries()
                if other.entry_id != entry.entry_id
                and (other.data[CONF_USERNAME].strip().casefold(), other.data[CONF_REGION])
                == identity
                and other.data[CONF_DEVICE_ID] in verified
            )
        for other in entries:
            changed = self.hass.config_entries.async_update_entry(
                other, data=dict(other.data) | self._credentials
            )
            # Loaded entries already reload through their update listener.
            if not other.disabled_by and (not changed or not other.update_listeners):
                self.hass.config_entries.async_schedule_reload(other.entry_id)
        recovered = {other.entry_id for other in entries}
        for flow in self.hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            if (
                flow["flow_id"] != self.flow_id
                and flow["context"].get("source") == SOURCE_REAUTH
                and flow["context"].get("entry_id") in recovered
            ):
                self.hass.config_entries.flow.async_abort(flow["flow_id"])

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "FluxOptionsFlow":
        return FluxOptionsFlow()


class FluxOptionsFlow(OptionsFlow):
    """Adjust polling with a conservative lower bound."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            value = user_input[CONF_POLL_INTERVAL]
            if (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and 10 <= value <= 300
            ):
                return self.async_create_entry(title="", data={CONF_POLL_INTERVAL: int(value)})
            errors = {"base": "invalid_interval"}
        else:
            errors = {}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10,
                            max=300,
                            step=1,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
            errors=errors,
        )
