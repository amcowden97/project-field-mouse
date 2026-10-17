# Server Ingestion Metadata Foundation

## Status and scope

Implemented on `feature/server-ingestion-metadata-foundation` from the approved
baseline `37c76841cdf7070ae996aa5c91f3c7943c4626c6`.

This slice implements only transport-independent metadata declaration,
recognition, idempotency, persistence, and inspection. It adds no HTTP endpoint,
network client, authentication, media upload or streaming, checksum of received
bytes, synchronization worker, retry scheduler, Station acknowledgement, spool
cleanup, deployment, dashboard change, scientific inference, or production data
operation.

The governing invariant is preserved: a metadata declaration is not a scientific
Recording.

## Persistence model

Migration `0012_server_ingestion_metadata_foundation.sql` creates
`server_recording_ingestions` with:

- a unique distributed `recording_identity`;
- the resolved local `station_id` and its canonical `station_uuid`;
- immutable declared timestamp, checksum, size, duration, sample properties, and
  media type;
- transport state restricted to `AWAITING_MEDIA` or `COMPLETED`;
- an optional canonical `recording_id`, with at most one ingestion per populated
  Recording mapping;
- creation, last-declaration, retry-count, and completion metadata.

Foreign keys use `ON DELETE RESTRICT`. Triggers enforce Station/Recording identity
consistency, immutable declaration and creation fields, immutable populated
Recording mappings, immutable completion timestamps, no reverse transition from
`COMPLETED`, and durable no-delete ingestion history. `AWAITING_MEDIA` requires no
completion time; `COMPLETED` requires both a canonical Recording and completion
time.

Migration 0012 creates no historical ingestion rows and performs no Recording,
source-lifecycle, scientific, checksum, or protection backfill.

## Declaration domain

`RecordingDeclaration` is an immutable value containing only:

- `station_uuid`;
- `recording_identity`;
- `recorded_at`;
- `content_sha256`;
- `file_size_bytes`;
- `duration_seconds`;
- `sample_rate`;
- `channels`;
- `sample_format`;
- `media_type`.

The Server resolves its own `station_id`. Server filesystem paths, local IDs,
outbox IDs, and scientific state are not accepted as declaration authority.

Validation requires canonical non-nil Station and Recording UUIDs, a known Station
UUID, lowercase SHA-256, a timezone-aware timestamp, bounded positive size and
duration, and supported audio properties. This slice supports repository-compatible
sample rates, mono/stereo channels, `S16_LE`, and `audio/wav`. Malformed input and
unknown Stations raise structured `IngestionDomainError` values and persist
nothing. Station recognition is identification only and adds no authentication.

## Outcomes and historical compatibility

### `NEEDS_MEDIA`

Returned after a valid new declaration, an identical pending retry, or recognition
of an existing compatible Recording whose canonical media is not authoritatively
verified as currently available. A new declaration creates one
`AWAITING_MEDIA` ledger row and no Recording, source event, Detection, Evidence,
Review, Assessment, Ground Truth object, RecordingProtection, Observation, or
Species Trust state. `NEEDS_MEDIA` is not an acknowledgement and cannot authorize
Station spool deletion.

Existing `MISSING` and `INTENTIONALLY_EXPIRED` Recordings remain unchanged and
return `NEEDS_MEDIA`; expiration provenance is preserved. An existing `AVAILABLE`
Recording with a null historical checksum also returns `NEEDS_MEDIA`. The Station
declaration is never used to populate that canonical checksum.

### `ALREADY_PRESENT`

Returned only when an existing canonical Recording has the same distributed
identity and compatible immutable facts, authoritative `AVAILABLE` source state,
and an existing non-null checksum and size matching the declaration. The domain
does not read or hash historical files to manufacture this result. A compatible
canonical Recording is mapped into a completed ledger row, or completes a matching
pending row, without creating a duplicate Recording.

If canonical media later becomes unavailable, the ingestion remains historically
`COMPLETED` while the declaration result becomes `NEEDS_MEDIA`; transport history
and source availability remain independent.

### `CONFLICT`

Contradictory immutable facts return `CONFLICT` without mutating the winning
declaration. Structured reasons cover checksum, Station, recorded-at, size,
duration, sample rate, channels, sample format, media type, canonical inconsistency,
and duplicate distributed identity. Validation failures remain domain errors rather
than false immutable conflicts.

Different Recording identities may use the same checksum and remain separate valid
declarations. Checksum never becomes identity.

## Transactions, concurrency, and observability

`declare_recording` uses `BEGIN IMMEDIATE` when it owns the transaction and a
savepoint for its complete mutation boundary. It intentionally does not commit;
the outer caller retains commit/rollback authority. A forced persistence failure
rolls back partial ingestion work.

SQLite transaction serialization plus unique indexes ensure concurrent identical
first declarations produce one durable ingestion and idempotent `NEEDS_MEDIA`
results. Concurrent contradictory declarations cannot overwrite the winner.
Identical retries update only `last_declared_at` and `declaration_count`, plus the
allowed future canonical mapping/completion fields; immutable declaration and
scientific state do not change. Lost-response and database-reopen retries are
idempotent.

Query helpers expose total, pending, completed, oldest-pending, and repeated
declaration counts plus last declaration activity by Station. No dashboard UI or
transport was added.

## Automated validation

| Gate | Result |
|---|---:|
| Approved-baseline suite before changes | 227 passed |
| Focused ingestion and migration suite | 40 passed |
| Combined ingestion/sync/scientific suite | 175 passed |
| Complete suite | 264 passed |
| Ruff | passed |
| Changed-file Ruff formatting check | passed |
| Python compilation | passed |
| `git diff --check` | passed |

Focused tests cover fresh and 0011-to-0012 migration, idempotency, schema and
lifecycle constraints, structured validation, every immutable conflict reason,
historical Recording states, transaction ownership and rollback, concurrency,
observability, and scientific safety. Metadata-only declaration tests assert that
no canonical Recording or scientific object is created except explicit pre-existing
fixtures used to test historical compatibility.

## Safe production-copy migration evidence

The read-only representative snapshot at
`pfm-storage-evidence-20260826/legacy-source/fieldmouse.db` was copied into an
isolated workspace. The copy was advanced through migration 0011 and
WAL-checkpointed; migration 0012 was then measured alone. The source snapshot
SHA-256 remained
`78115e53ea7512f19ccb76e5cc67be31eabf77d4da6482e6fbc1068caa3006d7`.

| Measure | Result |
|---|---:|
| Source snapshot size | 4,935,680 bytes |
| Database size immediately before migration 0012 | 6,926,336 bytes |
| Database size immediately after migration 0012 | 6,926,336 bytes |
| Allocated-file growth | 0 bytes |
| Migration 0012 wall time | 70.0483 ms |
| Applied versions | 12 only |
| Existing tables compared | 24 |
| Existing table signatures unchanged | yes, 24 / 24 |
| Recordings before/after | 2,820 / 2,820 |
| Detections before/after | 1,034 / 1,034 |
| Source availability before/after | 738 intentionally expired, 2,082 missing / unchanged |
| RecordingProtections before/after | 0 / 0; signature unchanged |
| Historical checksums before/after | 2,820 null, 0 populated / unchanged |
| Historical ingestion rows after migration | 0 |
| Idempotent rerun | 0 migrations in 3.6976 ms |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | 0 |

The representative source database, production database, production station, and
production audio were not modified.

## Known limitations and deferred attachment point

- `AWAITING_MEDIA` is durable transport state only. No code transfers, verifies,
  stores, retries, acknowledges, or cleans media.
- Historical null checksums remain deliberately unknown. Future verified media
  receipt/restoration must define the authoritative verification event rather than
  trusting a declaration or opportunistically hashing historical files.
- This slice recognizes a registered Station UUID but does not authenticate it.
- The ingestion ledger is durable cross-cutover state. Future canonical database
  migration must preserve or explicitly reconcile pending and completed ingestion
  history; it must not assume this table is disposable.
- The natural future media-transfer attachment point is the existing ingestion row:
  verified receipt can bind or create the canonical Recording and transition
  `AWAITING_MEDIA` to `COMPLETED` atomically under a separately approved design.

No production deployment, merge, push, database mutation, or audio operation was
performed by this implementation slice.
