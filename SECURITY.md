# Security Policy

## Supported versions

Only the latest release of this integration receives fixes.

## Reporting a vulnerability

Please do not open a public issue for security problems. Report them
privately through GitHub's form:

https://github.com/Videobarista/denon-dn500bd-ha/security/advisories/new

This is the **Report a vulnerability** button on the **Security** tab of
this repository. Please include the version, what you found and how to
reproduce it.

## What happens next

- You get a first answer within 14 days.
- A confirmed vulnerability is fixed in a new release as soon as possible,
  normally within 90 days.
- Disclosure is coordinated with you: the advisory is published once the
  fixed release is out, with credit if you want it.

## What counts as a vulnerability

Anything that makes the integration do more than its job: sending other
commands to the player than the built-in ones, crashing or hanging Home
Assistant, exposing data it should not, or leaking the player's address.
Weaknesses of the player itself (its control port has no login or
encryption) are outside the integration's reach; see below.

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
  defensive parsing, errors never stop the connection); the parser is
  fuzzed with Atheris in CI;
- limits the command rate and the number of waiting commands;
- opens no listening ports and uses no third-party Python packages;
- keeps the player's address out of log messages and diagnostics.

Reports about any of these are welcome.
