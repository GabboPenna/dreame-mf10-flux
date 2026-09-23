"""Exercise importable automations in Home Assistant. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from homeassistant import loader
from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import trigger
from homeassistant.helpers.script import Script
from homeassistant.helpers.script_variables import ScriptVariables
from homeassistant.util.yaml import load_yaml

ROOT = Path(__file__).resolve().parents[1] / "blueprints/automation"
INPUTS = {
    "fan": "fan.fixture",
    "temperature": "sensor.room",
    "enabled": "input_boolean.auto_speed",
    "presence": "binary_sensor.presence",
}


class BlueprintTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        loader.async_setup(self.hass)
        await trigger.async_setup(self.hass)
        self.calls = []
        self.scripts = []

        async def service(call):
            self.calls.append((call.service, dict(call.data)))
            if call.service == "set_percentage":
                self.fan(percentage=call.data["percentage"])
            else:
                self.fan("off")

        self.hass.services.async_register("fan", "set_percentage", service)
        self.hass.services.async_register("fan", "turn_off", service)
        self.fan()
        self.hass.states.async_set("input_boolean.auto_speed", "on")
        self.hass.states.async_set("binary_sensor.presence", "off")
        self.hass.states.async_set("sensor.room", "27", {"unit_of_measurement": "°C"})

    def fan(self, state="on", percentage=30, preset="manual"):
        self.hass.states.async_set(
            "fan.fixture", state, {"percentage": percentage, "preset_mode": preset}
        )

    async def asyncTearDown(self):
        for script in self.scripts:
            await script.async_stop()
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def config(self, name, **overrides):
        blueprint = Blueprint(
            load_yaml(str(ROOT / f"{name}.yaml")),
            expected_domain="automation",
            schema=BLUEPRINT_SCHEMA,
        )
        inputs = {key: value for key, value in INPUTS.items() if key in blueprint.inputs}
        resolved = BlueprintInputs(blueprint, {"use_blueprint": {"input": inputs | overrides}})
        resolved.validate()
        self.assertIsNone(blueprint.validate())
        return resolved.async_substitute()

    async def script(self, name, **overrides):
        config = await async_validate_config_item(
            self.hass, "automation", self.config(name, **overrides)
        )
        self.assertIsNotNone(config)
        script = Script(
            self.hass,
            [*config["conditions"], *config["actions"]],
            name,
            "automation",
            variables=config["variables"]
            if isinstance(config["variables"], ScriptVariables)
            else ScriptVariables(config["variables"]),
        )
        self.scripts.append(script)
        return script

    async def test_all_blueprints_validate_as_real_automations(self):
        for path in ROOT.glob("*.yaml"):
            with self.subTest(blueprint=path.name):
                await self.script(path.stem)

    async def test_temperature_maps_celsius_and_fahrenheit_to_physical_speed(self):
        script = await self.script("temperature_speed")
        await script.async_run(context=Context())
        self.assertEqual(self.calls[-1][1]["percentage"], 60)
        self.calls.clear()
        await script.async_run(context=Context())
        self.assertEqual(self.calls, [], "No redundant cloud commands for unchanged speed")
        self.fan()
        self.hass.states.async_set("sensor.room", "80.6", {"unit_of_measurement": "°F"})
        await script.async_run(context=Context())
        self.assertEqual(self.calls[-1][1]["percentage"], 60)

    async def test_temperature_never_starts_stopped_fan_or_uses_missing_sensor(self):
        script = await self.script("temperature_speed")
        self.fan("off")
        await script.async_run(context=Context())
        self.fan()
        self.hass.states.async_set("sensor.room", "unavailable")
        await script.async_run(context=Context())
        self.hass.states.async_set("sensor.room", "30", {"unit_of_measurement": "°C"})
        self.hass.states.async_set("input_boolean.auto_speed", "off")
        await script.async_run(context=Context())
        self.assertEqual(self.calls, [])

    async def test_absence_switches_off_after_uninterrupted_wait(self):
        script = await self.script("absence_off", absence_minutes=0.001)
        await script.async_run(context=Context())
        self.assertEqual([call[0] for call in self.calls], ["turn_off"])

    async def test_return_or_unavailable_presence_cancels_absence_wait(self):
        for value in ("on", "unavailable"):
            self.hass.states.async_set("binary_sensor.presence", "off")
            script = await self.script("absence_off", absence_minutes=1)
            task = asyncio.create_task(script.async_run(context=Context()))
            await asyncio.sleep(0.01)
            self.hass.states.async_set("binary_sensor.presence", value)
            await asyncio.wait_for(task, 2)
        self.assertEqual(self.calls, [])

    async def test_night_fade_steps_then_optionally_switches_off(self):
        script = await self.script("night_fade", interval_minutes=0.001, switch_off=True)
        await script.async_run(context=Context())
        self.assertEqual(
            [call[0] for call in self.calls], ["set_percentage", "set_percentage", "turn_off"]
        )
        self.assertEqual([call[1]["percentage"] for call in self.calls[:2]], [20, 10])

    async def test_night_fade_stops_on_manual_speed_change_or_power_off(self):
        for state, percentage in (("on", 70), ("off", 30)):
            self.fan()
            script = await self.script("night_fade", interval_minutes=1, switch_off=True)
            task = asyncio.create_task(script.async_run(context=Context()))
            await asyncio.sleep(0.01)
            self.fan(state, percentage)
            await asyncio.wait_for(task, 2)
        self.assertEqual(self.calls, [])
