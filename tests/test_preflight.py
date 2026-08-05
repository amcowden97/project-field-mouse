from pathlib import Path
from types import SimpleNamespace

import app.preflight as preflight


def test_preflight_stops_on_first_failure(capsys) -> None:
    checks = (
        preflight.PreflightCheck("first", lambda: "ok"),
        preflight.PreflightCheck(
            "second", lambda: (_ for _ in ()).throw(ModuleNotFoundError("missing"))
        ),
        preflight.PreflightCheck("never", lambda: "unexpected"),
    )
    original = preflight.CHECKS
    preflight.CHECKS = checks
    try:
        assert preflight.run_preflight() == 1
    finally:
        preflight.CHECKS = original

    output = capsys.readouterr()
    assert "RUNTIME PREFLIGHT OK: first: ok" in output.out
    assert "RUNTIME PREFLIGHT FAILED: second: ModuleNotFoundError: missing" in output.err
    assert "never" not in output.out


def test_birdnet_preflight_reports_version_and_location(monkeypatch) -> None:
    module = SimpleNamespace(__file__="/venv/site-packages/birdnet/__init__.py")
    monkeypatch.setattr(preflight.importlib, "import_module", lambda name: module)
    monkeypatch.setattr(preflight.importlib.metadata, "version", lambda name: "0.2.16")

    detail = preflight._import_birdnet()

    assert detail.startswith("0.2.16 at ")
    location = Path(detail.removeprefix("0.2.16 at "))
    assert location.name == "__init__.py"
    assert location.parent.name == "birdnet"


def test_birdnet_preflight_rejects_wrong_version(monkeypatch) -> None:
    module = SimpleNamespace(__file__="/venv/site-packages/birdnet/__init__.py")
    monkeypatch.setattr(preflight.importlib, "import_module", lambda name: module)
    monkeypatch.setattr(preflight.importlib.metadata, "version", lambda name: "0.2.15")

    try:
        preflight._import_birdnet()
    except RuntimeError as error:
        assert str(error) == "expected birdnet 0.2.16, installed 0.2.15"
    else:
        raise AssertionError("wrong BirdNET version was accepted")
