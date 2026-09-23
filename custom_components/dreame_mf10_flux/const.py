"""Integration constants. Copyright 2026 Gabriele Pennacchia."""

from homeassistant.const import Platform

DOMAIN = "dreame_mf10_flux"
NAME = "Dreame MF10 Flux"
VERSION = "1.1.0"
PLATFORMS = (
    Platform.FAN,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
)
CONF_DEVICE_ID = "device_id"
CONF_REGION = "region"
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 30
