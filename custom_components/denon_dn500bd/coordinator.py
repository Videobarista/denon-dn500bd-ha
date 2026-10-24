"""Connection manager and state for the Denon DN-500BD MKII.

One persistent TCP connection (the player accepts only one) carries both the
status polls and the status messages the player pushes by itself. A switched
off or unreachable player is a normal state here, never an error:

* the connection sensor stays available and shows offline plus the reason;
* nothing is logged above INFO, setup never fails because of it;
* while offline one small request is tried every 10 s, backing off to 30 s,
  forever; when it answers, a full refresh follows;
* a dropped connection first gets one quick reconnect check.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import const
from .api import (
    DenonClient,
    DenonConnectionError,
    Reply,
    clean_text,
    message_codes,
    parse_hhhmmss,
    split_message,
)
from .definitions import (
    BARE_KEYS,
    CMD_POWER_ON,
    DISC_STATUS,
    MEDIA_KEYS,
    OPTIONAL_CODES,
    PAUSED_STATES,
    PLAYBACK_STATUS,
    PLAYING_STATES,
    POLL_DETAILS,
    POLL_MEDIA,
    POLL_STATUS,
)

_LOGGER = logging.getLogger(__name__)

type DenonConfigEntry = ConfigEntry[DenonCoordinator]

# Pushed codes after which the media details are re-read.
_DETAIL_TRIGGERS = {"ST", "CD", "Tr", "Tt"}
# Seconds the reported position may differ from the extrapolated one.
_POSITION_TOLERANCE = 2.5
# Answers meaning "no value".
_EMPTY_ANSWERS = {"error", "unknow", "unkn", "ukn", ""}


@dataclass
class ProbeResult:
    """What a one-time probe learned about the player."""

    capabilities: list[str]
    model_id: str | None
    sw_version: str | None


@dataclass
class DenonData:
    """Everything the entities show."""

    online: bool = False
    reason: str | None = const.REASON_STARTING
    last_seen: datetime | None = None
    values: dict[str, str] = field(default_factory=dict)
    # Media position as handed to HA: only re-anchored when the position
    # jumps, so a playing disc does not write a new state on every poll.
    position: int | None = None
    position_updated_at: datetime | None = None

    def get(self, code: str) -> str | None:
        """Raw value of a code, None when unknown."""
        return self.values.get(code)

    @property
    def disc_status(self) -> str | None:
        """Disc / tray status key."""
        value = self.values.get("CD")
        return None if value is None else DISC_STATUS.get(value)

    @property
    def playback_status(self) -> str | None:
        """Playback status key."""
        value = self.values.get("ST")
        return None if value is None else PLAYBACK_STATUS.get(value)

    @property
    def is_playing(self) -> bool:
        """True while media is playing (any speed)."""
        return self.playback_status in PLAYING_STATES

    @property
    def is_paused(self) -> bool:
        """True while paused or stepping."""
        return self.playback_status in PAUSED_STATES

    @property
    def media_present(self) -> bool:
        """True when a disc is loaded or something is playing."""
        return self.values.get("CD") == "CI" or self.is_playing or self.is_paused

    @property
    def elapsed(self) -> int | None:
        """Elapsed time of the current title in seconds."""
        return parse_hhhmmss(self.values.get("ET"))

    @property
    def remaining(self) -> int | None:
        """Remaining time of the current title in seconds."""
        return parse_hhhmmss(self.values.get("RM"))

    @property
    def duration(self) -> int | None:
        """Length of the current title in seconds (elapsed + remaining)."""
        elapsed, remaining = self.elapsed, self.remaining
        if elapsed is None or remaining is None or elapsed + remaining == 0:
            return None
        return elapsed + remaining

    def text(self, code: str) -> str | None:
        """Free text value (title, artist, album)."""
        return clean_text(self.values.get(code))


def parse_version(payload: str | None) -> tuple[str | None, str | None]:
    """Split the ``?VN`` answer ``00004072DN-500BDUS`` into model and version."""
    if not payload:
        return None, None
    if len(payload) > 8 and payload[:8].isdigit():
        return payload[8:] or None, payload[:8]
    return payload, None


async def async_probe_player(client: DenonClient) -> ProbeResult:
    """Ask the player once which optional status requests it answers."""
    await client.request("?PW")
    reply = await client.request("?VN")
    model_id = sw_version = None
    for message in reply.messages:
        parts = split_message(message)
        if parts is not None and parts[0] == "VN":
            model_id, sw_version = parse_version(parts[1])
    capabilities: list[str] = []
    for code in OPTIONAL_CODES:
        reply = await client.request("?" + code)
        if reply.ok and code in message_codes(reply.messages):
            capabilities.append(code)
    return ProbeResult(capabilities, model_id, sw_version)


class DenonCoordinator(DataUpdateCoordinator[DenonData]):
    """Keeps the connection, polls lightly and applies pushed status."""

    config_entry: DenonConfigEntry

    def __init__(self, hass: HomeAssistant, entry: DenonConfigEntry) -> None:
        """Set up the coordinator; nothing is opened until async_start()."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{const.DOMAIN} {entry.data[CONF_HOST]}",
            update_interval=None,
        )
        self.client = DenonClient(
            entry.data[CONF_HOST],
            entry.data.get(CONF_PORT, const.DEFAULT_PORT),
            on_messages=self._handle_messages,
            on_disconnect=self._handle_disconnect,
        )
        caps = entry.data.get(const.CONF_CAPABILITIES)
        self.capabilities: set[str] | None = None if caps is None else set(caps)
        # What this instance was set up with; the update listener reloads
        # the entry when the options or the data change.
        self.setup_snapshot: tuple[dict[str, Any], dict[str, Any]] = (
            dict(entry.options),
            dict(entry.data),
        )
        self.data = DenonData()
        self._wake = asyncio.Event()
        self._connect_lock = asyncio.Lock()
        self._poll_handle: asyncio.TimerHandle | None = None
        self._quick_check = False
        self._polling = False
        self._details_due = True
        self._full_due = True
        self._last_full = 0.0
        self._unexpected_logged = False
        self._was_online = False
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._offline_since: float | None = None
        self._power_on_until = 0.0

    @property
    def poll_interval(self) -> float:
        """Seconds between light status polls."""
        return float(
            self.config_entry.options.get(const.CONF_POLL_INTERVAL, const.DEFAULT_POLL_INTERVAL)
        )

    # --- life cycle ---------------------------------------------------------
    async def async_start(self) -> None:
        """Try to reach the player once, then keep the connection in the background."""
        try:
            # Keep setup short: status and media now, settings right after.
            async with asyncio.timeout(const.FIRST_ATTEMPT_TIMEOUT):
                await self._try_connect(full=False, probe=False)
        except TimeoutError:
            await self.client.close()
            self._set_offline(const.REASON_NO_RESPONSE)
        self._task = self.config_entry.async_create_background_task(
            self.hass, self._run(), f"{const.DOMAIN} connection {self.client.host}"
        )

    async def async_shutdown(self) -> None:
        """Stop the connection loop and close the connection on unload."""
        self._stopping = True
        if self._poll_handle is not None:
            self._poll_handle.cancel()
            self._poll_handle = None
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.wait([task])
        await self.client.close()
        await super().async_shutdown()

    async def _run(self) -> None:
        """Poll while online, retry while offline. Never gives up."""
        while True:
            try:
                if self.client.connected and self.data.online:
                    if self.capabilities is None:
                        # Probed here, once setup has finished; the entry then
                        # reloads with the result.
                        if self.config_entry.state is not ConfigEntryState.LOADED:
                            await asyncio.sleep(1)
                            continue
                        await asyncio.sleep(1)
                        await self._probe_and_store()
                        continue
                    if not self._full_due:
                        await self._wait(self.poll_interval)
                    if not self.client.connected:
                        continue
                    full = (
                        self._full_due
                        or time.monotonic() - self._last_full >= const.FULL_REFRESH_INTERVAL
                    )
                    await self._poll(full=full)
                    continue
                if self._quick_check:
                    self._quick_check = False
                    if await self._try_connect(full=False):
                        continue
                await self._wait(self._retry_delay())
                await self._try_connect(full=True)
            except DenonConnectionError as err:
                await self._connection_failed(err)
            except Exception:  # noqa: BLE001 - keep the loop alive, but say so
                if not self._unexpected_logged:
                    self._unexpected_logged = True
                    _LOGGER.exception("Unexpected error talking to %s", self.client.host)
                await self._recover()
                await asyncio.sleep(const.RETRY_FIRST)

    def _retry_delay(self) -> float:
        """Seconds until the next small request while offline."""
        now = time.monotonic()
        if now < self._power_on_until:
            return const.RETRY_POWER_ON
        offline_for = now - (self._offline_since or now)
        if offline_for < const.FAST_RETRY_PERIOD:
            return const.RETRY_FIRST
        if offline_for < const.MIDDLE_RETRY_PERIOD:
            return const.RETRY_MIDDLE
        return const.RETRY_MAX

    async def _recover(self) -> None:
        """After an unexpected error: close and show offline, without killing the loop."""
        try:
            await self.client.close()
            self._set_offline(const.REASON_NETWORK)
        except Exception:  # noqa: BLE001 - the loop must keep running
            _LOGGER.debug(
                "Error while recovering connection to %s", self.client.host, exc_info=True
            )

    async def _connection_failed(self, err: DenonConnectionError) -> None:
        """A request failed: a dropped connection gets one quick check first."""
        await self.client.close()
        if err.reason == const.REASON_LOST and self.data.online:
            self._quick_check = True
            self._wake.set()
            return
        self._set_offline(err.reason)

    async def _wait(self, timeout: float) -> None:
        """Sleep until the timeout or until something wakes the loop."""
        try:
            async with asyncio.timeout(timeout):
                await self._wake.wait()
        except TimeoutError:
            pass
        self._wake.clear()

    async def _try_connect(self, *, full: bool, probe: bool = True) -> bool:
        """Connect and send one small request; refresh when it answers."""
        async with self._connect_lock:
            return await self._try_connect_locked(full=full, probe=probe)

    async def _try_connect_locked(self, *, full: bool, probe: bool) -> bool:
        try:
            if not self.client.connected:
                await self.client.connect()
            await self.client.request("?PW")
            if probe and self.capabilities is None:
                await self._probe_and_store()
            await self._poll(full=full)
        except DenonConnectionError as err:
            await self.client.close()
            self._set_offline(err.reason)
            return False
        if not self.data.online:
            self._set_online()
            self.async_set_updated_data(self.data)
        return True

    async def _probe_and_store(self) -> None:
        """Probe once and cache the result in the config entry."""
        result = await async_probe_player(self.client)
        self.capabilities = set(result.capabilities)
        entry = self.config_entry
        _LOGGER.debug("Player %s supports %s", self.client.host, result.capabilities)
        # The update listener reloads the entry so the new entities appear.
        self.hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                const.CONF_CAPABILITIES: sorted(result.capabilities),
                const.CONF_MODEL_ID: result.model_id,
                const.CONF_SW_VERSION: result.sw_version,
            },
        )

    # --- polling --------------------------------------------------------------
    async def _poll(self, *, full: bool) -> None:
        """Read the status; stops at the first request that gets no answer."""
        # Changes seen in our own replies are handled within this poll; they
        # must not schedule yet another poll.
        self._polling = True
        try:
            for command in POLL_STATUS:
                await self._query(command)
            if self.data.media_present:
                for command in POLL_MEDIA:
                    await self._query(command)
                if full or self._details_due:
                    self._details_due = False
                    for command in POLL_DETAILS:
                        await self._query(command)
            else:
                self._clear_media()
            if full:
                for code in sorted(self.capabilities or ()):
                    await self._query("?" + code)
                self._last_full = time.monotonic()
                self._full_due = False
        finally:
            self._polling = False
        self._mark_seen()
        self.async_set_updated_data(self.data)

    async def _query(self, command: str) -> Reply:
        reply = await self.client.request(command)
        self._apply_reply(command, reply)
        return reply

    def _apply_reply(self, command: str, reply: Reply) -> None:
        """Store answers that come without an ``@0`` code (``0000113``, ``error``)."""
        if not reply.ok:
            return
        key = BARE_KEYS.get(command)
        if key is None or reply.bare is None or key in message_codes(reply.messages):
            return
        bare = reply.bare
        if key == "ST" and bare == "":
            self._store("ST", "")
        elif bare.lower() in _EMPTY_ANSWERS:
            self._remove(key)
        else:
            self._store(key, bare)

    # --- state ----------------------------------------------------------------
    def _store(self, key: str, value: str) -> bool:
        if key in ("ET", "RM") and value.lower() in _EMPTY_ANSWERS:
            return self._remove(key)
        changed = self.data.values.get(key) != value
        self.data.values[key] = value
        if key == "ET":
            changed = self._update_position() or changed
        return changed

    def _remove(self, key: str) -> bool:
        if key == "ET":
            self.data.position = None
            self.data.position_updated_at = None
        return self.data.values.pop(key, None) is not None

    def _update_position(self) -> bool:
        """Re-anchor the media position only when it drifts or jumps."""
        new = self.data.elapsed
        if new is None:
            return False
        now = dt_util.utcnow()
        old, old_at = self.data.position, self.data.position_updated_at
        if old is not None and old_at is not None:
            if self.data.is_playing:
                expected = old + (now - old_at).total_seconds()
                if abs(expected - new) < _POSITION_TOLERANCE:
                    return False
            elif new == old:
                return False
        self.data.position = new
        self.data.position_updated_at = now
        return True

    def _clear_media(self) -> None:
        for key in MEDIA_KEYS:
            self.data.values.pop(key, None)
        self.data.position = None
        self.data.position_updated_at = None

    def _mark_seen(self) -> None:
        self.data.last_seen = dt_util.utcnow()

    def _set_online(self) -> None:
        self._mark_seen()
        if self.data.online:
            return
        if self._was_online:
            _LOGGER.info("Denon player at %s is back online", self.client.host)
        self._was_online = True
        self._offline_since = None
        self._power_on_until = 0.0
        self._unexpected_logged = False
        self._details_due = True
        self.data.online = True
        self.data.reason = None

    @callback
    def _set_offline(self, reason: str) -> None:
        """Mark the player offline (a state, not an error)."""
        if self._offline_since is None:
            self._offline_since = time.monotonic()
        if not self.data.online and self.data.reason == reason:
            return
        if self.data.online:
            _LOGGER.info("Denon player at %s is offline (%s)", self.client.host, reason)
        else:
            _LOGGER.debug("Denon player at %s still offline (%s)", self.client.host, reason)
        self.data.online = False
        self.data.reason = reason
        self.data.values.clear()
        self.data.position = None
        self.data.position_updated_at = None
        self.async_set_updated_data(self.data)

    @callback
    def _handle_messages(self, messages: list[str]) -> None:
        """Apply status the player pushed (or sent along with an answer)."""
        changed = False
        details = False
        for message in messages:
            parts = split_message(message)
            if parts is None:
                _LOGGER.debug("Ignoring unknown message %r", message)
                continue
            code, payload = parts
            if self._store(code, payload):
                changed = True
                if code in _DETAIL_TRIGGERS:
                    details = True
        if details:
            self._details_due = True
            if not self._polling:
                self._schedule_poll(const.REFRESH_DELAY_PUSH)
        if changed and self.data.online:
            self.async_set_updated_data(self.data)

    @callback
    def _handle_disconnect(self, reason: str) -> None:
        """Connection dropped: do one quick check before calling it offline."""
        _LOGGER.debug("Connection to %s dropped (%s), quick check", self.client.host, reason)
        self._quick_check = True
        self._wake.set()

    @callback
    def _schedule_poll(self, delay: float) -> None:
        if self._stopping:
            return
        if self._poll_handle is not None:
            self._poll_handle.cancel()
        self._poll_handle = self.hass.loop.call_later(delay, self._fire_poll)

    @callback
    def _fire_poll(self) -> None:
        self._poll_handle = None
        self._wake.set()

    # --- commands -----------------------------------------------------------
    async def async_send_command(self, command: str) -> bool:
        """Send a control command. Offline or refused is logged at debug only."""
        if not (self.client.connected and self.data.online):
            _LOGGER.debug("Player %s offline, %s not sent", self.client.host, command)
            return False
        try:
            reply = await self.client.request(command)
        except DenonConnectionError as err:
            _LOGGER.debug("Command %s to %s failed: %s", command, self.client.host, err)
            await self._connection_failed(err)
            return False
        if not reply.ok:
            # Normal during unskippable disc content or in menus.
            _LOGGER.debug("Player %s refused %s (nack)", self.client.host, command)
            return False
        self._details_due = True
        self._schedule_poll(const.REFRESH_DELAY_COMMAND)
        return True

    async def async_set_setting(self, code: str, suffix: str) -> bool:
        """Change a setting and read it back (the reply is the truth).

        Returns True when the player acknowledged the change and answered the
        read-back.
        """
        if not await self.async_send_command(code + suffix):
            return False
        try:
            await self._query("?" + code)
        except DenonConnectionError as err:
            await self._connection_failed(err)
            return False
        self.async_set_updated_data(self.data)
        return True

    @property
    def power_on_entity(self) -> str | None:
        """Entity that powers the player on (its LAN port is off in standby)."""
        return self.config_entry.options.get(const.CONF_POWER_ON_ENTITY) or None

    async def async_turn_on(self) -> None:
        """Power on through the configured entity, then look for the player quickly."""
        if self.data.online:
            await self.async_send_command(CMD_POWER_ON)
            return
        entity_id = self.power_on_entity
        if entity_id is None or self._stopping:
            _LOGGER.debug("No power-on entity configured for %s", self.client.host)
            return
        domain = entity_id.split(".", 1)[0]
        service = const.POWER_ON_SERVICES.get(domain)
        if service is None:
            _LOGGER.debug("Power-on entity %s has an unsupported domain", entity_id)
            return
        await self.hass.services.async_call(
            domain, service, {"entity_id": entity_id}, blocking=True
        )
        self._power_on_until = time.monotonic() + const.POWER_ON_WINDOW
        self._wake.set()
