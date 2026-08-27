"""Append-only Evidence and EvidenceSource persistence."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable

from app.science import ScienceInvariantError


class EvidenceFamily(StrEnum):
    MODEL = "MODEL"
    CONTEXTUAL = "CONTEXTUAL"
    HISTORICAL = "HISTORICAL"
    QUALITY = "QUALITY"
    HUMAN = "HUMAN"
    EXPERT = "EXPERT"
    DERIVED = "DERIVED"


class EvidenceStance(StrEnum):
    SUPPORTS = "SUPPORTS"
    CHALLENGES = "CHALLENGES"
    NEUTRAL = "NEUTRAL"
    INCONCLUSIVE = "INCONCLUSIVE"


class SourceRole(StrEnum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    CONTEXT = "CONTEXT"


@dataclass(frozen=True)
class EvidenceSourceInput:
    recording_id: int
    role: SourceRole
    interval_start_seconds: float | None = None
    interval_end_seconds: float | None = None


@dataclass(frozen=True)
class EvidenceLineageInput:
    parent_evidence_id: int
    relationship: str = "DERIVED_FROM"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_sources(
    connection: sqlite3.Connection,
    sources: tuple[EvidenceSourceInput, ...],
) -> None:
    seen: set[tuple] = set()
    for source in sources:
        key = (
            source.recording_id,
            source.role.value,
            source.interval_start_seconds,
            source.interval_end_seconds,
        )
        if key in seen:
            raise ScienceInvariantError("Duplicate EvidenceSource")
        seen.add(key)
        row = connection.execute(
            "SELECT duration_seconds FROM recordings WHERE id = ?",
            (source.recording_id,),
        ).fetchone()
        if row is None:
            raise ScienceInvariantError(f"Unknown source recording: {source.recording_id}")
        start = source.interval_start_seconds
        end = source.interval_end_seconds
        if (start is None) != (end is None):
            raise ScienceInvariantError("Source intervals require both offsets")
        if start is not None and (start < 0 or end <= start or end > float(row[0])):
            raise ScienceInvariantError("EvidenceSource interval is outside recording bounds")


def append_evidence(
    connection: sqlite3.Connection,
    *,
    detection_id: int,
    family: EvidenceFamily,
    evidence_type: str,
    stance: EvidenceStance,
    source_type: str,
    source_id: str,
    source_version: str,
    reason_code: str,
    reasoning: str,
    observed_at: str,
    idempotency_key: str,
    sources: Iterable[EvidenceSourceInput] = (),
    lineage: Iterable[EvidenceLineageInput] = (),
    claimed_scientific_name: str | None = None,
    claimed_common_name: str | None = None,
    algorithm_version: str | None = None,
    confidence_value: float | None = None,
    confidence_semantics: str | None = None,
    metadata: dict | None = None,
) -> int:
    """Append automated Evidence; Review-owned families remain disabled in M1."""
    if family in {EvidenceFamily.HUMAN, EvidenceFamily.EXPERT}:
        raise ScienceInvariantError("Human and Expert Evidence require the future Review system")
    if confidence_value is not None and not (confidence_semantics or "").strip():
        raise ScienceInvariantError("Confidence values require source-specific semantics")
    required = (source_type, source_id, source_version, reason_code, reasoning, idempotency_key)
    if any(not value or not value.strip() for value in required):
        raise ScienceInvariantError("Evidence provenance and reasoning are required")
    source_items = tuple(sources)
    lineage_items = tuple(lineage)
    if family is EvidenceFamily.DERIVED and not lineage_items:
        raise ScienceInvariantError("Derived Evidence requires source lineage")
    _validate_sources(connection, source_items)
    existing = connection.execute(
        "SELECT evidence_id FROM evidence WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if existing is not None:
        return int(existing[0])
    payload = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
    connection.execute("SAVEPOINT append_evidence")
    try:
        cursor = connection.execute(
            """
            INSERT INTO evidence (
                evidence_identity, detection_id, family, evidence_type, stance,
                claimed_scientific_name, claimed_common_name, source_type,
                source_id, source_version, algorithm_version, confidence_value,
                confidence_semantics, reason_code, reasoning, metadata_json,
                observed_at, created_at, idempotency_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                detection_id,
                family.value,
                evidence_type,
                stance.value,
                claimed_scientific_name,
                claimed_common_name,
                source_type,
                source_id,
                source_version,
                algorithm_version,
                confidence_value,
                confidence_semantics,
                reason_code,
                reasoning,
                payload,
                observed_at,
                _now(),
                idempotency_key,
            ),
        )
        if cursor.lastrowid is None:
            raise ScienceInvariantError("Evidence did not return an ID")
        evidence_id = int(cursor.lastrowid)
        for source in source_items:
            connection.execute(
                """
                INSERT INTO evidence_sources (
                    evidence_id, recording_id, source_role,
                    interval_start_seconds, interval_end_seconds, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    source.recording_id,
                    source.role.value,
                    source.interval_start_seconds,
                    source.interval_end_seconds,
                    _now(),
                ),
            )
        for edge in lineage_items:
            connection.execute(
                """
                INSERT INTO evidence_lineage (
                    child_evidence_id, parent_evidence_id, relationship, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (evidence_id, edge.parent_evidence_id, edge.relationship, _now()),
            )
        connection.execute("RELEASE SAVEPOINT append_evidence")
        return evidence_id
    except (sqlite3.Error, ScienceInvariantError) as error:
        connection.execute("ROLLBACK TO SAVEPOINT append_evidence")
        connection.execute("RELEASE SAVEPOINT append_evidence")
        if isinstance(error, ScienceInvariantError):
            raise
        raise ScienceInvariantError(str(error)) from error
