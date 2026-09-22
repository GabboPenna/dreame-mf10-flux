"""Tests against real Home Assistant classes. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dreame_mf10_flux import FluxRuntime, async_setup_entry, async_unload_entry
from custom_components.dreame_mf10_flux.api import (
    AuthenticationError,
    Device,
    FanState,
    FluxClient,
    Mode,
    Oscillation,
    Property,
    RateLimited,
    Unavailable,
)
from custom_components.dreame_mf10_flux.binary_sensor import FluxConnectivity
from custom_components.dreame_mf10_flux.config_flow import FluxConfigFlow, FluxOptionsFlow
from custom_components.dreame_mf10_flux.const import DOMAIN
from custom_components.dreame_mf10_flux.coordinator import FluxCoordinator
from custom_components.dreame_mf10_flux.diagnostics import async_get_config_entry_diagnostics
from custom_components.dreame_mf10_flux.fan import FluxFan
from custom_components.dreame_mf10_flux.select import FluxOscillation
from custom_components.dreame_mf10_flux.switch import FluxSwitch

CREDS = {"username": "fixture@example.test", "password": "private-fixture", "region": "eu"}
DEVICE = Device(
    "private-device",
    "MF10",
    "dreame.fan.u2519",
    "1.8.30_1047",
    True,
    "10000.fixture",
    "00:00:00:00:00:01",
)
STATE = FanState(True, True, 3, Mode.AI, True, False, Oscillation.STAGGERED, 28.0)


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        for module in (
            "custom_components.dreame_mf10_flux",
            "custom_components.dreame_mf10_flux.config_flow",
        ):
            transport = patch(module + ".async_get_clientsession", return_value=MagicMock())
            transport.start()
            self.addCleanup(transport.stop)
        self.entry = ConfigEntry(
            domain=DOMAIN,
            title="MF10",
            data=CREDS | {"device_id": DEVICE.did},
            options={},
            source="user",
            unique_id=DEVICE.did,
            version=1,
            minor_version=1,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        self.client = MagicMock(spec=FluxClient)
        self.client.requests = 3
        self.client.device = AsyncMock(return_value=DEVICE)
        self.client.devices = AsyncMock(return_value=(DEVICE,))
        self.client.snapshot = AsyncMock(return_value=(DEVICE, STATE))
        self.client.write = AsyncMock()
        self.client.power = AsyncMock()
        self.client.oscillate = AsyncMock()
        self.coordinator = FluxCoordinator(self.hass, self.entry, self.client, DEVICE)
        self.coordinator.async_set_updated_data(STATE)
        self.entry.runtime_data = FluxRuntime(self.coordinator, "test-account")
        self.fan = FluxFan(self.coordinator, "fan")

    async def asyncTearDown(self):
        await self.coordinator.async_shutdown()
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    async def test_speed_batches_manual_and_speed_with_one_confirmation(self):
        await self.fan.async_set_percentage(47)
        self.client.write.assert_awaited_once_with(DEVICE, {Property.MODE: 3, Property.SPEED: 5})
        self.client.power.assert_not_called()
        self.client.snapshot.assert_awaited_once()

    async def test_turn_on_off_and_zero_speed_have_explicit_power(self):
        await self.fan.async_turn_on(percentage=20)
        self.client.power.assert_awaited_with(DEVICE, True)
        self.assertEqual(self.client.snapshot.await_count, 1)
        await self.fan.async_set_percentage(0)
        self.client.power.assert_awaited_with(DEVICE, False)
        self.assertEqual(self.client.snapshot.await_count, 2)

    async def test_offline_disables_controls_but_reports_connectivity(self):
        self.coordinator.async_set_updated_data(FanState(online=False))
        connectivity = FluxConnectivity(self.coordinator, "connectivity")
        self.assertFalse(self.fan.available)
        self.assertTrue(connectivity.available)
        self.assertFalse(connectivity.is_on)
        with self.assertRaises(HomeAssistantError):
            await self.fan.async_turn_on()
        self.client.power.assert_not_called()

    async def test_cloud_failure_does_not_claim_device_disconnected(self):
        self.coordinator.async_set_update_error(UpdateFailed("Cloud unavailable"))
        self.assertFalse(FluxConnectivity(self.coordinator, "connectivity").available)
        self.assertFalse(self.fan.available)

    async def test_unknown_connectivity_does_not_become_false(self):
        self.coordinator.async_set_updated_data(replace(STATE, online=None))
        self.assertIsNone(FluxConnectivity(self.coordinator, "connectivity").is_on)

    async def test_each_oscillation_combination_is_consistent(self):
        selector = FluxOscillation(self.coordinator, "oscillation")
        for value in Oscillation:
            await selector.async_select_option(value)
            self.client.oscillate.assert_awaited_with(DEVICE, value)
        self.assertEqual(self.client.snapshot.await_count, 6)

    async def test_switches_use_distinct_fixed_properties(self):
        for key, prop in (("child_lock", Property.CHILD_LOCK), ("rotation", Property.ROTATION)):
            switch = FluxSwitch(self.coordinator, key, prop)
            await switch.async_turn_off()
            self.client.write.assert_awaited_with(DEVICE, {prop: 0})

    async def test_command_failure_is_not_replayed(self):
        self.client.power.side_effect = Unavailable("Request timed out")
        with self.assertRaises(HomeAssistantError):
            await self.fan.async_turn_off()
        self.client.power.assert_awaited_once()
        self.client.snapshot.assert_not_called()
        self.assertFalse(self.coordinator.last_update_success)

    async def test_poll_auth_and_rate_limits_have_framework_semantics(self):
        self.client.snapshot.side_effect = AuthenticationError("Expired")
        with self.assertRaises(ConfigEntryAuthFailed):
            await self.coordinator._async_update_data()
        self.client.snapshot.side_effect = RateLimited(120)
        with self.assertRaises(UpdateFailed) as result:
            await self.coordinator._async_update_data()
        self.assertEqual(result.exception.retry_after, 120)

    async def test_poll_and_commands_cannot_overlap(self):
        running = 0
        peak = 0

        async def snapshot(did):
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1
            return DEVICE, STATE

        self.client.snapshot.side_effect = snapshot
        await asyncio.gather(
            self.coordinator._async_update_data(),
            self.fan.async_turn_off(),
            self.fan.async_turn_on(),
        )
        self.assertEqual(peak, 1)

    async def test_diagnostics_exclude_all_account_and_device_identifiers(self):
        text = json.dumps(await async_get_config_entry_diagnostics(self.hass, self.entry))
        for secret in (
            CREDS["username"],
            CREDS["password"],
            DEVICE.did,
            DEVICE.mac,
            DEVICE.routing,
        ):
            self.assertNotIn(secret, text)
        self.assertIn("1.8.30_1047", text)

    async def test_entity_values_and_identity(self):
        self.assertEqual(self.fan.percentage, 30)
        self.assertEqual(self.fan.preset_mode, "ai")
        self.assertEqual(self.fan.unique_id, DEVICE.did + "_fan")
        self.assertIn((DOMAIN, DEVICE.did), self.fan.device_info["identifiers"])
        self.coordinator.async_set_updated_data(replace(STATE, power=False))
        self.assertEqual(self.fan.percentage, 0)

    async def test_setup_and_unload_release_account(self):
        self.entry._async_set_state(self.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
        with (
            patch("custom_components.dreame_mf10_flux.FluxClient", return_value=self.client),
            patch.object(self.hass.config_entries, "async_forward_entry_setups", AsyncMock()),
            patch.object(
                self.hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
            ),
        ):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
            runtime = self.entry.runtime_data
            self.assertEqual(len(self.hass.data[DOMAIN]), 1)
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
            self.assertFalse(self.hass.data[DOMAIN])
            await runtime.coordinator.async_shutdown()

    async def test_setup_auth_failure_leaves_no_account(self):
        self.client.device.side_effect = AuthenticationError("Expired")
        with patch("custom_components.dreame_mf10_flux.FluxClient", return_value=self.client):
            with self.assertRaises(ConfigEntryAuthFailed):
                await async_setup_entry(self.hass, self.entry)
        self.assertFalse(self.hass.data[DOMAIN])

    def flow(self):
        flow = FluxConfigFlow()
        flow.hass = self.hass
        flow.context = {"source": "user"}
        return flow

    async def test_user_flow_creates_entry_for_single_supported_device(self):
        with patch(
            "custom_components.dreame_mf10_flux.config_flow.FluxClient", return_value=self.client
        ):
            result = await self.flow().async_step_user(CREDS)
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["device_id"], DEVICE.did)

    async def test_flow_multiple_devices_requires_selection(self):
        self.client.devices.return_value = (DEVICE, replace(DEVICE, did="fixture-2"))
        with patch(
            "custom_components.dreame_mf10_flux.config_flow.FluxClient", return_value=self.client
        ):
            result = await self.flow().async_step_user(CREDS)
        self.assertEqual(result["step_id"], "device")

    async def test_flow_errors_and_empty_accounts(self):
        with patch(
            "custom_components.dreame_mf10_flux.config_flow.FluxClient", return_value=self.client
        ):
            for error, key in (
                (AuthenticationError("bad"), "invalid_auth"),
                (Unavailable("bad"), "cannot_connect"),
                (RateLimited(60), "rate_limited"),
            ):
                self.client.devices.side_effect = error
                result = await self.flow().async_step_user(CREDS)
                self.assertEqual(result["errors"]["base"], key)
            self.client.devices.side_effect = None
            self.client.devices.return_value = ()
            result = await self.flow().async_step_user(CREDS)
            self.assertEqual(result["reason"], "no_devices")

    async def test_options_store_valid_polling_interval(self):
        flow = FluxOptionsFlow()
        flow.hass = self.hass
        result = await flow.async_step_init({"poll_interval": 45})
        self.assertEqual(result["data"], {"poll_interval": 45})
