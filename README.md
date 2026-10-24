# Denon DN-500BD MKII for Home Assistant

[![Release](https://img.shields.io/github/v/release/Videobarista/denon-dn500bd-ha)](https://github.com/Videobarista/denon-dn500bd-ha/releases)
[![Ruff](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/ruff.yml/badge.svg?branch=main)](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/ruff.yml)
[![Hassfest](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/hassfest.yml/badge.svg?branch=main)](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/hassfest.yml)
[![HACS](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/hacs.yml/badge.svg?branch=main)](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/hacs.yml)
[![Tests](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/tests.yml)
[![CodeQL](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/Videobarista/denon-dn500bd-ha/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Quality scale: Bronze (aligned)](https://img.shields.io/badge/quality%20scale-Bronze%20(aligned)-cd7f32)](#quality-scale)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Videobarista&repository=denon-dn500bd-ha&category=integration)

Control and monitor a **Denon Professional DN-500BD MKII** Blu-ray / DVD / CD /
media player from Home Assistant over Ethernet (TCP port 9030).

> **Disclaimer:** this is an independent community project. It is **not
> affiliated with, endorsed by or connected to Denon, Denon Professional,
> inMusic Brands or D&M Holdings**. Product names are used for identification
> only. The logo in this repository is a generic drawing, not a Denon logo.

## Features

- **Media player** with play, pause, stop, next/previous chapter, power off,
  power on through an entity of your choice (see [Power on](#power-on)), mute, title/artist/album (CD text and file tags) and the position and
  length of the current chapter or track.
- **Push updates**: the player reports status changes itself (play/pause,
  chapter, tray); a light poll (default every 10 s) keeps the time code in
  step. The media position is extrapolated by Home Assistant, so a playing
  disc does not write a new state every few seconds.
- **Sensors**: connection (with the reason when offline), disc status, disc
  type, playback status, chapter / title numbers, audio format, channels,
  sample rate, audio and subtitle language, elapsed/remaining time, last seen.
- **Settings** (configuration entities): output level, maximum volume,
  picture adjustments, video resolution, aspect ratio, TV system, HDMI colour
  space and deep colour, HDMI and coaxial audio format, dynamic range,
  speaker configuration, time display, remote-control code, auto play, auto
  resume, on-screen display, IR sensor, HDMI CEC, program mode, 1080p24
  conversion, 3D output, PIP and secondary-audio marks.
- **Buttons** for the remote-control functions: tray, home, disc top/pop-up
  menu, options, setup, return, cursor keys, enter, audio track, subtitle,
  angle, colour keys, title skip and front-panel lock.
- **Only what your player supports**: during setup the integration asks the
  player once which settings it can report and caches the answer, so Home
  Assistant starts normally while the player is switched off.
- Entities are named in groups (Audio, Disc, Menu, Navigation, Playback,
  System, Video) so they sort logically. Less common ones are disabled by
  default; enable them in the entity settings.

There is no camera/snapshot entity: the player has no way to send a picture.

## Requirements

- Home Assistant 2025.2 or newer.
- The player connected to the network with its LAN port. Check the IP address
  on the player under **Setup > Network > Information**; a DHCP reservation
  or a fixed address is recommended.
- **Only one controller at a time.** The player accepts a single connection on
  port 9030. Close other control software (Extron, Crestron, Companion, test
  scripts) while Home Assistant is connected.

## Installation

### HACS (custom repository)

1. In HACS, open the menu (three dots) and choose **Custom repositories**.
2. Add `https://github.com/Videobarista/denon-dn500bd-ha` with category
   **Integration**.
3. Install **Denon DN-500BD MKII** and restart Home Assistant.

Or use the **Open in HACS** badge above.

### Manual

Copy `custom_components/denon_dn500bd` into the `custom_components` folder of
your Home Assistant configuration and restart Home Assistant.

## Configuration

**Settings > Devices & services > Add integration > Denon DN-500BD MKII**

| Field | Description |
| --- | --- |
| Host | IP address or hostname of the player. |
| Port | `9030` (the player's control port). |
| Add even if the player is switched off now | Creates the entry without testing the connection. The supported settings are detected the first time the player answers; the setting entities then appear by themselves. |

Options (**Configure** on the integration):

| Option | Description |
| --- | --- |
| Status poll interval | Seconds between light status polls (5-60, default 10). |
| Power-on entity | Script, switch, input boolean, button or input button that switches the player on (see [Power on](#power-on)). Leave empty to hide the power-on button. |
| Detect supported features again | Clears the cached capabilities, for example after a firmware update. |

The address can be changed later with **Reconfigure**.

## Behaviour when the player is off or unreachable

A switched off player is a normal state, not an error:

- Setup never fails because of it, and nothing is logged above INFO.
- The **Connection** sensor stays available and shows `offline` with the
  reason in its `reason` attribute. The media player shows **off**; the other
  entities are unavailable.
- An unreachable player is noticed within about 20 seconds (5 s timeouts; a
  poll stops at the first request that gets no answer).
- While offline, one small request is tried every 10 s for the first two
  minutes, then every 20 s, and after five minutes every 30 s. After a power
  on through the power-on entity it tries every 5 s for three minutes. As soon
  as the player answers, everything is refreshed and push updates resume. The
  integration never gives up.
- A dropped connection first gets one quick reconnect attempt, so a short
  network hiccup does not make the player flip to offline.
- Commands sent while the player is offline, or refused by the player, are
  only logged at debug level. No error appears in the UI.

### Power on

Power off works over the network, power on does not: in standby the player
switches its network port off completely (it does not even answer on the
network any more), so nothing can reach it over Ethernet.

To switch it on from Home Assistant, pick a **power-on entity** in the
options: a script, switch, input boolean, button or input button that powers
the player on, for example through an IR blaster, an RS-232 gateway or the
remote-control input. The media player then gets a power-on button that runs
this entity and looks for the player every 5 s while it boots. Without a
power-on entity the power-on button is hidden.

## Troubleshooting

| Connection reason | Meaning | What to do |
| --- | --- | --- |
| `connect_timeout` | Nothing answers at this address: the player is in standby (its network port is off) or switched off at the mains, the cable is unplugged or the IP address is wrong. | Switch the player on. Otherwise check power and cable, give the player a DHCP reservation and update the address with **Reconfigure**. |
| `host_unreachable` | The address does not answer on the network at all: usually the player in standby, otherwise no route to its network. | Switch the player on. If it is on, check VLANs, routing and firewall rules. |
| `connection_refused` | The player is on but refuses the connection: another controller holds the single connection on port 9030. | Close other control software. |
| `no_response` | The connection opens but the player does not answer within 5 s: standby, or its network interface is stuck. | Wake the player. If it keeps happening while the player is on, power-cycle it (a known issue of this player's LAN port). |
| `connection_lost` | The player closed the connection (switched off, rebooted, or another controller took over). | Usually recovers by itself within 10-30 s. |
| `network_error` | Any other network error. | Enable debug logging (below) and check the log. |
| `starting` | Home Assistant is still starting the integration. | Wait a few seconds. |

Other questions:

| Symptom | Explanation |
| --- | --- |
| Play, pause or next does nothing | The player refuses commands during unskippable disc content (warnings, trailers) and in some disc menus. This is expected and only logged at debug level. |
| No title for Blu-ray or DVD | Discs do not report a title; only CD text and file tags (USB/SD) do. |
| Position starts again at 0 | Position and length are those of the current chapter (DVD/BD) or track (CD/files), as reported by the player. |
| A setting entity is missing | It is disabled by default (enable it), or your player did not report it during the probe: use **Detect supported features again** with the player switched on. |
| A select shows `unknown` | The player reports a value that is not in the documented list (for example video resolution `7`). |

Debug logging:

```yaml
logger:
  logs:
    custom_components.denon_dn500bd: debug
```

The diagnostics download (device page > **Download diagnostics**) contains the
raw status values and never the IP address.

## Protocol notes

Built from the DN-500BD MKII *Serial Command Protocol Guide* (v1.1) and
measured on a real player (firmware 00004072). On the LAN port the player
differs from the RS-232 description:

- Replies are plain text without a terminator: `ack`, `nack`, or `ack+`
  followed by the answer (`@0STPL`, `0000113`, `error`, `unknow`).
- Status changes are pushed by the player (each one twice) and can arrive
  before or after the reply to a request.
- `?ET` / `?RM` answer `hhhmmss` without the `@0ET` prefix; the integration
  converts them to seconds for Home Assistant.
- Several settings that the guide lists as write-only can also be read back
  (mute, output level, picture, audio and video settings); those are what the
  capability probe looks for.
- Fast forward / rewind are not offered: the guide lists conflicting codes.

## Quality scale

This custom integration is **aligned with the Home Assistant quality scale:
Bronze**. Home Assistant only grades core integrations, so this is a
self-assessment; see [`quality_scale.yaml`](custom_components/denon_dn500bd/quality_scale.yaml).
Tests cover the config flow, the protocol parser, the offline behaviour and
reconnection.

## Removal

1. **Settings > Devices & services > Denon DN-500BD MKII > ⋮ > Delete**.
2. Remove the repository in HACS (or delete
   `custom_components/denon_dn500bd`) and restart Home Assistant.

## License

[MIT](LICENSE). Not affiliated with Denon; see the disclaimer at the top.
