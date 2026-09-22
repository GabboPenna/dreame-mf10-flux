"""Bounded asynchronous cloud transport. Copyright 2026 Gabriele Pennacchia."""

import asyncio
import hashlib
import itertools
import json
import re
from collections.abc import Mapping
from time import monotonic
from typing import Any

import aiohttp

from .errors import AuthenticationError, CloudError, CommandError, RateLimited, Unavailable
from .models import MODEL, Device, FanState, Oscillation, Property, oscillation_writes

# Public mobile-client protocol identifiers; these are not account credentials.
APP_AUTH = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
PASSWORD_SUFFIX = "RAylYC%fmSKp7%Tq"
USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
REGIONS = ("eu", "us", "cn", "sg", "ru", "kr", "ca")
TIMEOUT = aiohttp.ClientTimeout(total=15, connect=8)
WRITABLE = {
    Property.MODE: {0, 1, 2, 3, 7},
    Property.SPEED: set(range(1, 11)),
    Property.ROTATION: {0, 1},
    Property.CHILD_LOCK: {0, 1},
    Property.BLADES: {0, 1, 2, 3},
    Property.SYNC: {0, 1},
    Property.STAGGERED: {0, 1},
}


class FluxClient:
    """One account session, shared between devices and entity platforms."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str, region: str
    ) -> None:
        if region not in REGIONS:
            raise ValueError("Unsupported cloud region")
        self._session = session
        self._username = username.strip()
        self._password = password
        self.region = region
        self._base = f"https://{'us' if region == 'ca' else region}.iot.dreame.tech:13267"
        self._access = ""
        self._refresh = ""
        self._tenant = "000000"
        self._expires = 0.0
        self._pause_until = 0.0
        self._auth_lock = asyncio.Lock()
        self._devices_lock = asyncio.Lock()
        self._devices: tuple[Device, ...] = ()
        self._devices_until = 0.0
        self._sequence = itertools.count(1)
        self.requests = 0

    def _headers(self, authenticated: bool) -> dict[str, str]:
        headers = {
            "Authorization": APP_AUTH,
            "User-Agent": USER_AGENT,
            "Tenant-Id": self._tenant,
            "Accept": "application/json",
        }
        if authenticated:
            headers["Dreame-Auth"] = self._access
        if self.region == "cn":
            headers["Dreame-Rlc"] = "1c80b3787b2266776bcd"
        return headers

    async def _request(
        self, path: str, *, data: dict[str, Any], form: bool = False, authenticated: bool = True
    ) -> dict[str, Any]:
        if (remaining := self._pause_until - monotonic()) > 0:
            raise RateLimited(remaining)
        self.requests += 1
        try:
            async with self._session.post(
                self._base + path,
                headers=self._headers(authenticated),
                **({"data": data} if form else {"json": data}),
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as response:
                if response.status == 429:
                    try:
                        delay = max(1, min(3600, float(response.headers.get("Retry-After", "60"))))
                    except ValueError:
                        delay = 60
                    self._pause_until = monotonic() + delay
                    raise RateLimited(delay)
                if response.status in (401, 403):
                    raise AuthenticationError("Cloud authentication was rejected")
                if response.status >= 500:
                    raise Unavailable("The cloud service is temporarily unavailable")
                if response.status != 200:
                    if form and response.status == 400:
                        raise AuthenticationError("Cloud authentication was rejected")
                    raise CloudError(f"Cloud request failed (HTTP {response.status})")
                result = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise Unavailable("The cloud request could not be completed") from err
        except (ValueError, UnicodeError) as err:
            raise CloudError("The cloud returned an invalid response") from err
        if not isinstance(result, dict):
            raise CloudError("The cloud returned an invalid response")
        return result

    async def authenticate(self, rejected_token: str | None = None) -> None:
        """Renew once across simultaneous polls, including a rejected old token."""
        async with self._auth_lock:
            if self._access and monotonic() < self._expires:
                if rejected_token is None or rejected_token != self._access:
                    return
            common = {"platform": "IOS", "scope": "all"}
            if self._refresh:
                try:
                    result = await self._request(
                        "/dreame-auth/oauth/token",
                        form=True,
                        authenticated=False,
                        data=common
                        | {"grant_type": "refresh_token", "refresh_token": self._refresh},
                    )
                    if result.get("access_token"):
                        self._accept_token(result)
                        return
                except AuthenticationError:
                    pass
            password = hashlib.md5(
                (self._password + PASSWORD_SUFFIX).encode(), usedforsecurity=False
            ).hexdigest()
            result = await self._request(
                "/dreame-auth/oauth/token",
                form=True,
                authenticated=False,
                data=common
                | {
                    "grant_type": "password",
                    "type": "account",
                    "username": self._username,
                    "password": password,
                },
            )
            if not result.get("access_token"):
                raise AuthenticationError("The account credentials were not accepted")
            self._accept_token(result)

    def _accept_token(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload.get("access_token"), str):
            raise AuthenticationError("The cloud did not issue an access token")
        try:
            lifetime = max(30, int(payload.get("expires_in", 3600)))
        except (TypeError, ValueError) as err:
            raise CloudError("The cloud returned an invalid token lifetime") from err
        self._access = payload["access_token"]
        self._refresh = payload.get("refresh_token") or self._refresh
        self._tenant = payload.get("tenant_id") or "000000"
        self._expires = monotonic() + lifetime - min(120, lifetime / 4)

    async def _api(self, path: str, data: dict[str, Any], *, read: bool) -> dict[str, Any]:
        await self.authenticate()
        token = self._access
        for attempt in range(2):
            try:
                result = await self._request(path, data=data)
                if result.get("code") in (401, 403):
                    raise AuthenticationError("The cloud session has expired")
                if result.get("code") not in (0, "0"):
                    raise CloudError("The cloud rejected the request")
                return result
            except AuthenticationError:
                if attempt:
                    raise
                await self.authenticate(rejected_token=token)
            except RateLimited:
                raise
            except Unavailable:
                if attempt or not read:
                    raise
                await asyncio.sleep(1)
        raise CloudError("The cloud request could not be completed")

    async def devices(self, *, force: bool = False) -> tuple[Device, ...]:
        """Cache binding status for at most one minute across fan entries."""
        async with self._devices_lock:
            if not force and monotonic() < self._devices_until:
                return self._devices
            result = await self._api("/dreame-user-iot/iotuserbind/device/listV2", {}, read=True)
            try:
                rows = result["data"]["page"]["records"]
                if not isinstance(rows, list):
                    raise TypeError
                devices = tuple(
                    Device.parse(row)
                    for row in rows
                    if isinstance(row, dict) and row.get("model") == MODEL
                )
            except (KeyError, TypeError, ValueError) as err:
                raise CloudError("The cloud returned an invalid device list") from err
            self._devices, self._devices_until = devices, monotonic() + 60
            return devices

    async def device(self, did: str, *, force: bool = False) -> Device:
        for device in await self.devices(force=force):
            if device.did == did:
                return device
        raise CloudError("The selected fan is no longer linked to this account")

    async def _rpc(self, device: Device, method: str, params: Any, *, read: bool) -> Any:
        # The binding contains a broker address; only its numeric shard enters a URL.
        shard = device.routing.split(".", 1)[0] if device.routing else ""
        if shard and not re.fullmatch(r"\d{1,10}", shard):
            raise CloudError("The cloud returned an unsupported routing identifier")
        suffix = f"-{shard}" if shard else ""
        sequence = next(self._sequence)
        envelope = await self._api(
            f"/dreame-iot-com{suffix}/device/sendCommand",
            {
                "did": device.did,
                "id": sequence,
                "data": {"did": device.did, "id": sequence, "method": method, "params": params},
            },
            read=read,
        )
        payload = envelope.get("data")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError as err:
                raise CloudError("The cloud returned an invalid command response") from err
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        raise CloudError("The cloud did not return a command result")

    async def snapshot(self, did: str) -> tuple[Device, FanState]:
        device = await self.device(did)
        if device.online is False:
            return device, FanState(online=False)
        rows = await self._rpc(
            device, "get_properties", [prop.request(did) for prop in Property], read=True
        )
        if not isinstance(rows, list):
            raise CloudError("The cloud returned an invalid property list")
        return device, FanState.parse(rows, device.online)

    async def write(self, device: Device, properties: Mapping[Property, int]) -> None:
        """Only known writable properties; uncertain writes are never replayed."""
        if not properties:
            return
        if any(
            isinstance(value, bool) or prop not in WRITABLE or value not in WRITABLE[prop]
            for prop, value in properties.items()
        ):
            raise ValueError("Unsupported MF10 property value")
        result = await self._rpc(
            device,
            "set_properties",
            [prop.request(device.did, value) for prop, value in properties.items()],
            read=False,
        )
        if not isinstance(result, list):
            raise CommandError("The cloud did not confirm the property command")
        confirmed = {
            (row.get("siid"), row.get("piid"))
            for row in result
            if isinstance(row, dict) and row.get("code") == 0
        }
        if any(prop.value not in confirmed for prop in properties):
            raise CommandError("The cloud did not confirm every property command")

    async def oscillate(self, device: Device, value: Oscillation) -> None:
        """Apply blade movement before its dependent synchronization flag.

        Firmware 1047 resets synchronization when blade movement is written.
        A combined batch can acknowledge both writes but lose the selected flag.
        """
        desired = oscillation_writes(value)
        await self.write(
            device,
            {Property.BLADES: desired[Property.BLADES], Property.SYNC: 0, Property.STAGGERED: 0},
        )
        flags = {
            prop: desired[prop] for prop in (Property.SYNC, Property.STAGGERED) if desired[prop]
        }
        if flags:
            await self.write(device, flags)

    async def power(self, device: Device, on: bool) -> None:
        """A fixed power action with mandatory input; no generic action interface."""
        if not isinstance(on, bool):
            raise ValueError("Power must be a boolean")
        result = await self._rpc(
            device,
            "action",
            {"did": device.did, "siid": 2, "aiid": 1, "in": [{"piid": 1, "value": int(on)}]},
            read=False,
        )
        if not isinstance(result, dict) or result.get("code") != 0:
            raise CommandError("The cloud did not confirm the power command")
