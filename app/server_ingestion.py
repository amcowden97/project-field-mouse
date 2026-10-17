"""Transport-independent Server recording metadata declaration domain."""

from __future__ import annotations

import math
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from app.synchronization import normalize_station_uuid


MAX_DURATION_SECONDS = 86_400.0
MAX_FILE_SIZE_BYTES = 1 << 40
SUPPORTED_SAMPLE_RATES = frozenset(
    {8_000, 11_025, 16_000, 22_050, 24_000, 32_000, 44_100, 48_000, 96_000, 192_000}
)
SUPPORTED_CHANNEL_COUNTS = frozenset({1, 2})
SUPPORTED_SAMPLE_FORMATS = frozenset({"S16_LE"})
SUPPORTED_MEDIA_TYPES = frozenset({"audio/wav"})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class IngestionOutcome(StrEnum):
    NEEDS_MEDIA = "NEEDS_MEDIA"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    CONFLICT = "CONFLICT"


class IngestionState(StrEnum):
    AWAITING_MEDIA = "AWAITING_MEDIA"
    COMPLETED = "COMPLETED"


class ConflictReason(StrEnum):
    IMMUTABLE_CHECKSUM_MISMATCH = "IMMUTABLE_CHECKSUM_MISMATCH"
    RECORDING_STATION_MISMATCH = "RECORDING_STATION_MISMATCH"
    IMMUTABLE_RECORDED_AT_MISMATCH = "IMMUTABLE_RECORDED_AT_MISMATCH"
    IMMUTABLE_SIZE_MISMATCH = "IMMUTABLE_SIZE_MISMATCH"
    IMMUTABLE_DURATION_MISMATCH = "IMMUTABLE_DURATION_MISMATCH"
    IMMUTABLE_SAMPLE_RATE_MISMATCH = "IMMUTABLE_SAMPLE_RATE_MISMATCH"
    IMMUTABLE_CHANNELS_MISMATCH = "IMMUTABLE_CHANNELS_MISMATCH"
    IMMUTABLE_SAMPLE_FORMAT_MISMATCH = "IMMUTABLE_SAMPLE_FORMAT_MISMATCH"
    IMMUTABLE_MEDIA_TYPE_MISMATCH = "IMMUTABLE_MEDIA_TYPE_MISMATCH"
    CANONICAL_RECORDING_INCONSISTENT = "CANONICAL_RECORDING_INCONSISTENT"
    DUPLICATE_DISTRIBUTED_IDENTITY = "DUPLICATE_DISTRIBUTED_IDENTITY"


class ValidationErrorCode(StrEnum):
    INVALID_STATION_UUID = "INVALID_STATION_UUID"
    INVALID_RECORDING_IDENTITY = "INVALID_RECORDING_IDENTITY"
    INVALID_RECORDED_AT = "INVALID_RECORDED_AT"
    INVALID_CONTENT_SHA256 = "INVALID_CONTENT_SHA256"
    INVALID_FILE_SIZE = "INVALID_FILE_SIZE"
    INVALID_DURATION = "INVALID_DURATION"
    UNSUPPORTED_SAMPLE_RATE = "UNSUPPORTED_SAMPLE_RATE"
    UNSUPPORTED_CHANNEL_COUNT = "UNSUPPORTED_CHANNEL_COUNT"
    UNSUPPORTED_SAMPLE_FORMAT = "UNSUPPORTED_SAMPLE_FORMAT"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    UNKNOWN_STATION_UUID = "UNKNOWN_STATION_UUID"


class IngestionDomainError(RuntimeError):
    """Structured validation/domain failure that must not be persisted."""

    def __init__(self, code: ValidationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class IngestionPersistenceError(RuntimeError):
    """Raised when SQLite cannot preserve ingestion invariants."""


@dataclass(frozen=True)
class RecordingDeclaration:
    station_uuid: str
    recording_identity: str
    recorded_at: str
    content_sha256: str
    file_size_bytes: int
    duration_seconds: float
    sample_rate: int
    channels: int
    sample_format: str
    media_type: str = "audio/wav"


@dataclass(frozen=True)
class DeclarationResult:
    outcome: IngestionOutcome
    ingestion_id: int | None
    recording_id: int | None
    state: IngestionState | None
    conflict_reason: ConflictReason | None = None


@dataclass(frozen=True)
class IngestionSummary:
    total: int
    awaiting_media: int
    completed: int
    oldest_pending_at: str | None
    repeat_declarations: int


@dataclass(frozen=True)
class StationDeclarationActivity:
    station_id: str
    station_uuid: str
    last_declared_at: str
    ingestion_count: int
    declaration_count: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validation_error(code: ValidationErrorCode, message: str) -> IngestionDomainError:
    return IngestionDomainError(code, message)


def _uuid(value: object, *, station: bool) -> str:
    code = (
        ValidationErrorCode.INVALID_STATION_UUID
        if station
        else ValidationErrorCode.INVALID_RECORDING_IDENTITY
    )
    try:
        if station:
            return normalize_station_uuid(str(value), required=True)
        parsed = uuid.UUID(str(value).strip())
        if parsed.int == 0:
            raise ValueError("nil UUID")
        return str(parsed)
    except (AttributeError, TypeError, ValueError) as error:
        label = "Station UUID" if station else "Recording identity"
        raise _validation_error(code, f"{label} must be a non-nil UUID") from error


def _timestamp(value: object, *, field: str) -> str:
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        offset = parsed.utcoffset()
    except (TypeError, ValueError) as error:
        raise _validation_error(
            ValidationErrorCode.INVALID_RECORDED_AT,
            f"{field} must be a timezone-aware ISO-8601 timestamp",
        ) from error
    if parsed.tzinfo is None or offset is None:
        raise _validation_error(
            ValidationErrorCode.INVALID_RECORDED_AT,
            f"{field} must be timezone-aware",
        )
    return parsed.astimezone(timezone.utc).isoformat()


def _positive_integer(
    value: object,
    *,
    code: ValidationErrorCode,
    label: str,
    maximum: int,
) -> int:
    if isinstance(value, bool):
        raise _validation_error(code, f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise _validation_error(code, f"{label} must be an integer") from error
    if number != value or not 1 <= number <= maximum:
        raise _validation_error(code, f"{label} is outside the supported range")
    return number


def validate_declaration(declaration: RecordingDeclaration) -> RecordingDeclaration:
    station_uuid = _uuid(declaration.station_uuid, station=True)
    recording_identity = _uuid(declaration.recording_identity, station=False)
    recorded_at = _timestamp(declaration.recorded_at, field="recorded_at")
    checksum = str(declaration.content_sha256)
    if not SHA256_PATTERN.fullmatch(checksum):
        raise _validation_error(
            ValidationErrorCode.INVALID_CONTENT_SHA256,
            "content_sha256 must contain exactly 64 lowercase hexadecimal characters",
        )
    file_size = _positive_integer(
        declaration.file_size_bytes,
        code=ValidationErrorCode.INVALID_FILE_SIZE,
        label="file_size_bytes",
        maximum=MAX_FILE_SIZE_BYTES,
    )
    if isinstance(declaration.duration_seconds, bool):
        raise _validation_error(
            ValidationErrorCode.INVALID_DURATION,
            "duration_seconds must be a finite positive number",
        )
    try:
        duration = float(declaration.duration_seconds)
    except (TypeError, ValueError) as error:
        raise _validation_error(
            ValidationErrorCode.INVALID_DURATION,
            "duration_seconds must be a finite positive number",
        ) from error
    if not math.isfinite(duration) or not 0 < duration <= MAX_DURATION_SECONDS:
        raise _validation_error(
            ValidationErrorCode.INVALID_DURATION,
            "duration_seconds is outside the supported range",
        )
    sample_rate = _positive_integer(
        declaration.sample_rate,
        code=ValidationErrorCode.UNSUPPORTED_SAMPLE_RATE,
        label="sample_rate",
        maximum=max(SUPPORTED_SAMPLE_RATES),
    )
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise _validation_error(
            ValidationErrorCode.UNSUPPORTED_SAMPLE_RATE,
            "sample_rate is unsupported",
        )
    channels = _positive_integer(
        declaration.channels,
        code=ValidationErrorCode.UNSUPPORTED_CHANNEL_COUNT,
        label="channels",
        maximum=max(SUPPORTED_CHANNEL_COUNTS),
    )
    if channels not in SUPPORTED_CHANNEL_COUNTS:
        raise _validation_error(
            ValidationErrorCode.UNSUPPORTED_CHANNEL_COUNT,
            "channel count is unsupported",
        )
    sample_format = str(declaration.sample_format).strip().upper()
    if len(sample_format) > 32 or sample_format not in SUPPORTED_SAMPLE_FORMATS:
        raise _validation_error(
            ValidationErrorCode.UNSUPPORTED_SAMPLE_FORMAT,
            "sample_format is unsupported",
        )
    media_type = str(declaration.media_type).strip().lower()
    if len(media_type) > 100 or media_type not in SUPPORTED_MEDIA_TYPES:
        raise _validation_error(
            ValidationErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "media_type is unsupported",
        )
    return RecordingDeclaration(
        station_uuid=station_uuid,
        recording_identity=recording_identity,
        recorded_at=recorded_at,
        content_sha256=checksum,
        file_size_bytes=file_size,
        duration_seconds=duration,
        sample_rate=sample_rate,
        channels=channels,
        sample_format=sample_format,
        media_type=media_type,
    )


def _stored_timestamp(value: object) -> str | None:
    try:
        return _timestamp(value, field="stored recorded_at")
    except IngestionDomainError:
        return None


def _compare_values(
    declaration: RecordingDeclaration,
    *,
    station_uuid: str,
    recorded_at: object,
    content_sha256: object,
    file_size_bytes: object,
    duration_seconds: object,
    sample_rate: object,
    channels: object,
    sample_format: object,
    media_type: object,
    checksum_may_be_unknown: bool,
) -> ConflictReason | None:
    if station_uuid != declaration.station_uuid:
        return ConflictReason.RECORDING_STATION_MISMATCH
    normalized_recorded_at = _stored_timestamp(recorded_at)
    if normalized_recorded_at is None:
        return ConflictReason.CANONICAL_RECORDING_INCONSISTENT
    if normalized_recorded_at != declaration.recorded_at:
        return ConflictReason.IMMUTABLE_RECORDED_AT_MISMATCH
    if content_sha256 is None and checksum_may_be_unknown:
        pass
    elif str(content_sha256) != declaration.content_sha256:
        return ConflictReason.IMMUTABLE_CHECKSUM_MISMATCH
    if int(file_size_bytes) != declaration.file_size_bytes:
        return ConflictReason.IMMUTABLE_SIZE_MISMATCH
    if not math.isclose(
        float(duration_seconds), declaration.duration_seconds, rel_tol=0.0, abs_tol=1e-9
    ):
        return ConflictReason.IMMUTABLE_DURATION_MISMATCH
    if int(sample_rate) != declaration.sample_rate:
        return ConflictReason.IMMUTABLE_SAMPLE_RATE_MISMATCH
    if int(channels) != declaration.channels:
        return ConflictReason.IMMUTABLE_CHANNELS_MISMATCH
    if str(sample_format).upper() != declaration.sample_format:
        return ConflictReason.IMMUTABLE_SAMPLE_FORMAT_MISMATCH
    if str(media_type).lower() != declaration.media_type:
        return ConflictReason.IMMUTABLE_MEDIA_TYPE_MISMATCH
    return None


def _canonical_conflict(
    declaration: RecordingDeclaration,
    canonical: sqlite3.Row,
    station_uuid: str,
) -> ConflictReason | None:
    return _compare_values(
        declaration,
        station_uuid=station_uuid,
        recorded_at=canonical["recorded_at"],
        content_sha256=canonical["content_sha256"],
        file_size_bytes=canonical["file_size_bytes"],
        duration_seconds=canonical["duration_seconds"],
        sample_rate=canonical["sample_rate"],
        channels=canonical["channels"],
        sample_format=canonical["sample_format"],
        media_type=canonical["media_type"],
        checksum_may_be_unknown=True,
    )


def _ingestion_conflict(
    declaration: RecordingDeclaration,
    ingestion: sqlite3.Row,
) -> ConflictReason | None:
    return _compare_values(
        declaration,
        station_uuid=str(ingestion["station_uuid"]),
        recorded_at=ingestion["recorded_at"],
        content_sha256=ingestion["content_sha256"],
        file_size_bytes=ingestion["file_size_bytes"],
        duration_seconds=ingestion["duration_seconds"],
        sample_rate=ingestion["sample_rate"],
        channels=ingestion["channels"],
        sample_format=ingestion["sample_format"],
        media_type=ingestion["media_type"],
        checksum_may_be_unknown=False,
    )


def _canonical_satisfies(declaration: RecordingDeclaration, canonical: sqlite3.Row) -> bool:
    return (
        str(canonical["source_availability"]) == "AVAILABLE"
        and canonical["content_sha256"] is not None
        and str(canonical["content_sha256"]) == declaration.content_sha256
        and int(canonical["file_size_bytes"]) == declaration.file_size_bytes
    )


def _result(
    outcome: IngestionOutcome,
    ingestion: sqlite3.Row | None,
    *,
    recording_id: int | None = None,
    conflict_reason: ConflictReason | None = None,
) -> DeclarationResult:
    state = IngestionState(str(ingestion["state"])) if ingestion is not None else None
    return DeclarationResult(
        outcome=outcome,
        ingestion_id=(int(ingestion["ingestion_id"]) if ingestion is not None else None),
        recording_id=(
            recording_id
            if recording_id is not None
            else (
                int(ingestion["recording_id"])
                if ingestion is not None and ingestion["recording_id"] is not None
                else None
            )
        ),
        state=state,
        conflict_reason=conflict_reason,
    )


def _read_ingestion(connection: sqlite3.Connection, identity: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM server_recording_ingestions WHERE recording_identity = ?",
        (identity,),
    ).fetchone()


def _update_retry(
    connection: sqlite3.Connection,
    ingestion_id: int,
    declared_at: str,
    *,
    recording_id: int | None = None,
    complete: bool = False,
) -> sqlite3.Row:
    connection.execute(
        """
        UPDATE server_recording_ingestions
        SET last_declared_at = ?,
            declaration_count = declaration_count + 1,
            recording_id = COALESCE(recording_id, ?),
            state = CASE WHEN ? THEN 'COMPLETED' ELSE state END,
            completed_at = CASE WHEN ? THEN ? ELSE completed_at END
        WHERE ingestion_id = ?
        """,
        (declared_at, recording_id, complete, complete, declared_at, ingestion_id),
    )
    row = connection.execute(
        "SELECT * FROM server_recording_ingestions WHERE ingestion_id = ?",
        (ingestion_id,),
    ).fetchone()
    if row is None:
        raise IngestionPersistenceError("Ingestion disappeared during retry update")
    return row


def declare_recording(
    connection: sqlite3.Connection,
    declaration: RecordingDeclaration,
    *,
    declared_at: str | None = None,
) -> DeclarationResult:
    """Durably recognize metadata without creating a scientific Recording."""
    normalized = validate_declaration(declaration)
    timestamp = _timestamp(declared_at, field="declared_at") if declared_at else _now()
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    savepoint = "declare_server_recording_ingestion"
    connection.execute(f"SAVEPOINT {savepoint}")
    try:
        stations = connection.execute(
            "SELECT id, station_uuid FROM stations WHERE station_uuid = ?",
            (normalized.station_uuid,),
        ).fetchall()
        if not stations:
            raise _validation_error(
                ValidationErrorCode.UNKNOWN_STATION_UUID,
                "Station UUID is not registered",
            )
        if len(stations) != 1:
            raise IngestionPersistenceError("Station UUID registry is inconsistent")
        station_id = str(stations[0]["id"])

        canonical_rows = connection.execute(
            """
            SELECT recording.*, station.station_uuid AS resolved_station_uuid
            FROM recordings AS recording
            JOIN stations AS station ON station.id = recording.station_id
            WHERE recording.recording_identity = ?
            ORDER BY recording.id
            """,
            (normalized.recording_identity,),
        ).fetchall()
        ingestion = _read_ingestion(connection, normalized.recording_identity)
        if len(canonical_rows) > 1:
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            return _result(
                IngestionOutcome.CONFLICT,
                ingestion,
                conflict_reason=ConflictReason.DUPLICATE_DISTRIBUTED_IDENTITY,
            )
        canonical = canonical_rows[0] if canonical_rows else None
        canonical_id = int(canonical["id"]) if canonical is not None else None

        if canonical is not None:
            conflict = _canonical_conflict(
                normalized,
                canonical,
                str(canonical["resolved_station_uuid"] or ""),
            )
            if conflict is not None:
                connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                return _result(
                    IngestionOutcome.CONFLICT,
                    ingestion,
                    recording_id=canonical_id,
                    conflict_reason=conflict,
                )

        if ingestion is not None:
            conflict = _ingestion_conflict(normalized, ingestion)
            if conflict is not None:
                connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                return _result(
                    IngestionOutcome.CONFLICT,
                    ingestion,
                    recording_id=canonical_id,
                    conflict_reason=conflict,
                )
            mapped_id = ingestion["recording_id"]
            if mapped_id is not None and canonical_id != int(mapped_id):
                connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                return _result(
                    IngestionOutcome.CONFLICT,
                    ingestion,
                    recording_id=canonical_id,
                    conflict_reason=ConflictReason.CANONICAL_RECORDING_INCONSISTENT,
                )
            if canonical is None and str(ingestion["state"]) == IngestionState.COMPLETED:
                connection.execute(f"RELEASE SAVEPOINT {savepoint}")
                return _result(
                    IngestionOutcome.CONFLICT,
                    ingestion,
                    conflict_reason=ConflictReason.CANONICAL_RECORDING_INCONSISTENT,
                )
            satisfied = canonical is not None and _canonical_satisfies(normalized, canonical)
            updated = _update_retry(
                connection,
                int(ingestion["ingestion_id"]),
                timestamp,
                recording_id=canonical_id,
                complete=(satisfied and str(ingestion["state"]) == IngestionState.AWAITING_MEDIA),
            )
            connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            return _result(
                (IngestionOutcome.ALREADY_PRESENT if satisfied else IngestionOutcome.NEEDS_MEDIA),
                updated,
                recording_id=canonical_id,
            )

        satisfied = canonical is not None and _canonical_satisfies(normalized, canonical)
        state = IngestionState.COMPLETED if satisfied else IngestionState.AWAITING_MEDIA
        cursor = connection.execute(
            """
            INSERT INTO server_recording_ingestions (
                station_id, station_uuid, recording_identity, recorded_at,
                content_sha256, file_size_bytes, duration_seconds, sample_rate,
                channels, sample_format, media_type, state, recording_id,
                created_at, last_declared_at, declaration_count, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                station_id,
                normalized.station_uuid,
                normalized.recording_identity,
                normalized.recorded_at,
                normalized.content_sha256,
                normalized.file_size_bytes,
                normalized.duration_seconds,
                normalized.sample_rate,
                normalized.channels,
                normalized.sample_format,
                normalized.media_type,
                state.value,
                canonical_id,
                timestamp,
                timestamp,
                timestamp if satisfied else None,
            ),
        )
        if cursor.lastrowid is None:
            raise IngestionPersistenceError("Ingestion insert did not return an ID")
        ingestion = connection.execute(
            "SELECT * FROM server_recording_ingestions WHERE ingestion_id = ?",
            (int(cursor.lastrowid),),
        ).fetchone()
        if ingestion is None:
            raise IngestionPersistenceError("Ingestion insert was not readable")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        return _result(
            IngestionOutcome.ALREADY_PRESENT if satisfied else IngestionOutcome.NEEDS_MEDIA,
            ingestion,
            recording_id=canonical_id,
        )
    except (sqlite3.Error, IngestionDomainError, IngestionPersistenceError) as error:
        connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        if isinstance(error, (IngestionDomainError, IngestionPersistenceError)):
            raise
        raise IngestionPersistenceError(str(error)) from error


def ingestion_summary(connection: sqlite3.Connection) -> IngestionSummary:
    row = connection.execute(
        """
        SELECT COUNT(*),
               SUM(CASE WHEN state = 'AWAITING_MEDIA' THEN 1 ELSE 0 END),
               SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END),
               MIN(CASE WHEN state = 'AWAITING_MEDIA' THEN created_at END),
               SUM(declaration_count - 1)
        FROM server_recording_ingestions
        """
    ).fetchone()
    return IngestionSummary(
        total=int(row[0]),
        awaiting_media=int(row[1] or 0),
        completed=int(row[2] or 0),
        oldest_pending_at=row[3],
        repeat_declarations=int(row[4] or 0),
    )


def last_declarations_by_station(
    connection: sqlite3.Connection,
) -> list[StationDeclarationActivity]:
    rows = connection.execute(
        """
        SELECT station_id, station_uuid, MAX(last_declared_at),
               COUNT(*), SUM(declaration_count)
        FROM server_recording_ingestions
        GROUP BY station_id, station_uuid
        ORDER BY station_id
        """
    ).fetchall()
    return [StationDeclarationActivity(*row) for row in rows]
