# Security Policy

## Supported versions

Only the latest release of this integration receives fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's
**Report a vulnerability** button on the **Security** tab of this repository
to send a private report. You will get an answer as soon as possible.

## Scope and threat model

The Denon DN-500BD MKII is controlled over an unauthenticated, unencrypted
TCP connection (port 9030) on the local network. The integration cannot add
authentication or encryption to the player, so it relies on the network:
keep the player in a separate VLAN and allow only Home Assistant to reach
TCP 9030 (see the Security section of the README).

Within that scope the integration:

- sends only commands from fixed tables, behind a guard that refuses
  non-printable characters, the protocol's start/end characters and
  oversized packets;
- validates every user input (host, port, poll interval, power-on entity);
- treats the player's answers as untrusted (size limits, value caps,
  defensive parsing, errors never stop the connection);
- limits the command rate and the number of waiting commands;
- opens no listening ports and uses no third-party Python packages;
- keeps the player's address out of log messages and diagnostics.

Reports about any of these are welcome.
