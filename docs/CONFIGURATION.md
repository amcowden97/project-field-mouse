# Configuration

Project Field Mouse reads TOML configuration from the path passed with `--config`, then
from `PFM_CONFIG`, then from its default path. Environment variables override TOML
values using `PFM_SECTION_KEY`; for example, `PFM_DASHBOARD_PORT=8080` overrides
`dashboard.port`. Comma-separate list values.

## Configuration files

- `config/station.toml` is a versioned example and development baseline. Copy or
  generate a separate file before personalizing it.
- `config/verification.toml` selects verification rules and plugins.
- `config/regions/` and `config/calibration/` contain maintained profiles.
- Production stations use `/etc/fieldmouse/station.toml`.

Create a safe local configuration in the ignored development-data directory:

```bash
scripts/pfm --config data/processed/development.toml config init --name "Dev Station"
scripts/pfm --config data/processed/development.toml config validate
scripts/pfm --config data/processed/development.toml config show
```

## Required station choices

Assign every deployed station a unique, permanent ID and an IANA timezone such as
`America/Los_Angeles`. Select the ALSA capture device with `arecord -l`. Review storage
paths and retention limits before unattended use.

BirdNET latitude and longitude affect species occurrence filtering. Treat precise
coordinates as private: use an appropriately coarse location, keep personalized
configuration outside Git, and never include coordinates in issues or logs.

## Safe environment examples

`.env.example` documents non-secret local overrides, but the application does not load
that file automatically. Export only the values needed by your shell, service manager,
or container. Never commit `.env`, tokens, credentials, or station-specific secrets.

After any configuration change, run `scripts/pfm config validate` with the same config
path used by the service, then run `scripts/verify.sh` on deployed stations.
