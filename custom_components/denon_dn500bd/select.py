"""Select entities (settings with fixed choices) for the Denon DN-500BD MKII."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DenonConfigEntry, DenonCoordinator
from .definitions import SELECTS, SelectSetting
from .entity import DenonEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects the player reported during the probe."""
    coordinator = entry.runtime_data
    caps = coordinator.capabilities or set()
    async_add_entities(
        DenonSelect(coordinator, setting) for setting in SELECTS if setting.code in caps
    )


class DenonSelect(DenonEntity, SelectEntity):
    """A setting with a fixed list of choices."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: DenonCoordinator, setting: SelectSetting) -> None:
        """Initialise the select."""
        super().__init__(coordinator, setting.code.lower())
        self._setting = setting
        self._by_suffix = {suffix: option for option, suffix in setting.options.items()}
        self._attr_translation_key = setting.key
        self._attr_options = list(setting.options)
        self._attr_entity_registry_enabled_default = setting.enabled_default
        if setting.icon:
            self._attr_icon = setting.icon

    @property
    def current_option(self) -> str | None:
        """Current choice; None when the player reports a value not in the list."""
        value = self.coordinator.data.get(self._setting.code)
        return None if value is None else self._by_suffix.get(value)

    async def async_select_option(self, option: str) -> None:
        """Change the setting."""
        await self.coordinator.async_set_setting(self._setting.code, self._setting.options[option])
