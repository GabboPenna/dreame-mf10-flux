"""Observed runtime and persistence tests. Copyright 2026 Gabriele Pennacchia."""

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.dreame_mf10_flux.sensor import FluxUsageSensor
from custom_components.dreame_mf10_flux.usage import FluxUsage


class UsageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.hass = HomeAssistant(self.directory.name)
        await self.hass.config.async_set_time_zone("Europe/Rome")
        self.usage = FluxUsage(self.hass, "fixture", 90)
        await self.usage.async_load()
        self.start = datetime(2026, 9, 22, 12, tzinfo=UTC)

    async def asyncTearDown(self):
        await self.usage.async_shutdown()
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def observe(self, power, seconds):
        self.usage.observe(power, now=self.start + timedelta(seconds=seconds), tick=seconds)

    async def test_counts_observed_on_intervals_and_not_stopped_intervals(self):
        self.observe(False, 0)
        self.observe(True, 30)
        self.observe(True, 60)
        self.observe(False, 90)
        self.observe(False, 120)
        self.assertEqual(self.usage.total_seconds, 60)
        self.assertEqual(self.usage.today_seconds, 60)

    async def test_gaps_offline_and_clock_jumps_do_not_invent_runtime(self):
        self.observe(True, 0)
        self.observe(True, 30)
        self.usage.unavailable()
        self.observe(True, 60)
        self.observe(True, 160)
        self.observe(None, 190)
        self.observe(True, 220)
        self.usage.observe(True, now=self.start + timedelta(hours=1), tick=250)
        self.assertEqual(self.usage.total_seconds, 30)

    async def test_daily_counter_splits_at_local_midnight(self):
        self.start = datetime(2026, 9, 22, 21, 59, 40, tzinfo=UTC)
        self.observe(True, 0)
        self.observe(True, 60)
        self.assertEqual(self.usage.total_seconds, 60)
        self.assertEqual(self.usage.today_seconds, 40)
        self.assertEqual(self.usage.day, "2026-09-23")

    async def test_daylight_saving_time_counts_elapsed_seconds_once(self):
        for start in (
            datetime(2026, 3, 29, 0, 59, 40, tzinfo=UTC),
            datetime(2026, 10, 25, 0, 59, 40, tzinfo=UTC),
        ):
            self.usage.unavailable()
            before = self.usage.total_seconds
            self.start = start
            self.observe(True, 0)
            self.observe(True, 60)
            self.assertEqual(self.usage.total_seconds - before, 60)
            self.assertEqual(self.usage.today_seconds, 60)

    async def test_midnight_resets_daily_total_during_cloud_outage(self):
        self.observe(True, 0)
        self.observe(True, 30)
        self.usage.unavailable()
        self.usage._midnight(datetime(2026, 9, 22, 22, tzinfo=UTC))
        self.assertEqual(self.usage.total_seconds, 30)
        self.assertEqual(self.usage.today_seconds, 0)
        self.assertEqual(self.usage.day, "2026-09-23")

    async def test_reload_restores_totals_without_counting_downtime(self):
        self.observe(True, 0)
        self.observe(True, 30)
        self.usage.day = self.usage._day(datetime.now(UTC))
        started = self.usage.started_at
        await self.usage.async_shutdown()
        self.usage = FluxUsage(self.hass, "fixture", 90)
        await self.usage.async_load()
        self.assertEqual(self.usage.total_seconds, 30)
        self.assertEqual(self.usage.today_seconds, 30)
        self.assertEqual(self.usage.started_at, started)
        self.observe(True, 6000)
        self.assertEqual(self.usage.total_seconds, 30)

    async def test_invalid_storage_values_and_previous_day_are_sanitized(self):
        await self.usage.store.async_save(
            {"total_seconds": -1, "today_seconds": float("inf"), "day": "2020-01-01"}
        )
        await self.usage.async_load()
        self.assertEqual(self.usage.total_seconds, 0)
        self.assertEqual(self.usage.today_seconds, 0)

    async def test_same_fan_state_updates_usage_listeners(self):
        listener = MagicMock()
        remove = self.usage.async_add_listener(listener)
        self.observe(True, 0)
        listener.reset_mock()
        self.observe(True, 30)
        listener.assert_called_once_with()
        remove()
        listener.reset_mock()
        self.observe(True, 60)
        listener.assert_not_called()

    async def test_usage_sensors_keep_saved_values_readable_during_outage(self):
        coordinator = MagicMock()
        coordinator.device.did = "fixture"
        coordinator.usage = self.usage
        coordinator.last_update_success = False
        self.observe(True, 0)
        self.observe(True, 60)
        sensor = FluxUsageSensor(coordinator, "operating_hours", daily=False)
        self.assertTrue(sensor.available)
        self.assertAlmostEqual(sensor.native_value, 1 / 60)
