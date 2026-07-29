# Migration guide

SQL migrations live in `data/database/migrations` and use
`NNNN_short_description.sql`. Versions are immutable after release.

`pfm migrate` discovers pending files, verifies checksums of applied files, creates an
online database backup, and applies each migration in its own transaction. A failure
rolls back that migration. Foreign keys are validated before commit.

Create the next sequential file using idempotent indexes/tables where possible. Test
both a fresh database and a copy upgraded from the previous release. SQLite cannot
directly remove or alter many columns; use create/copy/validate/rename in one migration.
Never put `BEGIN`, `COMMIT`, `VACUUM`, or filesystem operations in migration SQL.
