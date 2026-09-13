# Migration guide

SQL migrations live in `data/database/migrations` and use
`NNNN_short_description.sql`. Versions are immutable after release.

`pfm migrate` discovers pending files, verifies checksums of applied files, creates an
online database backup, and applies each migration in its own transaction. A failure
rolls back that migration. Foreign keys are validated before commit.

Migration checksums are calculated after normalizing line endings to LF. This keeps
the immutable checksum stable when a release is staged from a Windows checkout while
still detecting substantive edits to an applied migration.

Create the next sequential file using idempotent indexes/tables where possible. Test
both a fresh database and a copy upgraded from the previous release. SQLite cannot
directly remove or alter many columns; use create/copy/validate/rename in one migration.
Never put `BEGIN`, `COMMIT`, `VACUUM`, or filesystem operations in migration SQL.

Migration 0006 adds the RC1.2 Evidence Schema Foundation. Its lifecycle backfill is
conservative: a present source becomes `AVAILABLE`; an absent source becomes
`INTENTIONALLY_EXPIRED` only when the RC1.1 `audio_expired` status supplies affirmative
provenance; every other absent source becomes `MISSING`. The run metrics and any
warnings are retained in `evidence_schema_migration_runs`.

Migration 0007 adds the RC1.2 Human Review Provenance Foundation. It preserves
`detection_reviews` as immutable legacy history and imports only `verified`, `rejected`,
and valid `corrected_species` rows into canonical append-only Reviews. `pending_review`
and `ignored` remain only in legacy history. Imported Reviews are marked
`LEGACY_IMPORT`, keep a unique legacy-row anchor, and do not fabricate Evidence links.
Counts, timings, invalid rows, ambiguities, and warnings are retained in
`review_schema_migration_runs`.

Migration 0008 adds the RC1.2 Assessment Provenance Foundation. It creates
Detection-scoped, append-only `assessments` and the many-to-many
`assessment_evidence` relationship. Assessment results use their own scientific
vocabulary, Evidence links are constrained to the assessed Detection, and explicit
supersession preserves all prior conclusions. This migration is schema-only: it does
not infer Assessments from Review or legacy Verification state, so historical
Assessment backfill is always zero.

Migration 0009 adds the RC1.2 Ground Truth Candidate Membership Foundation. It creates
immutable named candidate datasets and explicit Assessment-pinned membership in the
sole `CANDIDATE_POOL` stage. Admission requires Assessment-cited bounded source
provenance on the Detection Recording and source availability at nomination time.
The migration is schema-only and creates no datasets, memberships, protections,
Observations, or other scientific conclusions.

Migration 0010 adds the RC1.2 Ground Truth Adjudication Provenance Foundation. It
creates append-only, policy-versioned `ground_truth_adjudications` and the explicit
many-to-many `ground_truth_adjudication_evidence` relationship. The supported write
boundary derives eligibility from the current candidate, exact pinned Assessment,
bounded available sources, canonical human/expert Evidence, and adjudicator authority;
successful adjudication atomically protects only cited required bounded sources. The
migration itself is schema-only and creates zero adjudications, Evidence links,
RecordingProtections, or Observations.
