"""Denon DN-500BD MKII Blu-ray player integration.

Not affiliated with, endorsed by or connected to Denon, Denon Professional,
inMusic Brands or D&M Holdings. All product names are used for
identification only.
"""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DEFAULT_TITLE, OLD_DEFAULT_TITLE
from .coordinator import DenonConfigEntry, DenonCoordinator

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: DenonConfigEntry) -> bool:
    """Set up the player. Never fails because the player is switched off."""
    if entry.title == OLD_DEFAULT_TITLE:
        hass.config_entries.async_update_entry(entry, title=DEFAULT_TITLE)
    coordinator = DenonCoordinator(hass, entry)
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DenonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: DenonConfigEntry) -> None:
    """Reload when the options or the data (address, capability cache) changed."""
    if (dict(entry.options), dict(entry.data)) != entry.runtime_data.setup_snapshot:
        hass.config_entries.async_schedule_reload(entry.entry_id)
