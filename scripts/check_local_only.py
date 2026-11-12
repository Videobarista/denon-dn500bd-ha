"""Check that a Home Assistant integration only talks to its own device.

Runs with the Python standard library only (no installs), on Python 3.10+.
It reads the integration's manifest and source code and fails when it finds
anything that could send data elsewhere:

1. Manifest: the IoT class is local; no dependencies, no discovery and no
   Python requirements other than the ones explicitly allowed below.
2. Files: only Python, JSON, YAML and PNG files (no compiled code).
3. Imports: only modules on the allow list below; network libraries, Home
   Assistant's HTTP, cloud and webhook parts and dynamic imports always fail.
4. No listeners: nothing opens a server, webhook, HTTP view or UDP socket.
5. One connection: only the allowed file opens a connection, and only to the
   client's configured host and port. No raw socket use, no DNS lookups of
   other names, no subprocesses.
6. Service calls: only the allowed file calls a Home Assistant service, and
   only in the allowed domains.
7. No hard-coded addresses: no URLs with a host, host names, IPv4 or IPv6
   addresses in the code (text and bytes); every address comes from the
   configuration.

What it does not cover: Home Assistant itself, and the code of an allowed
requirement. The runtime side (every connection goes to the configured host
and port) is checked by tests/test_local_only.py.

Usage: python3 scripts/check_local_only.py [path/to/custom_components/<domain>]
"""

from __future__ import annotations

import ast
import ipaddress
import json
from pathlib import Path
import re
import sys

# ---------------------------------------------------------------------------
# Settings for this integration: the Denon DN-500BD MKII LAN protocol
# ---------------------------------------------------------------------------
# The player is controlled over one plain TCP connection (port 9030 by
# default) that the integration opens itself with asyncio streams. There is
# no HTTP, UDP/SNMP, TLS, discovery or device library involved.

# The only file that may open a connection ...
CONNECTION_FILES = {"api.py"}
# ... with exactly these arguments: the client's host and port, which come
# from the config entry (the tests check this at runtime).
CONNECTION_TARGET = ("self.host", "self.port")

# Exception 1: api.py imports the socket module, but only to switch off
# Nagle's algorithm (TCP_NODELAY) on the connection asyncio already opened to
# the player, so short commands are sent at once. Only these two constants
# may be used; any other use of the socket module fails.
SOCKET_FILES = {"api.py"}
SOCKET_ATTRIBUTES = {"IPPROTO_TCP", "TCP_NODELAY"}

# Exception 2: the player's network port is off in standby, so it can be
# switched on through a Home Assistant entity the user picks in the options
# (IR blaster, RS-232 bridge, smart plug or script). coordinator.py calls that
# entity's turn_on or press service. It is the only service call, and only
# these domains may be called (the keys of const.POWER_ON_SERVICES; a test
# keeps the two equal). What the chosen entity does is up to its own
# integration.
SERVICE_CALL_FILES = {"coordinator.py"}
ALLOWED_SERVICE_DOMAINS = {"button", "input_boolean", "input_button", "script", "switch"}

# No Python requirements, no dependencies, no literal addresses.
ALLOWED_REQUIREMENTS: set[str] = set()
ALLOWED_DEPENDENCIES: set[str] = set()
ALLOWED_ADDRESSES: set[str] = set()

# Every module the integration may import. Relative imports of its own files
# are always allowed; anything else has to be added here on purpose.
ALLOWED_IMPORTS = {
    # Standard library (socket: see exception 1).
    "__future__",
    "asyncio",
    "collections.abc",
    "dataclasses",
    "datetime",
    "enum",
    "errno",
    "functools",
    "ipaddress",
    "logging",
    "re",
    "socket",
    "time",
    "typing",
    # Home Assistant's schema library.
    "voluptuous",
    # Home Assistant: entity platforms and core helpers, nothing that talks to
    # the network.
    "homeassistant.components.button",
    "homeassistant.components.diagnostics",
    "homeassistant.components.media_player",
    "homeassistant.components.number",
    "homeassistant.components.select",
    "homeassistant.components.sensor",
    "homeassistant.components.switch",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.typing",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.util.dt",
}

# Files the integration folder may contain (__pycache__ is ignored).
ALLOWED_FILE_TYPES = {".json", ".png", ".py", ".yaml"}

# ---------------------------------------------------------------------------
# Rules (the same for every integration)
# ---------------------------------------------------------------------------
# Never allowed, even when the allow list above would match.
FORBIDDEN_MODULES = {
    "aiohttp",
    "ftplib",
    "http",
    "httpx",
    "importlib",
    "multiprocessing",
    "paho",
    "poplib",
    "pty",
    "requests",
    "smtplib",
    "socketserver",
    "ssl",
    "subprocess",
    "telnetlib",
    "urllib",
    "websockets",
    "xmlrpc",
    "homeassistant.components.cloud",
    "homeassistant.components.http",
    "homeassistant.components.mqtt",
    "homeassistant.components.network",
    "homeassistant.components.webhook",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.httpx_client",
    "homeassistant.helpers.network",
    "homeassistant.helpers.script",
    "homeassistant.helpers.service",
}
# The integration has no dependencies and no discovery: the address is
# entered by hand.
DISCOVERY_KEYS = {"bluetooth", "dhcp", "homekit", "mqtt", "ssdp", "usb", "zeroconf"}
# Calls that listen for incoming connections or open UDP sockets.
LISTEN_CALLS = {
    "create_datagram_endpoint",
    "create_server",
    "create_unix_server",
    "register_view",
    "start_server",
    "start_unix_server",
}
# Calls that open outgoing connections.
CONNECT_CALLS = {
    "create_connection",
    "create_unix_connection",
    "open_connection",
    "open_unix_connection",
    "sock_connect",
    "ws_connect",
}
# Raw socket and name lookup calls.
SOCKET_CALLS = {"bind", "listen", "accept", "sendto", "sendmsg", "recvfrom", "connect_ex"}
LOOKUP_CALLS = {"getaddrinfo", "getnameinfo", "gethostbyaddr", "gethostbyname", "gethostbyname_ex"}
# HTTP client sessions and requests.
SESSION_FACTORIES = {"async_create_clientsession", "async_get_clientsession", "ClientSession"}
SESSION_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "request"}
# Ways around the import check, and processes that could talk to anything.
DYNAMIC_CALLS = {
    "__import__",
    "create_subprocess_exec",
    "create_subprocess_shell",
    "eval",
    "exec",
    "import_module",
    "popen",
    "system",
}
SERVICE_CALLS = {"async_call", "call"}

_URL = re.compile(r"\b(?:https?|wss?|ftp|mqtts?|tcp|udp|ssh|telnet)://([^\s/'\"{}]+)", re.I)
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"(?<![\w:.])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:.])", re.I)
_TLDS = (
    "com|net|org|io|dev|app|cloud|ai|co|eu|nl|de|be|uk|fr|info|biz|me|tv|us|"
    "xyz|online|site|tech|ru|cn|jp|ly|gg|sh"
)
_HOSTNAME = re.compile(rf"(?:[a-z0-9-]+\.)+(?:{_TLDS})\.?", re.I)
# Loopback, "this host" and documentation addresses never leave the machine.
_HARMLESS_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "0.0.0.0/8",
        "127.0.0.0/8",
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "::/128",
        "::1/128",
        "2001:db8::/32",
    )
]


def _harmless_ip(text: str) -> bool:
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return True  # Not an address (a version number or a time, for instance).
    return any(address in network for network in _HARMLESS_NETWORKS)


def _dotted(node: ast.expr) -> str:
    """Return 'self.host' for an attribute chain, '' for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted(node.value)
        return f"{owner}.{node.attr}" if owner else ""
    return ""


def _call_name(node: ast.Call) -> tuple[str, str]:
    """Return (attribute or function name, name of the object it is called on)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        owner = func.value
        if isinstance(owner, ast.Attribute):
            return func.attr, owner.attr
        if isinstance(owner, ast.Name):
            return func.attr, owner.id
        return func.attr, ""
    if isinstance(func, ast.Name):
        return func.id, ""
    return "", ""


def _module_allowed(name: str) -> bool:
    return any(name == m or name.startswith(f"{m}.") for m in ALLOWED_IMPORTS)


def _module_forbidden(name: str) -> bool:
    return any(name == m or name.startswith(f"{m}.") for m in FORBIDDEN_MODULES)


def check_manifest(integration: Path) -> list[str]:
    """Check the manifest for cloud use, discovery and extra requirements."""
    manifest = json.loads((integration / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    iot_class = str(manifest.get("iot_class", ""))
    if not iot_class.startswith("local_"):
        problems.append(f"manifest.json: iot_class is {iot_class!r}, not local_*")
    dependencies = set(manifest.get("dependencies", [])) | set(
        manifest.get("after_dependencies", [])
    )
    for dependency in sorted(dependencies - ALLOWED_DEPENDENCIES):
        problems.append(f"manifest.json: depends on {dependency!r}")
    for key in sorted(DISCOVERY_KEYS & set(manifest)):
        problems.append(f"manifest.json: discovery through {key!r}")
    allowed = {r.lower() for r in ALLOWED_REQUIREMENTS}
    for requirement in manifest.get("requirements", []):
        name = re.split(r"[<>=!~\[; @]", requirement, maxsplit=1)[0].lower()
        if name not in allowed:
            problems.append(f"manifest.json: requirement {requirement!r} is not allowed")
    return problems


def check_files(integration: Path) -> list[str]:
    """Only source, data and image files; no compiled code."""
    problems = []
    for path in sorted(integration.rglob("*")):
        if "__pycache__" in path.parts or not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_FILE_TYPES:
            relative = path.relative_to(integration.parent)
            problems.append(f"{relative}: file type {path.suffix or '(none)'} is not allowed")
    return problems


def _check_text(text: str, where: str) -> list[str]:
    """Hard-coded addresses in one string."""
    if text in ALLOWED_ADDRESSES:
        return []
    problems = [f"{where}: hard-coded address {m.group(0)!r}" for m in _URL.finditer(text)]
    for pattern in (_IPV4, _IPV6):
        for match in pattern.finditer(text):
            if not _harmless_ip(match.group(0)):
                problems.append(f"{where}: hard-coded IP address {match.group(0)!r}")
    if _HOSTNAME.fullmatch(text.strip()):
        problems.append(f"{where}: hard-coded host name {text.strip()!r}")
    return problems


def _check_import(node: ast.Import | ast.ImportFrom, path: Path, where: str) -> list[str]:
    if isinstance(node, ast.ImportFrom) and node.level:
        return []  # The integration's own files.
    if isinstance(node, ast.Import):
        problems = []
        for alias in node.names:
            name = alias.name
            if name == "socket" and alias.asname:
                problems.append(f"{where}: imports socket as {alias.asname}")
            problems += _check_module(name, path, where)
        return problems
    module = node.module or ""
    problems = []
    for alias in node.names:
        full = f"{module}.{alias.name}"
        if module == "socket" and alias.name not in SOCKET_ATTRIBUTES:
            problems.append(f"{where}: imports {full}")
        elif _module_forbidden(module) or _module_forbidden(full):
            problems.append(f"{where}: imports {full}")
        elif _module_allowed(module):
            problems += _check_module(module, path, where)
        else:
            # "from package import submodule": the submodule must be allowed.
            problems += _check_module(full, path, where)
    return problems


def _check_module(name: str, path: Path, where: str) -> list[str]:
    if _module_forbidden(name):
        return [f"{where}: imports {name}"]
    if not _module_allowed(name):
        return [f"{where}: imports {name}, which is not on the allowed list"]
    if name == "socket" and path.name not in SOCKET_FILES:
        return [f"{where}: imports socket outside {sorted(SOCKET_FILES)}"]
    return []


def _check_call(node: ast.Call, path: Path, where: str) -> list[str]:
    name, owner = _call_name(node)
    if name in LISTEN_CALLS:
        return [f"{where}: {name}() listens for connections or opens a UDP socket"]
    if name in CONNECT_CALLS:
        if path.name not in CONNECTION_FILES or name != "open_connection":
            return [f"{where}: {name}() outside {sorted(CONNECTION_FILES)}"]
        target = tuple(_dotted(arg) for arg in node.args)
        if target != CONNECTION_TARGET or node.keywords:
            wanted = ", ".join(CONNECTION_TARGET)
            return [f"{where}: open_connection() must connect to ({wanted}) only"]
        return []
    if name in SOCKET_CALLS or (name == "connect" and (node.args or node.keywords)):
        return [f"{where}: {name}() is raw socket use"]
    if name in LOOKUP_CALLS:
        return [f"{where}: {name}() looks up addresses"]
    if name in SESSION_FACTORIES:
        return [f"{where}: {name}() creates an HTTP session"]
    if name in SESSION_METHODS and "session" in owner.lower():
        return [f"{where}: {owner}.{name}() is an HTTP request"]
    if name in DYNAMIC_CALLS:
        return [f"{where}: {name}() is not allowed"]
    if name in SERVICE_CALLS and owner == "services":
        if path.name not in SERVICE_CALL_FILES:
            return [f"{where}: service call outside {sorted(SERVICE_CALL_FILES)}"]
        domain = node.args[0] if node.args else None
        if isinstance(domain, ast.Constant) and domain.value not in ALLOWED_SERVICE_DOMAINS:
            return [f"{where}: service call to {domain.value!r} is not allowed"]
    return []


def _check_socket_names(tree: ast.AST, relative: str) -> list[str]:
    """The socket module may only be used for the allowed constants."""
    allowed_nodes = set()
    problems = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "socket"
        ):
            if node.attr in SOCKET_ATTRIBUTES:
                allowed_nodes.add(id(node.value))
            else:
                problems.append(f"{relative}:{node.lineno}: uses socket.{node.attr}")
                allowed_nodes.add(id(node.value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "socket" and id(node) not in allowed_nodes:
            problems.append(f"{relative}:{node.lineno}: uses the socket module directly")
    return problems


def check_source(path: Path, relative: str) -> list[str]:
    """Check one Python file of the integration."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    problems = []
    for node in ast.walk(tree):
        where = f"{relative}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            problems += _check_import(node, path, where)
        elif isinstance(node, ast.Call):
            problems += _check_call(node, path, where)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            problems += _check_text(node.value, where)
        elif isinstance(node, ast.Constant) and isinstance(node.value, bytes):
            problems += _check_text(node.value.decode("latin-1"), where)
    problems += _check_socket_names(tree, relative)
    return problems


def find_integration(argv: list[str]) -> Path:
    """Return the integration folder (argument, or the only one in custom_components)."""
    if len(argv) > 1:
        return Path(argv[1])
    root = Path(__file__).resolve().parents[1] / "custom_components"
    folders = [p for p in root.iterdir() if (p / "manifest.json").is_file()]
    if len(folders) != 1:
        raise SystemExit(f"Expected one integration in {root}, found {len(folders)}")
    return folders[0]


def main(argv: list[str]) -> int:
    """Run all checks and report."""
    integration = find_integration(argv)
    problems = check_manifest(integration) + check_files(integration)
    files = sorted(p for p in integration.rglob("*.py") if "__pycache__" not in p.parts)
    for path in files:
        problems += check_source(path, str(path.relative_to(integration.parent)))

    print(f"Local-only check of {integration.name}: {len(files)} Python files")
    if problems:
        for problem in problems:
            print(f"  FAIL {problem}")
        return 1
    print("  OK   manifest: local IoT class, no dependencies, discovery or requirements")
    print("  OK   only source, data and image files; only allowed imports")
    print("  OK   no listeners, webhooks, HTTP, UDP, raw sockets or subprocesses")
    target = ", ".join(CONNECTION_TARGET)
    print(f"  OK   one connection, from {', '.join(sorted(CONNECTION_FILES))}, to ({target})")
    print(f"  OK   service calls only from {', '.join(sorted(SERVICE_CALL_FILES))}")
    print("  OK   no hard-coded addresses")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
