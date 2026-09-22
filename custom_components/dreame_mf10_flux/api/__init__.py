"""Dreame MF10 Flux protocol library. Copyright 2026 Gabriele Pennacchia."""

from .client import FluxClient
from .errors import AuthenticationError, CloudError, CommandError, RateLimited, Unavailable
from .models import MODEL, Device, FanState, Mode, Oscillation, Property

__all__ = [
    "MODEL",
    "AuthenticationError",
    "CloudError",
    "CommandError",
    "Device",
    "FanState",
    "FluxClient",
    "Mode",
    "Oscillation",
    "Property",
    "RateLimited",
    "Unavailable",
]
