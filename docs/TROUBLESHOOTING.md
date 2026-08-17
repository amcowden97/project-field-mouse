# Troubleshooting

Start with the supported diagnostics:

```bash
scripts/pfm doctor
scripts/pfm health --pretty
scripts/pfm status
scripts/pfm logs
```

When using a non-default configuration, place `--config PATH` before the command.
Remove precise coordinates, hostnames, tokens, and private recording data before
sharing output.

## The microphone is unavailable

Run `arecord -l`, confirm the configured `audio.device`, and verify the service account
can access the audio device. USB numbering can change after reconnecting hardware.

## BirdNET produces no detections

Confirm recordings exist and are nonempty, BirdNET dependencies and model resources are
installed, and the worker service is running. Review confidence and occurrence
thresholds; avoid lowering them on a production station without recording the change.

## The dashboard does not open

Check `dashboard.host` and `dashboard.port`, then inspect `pfm status` and `pfm logs`.
The developer server command in [DEVELOPMENT.md](DEVELOPMENT.md) uses port 8000. Do not
expose the dashboard directly to the public internet.

## Database or migration errors occur

Stop write-producing services, create and verify a backup, then run `pfm migrate
--history` and consult [MIGRATIONS.md](MIGRATIONS.md). Do not edit migration history or
replace the database before preserving diagnostic evidence.

## Disk space is low

Run the health check, inspect configured recording and backup paths, and verify cleanup
timers. Preserve uncertain or rare-species recordings until reviewed. See
[OPERATIONS.md](OPERATIONS.md) and [BACKUPS.md](BACKUPS.md).

## Tests fail only on non-Linux hardware

The normal suite mocks Raspberry Pi interfaces, but some OS APIs vary. Include the OS,
Python version, failing test, and complete sanitized traceback in a bug report. Do not
silence a platform-specific failure without documenting why.

If these steps do not resolve the problem, search existing GitHub issues and open a bug
report with the version, reproduction steps, sanitized health output, and relevant logs.
