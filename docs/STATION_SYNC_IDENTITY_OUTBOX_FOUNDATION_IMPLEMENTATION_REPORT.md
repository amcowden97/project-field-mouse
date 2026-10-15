# Station Synchronization Identity & Outbox Foundation

## Status and scope

Implemented on `feature/station-sync-identity-outbox-foundation` from approved
baseline `7b5ca3ab0bcdc2de21962ad4fd96180d3c9cd3cb`.

This slice implements only durable local identity, media checksum, and
synchronization-intent persistence. It adds no HTTP client or endpoint, media
upload, authentication, retry worker, networking, Server behavior, deployment,
or ACK-producing integration.

## Architecture implemented

### Station identity

- `station.uuid` is parsed as a non-nil UUID and normalized to canonical text.
- A valid configured UUID is persisted to `stations.station_uuid` and cannot be
  replaced once stored.
- An absent UUID remains compatible and means synchronization is not enabled:
  capture, BirdNET, and dashboard behavior continue, but no outbox intent is
  created.
- A non-empty invalid UUID is a configuration error.
- Migration 0011 does not invent a missing Station UUID. This is important
  because a database-only value could conflict with the durable UUID in the
  Station TOML file. Normal station upsert safely fills a previously null
  database value from validated configuration.
- The human-readable `station.id` remains separate and is not used as the
  distributed Station identity.

### Recording identity

- Application recording writes generate UUIDv4 before insertion and persist it
  in the existing unique `recording_identity` column.
- UUIDv4 is used because the supported Python 3.11 runtime has no standard-library
  UUIDv7 implementation. UUIDv4 is opaque, globally unique, and independent of
  local row ID, path, checksum, and receipt order.
- Database triggers preserve immutability. A random UUID-form safety-net trigger
  covers compatible direct SQL writers that omit an identity.
- Equal media bytes are allowed to have different Recording identities.

### Historical identity migration

Migration `0011_station_sync_identity_outbox.sql` replaces migration 0006's
station-ID/local-row-ID identity values:

- With a valid stored Station UUID, historical identities are deterministic
  UUIDv5 values in that Station namespace.
- Without a valid stored Station UUID, each historical Recording receives one
  UUIDv4 inside the migration transaction.
- Once committed, identities are immutable and migration history makes reruns
  no-ops.
- Integer primary keys and all scientific foreign keys remain unchanged.
- The migration does not read WAV files and creates no scientific records,
  protections, or synchronization intents.

### Media checksum

`recordings.content_sha256` stores lowercase SHA-256 of the exact completed WAV
bytes. Recorder order is:

1. `arecord` completes;
2. existing file validation succeeds;
3. SHA-256 succeeds;
4. Recording and optional PENDING outbox intent are persisted atomically.

The checksum is immutable. Historical values remain null because the migration
must not read missing/expired media or fabricate completeness. Existing
`source_sha256` and source lifecycle state are untouched.

### Durable outbox

`station_sync_outbox` contains:

- `outbox_id`, `recording_id`, `recording_identity`, `station_uuid`;
- `state`, `attempt_count`, `last_attempt_at`, `last_error`;
- `server_acknowledged_at`, `created_at`, `updated_at`.

States are exactly `PENDING`, `ACKNOWLEDGED`, `FAILED_RETRYABLE`, and
`FAILED_PERMANENT`. One row is allowed per Recording. Recording and Station
identities must match their source rows. The Recording FK uses `ON DELETE
RESTRICT`; identity fields and creation time are immutable; intents cannot be
deleted. `ACKNOWLEDGED` requires a durable acknowledgement timestamp, but this
slice includes no code that produces that state.

### Atomic capture and failure behavior

`insert_recording` uses a SQLite savepoint around Recording insertion, source
lifecycle event creation, and outbox insertion. The outer caller still owns the
commit. Any database or invariant failure rolls the entire inner operation back.
Recorder failure, WAV validation failure, checksum failure, or database failure
creates no outbox row and removes the just-created WAV under existing cleanup
semantics. A valid configured Station UUID creates exactly one PENDING row; an
absent UUID creates no synchronization intent while still persisting Recording
identity and checksum.

## Compatibility

- Pre-0011 migration fixtures remain supported by the recording repository.
- The simulator preserves an already stored Station UUID instead of replacing it.
- Existing cleanup and backup code does not inspect outbox state.
- Recorder, BirdNET, dashboard, Evidence, Review, Assessment, Ground Truth,
  source lifecycle, and RecordingProtection regressions pass.
- No scientific conclusion, observation, species trust, review, assessment,
  protection, or source-availability state is inferred or changed.

## Automated validation

| Gate | Result |
|---|---:|
| Accepted-baseline suite before changes | 209 passed |
| Focused sync/config/migration/evidence suite | 46 passed |
| Combined recorder/science/BirdNET/dashboard/storage suite | 178 passed |
| Complete suite | 227 passed |
| Ruff | passed |
| Changed-file Ruff formatting check | passed |
| Python compilation | passed |
| `git diff --check` | passed |

Black is not installed in the established virtual environment. Repository-wide
`ruff format --check` also reports 67 accepted-baseline files as unformatted, so
no repository-wide formatting rewrite was performed. Only files changed by this
slice were formatted.

## Safe production-copy migration evidence

The read-only representative snapshot at
`pfm-storage-evidence-20260826/legacy-source/fieldmouse.db` was copied into an
isolated workspace. Its migrations 1-4 were advanced through migration 0010 and
WAL-checkpointed; migration 0011 was then measured alone. The source snapshot
SHA-256 remained
`78115e53ea7512f19ccb76e5cc67be31eabf77d4da6482e6fbc1068caa3006d7`.

| Measure | Result |
|---|---:|
| Source snapshot size | 4,935,680 bytes |
| Database size immediately before migration 0011 | 6,897,664 bytes |
| Database size immediately after migration 0011 | 6,897,664 bytes |
| Allocated-file growth | 0 bytes |
| Migration 0011 wall time | 85.6087 ms |
| Identity callback time | 26.8266 ms |
| Idempotent rerun | 0 migrations in 3.1342 ms |
| Recordings / detections | 2,820 / 1,034 |
| Valid/distinct historical identities | 2,820 / 2,820 |
| Station UUIDs invented by migration | 0 |
| Historical checksums populated | 0 |
| Historical checksums deliberately null | 2,820 |
| Historical outbox rows created | 0 |
| Source availability before/after | 738 expired, 2,082 missing / unchanged |
| RecordingProtections before/after | 0 / 0; signature unchanged |
| Existing scientific table signatures | 16 / 16 unchanged |
| Recording non-identity fields | unchanged |
| Station non-UUID fields | unchanged |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | 0 |

The source database, production station, and production audio were not modified.

## Known limitations and deferred work

- A station with an absent UUID remains deliberately non-sync-capable until its
  configuration is initialized with one. This does not interrupt existing local
  services.
- Historical checksums remain null; future work must not infer them for missing
  or intentionally expired media.
- PENDING rows are durable intent only. No process transmits, retries,
  acknowledges, or cleans media based on them.
- Server ingestion, authentication, transport, media storage, ACK networking,
  deployment, and Station spool cleanup remain explicitly deferred.
