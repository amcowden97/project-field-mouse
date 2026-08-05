# Contributing

Install `requirements-dev.txt`, run `pre-commit install`, then validate with:

```bash
ruff check app tests
pytest
python -m compileall -q app
```

Keep Raspberry Pi memory, CPU, disk writes, and offline use in mind. Mock ALSA,
BirdNET, systemd, and sensors. Never commit recordings, precise coordinates, databases,
credentials, or models. Pull requests should state impact, validation, compatibility,
and rollback.

Follow the [Repository Maintenance Policy](docs/REPOSITORY_MAINTENANCE_POLICY.md) for
branch naming, worktrees, temporary clones, release branches, and post-merge cleanup.
