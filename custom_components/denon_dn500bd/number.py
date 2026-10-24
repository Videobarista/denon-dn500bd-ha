"""Number entities (levels) for the Denon DN-500BD MKII."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import format_signed, parse_signed
from .coordinator import DenonConfigEntry, DenonCoordinator
from .definitions import NUMBERS, NumberSetting
from .entity import DenonEntity

PARALLEL_UPDATES = 1

STEP = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers the player reported during the probe."""
    coordinator = entry.runtime_data
    caps = coordinator.capabilities or set()
    async_add_entities(
        DenonNumber(coordinator, setting) for setting in NUMBERS if setting.code in caps
    )


def snap(value: float, minimum: int, maximum: int, step: int = STEP) -> int:
    """Round to the step and clamp to the range (whole numbers stay whole)."""
    snapped = int(round((value - minimum) / step)) * step + minimum
    return max(minimum, min(maximum, snapped))


class DenonNumber(DenonEntity, NumberEntity):
    """A level such as the output level or the picture brightness."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = STEP

    def __init__(self, coordinator: DenonCoordinator, setting: NumberSetting) -> None:
        """Initialise the number."""
        super().__init__(coordinator, setting.code.lower())
        self._setting = setting
        self._attr_translation_key = setting.key
        self._attr_native_min_value = setting.minimum
        self._attr_native_max_value = setting.maximum
        self._attr_native_unit_of_measurement = setting.unit
        self._attr_entity_registry_enabled_default = setting.enabled_default
        if setting.icon:
            self._attr_icon = setting.icon

    @property
    def native_value(self) -> int | None:
        """Current level as a whole number."""
        value = parse_signed(self.coordinator.data.get(self._setting.code), self._setting.minimum)
        if value is None:
            return None
        return snap(value, self._setting.minimum, self._setting.maximum)

    async def async_set_native_value(self, value: float) -> None:
        """Set the level, rounded to the step."""
        level = snap(value, self._setting.minimum, self._setting.maximum)
        await self.coordinator.async_set_setting(
            self._setting.code, format_signed(level, self._setting.width)
        )
