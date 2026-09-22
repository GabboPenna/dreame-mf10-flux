"""MF10 wire values and immutable state. Copyright 2026 Gabriele Pennacchia."""

from dataclasses import dataclass, field
from enum import Enum, IntEnum, StrEnum
from math import ceil
from typing import Any

from .errors import CloudError

MODEL = "dreame.fan.u2519"


class Mode(IntEnum):
    """Modes reported by the MF10."""

    AI = 0
    POWERFUL = 1
    NIGHT = 2
    MANUAL = 3
    NATURAL = 7


class Oscillation(StrEnum):
    """Stable, language-independent automation values."""

    OFF = "off"
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"
    SYNC = "both_sync"
    STAGGERED = "both_staggered"


class Property(Enum):
    """Known MF10 properties for firmware 1043 and later."""

    POWER = (2, 1)
    MODE = (2, 3)
    SPEED = (2, 4)
    ROTATION = (2, 7)
    BLADES = (2, 8)
    SYNC = (2, 9)
    STAGGERED = (2, 12)
    TEMPERATURE = (3, 2)
    CHILD_LOCK = (6, 10)

    def request(self, did: str, value: int | None = None) -> dict[str, Any]:
        """Build a read or write item."""
        result = {"did": did, "siid": self.value[0], "piid": self.value[1]}
        if value is not None:
            result["value"] = value
        return result


@dataclass(frozen=True, slots=True)
class Device:
    """Only the binding metadata needed to operate the fan."""

    did: str = field(repr=False)
    name: str
    model: str
    firmware: str
    online: bool | None
    routing: str = field(repr=False, default="")
    mac: str = field(repr=False, default="")

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> "Device":
        """Validate a cloud binding without guessing connectivity."""
        online = raw.get("online")
        if online not in (True, False, 0, 1):
            online = None
        return cls(
            did=str(raw["did"]),
            name=raw.get("customName") or "Dreame MF10 Flux",
            model=str(raw.get("model", "")),
            firmware=str(raw.get("ver") or ""),
            online=bool(online) if online is not None else None,
            routing=str(raw.get("bindDomain") or ""),
            mac=str(raw.get("mac") or ""),
        )


def bounded_int(value: Any, low: int, high: int) -> int | None:
    """Reject malformed, non-integral, or out-of-range property values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if low <= value <= high and int(value) == value:
        return int(value)
    return None


def speed_from_percentage(percentage: int) -> int:
    """Map a Home Assistant percentage to one of ten physical levels."""
    if isinstance(percentage, bool) or not 0 <= percentage <= 100:
        raise ValueError("Percentage must be between 0 and 100")
    return ceil(percentage / 10)


def oscillation_writes(value: Oscillation) -> dict[Property, int]:
    """Disable mutually exclusive flags before applying blade movement."""
    blades = {Oscillation.OFF: 0, Oscillation.LEFT: 1, Oscillation.RIGHT: 2}.get(value, 3)
    return {
        Property.SYNC: int(value == Oscillation.SYNC),
        Property.STAGGERED: int(value == Oscillation.STAGGERED),
        Property.BLADES: blades,
    }


@dataclass(frozen=True, slots=True)
class FanState:
    """A complete snapshot; missing values never carry over from an older poll."""

    online: bool | None
    power: bool | None = None
    speed: int | None = None
    mode: Mode | None = None
    rotation: bool | None = None
    child_lock: bool | None = None
    oscillation: Oscillation | None = None
    temperature: float | None = None

    @classmethod
    def parse(cls, rows: list[dict[str, Any]], online: bool | None) -> "FanState":
        """Match returned identifiers, never the response order."""
        properties: dict[Property, Any] = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("code") != 0:
                continue
            try:
                key = Property((row.get("siid"), row.get("piid")))
            except ValueError:
                continue
            properties[key] = row.get("value")
        power = bounded_int(properties.get(Property.POWER), 1, 2)
        if power is None:
            raise CloudError("The cloud did not return a valid power state")
        mode = bounded_int(properties.get(Property.MODE), 0, 7)
        blades = bounded_int(properties.get(Property.BLADES), 0, 3)
        sync = bounded_int(properties.get(Property.SYNC), 0, 1)
        staggered = bounded_int(properties.get(Property.STAGGERED), 0, 1)
        oscillation = None
        if blades is not None:
            if blades < 3:
                oscillation = (Oscillation.OFF, Oscillation.LEFT, Oscillation.RIGHT)[blades]
            elif sync is not None and staggered is not None and not (sync and staggered):
                oscillation = (
                    Oscillation.SYNC
                    if sync
                    else (Oscillation.STAGGERED if staggered else Oscillation.BOTH)
                )
        temperature = properties.get(Property.TEMPERATURE)
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not -40 <= temperature <= 100
        ):
            temperature = None
        rotation = bounded_int(properties.get(Property.ROTATION), 0, 1)
        child_lock = bounded_int(properties.get(Property.CHILD_LOCK), 0, 1)
        return cls(
            online=online,
            power=power == 1,
            speed=bounded_int(properties.get(Property.SPEED), 1, 10),
            mode=Mode(mode) if mode in Mode._value2member_map_ else None,
            rotation=bool(rotation) if rotation is not None else None,
            child_lock=bool(child_lock) if child_lock is not None else None,
            oscillation=oscillation,
            temperature=temperature,
        )
