# CLI reference

Run `scripts/pfm`, or `python -m app.cli` in an activated environment. Place global
`--config PATH` before the command.

- `config init|validate|show`: create and inspect station configuration.
- `simulate --mode MODE [--count N]`: generate realistic development activity.
- `status`, `health --pretty`, `doctor`, `logs`: inspect the station.
- `migrate [--history]`: safely update or display database schema history.
- `backup`, `verify-backup ARCHIVE`, `restore ARCHIVE`: protect station state.
- `install`, `update`: run the Linux lifecycle workflows.
- `--version`: print SemVer metadata.

Commands return zero on success and emit concise errors to standard error. `PFM_CONFIG`
sets the default configuration; `PFM_PYTHON` selects the wrapper's interpreter.
