"""Async client for the Denon DN-500BD MKII LAN control port (TCP 9030).

Wire format, as measured on real hardware (it differs from the RS-232 guide):

* Host -> player: ``@0`` + command + ``\\r``, one command at a time.
* Player -> host: plain text without any terminator:
  ``ack`` (control command or ``?PW``), ``ack+`` followed by the answer
  (``@0STPL``, ``0000001``, ``error``, ``unknow`` or nothing) or ``nack``.
* The player pushes status changes on its own (``@0STPL``, ``@0CDTC`` ...),
  usually twice, and these can arrive before or after the ``ack`` of a
  request in the same TCP read.

Because nothing terminates a message, bytes are grouped into a *burst* (a
short silence ends it) and a burst is split on the ``@0`` start characters.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import errno
import logging
import re
import socket
import time

from . import const
from .definitions import OPTIONAL_CODES

_LOGGER = logging.getLogger(__name__)

ACK = "ack"
NACK = "nack"

# Messages that carry free text (title, artist, album): only "ack+" ends
# them, so a title like "Black Jack" survives.
_TEXT_CODES = ("ti", "at", "al")

_SPLIT_RE = re.compile(r"(?=@0)")
_PREFACE_RE = re.compile(r"(nack|ack\+?)(.*)\Z", re.DOTALL)
_INLINE_MARKER_RE = re.compile(r"(nack|ack\+?)(.*)\Z", re.DOTALL)
_TEXT_MARKER_RE = re.compile(r"(ack\+)(.*)\Z", re.DOTALL)

# Known message codes, longest first so "PCTYP" never matches as "PC...".
STATUS_CODES: tuple[str, ...] = (
    "CD",
    "ST",
    "Tr",
    "Tt",
    "ti",
    "at",
    "al",
    "tl",
    "ET",
    "RM",
    "PCTYP",
    "PCAFMT",
    "BDACH",
    "PCDG+",
    "PCDG-",
    "DVSTC",
    "Fs",
    "PCGp",
    "PCTG",
    "VN",
    "mt",
    "PCPMR",
)

_unreachable_errnos = {
    errno.EHOSTUNREACH,
    errno.ENETUNREACH,
    getattr(errno, "EHOSTDOWN", errno.EHOSTUNREACH),
}


class DenonConnectionError(Exception):
    """The player could not be reached; ``reason`` is one of const.REASON_*."""

    def __init__(self, reason: str, detail: str = "") -> None:
        """Store the reason."""
        super().__init__(reason, detail)
        self.reason = reason
        self.detail = detail

    def __str__(self) -> str:
        """Readable form for debug logs."""
        return f"{self.reason}: {self.detail}" if self.detail else self.reason


@dataclass
class Burst:
    """One burst of bytes from the player, split into its parts."""

    marker: str | None = None  # "ack", "nack" or None (push only)
    bare: str | None = None  # answer without "@0" prefix (ET/RM, "error" ...)
    messages: list[str] = field(default_factory=list)  # "@0..." without "@0"


@dataclass
class Reply:
    """Reply to one command or status request."""

    marker: str  # "ack" or "nack"
    bare: str | None
    messages: list[str]

    @property
    def ok(self) -> bool:
        """True when the player acknowledged the command."""
        return self.marker == ACK


def parse_burst(raw: bytes) -> Burst:
    """Split a burst into its ack/nack marker, bare answer and messages."""
    text = raw.decode("latin-1")
    parts = _SPLIT_RE.split(text)
    burst = Burst()

    preface = parts[0]
    if preface:
        match = _PREFACE_RE.match(preface)
        if match:
            burst.marker = NACK if match.group(1) == NACK else ACK
            if match.group(1) == "ack+":
                burst.bare = match.group(2)
        else:
            _LOGGER.debug("Ignoring unexpected bytes from player: %r", preface)

    for part in parts[1:]:
        body = part[2:]
        # A marker can follow a pushed message directly: "@0STDVHMack+error".
        # Free text only splits on "ack+", which no real title contains.
        pattern = _TEXT_MARKER_RE if body.startswith(_TEXT_CODES) else _INLINE_MARKER_RE
        match = pattern.search(body)
        if match:
            body = body[: match.start()]
            if burst.marker is None:
                burst.marker = NACK if match.group(1) == NACK else ACK
                if match.group(1) == "ack+":
                    burst.bare = match.group(2)
        if body:
            burst.messages.append(body)
    return burst


_CODES: tuple[str, ...] = tuple(
    sorted(set(STATUS_CODES) | set(OPTIONAL_CODES), key=len, reverse=True)
)


def split_message(message: str) -> tuple[str, str] | None:
    """Split ``"STPL"`` into ``("ST", "PL")`` for the known codes."""
    for code in _CODES:
        if message.startswith(code):
            return code, message[len(code) :]
    return None


def message_codes(messages: list[str]) -> set[str]:
    """Return the codes present in a list of messages."""
    codes: set[str] = set()
    for message in messages:
        parts = split_message(message)
        if parts is not None:
            codes.add(parts[0])
    return codes


def parse_hhhmmss(value: str | None) -> int | None:
    """Convert the ``hhhmmss`` time of ``?ET``/``?RM`` into seconds."""
    if value is None or len(value) != 7 or not value.isdigit():
        return None
    hours, minutes, seconds = int(value[:3]), int(value[3:5]), int(value[5:7])
    if minutes > 59 or seconds > 59:
        return None
    return hours * 3600 + minutes * 60 + seconds


def parse_mmmss(value: str | None) -> int | None:
    """Convert the ``MMMSS`` or ``MMMSSFF`` time of ``?tl`` into seconds."""
    if value is None or len(value) not in (5, 7) or not value.isdigit():
        return None
    minutes, seconds = int(value[:3]), int(value[3:5])
    if seconds > 59:
        return None
    return minutes * 60 + seconds


def format_hms(seconds: int | None) -> str | None:
    """Format seconds as ``H:MM:SS`` for display."""
    if seconds is None:
        return None
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def parse_signed(value: str | None, minimum: int) -> int | None:
    """Parse ``-03``/``+10``/``000``/``inf`` style levels."""
    if value is None:
        return None
    if value.lower() == "inf":
        return minimum
    try:
        return int(value)
    except ValueError:
        return None


def format_signed(value: int, width: int) -> str:
    """Format a level the way the player expects (``-03``, ``+10``, ``000``)."""
    if value == 0:
        return "0" * width
    sign = "+" if value > 0 else "-"
    return sign + str(abs(value)).zfill(width - 1)


def parse_number(value: str | None) -> int | None:
    """Parse ``0001`` style counters; ``UNKN``/``unknow`` give None."""
    if value is None or not value.isdigit():
        return None
    return int(value)


def clean_text(value: str | None) -> str | None:
    """Title/artist/album: ``NULL`` or empty means nothing."""
    if value is None:
        return None
    value = value.strip()
    if not value or value.upper() == "NULL":
        return None
    return value


class DenonClient:
    """Persistent TCP connection to one player (it accepts only one)."""

    def __init__(
        self,
        host: str,
        port: int = const.DEFAULT_PORT,
        *,
        on_messages: Callable[[list[str]], None] | None = None,
        on_disconnect: Callable[[str], None] | None = None,
    ) -> None:
        """Initialise the client; nothing is opened until connect()."""
        self.host = host
        self.port = port
        self._on_messages = on_messages
        self._on_disconnect = on_disconnect
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._pending: asyncio.Future[Reply] | None = None
        self._last_send = 0.0
        self._closing = False

    @property
    def connected(self) -> bool:
        """True while the TCP connection is open."""
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the connection; raises DenonConnectionError."""
        await self.close()
        self._closing = False
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), const.CONNECT_TIMEOUT
            )
        except TimeoutError as err:
            raise DenonConnectionError(const.REASON_TIMEOUT) from err
        except ConnectionRefusedError as err:
            raise DenonConnectionError(const.REASON_REFUSED, str(err)) from err
        except OSError as err:
            if err.errno in _unreachable_errnos:
                raise DenonConnectionError(const.REASON_UNREACHABLE, str(err)) from err
            raise DenonConnectionError(const.REASON_NETWORK, str(err)) from err

        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError as err:
                _LOGGER.debug("Could not set TCP_NODELAY: %s", err)
        self._reader = reader
        self._writer = writer
        self._read_task = asyncio.create_task(self._read_loop(reader))
        _LOGGER.debug("Connected to %s:%s", self.host, self.port)

    async def close(self) -> None:
        """Close the connection without reporting a disconnect."""
        self._closing = True
        task, self._read_task = self._read_task, None
        writer, self._writer = self._writer, None
        self._reader = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.wait([task])
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError as err:
                _LOGGER.debug("Error while closing connection: %s", err)
        self._fail_pending(const.REASON_LOST)

    async def request(self, command: str) -> Reply:
        """Send one command (``"?ST"``, ``"2353"`` ...) and wait for ack/nack."""
        async with self._lock:
            writer = self._writer
            if writer is None or writer.is_closing():
                raise DenonConnectionError(const.REASON_LOST, "not connected")
            wait = const.COMMAND_GAP - (time.monotonic() - self._last_send)
            if wait > 0:
                await asyncio.sleep(wait)
            future: asyncio.Future[Reply] = asyncio.get_running_loop().create_future()
            self._pending = future
            self._last_send = time.monotonic()
            try:
                writer.write(b"@0" + command.encode("latin-1") + b"\r")
                await writer.drain()
                return await asyncio.wait_for(future, const.REQUEST_TIMEOUT)
            except TimeoutError as err:
                await self._drop(const.REASON_NO_RESPONSE)
                raise DenonConnectionError(const.REASON_NO_RESPONSE, command) from err
            except OSError as err:
                await self._drop(const.REASON_LOST)
                raise DenonConnectionError(const.REASON_LOST, str(err)) from err
            finally:
                self._pending = None

    async def _drop(self, reason: str) -> None:
        """Close after a failure and report it."""
        if self._writer is None:
            return
        await self.close()
        self._report_disconnect(reason)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        reason = const.REASON_LOST
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                eof = False
                while True:
                    try:
                        more = await asyncio.wait_for(reader.read(4096), const.BURST_IDLE)
                    except TimeoutError:
                        break
                    if not more:
                        eof = True
                        break
                    data += more
                self._handle_burst(data)
                if eof:
                    break
        except OSError as err:
            _LOGGER.debug("Read error from %s: %s", self.host, err)
        if self._closing or self._reader is not reader:
            return
        self._writer = None
        self._reader = None
        self._read_task = None
        self._fail_pending(reason)
        self._report_disconnect(reason)

    def _handle_burst(self, data: bytes) -> None:
        _LOGGER.debug("Received %r", data)
        burst = parse_burst(data)
        if burst.messages and self._on_messages is not None:
            self._on_messages(burst.messages)
        pending = self._pending
        if burst.marker is not None and pending is not None and not pending.done():
            pending.set_result(Reply(burst.marker, burst.bare, burst.messages))

    def _fail_pending(self, reason: str) -> None:
        pending = self._pending
        if pending is not None and not pending.done():
            pending.set_exception(DenonConnectionError(reason))

    def _report_disconnect(self, reason: str) -> None:
        _LOGGER.debug("Connection to %s lost (%s)", self.host, reason)
        if self._on_disconnect is not None:
            self._on_disconnect(reason)
