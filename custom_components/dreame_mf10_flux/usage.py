"""Observed running hours with persistent totals. Copyright 2026 Gabriele Pennacchia."""

from collections.abc import Callable
from datetime import UTC, datetime, time
from math import isfinite
from time import monotonic
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store

from .const import DOMAIN


class FluxUsage:
    """Estimate runtime between observations; never extrapolate across missing data."""

    def __init__(self, hass: HomeAssistant, entry_id: str, max_gap: float) -> None:
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}.{entry_id}.usage")
        self.max_gap = max_gap
        self.total_seconds = 0.0
        self.today_seconds = 0.0
        self.day = self._day(datetime.now(UTC))
        self.started_at: str | None = None
        self.loaded = False
        self._previous: tuple[datetime, float, bool] | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._unsub_midnight: Callable[[], None] | None = None

    def _day(self, now: datetime) -> str:
        return now.astimezone(ZoneInfo(self.hass.config.time_zone)).date().isoformat()

    async def async_load(self) -> None:
        data = await self.store.async_load()
        if isinstance(data, dict):
            self.total_seconds = self._seconds(data.get("total_seconds"))
            if data.get("day") == self.day:
                self.today_seconds = min(
                    self.total_seconds, self._seconds(data.get("today_seconds"))
                )
            if isinstance(data.get("started_at"), str):
                try:
                    started = datetime.fromisoformat(data["started_at"])
                    if started.tzinfo is not None:
                        self.started_at = started.isoformat()
                except ValueError:
                    pass
        self.loaded = True
        if self._unsub_midnight is None:
            self._unsub_midnight = async_track_time_change(
                self.hass, self._midnight, hour=0, minute=0, second=0
            )

    @callback
    def _midnight(self, now: datetime) -> None:
        """Reset the daily total even when the cloud remains unreachable."""
        day = self._day(now)
        if day != self.day:
            self.day, self.today_seconds = day, 0.0
            self._changed()

    @callback
    def _changed(self) -> None:
        if self.loaded:
            self.store.async_delay_save(self._data, 10)
        for listener in tuple(self._listeners):
            listener()

    @staticmethod
    def _seconds(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        return float(value) if isfinite(value) and value >= 0 else 0.0

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    @callback
    def unavailable(self) -> None:
        """Discard the open interval when a poll fails or the device is unreachable."""
        self._previous = None

    @callback
    def observe(
        self, power: bool | None, *, now: datetime | None = None, tick: float | None = None
    ) -> None:
        now = now or datetime.now(UTC)
        tick = monotonic() if tick is None else tick
        day = self._day(now)
        before = (self.total_seconds, self.today_seconds, self.day, self.started_at)
        if day != self.day:
            self.day, self.today_seconds = day, 0.0
        if self.started_at is None and power is not None:
            self.started_at = now.isoformat()
        if self._previous is not None and power is not None:
            previous_at, previous_tick, was_on = self._previous
            elapsed = tick - previous_tick
            wall_elapsed = (now - previous_at).total_seconds()
            if was_on and 0 <= elapsed <= self.max_gap and abs(wall_elapsed - elapsed) < 2:
                self.total_seconds += elapsed
                midnight = datetime.combine(
                    now.astimezone(ZoneInfo(self.hass.config.time_zone)).date(),
                    time.min,
                    ZoneInfo(self.hass.config.time_zone),
                ).astimezone(UTC)
                self.today_seconds += min(
                    elapsed, max(0, (now - max(previous_at, midnight)).total_seconds())
                )
        self._previous = (now, tick, power) if power is not None else None
        if before != (self.total_seconds, self.today_seconds, self.day, self.started_at):
            self._changed()

    @callback
    def _data(self) -> dict:
        return {
            "total_seconds": self.total_seconds,
            "today_seconds": self.today_seconds,
            "day": self.day,
            "started_at": self.started_at,
        }

    async def async_shutdown(self) -> None:
        self.unavailable()
        if self._unsub_midnight is not None:
            self._unsub_midnight()
            self._unsub_midnight = None
        if self.loaded:
            await self.store.async_save(self._data())
            self.loaded = False
