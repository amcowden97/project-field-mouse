# Frequently asked questions

## Do I need a Raspberry Pi to contribute?

No. The developer workflow and simulator run without microphone, BirdNET, systemd, or
sensor hardware. See [DEVELOPMENT.md](DEVELOPMENT.md).

## Which hardware and operating system are supported?

Raspberry Pi 5 with 64-bit Raspberry Pi OS is the primary production target. A USB
microphone and adequate storage are required for field recording. Other Linux systems
may work but should be reported as community-tested unless explicitly validated.

## Does the station require internet access?

Core collection and local dashboard operation are designed to work offline after
dependencies and BirdNET resources are installed. Remote access, updates, and copying
off-device backups require connectivity.

## Where is station data stored?

Paths are controlled by the station configuration. Recordings, the SQLite database,
logs, and backups are runtime data and should not be committed. See
[CONFIGURATION.md](CONFIGURATION.md) and [BACKUPS.md](BACKUPS.md).

## Can I expose the dashboard to the internet?

Not directly. Bind it to a trusted network or place it behind an authenticated TLS
reverse proxy. The project does not claim the development server is an internet-facing
security boundary.

## Can Project Field Mouse monitor species other than birds?

Bird monitoring is the current supported focus. Other taxa are roadmap goals, not
features of the current release.

## How should I report an incorrect identification?

Preserve the relevant non-sensitive evidence, note the model and project version, and
open a reproducible issue. Share audio only when you have the right to do so and it does
not disclose a sensitive location.

## What license applies?

The project is available under the [Apache License 2.0](../LICENSE).
