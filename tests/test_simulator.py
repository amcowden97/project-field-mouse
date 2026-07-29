from pathlib import Path

from app.config import load_config
from app.simulator import simulate


def test_simulator_populates_real_schema(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "station.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        """
[station]
id = "simulation"
name = "Simulation"
timezone = "UTC"
[storage]
database_path = "data/simulation.db"
recordings_directory = "data/recordings"
backups_directory = "backups"
""",
        encoding="utf-8",
    )
    result = simulate(load_config(config_path, {}), "detections", count=4)
    assert result["recordings"] == 4
    assert result["detections"] == 4
    assert list((tmp_path / "data" / "recordings").rglob("*.wav"))
