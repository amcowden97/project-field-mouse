# Developer quick start

Requirements are Python 3.11+, Git, and no Raspberry Pi hardware.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
scripts/pfm --config config/development.toml config init --name "Dev Station"
scripts/pfm --config config/development.toml simulate --mode high --count 20
flask --app app.web.app run
```

Open `http://127.0.0.1:5000`, then run `pytest`, `ruff check app tests`, and
`pre-commit run --all-files`. Use `pfm doctor`, `pfm health`, and `pfm logs` for
diagnostics. Do not use the production config or database for simulator work.
