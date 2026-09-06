# RC1.2 Ground Truth Candidate Membership Foundation - Implementation Report

## Implementation summary

The Ground Truth Candidate Membership Foundation adds an explicit, candidate-only,
append-only record that a scientific actor nominated one exact Assessment-backed
event into one named Ground Truth dataset under a documented policy and rationale.

- Branch: `feature/rc1.2-ground-truth-candidate-membership`
- Required starting point:
  `f409bebdf09d10caa7aad4f82ed1ed124ebaef5a`
- Implementation commit:
  `d54ad82571bea079bd70cdba8671181e411d0583`
- Validation-report commit: recorded in the final HQ handoff

This slice stops at:

```text
Named Ground Truth Dataset
  -> explicit Candidate Nomination
  -> exact Assessment
  -> Assessment-cited Evidence
  -> bounded EvidenceSource on the Detection Recording
```

Candidate membership is research selection. It is not adjudicated Ground Truth,
calibration eligibility, a released dataset, or an assertion that BirdNET was
correct.

## Starting-point verification

The branch was created directly from the required clean Assessment Provenance
Foundation SHA. Migrations 0001 through 0008 and the predecessor Evidence, Review,
and Assessment foundations were present. The divergent 100-recording research
candidate package was treated only as research context and was not merged, modified,
or imported.

## Schema implemented

Migration `0009_ground_truth_candidate_membership.sql` is additive and creates two
empty tables, supporting indexes, and history-preserving triggers.

### `ground_truth_datasets`

The table stores a unique stable `dataset_identity`, name, purpose, nomination policy
version, creator, and creation timestamp. Dataset rows are immutable: database
triggers reject update and delete operations.

No release, version, eligibility, adjudication, or mutable lifecycle state is
represented.

### `ground_truth_members`

Each membership stores:

- a unique stable `member_identity`;
- a restrictive foreign key to one dataset;
- a restrictive foreign key to one exact Assessment;
- the sole permitted stage, `CANDIDATE_POOL`;
- nomination reason code, reasoning, actor, and policy version;
- optional same-dataset `supersedes_member_id` with restrictive history semantics;
- unique deterministic input fingerprint and idempotency key;
- immutable creation time.

The stage check structurally rejects `ADJUDICATED` and every other later state. There
is no mutable `current`, `active`, released, or calibration-eligible field. Update and
delete triggers make membership history append-only. Database constraints and
triggers reject self-reference and cross-dataset supersession; a recursive trigger is
retained as cycle defense in depth. With append-only rows referencing only earlier
rows, cycles are also structurally unreachable through the supported write path.

Indexes support dataset history, Assessment lookup, and supersession traversal.

## Domain behavior

`app/science/ground_truth.py` provides the narrow candidate domain:

- `GroundTruthStage.CANDIDATE_POOL`;
- immutable `GroundTruthDatasetRecord` and `GroundTruthMemberRecord` values;
- idempotent dataset creation and dataset retrieval;
- explicit candidate nomination and member retrieval;
- complete dataset history and derived current-head queries.

Dataset creation normalizes required text and treats stable dataset identity as its
retry identity. Reuse with matching immutable fields returns the existing dataset;
reuse with different fields raises `ScienceInvariantError`.

Candidate nomination requires non-empty actor, reason code, reasoning, policy
version, and idempotency key. The supplied policy must equal the immutable dataset
policy. The operation pins one exact existing Assessment without modifying or
following later Assessment supersession.

## Event and source provenance

Admission validates that the Assessment targets an existing Detection whose start
and end offsets are finite, non-negative, and ordered with `start < end`.

At least one Evidence item explicitly cited by that Assessment must have an
EvidenceSource that:

- references the Detection's Recording;
- has both interval bounds;
- covers the Detection event interval; and
- resolves to an `AVAILABLE` Recording at initial nomination.

This prevents recording-level research rows from becoming canonical members without
exact event provenance. It does not create Encounter persistence.

After successful nomination, source availability remains resolved through the
canonical Assessment/Evidence/EvidenceSource/Recording chain. A later transition to
`INTENTIONALLY_EXPIRED` or `MISSING` does not mutate or erase membership or scientific
history. An exact idempotent retry continues to return the existing membership after
such a source transition because it is not a new admission.

## Idempotency and atomicity

The nomination fingerprint is SHA-256 over normalized material inputs: dataset,
Assessment, candidate stage, reason, reasoning, actor, policy, superseded membership,
and any caller-supplied member identity.

- An exact retry with the same idempotency key returns the existing member ID.
- Reuse of the key with changed input raises `ScienceInvariantError`.
- A unique input fingerprint prevents equivalent scientific input from creating a
  second row under a different retry key.
- New membership insertion uses a savepoint; forced insertion failure leaves no
  partial membership.

Creation timestamps and generated identities are intentionally not allowed to make
equivalent retries appear scientifically different.

## Supersession semantics

A correction creates a new immutable membership that may explicitly supersede an
earlier member of the same dataset. The earlier row and its exact Assessment remain
queryable. Cross-dataset supersession fails in both the service and schema.

`list_current_ground_truth_members()` derives heads as rows for which no later row
names them in `supersedes_member_id`. It stores no mutable current flag. Multiple
unsuperseded heads remain visible; this foundation does not infer consensus.

## Migration and compatibility

Migration 0009 is schema-only. It creates:

- 0 Ground Truth datasets;
- 0 Ground Truth members;
- 0 RecordingProtection rows;
- 0 Observations.

It does not inspect or infer membership from BirdNET confidence, Verification V2,
legacy or canonical Reviews, Assessments, Detection history, or research candidate
files. Candidate nomination similarly creates no RecordingProtection, Observation,
or Species Trust state and does not mutate Detection, Evidence, Review, Assessment,
or Verification records.

All four Assessment results remain nominatible: `SUPPORTED`, `NOT_SUPPORTED`,
`INCONCLUSIVE`, and `ALTERNATE_TAXON`.

## Automated validation

Validation used a fresh Python 3.13.14 environment installed from the repository's
production and development requirement files.

| Validation | Result |
|---|---:|
| Focused Ground Truth suite | 29 passed |
| Combined Ground Truth/Evidence/Review/Assessment/migration suite | 82 passed |
| Complete repository suite | 171 passed |
| Ruff over `app`, `scripts`, and `tests` | passed |
| Black check for new Python files | passed |
| `python -m compileall -q app scripts tests` | passed |
| Installed dependency consistency (`uv pip check`) | 74 compatible packages |
| BirdNET import/package compatibility | `birdnet==0.2.16` |
| Time-zone data compatibility | `tzdata==2026.3`; Los Angeles zone resolved |
| `git diff --check` | passed |
| Synthetic SQLite integrity | `ok` |
| Synthetic foreign-key violations | 0 |

GitHub Actions was not triggered because the assignment did not authorize external
publication. These are the repository's local CI-equivalent checks.

## Safe production-copy validation

The read-only representative snapshot at
`pfm-storage-evidence-20260826/legacy-source/fieldmouse.db` was copied into an isolated
workspace. The source snapshot, production station, and source audio were not
modified. The copy initially contained migrations 1 through 4; prerequisite
migrations 5 through 8 were applied before migration 0009 was measured independently.

| Measure | Result |
|---|---:|
| Source snapshot size | 4,935,680 bytes |
| Database size immediately before migration 0009 | 4,935,680 bytes |
| Database size immediately after migration 0009 | 4,935,680 bytes |
| Allocated-file growth | 0 bytes |
| Migration 0009 duration | 123.053 ms |
| Applied version | 9 only |
| Recordings before/after | 2,820 / 2,820 |
| Detections before/after | 1,034 / 1,034 |
| Evidence before/after | 0 / 0 |
| Reviews before/after | 0 / 0 |
| Assessments before/after | 0 / 0 |
| RecordingProtections before/after | 0 / 0 |
| Ground Truth datasets before/after | 0 / 0 |
| Ground Truth members before/after | 0 / 0 |
| Observation tables after | 0 |
| Existing table row signatures unchanged | yes, all 18 pre-existing tables |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | 0 |
| Idempotent rerun | 0 migrations in 3.395 ms |

## Scientific invariant coverage

| Invariants | Validation evidence |
|---|---|
| GT-INV-01 through GT-INV-04 | Before/after snapshots prove nomination does not mutate Detection, Evidence, Review, or Assessment. |
| GT-INV-05 through GT-INV-09 | Explicit tests prove `SUPPORTED`, Review `CONFIRM`, Verification `verified`, and high BirdNET confidence create zero members until nomination is called. |
| GT-INV-10, GT-INV-11, GT-INV-24 | Schema permits only `CANDIDATE_POOL` and contains no truth, eligibility, or release state. A direct `ADJUDICATED` insert fails. |
| GT-INV-12, GT-INV-13 | Restrictive exact Assessment FK and Assessment-supersession tests preserve the originally pinned Assessment. |
| GT-INV-14 through GT-INV-16, GT-INV-25 | Append-only triggers, immutable identities, preserved history, derived heads, and same-dataset-only supersession are tested. |
| GT-INV-17, GT-INV-18 | Both source lifecycle transitions preserve membership; `MISSING` remains distinct from `INTENTIONALLY_EXPIRED`. |
| GT-INV-19 through GT-INV-21 | Nomination creates no RecordingProtection, Observation, or Species Trust state. |
| GT-INV-22 | Missing, non-covering, partially covering, unavailable, and unbounded event provenance all fail admission. |
| GT-INV-23 | Migration from the migrations 1-8 schema creates zero datasets and members and is idempotent. |

## Known limitations and deferred policy

- Candidate membership has no adjudication, expert authority, consensus, release, or
  calibration-eligibility semantics.
- There is no Ground Truth Dataset v0.1 population, 100-recording import, reconciliation
  workflow, train/test split, or leakage policy.
- There is no automatic retention or RecordingProtection behavior.
- There is no Encounter, Observation, Species Trust, HTTP API, UI, dashboard, external
  service, classifier, or Assessment Engine work in this slice.
- Current-head queries expose the supersession graph; they deliberately do not decide
  among conflicting heads.

Ground Truth candidate membership is pinned to an exact Assessment because Assessment
is the current canonical persisted scientific conclusion. This does not predetermine
how later Ground Truth adjudication or released dataset semantics will be modeled.

## Recommendation

The RC1.2 Ground Truth Candidate Membership Foundation satisfies the authorized
candidate-only boundary and is ready for HQ review. Stop at `CANDIDATE_POOL`; later
Ground Truth governance and lifecycle work requires separate authorization.
