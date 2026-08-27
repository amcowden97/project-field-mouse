# Developer quick start

Requirements are Python 3.11+, Git, and no Raspberry Pi hardware.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
scripts/pfm --config data/processed/development.toml config init --name "Dev Station"
scripts/pfm --config data/processed/development.toml simulate --mode high --count 20
PFM_CONFIG=data/processed/development.toml flask --app app.web.app run --port 8000
```

Open `http://127.0.0.1:8000`, then run `pytest`, `ruff check app tests`, and
`pre-commit run --all-files`. Use `pfm doctor`, `pfm health`, and `pfm logs` for
diagnostics. The `data/processed/` development configuration and its generated data are
ignored by Git. Do not use the production config or database for simulator work.

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`, invoke
`python -m app.cli` in place of `scripts/pfm`, and set the Flask configuration with
`$env:PFM_CONFIG = "data/processed/development.toml"` before starting Flask.

See [configuration](CONFIGURATION.md), [architecture](ARCHITECTURE.md), and
[troubleshooting](TROUBLESHOOTING.md) for the next steps.
