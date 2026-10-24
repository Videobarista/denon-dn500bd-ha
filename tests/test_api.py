"""Tests for the protocol layer (parser, time codes, client)."""

from __future__ import annotations

import pytest

from custom_components.denon_dn500bd import const
from custom_components.denon_dn500bd.api import (
    DenonClient,
    DenonConnectionError,
    clean_text,
    format_hms,
    format_signed,
    parse_burst,
    parse_hhhmmss,
    parse_mmmss,
    parse_number,
    parse_signed,
    split_message,
)

from .fake_player import FakePlayer, free_port, wait_for


@pytest.mark.parametrize(
    ("raw", "marker", "bare", "messages"),
    [
        # Bursts captured from a real DN-500BD MKII.
        (b"ack", "ack", None, []),
        (b"nack", "nack", None, []),
        (b"ack+error", "ack", "error", []),
        (b"ack+unknow", "ack", "unknow", []),
        (b"ack+", "ack", "", []),
        (b"ack+0000113", "ack", "0000113", []),
        (b"ack+@0STDVHM", "ack", "", ["STDVHM"]),
        (b"ack+@0CDTO@0CDTC@0CDTC", "ack", "", ["CDTO", "CDTC", "CDTC"]),
        (b"@0CDCI@0CDCIack", "ack", None, ["CDCI", "CDCI"]),
        (b"@0STDVHMack+error@0STDVHM", "ack", "error", ["STDVHM", "STDVHM"]),
        (b"@0STPLack+0000000@0STPL", "ack", "0000000", ["STPL", "STPL"]),
        (
            b"@0PCGpUNKNack+@0tiNULL@0PCGpUNKN@0PCTG0091",
            "ack",
            "",
            ["PCGpUNKN", "tiNULL", "PCGpUNKN", "PCTG0091"],
        ),
        (b"ack@0STPP@0STPP", "ack", None, ["STPP", "STPP"]),
        (b"@0STPL@0STPL", None, None, ["STPL", "STPL"]),
        (b"ack+@0VN00004072DN-500BDUS", "ack", "", ["VN00004072DN-500BDUS"]),
        # A title containing "ack" must survive.
        (b"ack+@0tiBlack Jack", "ack", "", ["tiBlack Jack"]),
    ],
)
def test_parse_burst(raw: bytes, marker: str | None, bare: str | None, messages: list[str]) -> None:
    """Bursts split into marker, bare answer and messages."""
    burst = parse_burst(raw)
    assert burst.marker == marker
    assert burst.bare == bare
    assert burst.messages == messages


def test_split_message() -> None:
    """Codes are matched longest first."""
    assert split_message("STPL") == ("ST", "PL")
    assert split_message("PCTYPBDM") == ("PCTYP", "BDM")
    assert split_message("PCTMDTR") == ("PCTMD", "TR")
    assert split_message("PCDG+eng") == ("PCDG+", "eng")
    assert split_message("DVOV-03") == ("DVOV", "-03")
    assert split_message("BDACH51C") == ("BDACH", "51C")
    assert split_message("XYZ") is None


def test_time_codes() -> None:
    """The hhhmmss / MMMSS time codes become seconds HA understands."""
    assert parse_hhhmmss("0000113") == 73
    assert parse_hhhmmss("0012345") == 1 * 3600 + 23 * 60 + 45
    assert parse_hhhmmss("error") is None
    assert parse_hhhmmss("0006099") is None
    assert parse_mmmss("00113") == 73
    assert parse_mmmss("1201530") == 120 * 60 + 15
    assert parse_mmmss("00160") is None
    assert format_hms(3725) == "1:02:05"
    assert format_hms(None) is None


def test_levels_and_numbers() -> None:
    """Signed levels in the player's own format."""
    assert format_signed(-3, 3) == "-03"
    assert format_signed(10, 3) == "+10"
    assert format_signed(0, 3) == "000"
    assert format_signed(5, 2) == "+5"
    assert format_signed(0, 2) == "00"
    assert parse_signed("-03", -90) == -3
    assert parse_signed("inf", -90) == -90
    assert parse_signed("bad", -90) is None
    assert parse_number("0087") == 87
    assert parse_number("UNKN") is None
    assert clean_text("NULL") is None
    assert clean_text(" Movie ") == "Movie"


async def test_client_request_and_push(player: FakePlayer) -> None:
    """Requests get their answer; pushed messages reach the callback."""
    pushed: list[str] = []
    client = DenonClient("127.0.0.1", player.port, on_messages=pushed.extend)
    await client.connect()
    try:
        reply = await client.request("?PW")
        assert reply.ok
        reply = await client.request("?ET")
        assert reply.bare == "0000113"
        reply = await client.request("?ZZ")
        assert reply.marker == "nack"
        reply = await client.request("2348")
        assert reply.ok
        await wait_for(lambda: "STPP" in pushed)
        player.push("CDTO")
        await wait_for(lambda: "CDTO" in pushed)
    finally:
        await client.close()
    assert not client.connected


async def test_client_connect_refused() -> None:
    """A closed port gives the connection_refused reason."""
    client = DenonClient("127.0.0.1", free_port())
    with pytest.raises(DenonConnectionError) as err:
        await client.connect()
    assert err.value.reason == const.REASON_REFUSED


async def test_client_no_response(player: FakePlayer) -> None:
    """A player that accepts but never answers gives no_response."""
    lost: list[str] = []
    client = DenonClient("127.0.0.1", player.port, on_disconnect=lost.append)
    await client.connect()
    player.respond = False
    with pytest.raises(DenonConnectionError) as err:
        await client.request("?PW")
    assert err.value.reason == const.REASON_NO_RESPONSE
    assert lost == [const.REASON_NO_RESPONSE]
    assert not client.connected


async def test_client_reports_dropped_connection(player: FakePlayer) -> None:
    """The player closing the connection is reported once."""
    lost: list[str] = []
    client = DenonClient("127.0.0.1", player.port, on_disconnect=lost.append)
    await client.connect()
    await player.drop_connections()
    await wait_for(lambda: lost == [const.REASON_LOST])
    assert not client.connected
    with pytest.raises(DenonConnectionError):
        await client.request("?PW")
    await client.close()
