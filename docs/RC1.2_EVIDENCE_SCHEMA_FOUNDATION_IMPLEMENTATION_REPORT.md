# RC1.2 Evidence Schema Foundation — Implementation Report

## Status and scope

- Branch: `feature/rc1.2-evidence-schema-foundation`
- Canonical baseline: `f85c9332c65deff7f545ccde159cb4e194640861` (`v1.1.0`)
- Implementation commit: `a0da449f9778b5f7beba955ce140a9e54a194c47`
- Final documentation commit: recorded in the review handoff after CI completes
- Scope: Recording lifecycle primitives, Evidence, EvidenceSource, Evidence lineage,
  RecordingProtection, conservative migration, compatibility adapters, tests, and
  migration documentation
- Deferred as required: Review, Assessment, Observation automation, Ground Truth,
  Species Trust, retention automation, destructive cleanup, and new dashboard behavior

## Files and schema changed

Migration `0006_evidence_schema_foundation.sql` adds these Recording fields:

- `recording_identity`: immutable station-scoped identity; existing integer IDs remain
  unchanged.
- `source_availability`: `AVAILABLE`, `INTENTIONALLY_EXPIRED`, or `MISSING`.
- `media_type`, `source_sha256`, and `source_last_verified_at`: historical media
  description and verification metadata. Existing path, duration, sample rate,
  channels, format, and byte size remain intact.

It adds:

- `recording_source_events`: append-only availability and expiration provenance.
- `evidence`: append-only scientific assertions linked to an existing Detection.
- `evidence_lineage`: append-only, acyclic relationships between Evidence items.
- `evidence_sources`: explicit many-to-many Evidence-to-Recording sources.
- `recording_protections`: independent, multi-valued protection records and release
  history.
- `evidence_schema_migration_runs`: backfill counts, timings, warnings, and ambiguity
  evidence.

Application services in `app/science` provide the narrow write boundaries. Recorder
insertion records a new source as available. The existing cleanup service excludes
active protections and records authorized expiration provenance while retaining all
RC1.1 behavior for pre-0006/minimal schemas. Both migration entry points execute the
same 0006 backfill. Migration checksum validation is now line-ending independent.

## Migration and availability backfill

The migration applies these rules per existing Recording:

1. A source that exists is `AVAILABLE`.
2. An absent source whose RC1.1 `processing_status` is `audio_expired` is
   `INTENTIONALLY_EXPIRED`, with an append-only event naming that affirmative legacy
   provenance.
3. Any other absent source is `MISSING`; absence alone is never treated as authorized
   expiration.
4. If a source marked `audio_expired` is present, the migration records the historical
   expiration and subsequent restoration, ending in `AVAILABLE` without erasing
   history.

The backfill assigns stable identities and source events but does not fabricate
Evidence, protections, reviews, Observations, or scientific conclusions. It does not
delete files or rows.

## Evidence and EvidenceSource

Evidence has immutable identity, Detection target, schema version, controlled family
and type, stance, optional taxon claim, source identity/version, optional algorithm
version, source-specific confidence semantics, reason code, explanation, metadata,
event time, creation time, and idempotency key. Confidence is not relabeled as
scientific confidence.

The automated M1 write service rejects Human and Expert families because those require
the future Review boundary. Derived Evidence requires lineage. Lineage rejects cycles.
In this milestone Evidence targets Detection because Encounter and Observation storage
do not yet exist; adding unenforceable polymorphic references would prematurely pull
deferred subsystems into M1.

EvidenceSource supports zero or more sources per Evidence and zero or more Evidence
items per Recording. Roles are `PRIMARY`, `SUPPORTING`, and `CONTEXT`. Both offsets
null means the full Recording. Bounded intervals require both offsets, a non-negative
start, end greater than start, and end no later than Recording duration. A functional
unique index rejects duplicate relationships. Current availability is read only from
Recording and is not copied into EvidenceSource.

## RecordingProtection

The schema represents all approved types:

- `MANUALLY_PINNED`, `FIRST_CONFIRMED`, `VERIFICATION_EVIDENCE`
- `GROUND_TRUTH_EVIDENCE`, `SCIENTIFICALLY_INTERESTING`, `RESEARCH_HOLD`
- `SIGNIFICANT_OBSERVATION`

Origins support `MANUAL`, `EVIDENCE`, `REVIEW`, `OBSERVATION`, `GROUND_TRUTH`,
`RESEARCH`, and `SYSTEM_POLICY`. Every row carries origin reference, reason, actor, and
time. Multiple protections may be active simultaneously and released independently.
Rows cannot be deleted; only a one-time, attributed release transition is permitted.
A partial unique index prevents duplicate active protections. Active protections block
intentional expiration in both the application boundary and the database.

No automatic protection creator was added.

## Recording quality decision

`RecordingQualityMeasurement` is deferred. A useful version needs an approved,
source-specific measurement contract; adding a placeholder now would invite detector
confidence to be misused as audio quality. The schema keeps detector confidence,
scientific confidence, and recording quality as separate concepts, without introducing
a composite quality algorithm.

## Constraints, indexes, and invariant validation

Foreign keys use `ON DELETE RESTRICT` for Evidence, EvidenceSource, lineage, source
events, and protection history. Append-only triggers protect scientific and lifecycle
history. Check constraints control enumerations, JSON, confidence semantics, reviewer
boundaries, intervals, protection origin, and release attribution. Indexes cover stable
Recording identity, availability/time, Evidence target/claim/source, EvidenceSource in
both directions, lineage parents, active protections, protection origin, and lifecycle
events.

The applicable contract invariants were exercised as follows:

| Invariant | Validated behavior |
|---|---|
| INV-01 | Recording identity is stable and immutable. |
| INV-02 | Media payload and Recording identity remain separate. |
| INV-03 | A stored path does not establish availability. |
| INV-04 | `MISSING` and `INTENTIONALLY_EXPIRED` remain distinct. |
| INV-05 | Intentional expiration requires current, attributed provenance. |
| INV-06 | Historical path and media metadata survive expiration. |
| INV-07 | Restoration returns to `AVAILABLE` without erasing expiration history. |
| INV-08 | Source lifecycle changes retain Recording, Detection, and Evidence metadata. |
| INV-09 | Evidence is append-only and idempotent. |
| INV-10 | Automated writes cannot impersonate Human or Expert review. |
| INV-11 | Derived Evidence requires acyclic lineage. |
| INV-12 | Evidence supports zero, one, or multiple Recording sources. |
| INV-13 | One Recording may support multiple Evidence items. |
| INV-14 | EvidenceSource roles are controlled. |
| INV-15 | Full and valid bounded source references are supported. |
| INV-16 | Invalid, incomplete, out-of-range, and duplicate offsets are rejected. |
| INV-17 | Availability remains canonical on Recording, not EvidenceSource. |
| INV-18 | Multiple protections coexist and release independently with history retained. |
| INV-19 | Manual pins persist and block expiration until explicit attributed release. |
| INV-20 | Protection origin, duplicate-active, foreign-key, and history constraints hold. |

## Automated validation

- Full test suite: **110 passed**.
- Focused migration and schema tests: **21 passed** after the final atomicity/checksum
  change.
- Ruff: **passed** for `app` and `tests`.
- Compile check: `python -m compileall -q app tests` **passed**.
- Patch hygiene: `git diff --check` **passed**.
- GitHub Actions CI: pending branch push; the final handoff records the run result.

The regression suite covers fresh creation, v1.1.0 upgrade, all three availability
states, provenance rejection, retained path/history, restoration, all EvidenceSource
cardinalities and offset cases, source expiration survival, append-only Evidence and
lineage, simultaneous protections, independent release, manual pins, duplicate and
origin constraints, scientific-history survival, and the complete existing v1.1.0
suite.

## Production-sized Raspberry Pi migration benchmark

The migration was run only against an online-backup copy on the production Raspberry
Pi. The live database was not opened for migration.

| Measure | Result |
|---|---:|
| Database size before | 40,988,672 bytes (39.09 MiB) |
| Database size after | 62,451,712 bytes (59.56 MiB) |
| Increase | 21,463,040 bytes (20.47 MiB) |
| Recording rows | 29,067 |
| Detection rows | 4,901 |
| Total migration duration | 93.853 seconds |
| Availability backfill | 93.594 seconds |
| Index creation | 32.122 milliseconds |
| Peak process RSS | 35,936 KiB (35.09 MiB) |
| Second/idempotent run | 0 migrations in 0.002 seconds |

Availability result:

| Availability | Count |
|---|---:|
| `AVAILABLE` | 3,444 |
| `INTENTIONALLY_EXPIRED` | 25,623 |
| `MISSING` | 0 |

- Confident historical expirations: **25,623**.
- Absent sources without sufficient expiration provenance: **0**.
- Ambiguous legacy cases: **0**.
- Migration warnings: **none** (`[]`).
- `PRAGMA integrity_check`: **ok**.
- `PRAGMA foreign_key_check`: **0 violations**.
- Recording RC1.1-field signature before/after: identical.
- Detection full-row signature before/after: identical.
- Recording IDs, Detection IDs, counts, and prior scientific fields changed: **none**.
- Evidence and protection rows fabricated: **0**.
- Live production database SHA-256 before/after the timed benchmark: identical.
- Temporary benchmark footprint: 242 MiB, removed after validation.

The result is practical on current Raspberry Pi hardware. The one-time 94-second
migration is bounded, idempotent, backed up, transactional, and uses approximately 35
MiB peak RSS. Most time is filesystem verification of 29,067 historical source paths,
not SQLite index work.

## Compatibility, deviations, and limitations

Compatibility findings:

- Existing integer identities, timestamps, Detection meaning, counts, and scientific
  rows are retained.
- Recorder insertion now adds lifecycle provenance without changing recorder output.
- Current cleanup policy is unchanged; when it expires a source it now records the
  lifecycle transition and respects active protections.
- Dashboard, BirdNET, backup, and restore interfaces are unchanged.
- Migration history remains immutable across LF/CRLF staging environments.

Narrow implementation choices:

- `EXTERNALLY_ARCHIVED` was optional and is not implemented.
- Evidence targets existing Detection rows in M1. Encounter/Observation targets are
  deferred until those approved tables exist.
- Recording quality storage is deferred for the boundary reason documented above.

Known limitations:

- The migration trusts the explicit RC1.1 `audio_expired` status as the available
  row-level provenance from the authorized cleanup. It deliberately classifies any
  other absent source as `MISSING`.
- Filesystem checks dominate the one-time migration duration and therefore depend on
  storage latency.
- Human/Expert Evidence is representable at the database layer but intentionally has
  no M1 application creator; the Review System owns that future write path.

No production audio, database history, or production scientific record was deleted or
modified. Only the isolated benchmark copy and its temporary files were changed; the
temporary directory was removed after evidence capture.

Recommendation: merge only after review and CI approval. Do not begin the Review
System until HQ accepts this milestone.
