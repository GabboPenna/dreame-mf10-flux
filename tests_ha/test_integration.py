"""Tests against real Home Assistant classes. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import (
    ConfigEntries,
    ConfigEntry,
    ConfigEntryDisabler,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.dreame_mf10_flux import FluxRuntime, async_setup_entry, async_unload_entry
from custom_components.dreame_mf10_flux.api import (
    AuthenticationError,
    CommandError,
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
        self.state = STATE
        self.client.snapshot = AsyncMock(side_effect=self.snapshot)
        self.client.write = AsyncMock(side_effect=self.write)
        self.client.power = AsyncMock(side_effect=self.power)
        self.client.oscillate = AsyncMock(side_effect=self.oscillate)
        self.coordinator = FluxCoordinator(self.hass, self.entry, self.client, DEVICE)
        self.coordinator.async_set_updated_data(STATE)
        self.entry.runtime_data = FluxRuntime(self.coordinator, "test-account")
        self.fan = FluxFan(self.coordinator, "fan")

    async def snapshot(self, did):
        return DEVICE, self.state

    async def write(self, device, properties):
        fields = {
            Property.MODE: "mode",
            Property.SPEED: "speed",
            Property.ROTATION: "rotation",
            Property.CHILD_LOCK: "child_lock",
        }
        values = {fields[prop]: value for prop, value in properties.items()}
        if "mode" in values:
            values["mode"] = Mode(values["mode"])
        self.state = replace(self.state, **values)

    async def power(self, device, on):
        self.state = replace(self.state, power=on)

    async def oscillate(self, device, value):
        self.state = replace(self.state, oscillation=value)

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
        self.client.snapshot.assert_awaited_once()
        self.assertTrue(self.coordinator.last_update_success)
        self.assertTrue(self.fan.is_on)

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
            return DEVICE, self.state

        self.client.snapshot.side_effect = snapshot
        await asyncio.gather(
            self.coordinator._async_update_data(),
            self.fan.async_turn_off(),
            self.fan.async_turn_on(),
        )
        self.assertEqual(peak, 1)

    async def test_speed_after_inflight_turn_off_turns_fan_back_on(self):
        off_started = asyncio.Event()
        release_off = asyncio.Event()

        async def power(device, on):
            if not on:
                off_started.set()
                await release_off.wait()
            await self.power(device, on)

        self.client.power.side_effect = power
        off_task = asyncio.create_task(self.fan.async_turn_off())
        await asyncio.wait_for(off_started.wait(), 1)
        speed_task = asyncio.create_task(self.fan.async_set_percentage(50))
        await asyncio.sleep(0)
        release_off.set()
        await asyncio.wait_for(asyncio.gather(off_task, speed_task), 1)
        self.assertEqual(
            [call.args[1] for call in self.client.power.await_args_list], [False, True]
        )
        self.assertTrue(self.fan.is_on)
        self.assertEqual(self.fan.percentage, 50)

    async def test_delayed_cloud_state_gets_bounded_reads_without_replaying_write(self):
        self.client.snapshot.side_effect = [
            (DEVICE, STATE),
            (DEVICE, STATE),
            (DEVICE, replace(STATE, power=False)),
        ]
        with patch(
            "custom_components.dreame_mf10_flux.coordinator.asyncio.sleep", AsyncMock()
        ) as pause:
            await self.fan.async_turn_off()
        self.assertEqual([call.args[0] for call in pause.await_args_list], [0.5, 1.0])
        self.client.power.assert_awaited_once_with(DEVICE, False)
        self.assertEqual(self.client.snapshot.await_count, 3)
        self.assertFalse(self.fan.is_on)

    async def test_unconfirmed_command_fails_and_keeps_actual_state_available(self):
        self.client.snapshot.side_effect = None
        self.client.snapshot.return_value = (DEVICE, STATE)
        with patch("custom_components.dreame_mf10_flux.coordinator.asyncio.sleep", AsyncMock()):
            with self.assertRaises(HomeAssistantError) as result:
                await self.fan.async_turn_off()
        self.assertEqual(result.exception.translation_key, "command_failed")
        self.client.power.assert_awaited_once()
        self.assertEqual(self.client.snapshot.await_count, 3)
        self.assertTrue(self.fan.available)
        self.assertTrue(self.fan.is_on)

    async def test_missing_requested_value_does_not_confirm_a_command(self):
        self.client.snapshot.side_effect = None
        self.client.snapshot.return_value = (DEVICE, replace(STATE, rotation=None))
        with patch("custom_components.dreame_mf10_flux.coordinator.asyncio.sleep", AsyncMock()):
            with self.assertRaises(HomeAssistantError):
                await FluxSwitch(self.coordinator, "rotation", Property.ROTATION).async_turn_off()
        self.assertIsNone(self.coordinator.data.rotation)
        self.assertEqual(self.client.snapshot.await_count, 3)

    async def test_partial_oscillation_failure_refreshes_applied_changes(self):
        async def partial(device, value):
            self.state = replace(self.state, oscillation=Oscillation.BOTH)
            raise CommandError("Flag write not confirmed")

        self.client.oscillate.side_effect = partial
        with self.assertRaises(HomeAssistantError):
            await self.coordinator.execute(oscillation=Oscillation.SYNC)
        self.client.oscillate.assert_awaited_once()
        self.client.snapshot.assert_awaited_once()
        self.assertEqual(self.coordinator.data.oscillation, Oscillation.BOTH)
        self.assertTrue(self.fan.available)

    async def test_command_rate_limit_preserves_cooldown_without_confirmation_reads(self):
        self.client.power.side_effect = RateLimited(120)
        with self.assertRaises(HomeAssistantError):
            await self.fan.async_turn_off()
        self.assertEqual(self.coordinator.last_exception.retry_after, 120)
        self.client.snapshot.assert_not_called()

    async def test_command_auth_failure_starts_reauth_without_confirmation_reads(self):
        self.client.power.side_effect = AuthenticationError("Expired")
        with patch.object(ConfigEntry, "async_start_reauth") as reauth:
            with self.assertRaises(HomeAssistantError) as result:
                await self.fan.async_turn_off()
        self.assertEqual(result.exception.translation_key, "authentication_failed")
        reauth.assert_called_once_with(self.hass)
        self.client.snapshot.assert_not_called()
        self.assertFalse(self.fan.available)

    async def test_confirmation_read_failure_does_not_replay_write_or_read_again(self):
        self.client.snapshot.side_effect = Unavailable("Cloud unavailable")
        with self.assertRaises(HomeAssistantError):
            await self.fan.async_turn_off()
        self.client.power.assert_awaited_once()
        self.client.snapshot.assert_awaited_once()
        self.assertFalse(self.fan.available)

    async def test_automatic_preset_takes_priority_over_requested_speed(self):
        await self.fan.async_turn_on(percentage=50, preset_mode="ai")
        self.client.write.assert_awaited_once_with(DEVICE, {Property.MODE: Mode.AI})
        self.client.snapshot.assert_awaited_once()
        self.assertEqual(self.fan.preset_mode, "ai")

    async def test_diagnostics_track_success_failure_and_recovery(self):
        self.client.snapshot.side_effect = Unavailable("Cloud unavailable")
        for _ in range(2):
            with self.assertRaises(UpdateFailed):
                await self.coordinator._async_update_data()
        diagnostics = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(diagnostics["consecutive_update_failures"], 2)
        self.assertIsNone(diagnostics["last_successful_update"])
        with self.assertRaises(HomeAssistantError):
            await self.fan.async_turn_off()
        diagnostics = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(diagnostics["command_failures"], 1)
        self.assertEqual(diagnostics["consecutive_command_failures"], 1)
        self.assertFalse(diagnostics["last_command_success"])
        self.assertEqual(diagnostics["last_command_error"], "command_failed")
        self.client.snapshot.side_effect = self.snapshot
        await self.fan.async_turn_on()
        diagnostics = await async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(diagnostics["commands"], 2)
        self.assertEqual(diagnostics["command_failures"], 1)
        self.assertEqual(diagnostics["consecutive_command_failures"], 0)
        self.assertEqual(diagnostics["consecutive_update_failures"], 0)
        self.assertTrue(diagnostics["last_command_success"])
        self.assertIsNone(diagnostics["last_command_error"])
        self.assertTrue(diagnostics["last_successful_update"].endswith("+00:00"))
        self.assertGreaterEqual(diagnostics["last_command_ms"], 0)

    async def test_diagnostics_exclude_all_account_and_device_identifiers(self):
        self.coordinator.device = replace(DEVICE, name="private-room-name")
        text = json.dumps(await async_get_config_entry_diagnostics(self.hass, self.entry))
        for secret in (
            CREDS["username"],
            CREDS["password"],
            DEVICE.did,
            DEVICE.mac,
            DEVICE.routing,
            "private-room-name",
        ):
            self.assertNotIn(secret, text)
        self.assertIn("1.8.30_1047", text)

    async def test_entity_values_and_identity(self):
        self.assertEqual(self.fan.percentage, 30)
        self.assertEqual(self.fan.preset_mode, "ai")
        self.assertEqual(self.fan.unique_id, DEVICE.did + "_fan")
        self.assertIn((DOMAIN, DEVICE.did), self.fan.device_info["identifiers"])
        self.assertEqual(self.fan.device_info["name"], DEVICE.name)
        self.coordinator.async_set_updated_data(replace(STATE, power=False))
        self.assertEqual(self.fan.percentage, 0)

    def register_entry(self, did, *, credentials=None, disabled_by=None):
        entry = ConfigEntry(
            domain=DOMAIN,
            title="Fixture fan",
            data=(credentials or CREDS) | {"device_id": did},
            options={"poll_interval": 45},
            source="user",
            unique_id=did,
            version=1,
            minor_version=1,
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
            disabled_by=disabled_by,
        )
        self.hass.config_entries._entries[entry.entry_id] = entry
        return entry

    async def test_cloud_device_name_refresh_preserves_home_assistant_override(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        dr.async_setup(self.hass)
        await dr.async_load(self.hass, load_empty=True)
        registry = dr.async_get(self.hass)
        device = registry.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, DEVICE.did)},
            name=DEVICE.name,
        )
        registry.async_update_device(device.id, name_by_user="My preferred name")
        renamed = replace(DEVICE, name="Bedroom MF10", firmware="fixture-update")
        self.client.snapshot.side_effect = None
        self.client.snapshot.return_value = (renamed, STATE)
        await self.coordinator._async_update_data()
        updated = registry.async_get(device.id)
        self.assertEqual(updated.name, "Bedroom MF10")
        self.assertEqual(updated.name_by_user, "My preferred name")
        self.assertEqual(updated.sw_version, "fixture-update")
        self.assertEqual(self.fan.unique_id, DEVICE.did + "_fan")

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

    async def test_two_fans_share_session_until_last_entry_unloads(self):
        second = self.register_entry("fixture-2")
        for entry in (self.entry, second):
            entry._async_set_state(self.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
        with (
            patch(
                "custom_components.dreame_mf10_flux.FluxClient", return_value=self.client
            ) as factory,
            patch.object(self.hass.config_entries, "async_forward_entry_setups", AsyncMock()),
            patch.object(
                self.hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
            ),
        ):
            await async_setup_entry(self.hass, self.entry)
            await async_setup_entry(self.hass, second)
            factory.assert_called_once()
            self.assertIs(
                self.entry.runtime_data.coordinator.client, second.runtime_data.coordinator.client
            )
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
            self.assertEqual(len(self.hass.data[DOMAIN]), 1)
            self.assertTrue(await async_unload_entry(self.hass, second))
            self.assertFalse(self.hass.data[DOMAIN])
        for entry in (self.entry, second):
            await entry.runtime_data.coordinator.async_shutdown()

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

    async def test_reauth_updates_verified_account_fans_and_preserves_other_entries(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        sibling = self.register_entry("sibling")
        disabled = self.register_entry("disabled", disabled_by=ConfigEntryDisabler.USER)
        missing = self.register_entry("missing")
        other_account = self.register_entry(
            "other", credentials=CREDS | {"username": "other@example.test"}
        )
        other_region = self.register_entry("region", credentials=CREDS | {"region": "us"})
        self.client.devices.return_value = tuple(
            replace(DEVICE, did=entry.data["device_id"])
            for entry in (self.entry, sibling, disabled, other_account, other_region)
        )
        flow = self.flow()
        flow.context = {"source": "reauth", "entry_id": self.entry.entry_id}
        new_credentials = CREDS | {"password": "updated-fixture"}
        listener = AsyncMock()
        self.entry.add_update_listener(listener)
        with (
            patch(
                "custom_components.dreame_mf10_flux.config_flow.FluxClient",
                return_value=self.client,
            ),
            patch.object(self.hass.config_entries, "async_schedule_reload") as reload,
            patch.object(
                self.hass.config_entries.flow,
                "async_progress_by_handler",
                return_value=[
                    {
                        "flow_id": "sibling-reauth",
                        "context": {"source": "reauth", "entry_id": sibling.entry_id},
                    },
                    {
                        "flow_id": "other-reauth",
                        "context": {"source": "reauth", "entry_id": other_account.entry_id},
                    },
                ],
            ),
            patch.object(self.hass.config_entries.flow, "async_abort") as abort,
        ):
            result = await flow.async_step_reauth_confirm(new_credentials)
            await self.hass.async_block_till_done()
        self.assertEqual(result["reason"], "reauth_successful")
        listener.assert_awaited_once_with(self.hass, self.entry)
        reload.assert_called_once_with(sibling.entry_id)
        abort.assert_called_once_with("sibling-reauth")
        for entry in (self.entry, sibling, disabled):
            self.assertEqual(entry.data["password"], "updated-fixture")
            self.assertEqual(entry.data["device_id"], entry.unique_id)
        self.assertEqual(sibling.options["poll_interval"], 45)
        self.assertEqual(disabled.disabled_by, ConfigEntryDisabler.USER)
        for entry in (missing, other_account, other_region):
            self.assertEqual(entry.data["password"], CREDS["password"])

    async def test_reauth_same_credentials_still_reloads_recovered_fans(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        flow = self.flow()
        flow.context = {"source": "reauth", "entry_id": self.entry.entry_id}
        with (
            patch(
                "custom_components.dreame_mf10_flux.config_flow.FluxClient",
                return_value=self.client,
            ),
            patch.object(self.hass.config_entries, "async_schedule_reload") as reload,
        ):
            result = await flow.async_step_reauth_confirm(CREDS)
        self.assertEqual(result["reason"], "reauth_successful")
        reload.assert_called_once_with(self.entry.entry_id)

    async def test_reauth_wrong_account_does_not_change_or_reload_entries(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        self.client.devices.return_value = (replace(DEVICE, did="unrelated"),)
        flow = self.flow()
        flow.context = {"source": "reauth", "entry_id": self.entry.entry_id}
        with (
            patch(
                "custom_components.dreame_mf10_flux.config_flow.FluxClient",
                return_value=self.client,
            ),
            patch.object(self.hass.config_entries, "async_schedule_reload") as reload,
        ):
            result = await flow.async_step_reauth_confirm(CREDS | {"password": "wrong-fixture"})
        self.assertEqual(result["errors"]["base"], "wrong_account")
        self.assertEqual(self.entry.data["password"], CREDS["password"])
        reload.assert_not_called()

    async def test_switching_reauth_account_does_not_overwrite_sibling_credentials(self):
        self.hass.config_entries._entries[self.entry.entry_id] = self.entry
        sibling = self.register_entry("sibling")
        self.client.devices.return_value = (DEVICE, replace(DEVICE, did="sibling"))
        flow = self.flow()
        flow.context = {"source": "reauth", "entry_id": self.entry.entry_id}
        with (
            patch(
                "custom_components.dreame_mf10_flux.config_flow.FluxClient",
                return_value=self.client,
            ),
            patch.object(self.hass.config_entries, "async_schedule_reload") as reload,
        ):
            await flow.async_step_reauth_confirm(CREDS | {"username": "different@example.test"})
        reload.assert_called_once_with(self.entry.entry_id)
        self.assertEqual(sibling.data["username"], CREDS["username"])

    async def test_options_store_valid_polling_interval(self):
        flow = FluxOptionsFlow()
        flow.hass = self.hass
        result = await flow.async_step_init({"poll_interval": 45})
        self.assertEqual(result["data"], {"poll_interval": 45})
