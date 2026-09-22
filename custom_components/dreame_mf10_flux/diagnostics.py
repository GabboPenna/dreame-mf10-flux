"""Allowlisted diagnostics. Copyright 2026 Gabriele Pennacchia."""

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import FluxEntry
from .const import CONF_POLL_INTERVAL, CONF_REGION, DEFAULT_POLL_INTERVAL, VERSION


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FluxEntry
) -> dict[str, Any]:
    """Export operational facts without identifiers, credentials, or raw responses."""
    coordinator = entry.runtime_data.coordinator
    return {
        "integration_version": VERSION,
        "model": coordinator.device.model,
        "firmware": coordinator.device.firmware,
        "region": entry.data[CONF_REGION],
        "poll_interval": entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        "last_update_success": coordinator.last_update_success,
        "last_exception_type": type(coordinator.last_exception).__name__
        if coordinator.last_exception
        else None,
        "last_poll_ms": coordinator.last_poll_ms,
        "last_successful_update": coordinator.last_successful_update.isoformat()
        if coordinator.last_successful_update
        else None,
        "consecutive_update_failures": coordinator.consecutive_update_failures,
        "last_command_ms": coordinator.last_command_ms,
        "last_command_success": coordinator.last_command_success,
        "last_command_error": coordinator.last_command_error,
        "commands": coordinator.commands,
        "command_failures": coordinator.command_failures,
        "consecutive_command_failures": coordinator.consecutive_command_failures,
        "requests": coordinator.client.requests,
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
