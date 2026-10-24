"""Switch entities (on/off settings) for the Denon DN-500BD MKII."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DenonConfigEntry, DenonCoordinator
from .definitions import SWITCHES, SwitchSetting
from .entity import DenonEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches the player reported during the probe."""
    coordinator = entry.runtime_data
    caps = coordinator.capabilities or set()
    async_add_entities(
        DenonSwitch(coordinator, setting) for setting in SWITCHES if setting.code in caps
    )


class DenonSwitch(DenonEntity, SwitchEntity):
    """An on/off setting."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DenonCoordinator, setting: SwitchSetting) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, setting.code.lower())
        self._setting = setting
        self._attr_translation_key = setting.key
        self._attr_entity_registry_enabled_default = setting.enabled_default
        if setting.icon:
            self._attr_icon = setting.icon

    @property
    def is_on(self) -> bool | None:
        """On/off as reported by the player."""
        value = self.coordinator.data.get(self._setting.code)
        if value == self._setting.on:
            return True
        if value == self._setting.off:
            return False
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self.coordinator.async_set_setting(self._setting.code, self._setting.on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self.coordinator.async_set_setting(self._setting.code, self._setting.off)
