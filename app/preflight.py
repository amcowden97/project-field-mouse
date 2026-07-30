"""Fast, read-only runtime compatibility checks for RC1 activation."""
from __future__ import annotations

import importlib
import importlib.metadata
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    action: Callable[[], str]


def _import_app() -> str:
    module = importlib.import_module("app")
    return str(Path(module.__file__).resolve())


def _import_config() -> str:
    module = importlib.import_module("app.config")
    getattr(module, "BirdNETConfig")
    return str(Path(module.__file__).resolve())


def _import_birdnet() -> str:
    module = importlib.import_module("birdnet")
    version = importlib.metadata.version("birdnet")
    if version != "0.2.16":
        raise RuntimeError(f"expected birdnet 0.2.16, installed {version}")
    return f"{version} at {Path(module.__file__).resolve()}"


def _import_prediction_strategy() -> str:
    module = importlib.import_module(
        "birdnet.acoustic.inference.prediction_strategy"
    )
    return str(Path(module.__file__).resolve())


CHECKS = (
    PreflightCheck("application import", _import_app),
    PreflightCheck("configuration import", _import_config),
    PreflightCheck("BirdNET package", _import_birdnet),
    PreflightCheck("BirdNET prediction strategy", _import_prediction_strategy),
)


def run_preflight() -> int:
    """Run all checks, stopping at the first failure without changing state."""
    for check in CHECKS:
        try:
            detail = check.action()
        except Exception as error:
            print(
                f"RUNTIME PREFLIGHT FAILED: {check.name}: "
                f"{type(error).__name__}: {error}",
                file=sys.stderr,
            )
            if check.name.startswith("BirdNET"):
                print(
                    "BirdNET must be installed from the pinned 0.2.16 wheel; "
                    "inspect birdnet.__file__ and the installed package contents.",
                    file=sys.stderr,
                )
            return 1
        print(f"RUNTIME PREFLIGHT OK: {check.name}: {detail}")
    return 0


def main() -> int:
    return run_preflight()


if __name__ == "__main__":
    raise SystemExit(main())
