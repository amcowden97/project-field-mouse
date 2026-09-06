# RC1.2 Human Review Provenance Foundation — Implementation Report

## Implementation summary

The Human Review Provenance Foundation adds a canonical, append-only human Review
model without replacing RC1.1 review history. A Review evaluates one existing
Detection, identifies the reviewer and decision, cites explicit Evidence, and may
explicitly supersede one earlier Review of the same Detection. Conflicting Reviews are
preserved and remain simultaneously current unless one is explicitly superseded.

- Branch: `feature/rc1.2-human-review-provenance`
- Starting point: Evidence Schema Foundation `00bd6c8afb387d12b0c14fe9bbfc7b6f0df3b96a`
- Implementation commit: `44c708a045da2a70fca80ea7f0993a742ad14d25`
- Validation report commit: `ff20ec2` (the final status-only commit is recorded in
  the HQ handoff)

## Files and final schema

Migration `0007_human_review_provenance.sql` adds:

- `reviews`: stable identity, Detection, controlled decision, reviewer identity and
  role, review time, reason code, notes, optional corrected taxon, optional explicit
  supersession, optional legacy anchor, and creation time.
- `review_evidence`: an append-only many-to-many Review-to-Evidence relationship with
  `PRIMARY`, `SUPPORTING`, and `CONTEXT` roles.
- `review_schema_migration_runs`: deterministic legacy-backfill counts, duration,
  ambiguities, invalid rows, and warnings.
- append-only protection for both canonical records and existing
  `detection_reviews` history.

Indexes support Review history by Detection, reviewer, decision, supersession lookup,
Evidence lookup in both relationship directions, stable Review identity, and the
unique legacy anchor. Foreign keys use `ON DELETE RESTRICT` for scientific provenance.

No source-availability field is present on `review_evidence`. Media availability
remains canonical on Recording, while EvidenceSource remains the Evidence-to-media
boundary.

## Review domain behavior

The service in `app/science/reviews.py` supports:

- create and retrieve Review;
- list all Review history for a Detection;
- retrieve every Evidence relationship for a Review;
- list all currently non-superseded Reviews without selecting a winner;
- atomic validation and persistence of Review plus ReviewEvidence.

Supported decisions are exactly `CONFIRM`, `REJECT`, `UNSURE`, and `CORRECT_TAXON`.
Absence represents not reviewed; no pending scientific decision exists. Reviewer roles
are exactly `USER`, `EXPERT`, and `LEGACY_IMPORT`, with no authority weighting or trust
score.

New USER and EXPERT Reviews require one or more explicit Evidence items. Each Evidence
must exist and target the same Detection. Duplicate Evidence relationships are
rejected. The legacy exception permits zero Evidence only for a `LEGACY_IMPORT` Review
with a unique `legacy_detection_review_id`.

`CORRECT_TAXON` requires a proposed scientific or common name. The service never
updates Detection species, confidence, detector, timestamps, or machine provenance.
Proposed taxa on other decisions are rejected.

## ReviewEvidence and supersession

One Review may cite multiple Evidence items and one Evidence item may inform multiple
Reviews. Relationships are immutable, foreign-key protected, role controlled, and
unique per Review/Evidence pair. A database trigger independently enforces that Review
and Evidence target the same Detection.

Supersession is optional and explicit. It must reference an existing Review for the
same Detection. The superseded row and its Evidence links remain queryable. Because
Reviews are append-only and new edges can point only to existing rows, the graph is
inherently acyclic; self-reference, cross-Detection edges, mutation-based cycles, and a
defensive recursive cycle case are rejected. A later Review does not implicitly
supersede anything, and disagreement does not invoke consensus.

## Legacy migration and compatibility

Migration 0007 maps only:

| RC1.1 state | Canonical decision |
|---|---|
| `verified` | `CONFIRM` |
| `rejected` | `REJECT` |
| valid `corrected_species` | `CORRECT_TAXON` |

`pending_review` and `ignored` are preserved but skipped. A correction without a
proposed taxon is reported invalid. Unknown states are reported ambiguous. Every
imported identity is deterministic from the legacy row ID, and the unique
`legacy_detection_review_id` is the idempotency anchor. Legacy `confidence_after`
remains only in `detection_reviews`; it is not promoted to Review or scientific
confidence. No Evidence or ReviewEvidence is fabricated for historical rows.

The existing `record_review()` and operator CLI remain compatible. The legacy row is
still appended and `verifications.review_status` is still updated as an isolated RC1.1
projection. When an operator supplies explicit `--evidence-id` values, the same atomic
adapter also creates the canonical Review; the first cited item is PRIMARY and later
items are SUPPORTING. Existing invocations without Evidence continue to create only
legacy history rather than fabricating canonical provenance. Canonical scientific
logic does not read `verifications.review_status`.

The evaluation exporter, reviewed-Detection preservation logic, legacy view, and
dashboard/backend compatibility consumers remain unchanged.

## Tests and scientific validation

Focused tests cover:

- fresh schema, controlled decisions/roles, missing Detection, identity uniqueness,
  and append-only Review/ReviewEvidence;
- one-to-one, one-to-many, and many-to-many ReviewEvidence, duplicate rejection, and
  cross-Detection incompatibility;
- USER/EXPERT Evidence requirements and the narrow LEGACY_IMPORT exception;
- all four decisions and correction-without-taxon rejection;
- byte-for-byte preservation of historical Detection claim fields after correction;
- conflicting unsuperseded Reviews from multiple reviewers;
- valid supersession, retained history, self-reference, cross-Detection reference,
  and cycle rejection;
- Recording source expiration after Detection → Evidence → Review, with every
  scientific row and relationship retained;
- deterministic legacy mapping of all supported and skipped states, invalid legacy
  correction reporting, idempotence, legacy-row immutability, and non-promotion of
  legacy confidence;
- the explicit CLI/legacy compatibility adapter.

Local validation:

- Focused review/migration/verification tests: **38 passed**.
- Full automated suite: **127 passed**.
- Ruff over `app`, `scripts`, and `tests`: **passed**.
- `python -m compileall -q app scripts tests`: **passed**.
- `git diff --check`: **passed**.
- SQLite synthetic migration: integrity **ok**, foreign-key violations **0**.
- GitHub Actions: not triggered. The branch remains local because this assignment did
  not explicitly authorize external publication; local CI-equivalent checks passed.

The synthetic legacy fixture contained six rows: three migrated, two non-conclusive
rows skipped, zero ambiguous, and one invalid correction. All six source rows remained
unchanged; the rerun created no duplicates.

## Safe production-copy validation

A read-only production database snapshot captured `2026-08-26T22:34:31Z` was copied
to an isolated benchmark location. The source snapshot was never modified.

| Measure | Result |
|---|---:|
| Database size before | 4,935,680 bytes |
| Database size after | 4,935,680 bytes |
| Starting migrations | 1–4 |
| Applied migrations | 5, 6, 7 |
| Total migration duration | 0.343448 seconds |
| Review backfill duration | 0.0348 milliseconds |
| Idempotent rerun | 0 migrations in 0.002242 seconds |
| Recordings | 2,820 |
| Detections | 1,034 |
| Legacy review rows | 0 |
| Canonical Reviews created | 0 |
| ReviewEvidence created | 0 |
| Migration warnings/ambiguities/invalid rows | 0 / 0 / 0 |

`PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned zero
violations. Detection, legacy-review, and all original RC1.1 Recording-field
signatures were unchanged. No Evidence or RecordingProtection was fabricated.

This safe snapshot contains no legacy human-review rows, so real production mapping
counts are all zero. The complete nonzero state mapping is therefore demonstrated by
the deterministic synthetic migration test rather than inferred from unrelated data.

## Deviations, risks, and scope confirmation

No scientific semantic deviation was required. Two narrow compatibility choices are
explicit:

- Existing operator calls without Evidence remain legacy-only so RC1.1 workflows do
  not break and provenance is not invented.
- No HTTP write endpoint was added; authentication and authorization policy remains a
  future prerequisite.

Current risks/limitations:

- Operators must supply Evidence IDs to the compatibility CLI for a new canonical
  scientific Review.
- Production-copy validation used the available August 26 snapshot. It had no legacy
  Review rows, so only the synthetic fixture exercises nonzero backfill mappings.
- Reviewer identity is attributed text under the current local operator boundary; no
  general authentication system was introduced.

Explicit scope confirmation:

- No Assessment or assessment semantics were implemented.
- No Observation was created.
- No Ground Truth eligibility or dataset behavior was implemented.
- No Species Trust score or reviewer weighting was implemented.
- No Evidence was fabricated by migration.
- No protection or automatic reviewed-recording retention was created.
- No destructive retention behavior, Recording deletion, audio deletion, or
  production-data mutation occurred.

Recommendation: ready for HQ review after CI passes. Do not begin the next RC1.2 slice
until HQ accepts this foundation.
