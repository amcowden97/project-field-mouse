# RC1 Runtime Compatibility

## Configuration compatibility

`BirdNETConfig` is a frozen dataclass in `app/config.py`. Its RC1 fields and
defaults are:

| Field | Default |
| --- | --- |
| `enabled` | `true` |
| `latitude` | `null` |
| `longitude` | `null` |
| `minimum_confidence` | `0.25` |
| `occurrence_threshold` | `0.03` |
| `poll_interval_seconds` | `10` |

The preserved production configuration instead contains
`birdnet.poll_interval`. That name does not occur in repository history, so it
predates or was maintained outside the shared configuration schema.
`poll_interval_seconds` first appeared in repository configuration work on
2026-07-22 and became part of the central dataclass schema in commit `9116930`
on 2026-07-28. The loader previously merged arbitrary TOML fields and expanded
the complete `[birdnet]` mapping into `BirdNETConfig`, which allowed the legacy
name to reach the generated constructor and raise `TypeError`.

RC1 uses configuration migration (Option B). The loader translates
`poll_interval` and `PFM_BIRDNET_POLL_INTERVAL` to
`poll_interval_seconds`. If both TOML names are present with different values,
loading fails explicitly instead of choosing one silently.

## BirdNET package compatibility

The failed candidate reported `birdnet==0.2.16` but raised:

```text
No module named 'birdnet.acoustic.inference.prediction_strategy'
```

The official 0.2.16 source tag and PyPI wheel both contain:

```text
birdnet/acoustic/inference/__init__.py
birdnet/acoustic/inference/session.py
birdnet/acoustic/inference/prediction_strategy.py
birdnet/acoustic/inference/encoding_strategy.py
birdnet/acoustic/inference/strategy.py
```

`session.py` imports `PredictionStrategy` from that module. The file is also
listed in the wheel's `RECORD`. It was not renamed or removed in 0.2.16.
Therefore the candidate contained an incomplete or shadowed BirdNET
installation even though package metadata and `pip check` succeeded. No
Project Field Mouse source tree contains a top-level `birdnet` package, so
there is no evidence that a repository-local development module shadowed the
dependency.

The runtime constraint now selects the exact universal 0.2.16 wheel by URL and
SHA-256:

```text
e26ee0419446d3cf634a8f5fb65182626590063f2c0a1ed7cb72659a9ce1ce69
```

The expected installed location is:

```text
<release>/.venv/lib/python3.13/site-packages/birdnet/__init__.py
```

The prior candidate's exact `birdnet.__file__` output and filesystem inventory
were not captured in the repository evidence. The new preflight prints the
resolved location so a shadowed or incomplete installation is visible before
activation.

## Startup preflight

Run this read-only gate from the candidate release before migrations or any
service switch:

```bash
python -m app.preflight
```

It verifies, in order:

1. `import app`
2. `from app.config import BirdNETConfig`
3. `import birdnet`, version `0.2.16`, and resolved package location
4. `from birdnet.acoustic.inference import prediction_strategy`

It stops at the first failure, writes a clear error to stderr, and returns
nonzero. It does not modify configuration, databases, services, or logs.
`python -m app.cli migrate` invokes the same gate before configuration loading
and before any migration operation. Infrastructure should invoke the
standalone gate before service activation; no deployment or rollback tooling
was changed in this branch.

The target duration is less than 10 seconds. Treat a slower result as a failed
activation gate and retain its stdout/stderr with the deployment log.

## Compatibility matrix

| Component | Expected version | Installed version in last Pi evidence | Status |
| --- | --- | --- | --- |
| Python | `>=3.11,<3.14`; RC1 Pi uses `3.13` | `3.13` | Compatible |
| TensorFlow | `2.21.0` | `2.21.0` | Compatible |
| BirdNET | exact canonical wheel `0.2.16` | metadata `0.2.16`; package contents incomplete or shadowed | Corrected constraint; Pi revalidation required |
| Gunicorn | `23.0.0` | `23.0.0` | Compatible |
| Flask | `3.1.3` | `3.1.3` | Compatible |

## Runtime assumptions

- Commands run from the candidate release root with its `.venv/bin/python`.
- Python is CPython 3.11 through 3.13; the validated Pi candidate used 3.13.
- Linux ARM64 is supported by the selected BirdNET/TensorFlow backend.
- BirdNET 0.2.16 is installed from the pinned universal wheel, not a local
  checkout or a partial cached tree.
- TensorFlow 2.21.0 is importable before BirdNET model loading.
- The release root precedes unrelated directories on `sys.path`.
- `PFM_CONFIG` selects the preserved station TOML when set.
- Legacy `birdnet.poll_interval` is accepted and migrated in memory.
- Conflicting legacy and current poll interval names abort configuration load.
- Preflight stdout and stderr are retained by the caller.
- No migration or service activation occurs after a nonzero preflight result.

## Required Pi validation

Run from the candidate root using the candidate interpreter:

```bash
python -c "import app"
python -c "import birdnet; print(birdnet.__file__)"
python -m app.cli --help
python -c "from app.config import BirdNETConfig"
python -c "from birdnet.acoustic.inference import prediction_strategy"
python -m app.preflight
```

Also inspect the package tree:

```bash
find .venv -path "*birdnet*"
```

Do not retry cutover unless every command succeeds and the complete preflight
finishes in less than 10 seconds.
