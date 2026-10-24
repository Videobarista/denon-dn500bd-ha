"""Diagnostics for the Denon DN-500BD MKII (the address is redacted)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import DenonConfigEntry

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DenonConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "online": data.online,
        "reason": data.reason,
        "last_seen": data.last_seen.isoformat() if data.last_seen else None,
        "capabilities": sorted(coordinator.capabilities or ()),
        "values": dict(data.values),
    }
