# Contributing

Thank you for helping Project Field Mouse support reliable, accessible wildlife
monitoring. Documentation, testing, hardware compatibility reports, bug fixes, and
focused enhancements are welcome.

## Before you begin

- Use GitHub Discussions for setup questions and design exploration.
- Search existing issues before filing a bug or proposal.
- Do not post recordings, precise station coordinates, credentials, hostnames, or other
  sensitive field data.
- Report security concerns privately according to [SECURITY.md](SECURITY.md).

## Development setup

Follow the [developer quick start](docs/DEVELOPMENT.md). Install
`requirements-dev.txt` and enable the repository checks:

```bash
python -m pip install -r requirements-dev.txt
pre-commit install
```

No Raspberry Pi or BirdNET model is required for the standard test suite. Mock ALSA,
BirdNET, systemd, and hardware sensors in tests.

## Making a change

Create a focused branch using the conventions in the
[Repository Maintenance Policy](docs/REPOSITORY_MAINTENANCE_POLICY.md). Keep unrelated
formatting or refactoring out of the same pull request. Add or update tests and public
documentation when behavior, configuration, or operator expectations change.

Keep Raspberry Pi memory, CPU, disk writes, offline use, and backward-compatible
configuration in mind. Never commit recordings, precise coordinates, databases,
credentials, or model files.

## Validation

Run before opening a pull request:

```bash
ruff check app tests
pytest
python -m compileall -q app
pre-commit run --all-files
```

Environment-specific changes should also include relevant Raspberry Pi validation. If
a check cannot run locally, explain why and provide the closest available evidence.

## Pull requests

Pull requests should be small enough to review and must describe purpose, validation,
Raspberry Pi or configuration impact, migration considerations, and rollback. Link the
related issue where applicable. By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

Follow the [Repository Maintenance Policy](docs/REPOSITORY_MAINTENANCE_POLICY.md) for
branch naming, worktrees, temporary clones, release branches, and post-merge cleanup.
