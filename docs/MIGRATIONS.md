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
