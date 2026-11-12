"""The integration only talks to the configured player.

The runtime half of the "Local only" badge: the real client runs against the
fake player, and every connection attempt made during the config flow,
setup, polling, a reconnect and commands is recorded at the socket level.
All of them must go to the configured address and port. Real network access
beyond 127.0.0.1 is blocked in the tests anyway. The static half is
scripts/check_local_only.py, which is tested here as well.
"""

from __future__ import annotations

from collections.abc import Generator
import importlib.util
import json
from pathlib import Path
import shutil
import socket
from typing import Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.denon_dn500bd import const
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .common import entity_id, make_entry, setup_entry, unload_entry
from .fake_player import FakePlayer, free_port, wait_for

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"


def _load_checker() -> Any:
    spec = importlib.util.spec_from_file_location(
        "check_local_only", ROOT / "scripts" / "check_local_only.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connections() -> Generator[list[tuple[str, Any]]]:
    """Record every outgoing connection and datagram of the process."""
    recorded: list[tuple[str, Any]] = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_sendto = socket.socket.sendto

    def _connect(sock: socket.socket, address: Any) -> Any:
        recorded.append(("connect", address))
        return original_connect(sock, address)

    def _connect_ex(sock: socket.socket, address: Any) -> Any:
        recorded.append(("connect_ex", address))
        return original_connect_ex(sock, address)

    def _sendto(sock: socket.socket, data: bytes, *args: Any) -> Any:
        recorded.append(("sendto", args[-1]))
        return original_sendto(sock, data, *args)

    with (
        patch.object(socket.socket, "connect", _connect),
        patch.object(socket.socket, "connect_ex", _connect_ex),
        patch.object(socket.socket, "sendto", _sendto),
    ):
        yield recorded


def _service_calls(hass: HomeAssistant) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def _record(event: Event) -> None:
        calls.append((event.data["domain"], event.data["service"]))

    hass.bus.async_listen(EVENT_CALL_SERVICE, _record)
    return calls


async def test_all_traffic_goes_to_the_player(
    hass: HomeAssistant,
    player: FakePlayer,
    connections: list[tuple[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config flow, setup, polling, a reconnect and commands only reach the player."""
    monkeypatch.setattr(const, "DEFAULT_POLL_INTERVAL", 0.2)
    service_calls = _service_calls(hass)

    # Config flow: probes the player, then sets the entry up.
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: player.port}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()
    player_id = entity_id(hass, entry, "media_player", "media_player")
    try:
        await wait_for(lambda: hass.states.get(player_id).state == "playing")

        # Polling: a few more status rounds.
        polls = player.received.count("?ST")
        await wait_for(lambda: player.received.count("?ST") >= polls + 3)

        # A dropped connection: the integration reconnects to the same player.
        made = len(connections)
        await player.drop_connections()
        await wait_for(lambda: len(connections) > made)
        await wait_for(lambda: hass.states.get(player_id).state == "playing")

        # Commands of every platform.
        await hass.services.async_call(
            "media_player", "media_pause", {"entity_id": player_id}, blocking=True
        )
        await hass.services.async_call(
            "media_player",
            "volume_mute",
            {"entity_id": player_id, "is_volume_muted": True},
            blocking=True,
        )
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, entry, "number", "dvov"), "value": 2},
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id(hass, entry, "select", "dvvr"), "option": "1080i"},
            blocking=True,
        )
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_id(hass, entry, "switch", "pcap")},
            blocking=True,
        )
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, entry, "button", "menu_home")},
            blocking=True,
        )
        for code in ("2348", "mt00", "DVOV+02", "DVVR5", "PCAP01", "PCHM"):
            assert code in player.received, code
    finally:
        await unload_entry(hass, entry)

    assert connections, "the test made no connections"
    assert {address for _, address in connections} == {(HOST, player.port)}
    assert {kind for kind, _ in connections} == {"connect"}
    # The integration itself called no service: only the test's own calls.
    assert set(service_calls) == {
        ("media_player", "media_pause"),
        ("media_player", "volume_mute"),
        ("number", "set_value"),
        ("select", "select_option"),
        ("switch", "turn_off"),
        ("button", "press"),
    }


async def test_power_on_only_calls_the_configured_entity(
    hass: HomeAssistant, connections: list[tuple[str, Any]]
) -> None:
    """The one exception: power-on calls the configured entity and nothing else."""
    script_calls = async_mock_service(hass, "script", "turn_on")
    port = free_port()
    entry = make_entry(port, options={const.CONF_POWER_ON_ENTITY: "script.denon_on"})
    await setup_entry(hass, entry)
    service_calls = _service_calls(hass)
    player_id = entity_id(hass, entry, "media_player", "media_player")
    try:
        await hass.services.async_call(
            "media_player", "turn_on", {"entity_id": player_id}, blocking=True
        )
        # While the player is off, it keeps looking for it at the same place.
        made = len(connections)
        await wait_for(lambda: len(connections) > made)
    finally:
        await unload_entry(hass, entry)

    assert service_calls == [("media_player", "turn_on"), ("script", "turn_on")]
    assert [call.data["entity_id"] for call in script_calls] == ["script.denon_on"]
    assert {address for _, address in connections} == {(HOST, port)}


def test_static_check_passes() -> None:
    """The integration passes scripts/check_local_only.py."""
    checker = _load_checker()
    assert checker.main(["check_local_only.py"]) == 0


def test_static_check_matches_power_on_domains() -> None:
    """The checker allows exactly the power-on domains the integration uses."""
    checker = _load_checker()
    assert set(const.POWER_ON_SERVICES) == checker.ALLOWED_SERVICE_DOMAINS


def test_static_check_catches_leaks(tmp_path: Path) -> None:
    """The check fails on an integration that could send data elsewhere."""
    checker = _load_checker()
    leaky = tmp_path / "leaky"
    shutil.copytree(
        ROOT / "custom_components" / "denon_dn500bd",
        leaky,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    manifest = json.loads((leaky / "manifest.json").read_text())
    manifest.update(
        iot_class="cloud_polling",
        requirements=["phonehome==1.0"],
        dependencies=["cloud"],
        zeroconf=["_denon._tcp.local."],
    )
    (leaky / "manifest.json").write_text(json.dumps(manifest))
    api = (leaky / "api.py").read_text()
    api = api.replace(
        "asyncio.open_connection(self.host, self.port)", "asyncio.open_connection(self.host, 443)"
    )
    api = api.replace(
        "socket.TCP_NODELAY, 1)",
        "socket.TCP_NODELAY, 1)\n"
        "                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)",
    )
    (leaky / "api.py").write_text(api)
    coordinator = (leaky / "coordinator.py").read_text()
    (leaky / "coordinator.py").write_text(
        coordinator
        + "\n\nasync def _leak(hass):\n"
        + "    await hass.services.async_call('notify', 'notify', {'message': 'hi'})\n"
    )
    (leaky / "helper.so").write_bytes(b"\x7fELF")
    (leaky / "telemetry.py").write_text(
        "import asyncio\n"
        "import socket\n"
        "import subprocess\n"
        "import requests\n"
        "from homeassistant.helpers.aiohttp_client import async_get_clientsession\n"
        "from homeassistant.helpers import network\n\n\n"
        "async def leak(hass):\n"
        "    session = async_get_clientsession(hass)\n"
        "    await session.post('https://telemetry.example.com/collect')\n"
        "    await asyncio.start_server(None, '0.0.0.0', 8080)\n"
        "    await asyncio.open_connection('8.8.8.8', 53)\n"
        "    loop = asyncio.get_running_loop()\n"
        "    await loop.create_datagram_endpoint(None, remote_addr=('10.0.0.5', 161))\n"
        "    await loop.getaddrinfo('player.example.org', 9030)\n"
        "    socket.socket().connect(('192.168.1.10', 9030))\n"
        "    await hass.services.async_call('notify', 'notify', {'message': 'hi'})\n"
        "    __import__('urllib.request')\n"
        "    return 'analytics.vendor.io', b'2606:4700:4700::1111'\n"
    )

    problems = checker.check_manifest(leaky) + checker.check_files(leaky)
    for name in ("api.py", "coordinator.py", "telemetry.py"):
        problems += checker.check_source(leaky / name, f"leaky/{name}")
    text = "\n".join(problems)
    for expected in (
        "iot_class",
        "depends on 'cloud'",
        "discovery through 'zeroconf'",
        "phonehome",
        "helper.so",
        "open_connection() must connect to (self.host, self.port)",
        "uses socket.SO_BROADCAST",
        "coordinator.py:",
        "service call to 'notify' is not allowed",
        "imports socket outside",
        "imports subprocess",
        "imports requests",
        "imports homeassistant.helpers.aiohttp_client",
        "imports homeassistant.helpers.network",
        "async_get_clientsession() creates an HTTP session",
        "session.post() is an HTTP request",
        "start_server() listens",
        "open_connection() outside",
        "create_datagram_endpoint() listens for connections or opens a UDP socket",
        "getaddrinfo() looks up addresses",
        "connect() is raw socket use",
        "uses socket.socket",
        "service call outside",
        "__import__() is not allowed",
        "https://telemetry.example.com",
        "8.8.8.8",
        "10.0.0.5",
        "192.168.1.10",
        "player.example.org",
        "analytics.vendor.io",
        "2606:4700:4700::1111",
    ):
        assert expected in text, expected
    assert checker.main(["check_local_only.py", str(leaky)]) == 1
