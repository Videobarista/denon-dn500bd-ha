"""A fake DN-500BD MKII that speaks the LAN protocol (no Home Assistant needed)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import socket

# Replies as captured from a real player (firmware 00004072).
DEFAULT_VALUES: dict[str, str] = {
    "CD": "CI",
    "ST": "PL",
    "Tr": "0001",
    "Tt": "0002",
    "ti": "NULL",
    "at": "NULL",
    "al": "NULL",
    "tl": "00113",
    "ET": "0000113",
    "RM": "0000040",
    "PCTYP": "BDM",
    "PCAFMT": "DBD",
    "BDACH": "51C",
    "PCDG+": "eng",
    "PCDG-": "ukn",
    "DVSTC": "ukn",
    "Fs": "UKN",
    "PCGp": "0087",
    "PCTG": "0091",
    "VN": "00004072DN-500BDUS",
    "mt": "01",
    "DVOV": "-03",
    "DVMV": "000",
    "DVPABN": "000",
    "DVPACT": "000",
    "DVPAHU": "00",
    "DVPASR": "00",
    "DVVR": "7",
    "DVAr": "9A",
    "DVFM": "MS",
    "DVCS": "Y2",
    "DVDC": "30",
    "DVHA": "LP",
    "DVDO": "48",
    "DVDR": "01",
    "DVSCCh": "51",
    "PCTMD": "TR",
    "DVRC": "C1",
    "PCAP": "00",
    "PCAR": "00",
    "DVHOSD": "00",
    "PCIRLK": "01",
    "DVHDC": "OF",
    "PCPMP": "01",
    "DV1K24": "00",
    "DV3D": "01",
    "DVPIP": "00",
    "DVSA": "01",
}

# Request code -> code used in the answer, where they differ.
_ANSWER_CODE = {"fs": "Fs", "PCACH": "BDACH"}
# Answers without "@0" code.
_BARE = {"ET", "RM"}
_SETTING_CODES = sorted(
    (
        "DVOV",
        "DVMV",
        "DVPABN",
        "DVPACT",
        "DVPAHU",
        "DVPASR",
        "DVVR",
        "DVAr",
        "DVFM",
        "DVCS",
        "DVDC",
        "DVHA",
        "DVDO",
        "DVDR",
        "DVSCCh",
        "PCTMD",
        "DVRC",
        "PCAP",
        "PCAR",
        "DVHOSD",
        "PCIRLK",
        "DVHDC",
        "PCPMP",
        "DV1K24",
        "DV3D",
        "DVPIP",
        "DVSA",
        "mt",
    ),
    key=len,
    reverse=True,
)

ALL_CAPABILITIES = sorted(_SETTING_CODES)


class FakePlayer:
    """Minimal fake of the player's TCP 9030 control port."""

    def __init__(self) -> None:
        """Initialise with the values of a playing Blu-ray."""
        self.values: dict[str, str] = dict(DEFAULT_VALUES)
        self.received: list[str] = []
        self.respond = True
        self.nack: set[str] = set()
        # Codes whose reported value runs this much higher than the set code.
        self.readback_shift: dict[str, int] = {}
        self.port = 0
        self._server: asyncio.Server | None = None
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self, port: int = 0) -> None:
        """Start listening (port 0 picks a free one)."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def drop_connections(self) -> None:
        """Close every client connection but keep listening."""
        for writer in list(self._writers):
            writer.close()
        await asyncio.sleep(0.05)

    async def stop(self) -> None:
        """Stop listening and close all connections (player switched off)."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
        await self.drop_connections()
        if server is not None:
            await server.wait_closed()

    def push(self, *messages: str) -> None:
        """Push status messages (twice, like the real player)."""
        payload = "".join(f"@0{m}@0{m}" for m in messages).encode("latin-1")
        for writer in self._writers:
            writer.write(payload)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.append(writer)
        buffer = b""
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                buffer += data
                while b"\r" in buffer:
                    line, buffer = buffer.split(b"\r", 1)
                    reply = self._answer(line.decode("latin-1"))
                    if reply:
                        writer.write(reply.encode("latin-1"))
                        await writer.drain()
        except OSError:
            pass
        finally:
            if writer in self._writers:
                self._writers.remove(writer)
            writer.close()

    def _answer(self, line: str) -> str | None:
        if not line.startswith("@0"):
            return "nack"
        command = line[2:]
        self.received.append(command)
        if not self.respond:
            return None
        if command in self.nack:
            return "nack"
        if command.startswith("?"):
            return self._status(command[1:])
        return self._control(command)

    def _status(self, code: str) -> str:
        if code == "PW":
            return "ack"
        answer = _ANSWER_CODE.get(code, code)
        if answer in _BARE:
            value = self.values.get(answer)
            return "ack+" + (value if value else "error")
        if answer in self.values:
            return f"ack+@0{answer}{self.values[answer]}"
        return "nack"

    def _control(self, command: str) -> str:
        pushes: list[str] = []
        if command == "2353":
            self.values["ST"] = "PL"
            pushes.append("STPL")
        elif command == "2348":
            self.values["ST"] = "PP"
            pushes.append("STPP")
        elif command == "2354":
            self.values["ST"] = "DVHM"
            pushes.append("STDVHM")
        elif command in ("2332", "2333", "PW00", "PW01") or command.startswith(("PC", "DV", "23")):
            for code in _SETTING_CODES:
                if command.startswith(code) and len(command) > len(code):
                    value = command[len(code) :]
                    if code in self.readback_shift and value.isdigit():
                        value = str(int(value) + self.readback_shift[code])
                    self.values[code] = value
                    break
        elif command.startswith("mt"):
            self.values["mt"] = command[2:]
        else:
            return "nack"
        return "ack" + "".join(f"@0{p}@0{p}" for p in pushes)


def free_port() -> int:
    """A local port with nothing listening on it (connection refused)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    """Wait until condition() is true."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        if loop.time() > deadline:
            raise AssertionError("condition not met in time")
        await asyncio.sleep(0.02)
