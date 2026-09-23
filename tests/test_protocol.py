"""HTTP contract and concurrency tests. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import unittest
from time import monotonic
from unittest.mock import AsyncMock, patch

import aiohttp
import support  # noqa: F401
from aiohttp import web
from mf10_flux import (
    AuthenticationError,
    CloudError,
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
from mf10_flux.models import oscillation_writes, speed_from_percentage

RAW_DEVICE = {
    "did": "fixture-fan",
    "model": "dreame.fan.u2519",
    "customName": "Test fan",
    "ver": "1.8.30_1047",
    "bindDomain": "10000.mt.eu.iot.dreame.tech:19973",
    "online": True,
}
VALUES = {
    Property.POWER: 1,
    Property.SPEED: 3,
    Property.MODE: 0,
    Property.ROTATION: 1,
    Property.BLADES: 3,
    Property.SYNC: 0,
    Property.STAGGERED: 1,
    Property.TEMPERATURE: 28,
    Property.CHILD_LOCK: 0,
    Property.DISPLAY: 1,
    Property.OFF_TIMER: 0,
}


def rows():
    return [
        {"siid": prop.value[0], "piid": prop.value[1], "code": 0, "value": value}
        for prop, value in VALUES.items()
    ]


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.auth_count = 0
        self.invalid_auth = False
        self.reject_token = False
        self.failure = None
        self.command_result = None
        self.emulate_firmware = False
        self.properties = dict(VALUES)
        self.device_rows = [dict(RAW_DEVICE)]
        app = web.Application()
        app.router.add_post("/{path:.*}", self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.session = aiohttp.ClientSession()
        self.client = FluxClient(self.session, "a+b&c@example.test", "fixture-password", "eu")
        self.client._base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}"

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def handle(self, request):
        auth = request.path.endswith("/oauth/token")
        data = dict(await request.post()) if auth else await request.json()
        self.calls.append((request.path, data, dict(request.headers)))
        if auth:
            self.auth_count += 1
            await asyncio.sleep(0.01)
            if self.invalid_auth:
                return web.json_response({"error": "invalid_grant"}, status=400)
            return web.json_response(
                {
                    "access_token": f"fixture-access-{self.auth_count}",
                    "refresh_token": "fixture+refresh&=",
                    "expires_in": 3600,
                }
            )
        if self.reject_token and request.headers.get("Dreame-Auth") == "fixture-access-1":
            return web.json_response({}, status=401)
        if self.failure:
            status, headers = self.failure
            return web.json_response({"secret": "must-not-leak"}, status=status, headers=headers)
        if request.path.endswith("/listV2"):
            return web.json_response({"code": 0, "data": {"page": {"records": self.device_rows}}})
        if request.path == "/fixture":
            return web.json_response({"code": 0, "data": {}})
        method = data["data"]["method"]
        if self.command_result is not None:
            result = self.command_result
        elif method == "get_properties":
            result = (
                [
                    {"siid": prop.value[0], "piid": prop.value[1], "code": 0, "value": value}
                    for prop, value in self.properties.items()
                ]
                if self.emulate_firmware
                else rows()
            )
        elif method == "set_properties":
            if self.emulate_firmware:
                for item in data["data"]["params"]:
                    prop = Property((item["siid"], item["piid"]))
                    self.properties[prop] = item["value"]
                    if prop == Property.BLADES:
                        self.properties[Property.SYNC] = 0
                        self.properties[Property.STAGGERED] = 0
            result = [
                {"siid": p["siid"], "piid": p["piid"], "code": 0} for p in data["data"]["params"]
            ]
        else:
            result = {"code": 0}
        return web.json_response({"code": 0, "data": {"result": result}})

    async def test_snapshot_batches_all_properties_and_checks_binding(self):
        device, state = await self.client.snapshot("fixture-fan")
        self.assertEqual(device.firmware, "1.8.30_1047")
        self.assertEqual(state.oscillation, Oscillation.STAGGERED)
        self.assertTrue(state.online)
        self.assertEqual(len(self.calls), 3)
        rpc = self.calls[-1]
        self.assertIn("dreame-iot-com-10000", rpc[0])
        self.assertEqual(len(rpc[1]["data"]["params"]), 11)
        await self.client.snapshot("fixture-fan")
        self.assertEqual(len(self.calls), 4, "Tokens and binding metadata should be reused")

    async def test_optional_controls_round_trip_without_power_actions(self):
        self.emulate_firmware = True
        device = await self.client.device("fixture-fan")
        for hours in (0, 1, 8):
            await self.client.write(device, {Property.DISPLAY: 0, Property.OFF_TIMER: hours})
            _, state = await self.client.snapshot(device.did)
            self.assertFalse(state.display)
            self.assertEqual(state.off_timer, hours)
        self.assertFalse(
            any(data.get("data", {}).get("method") == "action" for _, data, _ in self.calls)
        )

    async def test_unsupported_optional_fields_do_not_break_core_state(self):
        core_rows = [row for row in rows() if (row["siid"], row["piid"]) not in ((6, 8), (6, 12))]
        self.client._rpc = AsyncMock(side_effect=[CloudError("Unsupported"), core_rows, core_rows])
        _, state = await self.client.snapshot("fixture-fan")
        self.assertTrue(state.power)
        self.assertIsNone(state.display)
        self.assertIsNone(state.off_timer)
        await self.client.snapshot("fixture-fan")
        self.assertEqual(
            [len(call.args[2]) for call in self.client._rpc.call_args_list], [11, 9, 9]
        )
        self.device_rows[0]["ver"] = "1.8.30_1048"
        self.client._devices_until = 0
        self.client._rpc.side_effect = [rows()]
        _, state = await self.client.snapshot("fixture-fan")
        self.assertTrue(state.display)
        self.assertEqual(len(self.client._rpc.call_args.args[2]), 11)

    async def test_optional_probe_does_not_retry_auth_rate_limits_or_transport_errors(self):
        for error in (AuthenticationError("Expired"), RateLimited(60), Unavailable("Timeout")):
            self.client._rpc = AsyncMock(side_effect=error)
            with self.assertRaises(type(error)):
                await self.client.snapshot("fixture-fan")
            self.client._rpc.assert_awaited_once()

    async def test_reserved_characters_are_form_encoded(self):
        await self.client.authenticate()
        form = self.calls[0][1]
        self.assertEqual(form["username"], "a+b&c@example.test")
        self.assertEqual(form["grant_type"], "password")
        self.assertNotEqual(form["password"], "fixture-password")
        self.client._expires = 0
        await self.client.authenticate()
        self.assertEqual(self.calls[-1][1]["refresh_token"], "fixture+refresh&=")

    async def test_concurrent_login_is_single_flight(self):
        await asyncio.gather(*(self.client.authenticate() for _ in range(8)))
        self.assertEqual(self.auth_count, 1)

    async def test_concurrent_401_recovery_renews_only_once(self):
        await self.client.authenticate()
        self.reject_token = True
        await asyncio.gather(*(self.client._api("/fixture", {}, read=True) for _ in range(6)))
        self.assertEqual(self.auth_count, 2)

    async def test_concurrent_discovery_is_shared(self):
        await asyncio.gather(*(self.client.devices() for _ in range(5)))
        self.assertEqual(sum(path.endswith("/listV2") for path, _, _ in self.calls), 1)

    async def test_oscillation_survives_firmware_reset_of_dependent_flags(self):
        self.emulate_firmware = True
        device = await self.client.device("fixture-fan")
        for value in Oscillation:
            with self.subTest(value=value):
                await self.client.oscillate(device, value)
                _, state = await self.client.snapshot(device.did)
                self.assertEqual(state.oscillation, value)

    async def test_invalid_credentials_are_recoverable_and_safe(self):
        self.invalid_auth = True
        with self.assertRaises(AuthenticationError) as failure:
            await self.client.authenticate()
        self.assertNotIn("fixture-password", str(failure.exception))
        self.assertNotIn("a+b", str(failure.exception))

    async def test_rate_limit_is_shared_and_not_retried_early(self):
        await self.client.authenticate()
        self.failure = (429, {"Retry-After": "120"})
        with self.assertRaises(RateLimited) as failure:
            await self.client.devices()
        self.assertEqual(failure.exception.retry_after, 120)
        count = len(self.calls)
        with self.assertRaises(RateLimited):
            await self.client.devices()
        self.assertEqual(len(self.calls), count)

    async def test_server_error_response_never_exposes_body(self):
        await self.client.authenticate()
        self.failure = (500, {})
        with patch("mf10_flux.client.asyncio.sleep", return_value=None):
            with self.assertRaises(Unavailable) as failure:
                await self.client.devices()
        self.assertNotIn("must-not-leak", str(failure.exception))
        self.assertEqual(len(self.calls), 3, "A read has at most one retry")

    async def test_write_is_not_replayed_after_uncertain_failure(self):
        device = (await self.client.devices())[0]
        self.failure = (503, {})
        count = len(self.calls)
        with self.assertRaises(Unavailable):
            await self.client.write(device, {Property.CHILD_LOCK: 1})
        self.assertEqual(len(self.calls), count + 1)

    async def test_offline_binding_prevents_cached_property_state(self):
        self.device_rows[0]["online"] = False
        _, state = await self.client.snapshot("fixture-fan")
        self.assertIs(state.online, False)
        self.assertIsNone(state.power)
        self.assertEqual(len(self.calls), 2)

    async def test_binding_status_refreshes_after_cache_expiry(self):
        await self.client.snapshot("fixture-fan")
        self.device_rows[0]["online"] = False
        self.client._devices_until = monotonic() - 1
        _, state = await self.client.snapshot("fixture-fan")
        self.assertIs(state.online, False)

    async def test_other_models_are_not_exposed(self):
        self.device_rows.append({"did": "other", "model": "unsupported.fan"})
        self.assertEqual(len(await self.client.devices()), 1)

    async def test_missing_device_is_not_silently_replaced(self):
        with self.assertRaises(CloudError):
            await self.client.device("different-fan")

    async def test_power_input_is_always_nonempty(self):
        device = (await self.client.devices())[0]
        for on in (True, False):
            await self.client.power(device, on)
            payload = self.calls[-1][1]["data"]["params"]
            self.assertEqual(payload["aiid"], 1)
            self.assertEqual(payload["siid"], 2)
            self.assertEqual(payload["in"], [{"piid": 1, "value": int(on)}])

    async def test_unconfirmed_writes_raise(self):
        device = (await self.client.devices())[0]
        self.command_result = [{"siid": 6, "piid": 10, "code": 80001}]
        with self.assertRaises(CommandError):
            await self.client.write(device, {Property.CHILD_LOCK: 1})

    async def test_missing_write_acknowledgement_is_failure(self):
        device = (await self.client.devices())[0]
        self.command_result = [{"siid": 2, "piid": 3, "code": 0}]
        with self.assertRaises(CommandError):
            await self.client.write(device, {Property.MODE: 3, Property.SPEED: 4})

    async def test_dangerous_properties_and_invalid_values_cannot_be_sent(self):
        device = (await self.client.devices())[0]
        count = len(self.calls)
        for properties in (
            {Property.POWER: 1},
            {Property.SPEED: 13},
            {Property.MODE: 6},
            {Property.TEMPERATURE: 99},
            {Property.CHILD_LOCK: True},
            {Property.DISPLAY: 2},
            {Property.OFF_TIMER: 9},
            {Property.OFF_TIMER: 1.5},
            {Property.OFF_TIMER: True},
        ):
            with self.assertRaises(ValueError):
                await self.client.write(device, properties)
        with self.assertRaises(ValueError):
            await self.client.power(device, None)
        self.assertEqual(len(self.calls), count)


class StateTests(unittest.TestCase):
    def test_property_order_and_unknown_rows_do_not_change_state(self):
        source = rows()
        source.reverse()
        source.append({"siid": 4, "piid": 2, "code": 0, "value": 999})
        state = FanState.parse(source, True)
        self.assertEqual(state.speed, 3)
        self.assertEqual(state.mode, Mode.AI)

    def test_missing_properties_do_not_reuse_previous_values(self):
        state = FanState.parse([rows()[0]], True)
        self.assertTrue(state.power)
        self.assertIsNone(state.temperature)
        self.assertIsNone(state.speed)

    def test_missing_or_corrupt_power_fails_the_snapshot(self):
        for value in (None, "1", True, 0, 3):
            with self.assertRaises(CloudError):
                FanState.parse([{"siid": 2, "piid": 1, "code": 0, "value": value}], True)

    def test_mutually_exclusive_oscillation_flags(self):
        for choice in Oscillation:
            changes = oscillation_writes(choice)
            self.assertFalse(changes[Property.SYNC] and changes[Property.STAGGERED])
            self.assertEqual(
                changes[Property.BLADES] == 3,
                choice in (Oscillation.BOTH, Oscillation.SYNC, Oscillation.STAGGERED),
            )

    def test_percentage_boundaries(self):
        self.assertEqual(
            [speed_from_percentage(p) for p in (0, 1, 10, 11, 50, 100)], [0, 1, 1, 2, 5, 10]
        )
        for value in (-1, 101, True):
            with self.assertRaises(ValueError):
                speed_from_percentage(value)

    def test_unknown_online_status_is_not_claimed_online(self):
        for value in (None, "online", "0", 2):
            self.assertIsNone(Device.parse(RAW_DEVICE | {"online": value}).online)

    def test_private_identity_is_not_in_object_repr(self):
        self.assertNotIn("fixture-fan", repr(Device.parse(RAW_DEVICE)))


if __name__ == "__main__":
    unittest.main()
