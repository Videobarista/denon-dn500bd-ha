"""Sensors for the Denon DN-500BD MKII."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfFrequency, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .api import parse_number
from .coordinator import DenonConfigEntry, DenonCoordinator, DenonData
from .definitions import AUDIO_CHANNELS, AUDIO_FORMAT, DISC_STATUS, MEDIA_TYPE, PLAYBACK_STATUS
from .entity import DenonEntity

PARALLEL_UPDATES = 0


def _number(code: str) -> Callable[[DenonData], StateType]:
    def value(data: DenonData) -> StateType:
        number = parse_number(data.get(code))
        return number if number else None

    return value


def _mapped(code: str, table: dict[str, str]) -> Callable[[DenonData], StateType]:
    def value(data: DenonData) -> StateType:
        raw = data.get(code)
        return None if raw is None else table.get(raw)

    return value


def _language(code: str) -> Callable[[DenonData], StateType]:
    def value(data: DenonData) -> StateType:
        raw = (data.get(code) or "").strip()
        return None if not raw or raw.lower() in ("ukn", "unkn") else raw.lower()

    return value


def _sample_rate(data: DenonData) -> StateType:
    raw = data.get("Fs")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class DenonSensorDescription(SensorEntityDescription):
    """Describes a Denon sensor."""

    value_fn: Callable[[DenonData], StateType | datetime]
    always_available: bool = False


SENSORS: tuple[DenonSensorDescription, ...] = (
    DenonSensorDescription(
        key="connection",
        translation_key="connection",
        device_class=SensorDeviceClass.ENUM,
        options=["online", "offline"],
        value_fn=lambda data: "online" if data.online else "offline",
        always_available=True,
    ),
    DenonSensorDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_seen,
        always_available=True,
    ),
    DenonSensorDescription(
        key="disc_status",
        translation_key="disc_status",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(DISC_STATUS.values())),
        value_fn=_mapped("CD", DISC_STATUS),
    ),
    DenonSensorDescription(
        key="disc_type",
        translation_key="disc_type",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(MEDIA_TYPE.values())),
        value_fn=_mapped("PCTYP", MEDIA_TYPE),
    ),
    DenonSensorDescription(
        key="playback_status",
        translation_key="playback_status",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(PLAYBACK_STATUS.values())),
        value_fn=_mapped("ST", PLAYBACK_STATUS),
    ),
    DenonSensorDescription(
        key="playback_chapter",
        translation_key="playback_chapter",
        value_fn=_number("Tr"),
    ),
    DenonSensorDescription(
        key="playback_chapter_count",
        translation_key="playback_chapter_count",
        value_fn=_number("Tt"),
    ),
    DenonSensorDescription(
        key="playback_title",
        translation_key="playback_title",
        value_fn=_number("PCGp"),
    ),
    DenonSensorDescription(
        key="playback_title_count",
        translation_key="playback_title_count",
        value_fn=_number("PCTG"),
    ),
    DenonSensorDescription(
        key="playback_elapsed",
        translation_key="playback_elapsed",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.elapsed,
    ),
    DenonSensorDescription(
        key="playback_remaining",
        translation_key="playback_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.remaining,
    ),
    DenonSensorDescription(
        key="audio_format",
        translation_key="audio_format",
        value_fn=_mapped("PCAFMT", AUDIO_FORMAT),
    ),
    DenonSensorDescription(
        key="audio_channels",
        translation_key="audio_channels",
        value_fn=_mapped("BDACH", AUDIO_CHANNELS),
    ),
    DenonSensorDescription(
        key="audio_sample_rate",
        translation_key="audio_sample_rate",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.KILOHERTZ,
        entity_registry_enabled_default=False,
        value_fn=_sample_rate,
    ),
    DenonSensorDescription(
        key="audio_language",
        translation_key="audio_language",
        value_fn=_language("PCDG+"),
    ),
    DenonSensorDescription(
        key="audio_language_secondary",
        translation_key="audio_language_secondary",
        entity_registry_enabled_default=False,
        value_fn=_language("PCDG-"),
    ),
    DenonSensorDescription(
        key="subtitle_language",
        translation_key="subtitle_language",
        value_fn=_language("DVSTC"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(DenonSensor(coordinator, description) for description in SENSORS)


class DenonSensor(DenonEntity, SensorEntity):
    """A value reported by the player."""

    entity_description: DenonSensorDescription

    def __init__(self, coordinator: DenonCoordinator, description: DenonSensorDescription) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """The connection sensors stay available while the player is offline."""
        if self.entity_description.always_available:
            return True
        return super().available

    @property
    def native_value(self) -> StateType | datetime:
        """Current value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The Connection sensor tells why the player is offline."""
        if self.entity_description.key != "connection":
            return None
        data = self.coordinator.data
        return {"reason": None if data.online else data.reason}
