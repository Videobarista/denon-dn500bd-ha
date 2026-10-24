"""Media player entity for the Denon DN-500BD MKII."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DenonConfigEntry, DenonCoordinator
from .definitions import (
    CAP_MUTE,
    CMD_MUTE_OFF,
    CMD_MUTE_ON,
    CMD_NEXT,
    CMD_PAUSE,
    CMD_PLAY,
    CMD_POWER_OFF,
    CMD_PREVIOUS,
    CMD_STOP,
    MEDIA_TYPE,
    MUSIC_MEDIA,
)
from .entity import DenonEntity

PARALLEL_UPDATES = 1

_BASE_FEATURES = (
    MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DenonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player."""
    async_add_entities([DenonMediaPlayer(entry.runtime_data)])


class DenonMediaPlayer(DenonEntity, MediaPlayerEntity):
    """The player itself.

    Position and duration are those of the current chapter (DVD/BD) or track
    (CD/files), as the player reports them; the position is only re-anchored
    when it jumps so a playing disc does not cause a state write every poll.
    """

    _attr_name = None

    def __init__(self, coordinator: DenonCoordinator) -> None:
        """Initialise the media player."""
        super().__init__(coordinator, "media_player")
        features = _BASE_FEATURES
        if CAP_MUTE in (coordinator.capabilities or ()):
            features |= MediaPlayerEntityFeature.VOLUME_MUTE
        # The player's network port is off in standby: power on only works
        # through an entity configured in the options (IR, RS-232, plug ...).
        if coordinator.power_on_entity:
            features |= MediaPlayerEntityFeature.TURN_ON
        self._attr_supported_features = features

    @property
    def available(self) -> bool:
        """Always available: a switched off player is simply off."""
        return True

    @property
    def state(self) -> MediaPlayerState:
        """Map the player status to a media player state."""
        data = self.coordinator.data
        if not data.online:
            return MediaPlayerState.OFF
        if data.is_playing:
            return MediaPlayerState.PLAYING
        if data.is_paused:
            return MediaPlayerState.PAUSED
        if data.playback_status in ("menu", "setup", "track_menu"):
            return MediaPlayerState.ON
        return MediaPlayerState.IDLE

    @property
    def is_volume_muted(self) -> bool | None:
        """Mute state (``mt00`` = muted)."""
        value = self.coordinator.data.get("mt")
        return None if value is None else value == "00"

    @property
    def media_content_type(self) -> MediaType | None:
        """Music for audio discs, video for everything else."""
        data = self.coordinator.data
        media = MEDIA_TYPE.get(data.get("PCTYP") or "")
        if media is None:
            return None
        return MediaType.MUSIC if media in MUSIC_MEDIA else MediaType.VIDEO

    @property
    def media_title(self) -> str | None:
        """Title (CD text / ID3); Blu-ray and DVD discs usually report none."""
        return self.coordinator.data.text("ti")

    @property
    def media_artist(self) -> str | None:
        """Artist (CD text / ID3)."""
        return self.coordinator.data.text("at")

    @property
    def media_album_name(self) -> str | None:
        """Album (CD text / ID3)."""
        return self.coordinator.data.text("al")

    @property
    def media_track(self) -> int | None:
        """Current chapter (DVD/BD) or track number."""
        value = self.coordinator.data.get("Tr")
        return int(value) if value and value.isdigit() and int(value) > 0 else None

    @property
    def media_duration(self) -> int | None:
        """Length of the current chapter/track in seconds."""
        return self.coordinator.data.duration

    @property
    def media_position(self) -> int | None:
        """Position in the current chapter/track in seconds."""
        return self.coordinator.data.position

    @property
    def media_position_updated_at(self) -> datetime | None:
        """When the position was valid."""
        return self.coordinator.data.position_updated_at

    async def async_turn_on(self) -> None:
        """Power on through the configured power-on entity."""
        await self.coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        """Power off (standby)."""
        await self.coordinator.async_send_command(CMD_POWER_OFF)

    async def async_media_play(self) -> None:
        """Play."""
        await self.coordinator.async_send_command(CMD_PLAY)

    async def async_media_pause(self) -> None:
        """Pause."""
        await self.coordinator.async_send_command(CMD_PAUSE)

    async def async_media_stop(self) -> None:
        """Stop."""
        await self.coordinator.async_send_command(CMD_STOP)

    async def async_media_next_track(self) -> None:
        """Next chapter/track."""
        await self.coordinator.async_send_command(CMD_NEXT)

    async def async_media_previous_track(self) -> None:
        """Restart the chapter/track or go to the previous one."""
        await self.coordinator.async_send_command(CMD_PREVIOUS)

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the analog outputs."""
        code = CMD_MUTE_ON if mute else CMD_MUTE_OFF
        await self.coordinator.async_set_setting(code[:2], code[2:])
