# Simulator guide

The simulator is the recommended hardware-free development workflow:

```bash
python -m venv .venv
. .venv/bin/activate
pip install flask psutil pytest
scripts/pfm --config config/development.toml config init --name "Dev Station"
scripts/pfm --config config/development.toml simulate --mode detections
flask --app app.web.app run --port 8000
```

Modes are `samples`, `detections`, `high`, `low`, `offline`, and `errors`. Synthetic
one-second WAV files are generated from the standard library and detections come from
the bundled sample catalog. All records use the production schema and paths.

Simulation is deterministic by default; change `--seed` for another sequence. Use a
dedicated development config because runs append data. When the Bird Verification
package is present, each simulated detection is passed through its public manager API.
