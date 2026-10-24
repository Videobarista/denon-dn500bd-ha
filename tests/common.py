"""Helpers shared by the tests."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denon_dn500bd import const
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .fake_player import ALL_CAPABILITIES


def entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    """Entity id from the unique id."""
    result = er.async_get(hass).async_get_entity_id(
        platform, const.DOMAIN, f"{entry.entry_id}_{key}"
    )
    assert result is not None, f"{platform} {key} not registered"
    return result


def make_entry(
    port: int,
    capabilities: list[str] | None = ALL_CAPABILITIES,
    *,
    title: str = const.DEFAULT_TITLE,
    options: dict | None = None,
) -> MockConfigEntry:
    """A config entry for the fake player."""
    return MockConfigEntry(
        domain=const.DOMAIN,
        title=title,
        unique_id="127.0.0.1",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: port,
            const.CONF_CAPABILITIES: capabilities,
            const.CONF_MODEL_ID: "DN-500BDUS",
            const.CONF_SW_VERSION: "00004072",
        },
        options={const.CONF_POLL_INTERVAL: 0.2, **(options or {})},
    )


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add and set up an entry."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def unload_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Unload an entry so no task or connection lingers."""
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
