"""Constants for the Denon DN-500BD MKII integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "denon_dn500bd"

MANUFACTURER: Final = "Denon Professional"
MODEL: Final = "DN-500BD MKII"
DEFAULT_TITLE: Final = "Denon DN-500BD MKII"
# Title used by v1.0.x, renamed on setup.
OLD_DEFAULT_TITLE: Final = "DN-500BD MKII"

DEFAULT_PORT: Final = 9030

CONF_CAPABILITIES: Final = "capabilities"
CONF_MODEL_ID: Final = "model_id"
CONF_SW_VERSION: Final = "sw_version"
CONF_ADD_OFFLINE: Final = "add_offline"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_REPROBE: Final = "reprobe"
CONF_POWER_ON_ENTITY: Final = "power_on_entity"

# The player switches its network port off in standby, so it can only be
# powered on by something else: an entity of one of these domains, called
# with the matching action.
POWER_ON_SERVICES: Final = {
    "script": "turn_on",
    "switch": "turn_on",
    "input_boolean": "turn_on",
    "button": "press",
    "input_button": "press",
}

DEFAULT_POLL_INTERVAL: Final = 10
MIN_POLL_INTERVAL: Final = 5
MAX_POLL_INTERVAL: Final = 60

# Settings (mute, picture, audio ...) are re-read at this interval; the light
# status poll runs every poll interval and the player pushes changes itself.
FULL_REFRESH_INTERVAL: Final = 60.0

# Timing (module attributes so the tests can shorten them).
CONNECT_TIMEOUT: Final = 5.0
REQUEST_TIMEOUT: Final = 5.0
# Offline: one small request every 10 s for the first 2 minutes, then every
# 20 s, after 5 minutes every 30 s. Never gives up.
RETRY_FIRST: Final = 10.0
RETRY_MIDDLE: Final = 20.0
RETRY_MAX: Final = 30.0
FAST_RETRY_PERIOD: Final = 120.0
MIDDLE_RETRY_PERIOD: Final = 300.0
# After a power-on through the configured entity: try every 5 s for 3 minutes.
RETRY_POWER_ON: Final = 5.0
POWER_ON_WINDOW: Final = 180.0
FIRST_ATTEMPT_TIMEOUT: Final = 12.0

# The protocol asks for >= 30 ms between commands on the LAN port.
COMMAND_GAP: Final = 0.04
# A burst of bytes from the player is complete after this much silence.
BURST_IDLE: Final = 0.03
# A refresh requested by a push notification or a command is delayed a bit.
REFRESH_DELAY_PUSH: Final = 0.5
REFRESH_DELAY_COMMAND: Final = 1.0

# Why the player is offline (also the translation keys of the Connection sensor).
REASON_STARTING: Final = "starting"
REASON_REFUSED: Final = "connection_refused"
REASON_TIMEOUT: Final = "connect_timeout"
REASON_UNREACHABLE: Final = "host_unreachable"
REASON_NO_RESPONSE: Final = "no_response"
REASON_LOST: Final = "connection_lost"
REASON_NETWORK: Final = "network_error"
