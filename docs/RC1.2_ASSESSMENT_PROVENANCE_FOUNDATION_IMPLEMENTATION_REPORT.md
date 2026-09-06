# RC1.2 Assessment Provenance Foundation — Implementation Report

## Implementation summary

The Assessment Provenance Foundation adds a canonical, Detection-scoped,
append-only representation of an explicit Project Field Mouse scientific conclusion.
Every Assessment is created explicitly, cites one or more canonical Evidence items,
and may supersede one earlier Assessment of the same Detection without rewriting it.

- Branch: `feature/rc1.2-assessment-provenance`
- Starting point: Human Review Provenance Foundation
  `fa41f1d8236b7802459913e1882c0459dd259e0d`
- Implementation commit: `76bd3c7`
- Validation report commit: recorded in the final HQ handoff

This slice stops at:

```text
Evidence → AssessmentEvidence → Assessment
```

It does not implement an Assessment Engine, Encounter persistence, Observation,
Ground Truth, Species Trust, confidence calibration, or automatic retention.

## Starting-point verification

The worktree was clean at the required Human Review SHA before the Assessment branch
was created. The inherited suite passed with 127 tests. Inspection confirmed:

- canonical `reviews` and `review_evidence` are append-only;
- Review supersession is explicit, same-Detection, and preserves history;
- a canonical Review cites caller-supplied Evidence and does not synthesize Evidence;
- migration 0007 performs its documented conservative legacy import;
- `verifications.review_status` remains an RC1.1 compatibility projection;
- canonical Review APIs do not create Assessment or Observation.

The fact that Review cites existing Evidence, rather than creating a new Evidence row,
matches the approved predecessor implementation and does not change the Assessment
boundary.

## Schema implemented

Migration `0008_assessment_provenance.sql` adds two tables.

### `assessments`

| Field | Purpose |
|---|---|
| `assessment_id` | Integer primary key. |
| `assessment_identity` | Stable, unique durable identity. |
| `payload_schema_version` | Version of the persisted Assessment payload. |
| `detection_id` | Required Detection target; `ON DELETE RESTRICT`. |
| `result` | `SUPPORTED`, `NOT_SUPPORTED`, `INCONCLUSIVE`, or `ALTERNATE_TAXON`. |
| `assessed_scientific_name` / `assessed_common_name` | Immutable snapshot of the machine Detection claim. |
| `alternate_scientific_name` / `alternate_common_name` | Alternate claim, permitted and required only for `ALTERNATE_TAXON`. |
| `reason_code` / `reasoning` / `created_by` | Explicit conclusion provenance and rationale. |
| `supersedes_assessment_id` | Optional prior Assessment of the same Detection; `ON DELETE RESTRICT`. |
| `input_fingerprint` | Unique deterministic SHA-256 of normalized scientific inputs. |
| `idempotency_key` | Unique caller retry key. |
| `created_at` | Immutable creation timestamp. |

There is deliberately no Assessment confidence, Review foreign key, Observation
field, protection field, or mutable `is_current` flag.

Indexes cover Detection history, result history, assessed taxon, alternate taxon,
and supersession lookup. Database triggers reject Detection-claim mismatch,
cross-Detection supersession, update, and delete. A recursive cycle trigger provides
defense in depth. In normal operation, cycles are already structurally impossible:
new append-only rows can reference only existing rows, self-reference is rejected,
and existing edges cannot be updated.

### `assessment_evidence`

The relationship stores only its primary key, `assessment_id`, `evidence_id`, and
`created_at`. It intentionally carries no supporting/challenging/context role because
Evidence already owns stance semantics.

The `(assessment_id, evidence_id)` pair is unique. Both foreign keys use
`ON DELETE RESTRICT`, indexes support traversal in both directions, and a database
trigger independently rejects Evidence whose Detection differs from the Assessment
target. Update and delete are blocked by append-only triggers.

One Assessment may cite many Evidence items, and one Evidence item may be reused by
many historical Assessments.

## Domain and repository behavior

`app/science/assessments.py` provides:

- `create_assessment()`;
- `get_assessment()`;
- `get_assessment_evidence()`;
- `list_assessment_history()`;
- `list_current_assessments()`.

The explicit write boundary validates the controlled result, Detection, alternate
taxon rules, non-empty and duplicate-free Evidence set, same-Detection Evidence,
provenance fields, and same-Detection supersession. It snapshots the original
Detection taxon without mutating Detection and writes the Assessment plus all
AssessmentEvidence relationships inside one savepoint.

Evidence IDs are canonicalized before fingerprinting, so retries do not depend on
input order. A reused idempotency key returns the existing Assessment only when the
full normalized input fingerprint matches; changed inputs are rejected. Forced
relationship failure rolls back both the Assessment and all links.

Currentness is derived by selecting Assessments that no later Assessment explicitly
supersedes. Multiple unsuperseded heads remain visible; the foundation does not invent
consensus or select scientific truth.

The service enforces the required one-or-more Evidence cardinality. SQLite cannot
express a deferred parent-must-have-child assertion at transaction commit without an
extra duplicated anchor or a materially different staging design. Direct unmanaged
SQL can therefore insert a parent without a link, but the only supported application
write path cannot. Foreign keys, same-Detection triggers, append-only triggers, and
the atomic service provide the remaining database and repository defenses.

## Migration and compatibility

Migration 0008 is additive and schema-only. Its historical Assessment backfill is
exactly zero. It does not inspect or translate truth-looking values from:

- `verifications.status`;
- `verifications.consensus_score`;
- `verifications.review_status`;
- `verification_results`;
- `detection_reviews`;
- canonical Review decisions;
- BirdNET confidence or Evidence stance.

No existing table or scientific row is updated by migration 0008. Existing RC1.1
Verification behavior, Evidence persistence, Review persistence, and legacy review
history continue to coexist unchanged.

Assessment creation has no side effect on Detection, Review, Verification V2,
RecordingProtection, source lifecycle, or dashboard compatibility state. It creates
no Observation table or row.

## Test coverage

Focused tests cover:

- fresh schema, indexes, foreign keys, controlled results, and absence of Assessment
  confidence or direct Review linkage;
- all four result values and `ALTERNATE_TAXON` validation;
- preservation of the original machine taxon;
- one-to-many and many-to-many AssessmentEvidence;
- missing, duplicate, and cross-Detection Evidence rejection;
- missing Detection and invalid Review-domain result rejection;
- deterministic retry and changed-input idempotency rejection;
- forced mid-write failure with zero partial rows;
- append-only Assessment and AssessmentEvidence behavior;
- same-Detection supersession, preserved history, current-head derivation,
  self-reference, cross-Detection reference, and mutation-based cycle rejection;
- independent Human Evidence, Review, and explicit Assessment creation;
- legacy Verification, corrected/rejected legacy reviews, and canonical Review
  separation;
- `AVAILABLE → INTENTIONALLY_EXPIRED` and `AVAILABLE → MISSING` source transitions
  with complete Assessment provenance retained;
- zero automatic RecordingProtection and Observation side effects;
- migration from the actual migrations 1–7 schema, zero backfill, unchanged existing
  table signatures, integrity, foreign keys, and idempotent rerun.

Validation results:

| Validation | Result |
|---|---:|
| Focused Assessment/Evidence/Review/migration suite | 53 passed |
| Full automated suite | 142 passed |
| Ruff over `app`, `scripts`, and `tests` | passed |
| `python -m compileall -q app scripts tests` | passed |
| `git diff --check` | passed |
| Synthetic SQLite integrity | `ok` |
| Synthetic SQLite foreign-key violations | 0 |

GitHub Actions was not triggered because this assignment did not authorize external
publication. The local checks are the repository's CI-equivalent validation.

## Safe production-copy validation

The read-only production snapshot captured on 2026-08-26 was copied to an isolated
workspace. The source snapshot and production station were never modified. The copy
contained 2,820 Recordings, 1,034 Detections, and migrations 1–4. Prerequisite
migrations 5–7 were first applied; migration 0008 was then measured independently.

| Measure | Result |
|---|---:|
| Database size before migration 0008 | 4,935,680 bytes |
| Database size after migration 0008 | 4,935,680 bytes |
| Allocated-file growth | 0 bytes |
| Migration 0008 duration | 47.334 ms |
| Applied version | 8 only |
| Historical Assessments created | 0 |
| AssessmentEvidence rows created | 0 |
| Existing scientific-table signatures unchanged | yes |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | 0 |
| Idempotent rerun | 0 migrations in 7.932 ms |

No Pi benchmark was run. Migration 0008 creates empty tables, indexes, and triggers;
it performs no row scan, backfill, or populated index construction. The production
copy completed in 47.334 ms with no allocated growth, so a new on-device benchmark
would not provide meaningful risk reduction.

## Scientific Integrity Invariant mapping

| Invariant | Validation evidence |
|---|---|
| INV-01 | Detection row snapshots are identical before and after Review and Assessment operations. |
| INV-02 | Evidence and its identity survive both tested source-availability transitions. |
| INV-03 | Review and Assessment occupy independent tables and require independent explicit writes. |
| INV-04 | No Observation model or side effect was introduced. |
| INV-05 | Review `CONFIRM` leaves Assessment count at zero until explicit creation. |
| INV-06 | Schema contains no Assessment confidence; detector and legacy confidence remain unchanged. |
| INV-07 | Existing Review supersession tests pass unchanged. |
| INV-08 | The supported write boundary rejects an empty Evidence set. |
| INV-09 | Source expiration retains Assessment, AssessmentEvidence, and Evidence. |
| INV-10 | Truth-looking legacy Verification/Review states create zero Assessments. |
| INV-11 | Assessment reasoning remains queryable after source becomes unavailable. |
| INV-12 | Assessment creation leaves RecordingProtection count unchanged at zero. |
| INV-13 | Database triggers reject Assessment and relationship update/delete. |
| INV-14 | `A → B` supersession retains and returns both historical rows. |
| INV-15 | Service and database constraints reject cross-Detection supersession. |
| INV-16 | AssessmentEvidence survives both ordinary lifecycle transitions. |
| INV-17 | The supported atomic creation API cannot persist Assessment without Evidence. |
| INV-18 | Service validation and a database trigger enforce same-Detection Evidence. |
| INV-19 | Assessment creation creates no Observation table or row. |
| INV-20 | `SUPPORTED` persists only an Assessment; no Observation semantics are inferred. |

## Limitations and exact deferred scope

- Assessment remains Detection-scoped until the approved Encounter slice exists.
- The foundation records explicit conclusions but does not calculate them.
- Human Evidence creation remains owned by the Review foundation; Assessment only
  consumes canonical Evidence IDs.
- No HTTP API or UI was added.
- No generalized taxonomy model was introduced; the Detection claim and optional
  alternate taxon are preserved as scientific/common-name snapshots.
- No automated creation, scoring, confidence, Observation, Encounter, Ground Truth,
  Species Trust, protection, retention, cleanup, source restoration, model, or
  dashboard behavior was added.

No production database or audio was modified or deleted.

## Recommendation

The RC1.2 Assessment Provenance Foundation is ready for HQ review. Do not proceed to
Assessment Engine, Observation, Ground Truth, Encounter, or Species Trust work until
HQ accepts this persistence foundation.
