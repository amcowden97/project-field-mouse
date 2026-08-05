# RC1 Runtime Candidate Validation

## Decision

**BLOCKED**

No production cutover was attempted. Legacy services and production data
remained active and unchanged throughout the rehearsal.

## Integrated input

The isolated staging tree at
`/home/amcowden97/pfm-rc1-runtime-staging` combines the existing RC1 staging
source and infrastructure deployer with:

- `19c9687` — restore `BirdNETConfig` compatibility;
- `a3c50d6` — select the canonical BirdNET wheel;
- `8064196` — add startup preflight validation;
- `41cda84` — document the runtime compatibility matrix.

Staging, bootstrap, and installed deployers remained identical:

```text
451f5cf0b6f13fd412ccf17fea40e9b924260241de5e681a65592150a308ec74
```

No branch was merged to `master`.

## Runtime preflights

The isolated Pi candidate root was:

```text
/home/amcowden97/pfm-rc1-runtime-candidate
```

The ordered preflight completed successfully in 1.06 seconds:

```text
RUNTIME PREFLIGHT OK: application import
RUNTIME PREFLIGHT OK: configuration import
RUNTIME PREFLIGHT OK: BirdNET package
RUNTIME PREFLIGHT OK: BirdNET prediction strategy
```

These individual checks also passed:

- `import app`;
- `from app.config import BirdNETConfig`;
- `python -m app.cli --help`;
- `import birdnet`;
- `from birdnet.acoustic.inference import prediction_strategy`.

The legacy `birdnet.poll_interval` rehearsal field loaded as
`poll_interval_seconds=10`.

## BirdNET wheel

```text
Version: 0.2.16
SHA-256: e26ee0419446d3cf634a8f5fb65182626590063f2c0a1ed7cb72659a9ce1ce69
Package owner: amcowden97:amcowden97
```

Resolved paths:

```text
/home/amcowden97/pfm-rc1-runtime-candidate/.venv/lib/python3.13/site-packages/birdnet/__init__.py
/home/amcowden97/pfm-rc1-runtime-candidate/.venv/lib/python3.13/site-packages/birdnet/acoustic/inference/prediction_strategy.py
```

The prediction-strategy import succeeded.

## Activation rehearsal

An isolated configuration referenced a copied SQLite database and rehearsal
logs/backups. It retained read-only access to legacy recording files. No
production database or service was used as a write target.

Migration dry-run is not implemented. The read-only `migrate --history`
substitute reported migrations `0001` through `0004`, and the copied database
passed `PRAGMA integrity_check`.

Gunicorn 23.0.0 started successfully through the candidate interpreter on
`127.0.0.1:18000`. Its worker booted and served requests without configuration
or import errors.

The BirdNET worker started through the candidate interpreter against the copied
database, found no pending recording, stopped normally, and exited 0. The
copied database retained integrity and unchanged counts.

Manual Gunicorn was stopped after rehearsal. Port 18000 was released. Legacy
recorder, BirdNET, and dashboard services remained active on port 8000.

## Blocking gates

Two HTTP gates did not pass:

1. `/health` returned HTTP 503. Application, database, microphone, network, and
   systemd service checks were healthy, but disk usage was 89.9%, exceeding the
   configured warning threshold.
2. `/metrics` returned HTTP 404; the candidate application does not expose the
   expected endpoint.

The isolated candidate venv and retained failed production candidate consume
approximately 2 GiB each. About 5.5 GiB remained free during rehearsal.

Do not attempt cutover until disk use is below the health threshold and the
release owner determines whether `/metrics` is an RC1-required route or the
validation expectation should be changed explicitly.
