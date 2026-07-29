from __future__ import annotations

import json
import sqlite3
import tomllib
from pathlib import Path
from typing import Any

from app.verification.consensus import ConsensusEngine
from app.verification.manager import VerificationManager
from app.verification.plugins.audio_quality import AudioQualityPlugin
from app.verification.plugins.geographic import (
    GeographicOccurrence,
    GeographicPlugin,
)
from app.verification.plugins.historical import HistoricalPlugin
from app.verification.plugins.seasonal import SeasonalPattern, SeasonalPlugin
from app.verification.rules import RuleConfig, RuleEngine


def build_verification_manager(
    connection: sqlite3.Connection,
    config_path: Path = Path("config/verification.toml"),
) -> VerificationManager | None:
    with config_path.open("rb") as config_file:
        root = tomllib.load(config_file)
    config: dict[str, Any] = root["verification"]
    if not config.get("enabled", True):
        return None

    profile_path = Path(config["region_profile"])
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    enabled = config.get("plugins", {})
    plugins = []
    if enabled.get("geographic", True):
        occurrences = {
            name: GeographicOccurrence(**value)
            for name, value in profile.get("occurrences", {}).items()
        }
        plugins.append(
            GeographicPlugin(occurrences, region_name=profile["name"])
        )
    if enabled.get("seasonal", True):
        patterns = {
            name: SeasonalPattern(
                frozenset(value["expected_months"]),
                tuple(value["active_hours"]) if value.get("active_hours") else None,
                value.get("note", ""),
            )
            for name, value in profile.get("seasonal_patterns", {}).items()
        }
        plugins.append(SeasonalPlugin(patterns))
    if enabled.get("audio_quality", True):
        plugins.append(AudioQualityPlugin())
    if enabled.get("historical", True):
        plugins.append(HistoricalPlugin(connection))

    rule_values = config.get("rules", {})
    consensus_values = config.get("consensus", {})
    return VerificationManager(
        plugins,
        rules=RuleEngine(RuleConfig(**rule_values)),
        consensus=ConsensusEngine(**consensus_values),
    )
