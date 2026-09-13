# RC1.2 Ground Truth Adjudication Provenance Foundation — Implementation Report

## Implementation summary

The Ground Truth Adjudication Provenance Foundation adds an explicit, append-only,
policy-versioned scientific determination for one current Ground Truth candidate.
Each adjudication remains pinned through the candidate to one exact Assessment and
Detection, cites canonical Evidence, records adjudicator authority, and atomically
protects only the bounded source Recordings required by that adjudication.

- Branch: `feature/rc1.2-ground-truth-adjudication-provenance`
- Canonical base: `d6eb4e4f55ca474b0a497c3bb5e12000b6423e76`
- Implementation commit: `97648b4`
- Validation-report commit: recorded in the final HQ handoff

This slice implements only:

```text
GroundTruthMember (CANDIDATE_POOL)
  → exact Assessment
  → bounded Detection
  → explicit GroundTruthAdjudication
  → cited canonical Evidence
  → required bounded-source RecordingProtection
```

It does not implement Ground Truth dataset release, adjudication automation,
Observation, Species Trust, model training, or a research-pool import.

## Starting-point verification

The branch was created from the exact required clean SHA. Migrations 0001–0009 and
the approved Evidence, Human Review, Assessment, Candidate Membership,
RecordingProtection, and source-availability implementations were present. The
inherited full suite passed with 171 tests before implementation.

No material contradiction with the approved architecture was found.

## Schema implemented

Migration `0010_ground_truth_adjudication_provenance.sql` is additive and creates two
empty tables, supporting indexes, restrictive foreign keys, consistency triggers,
and append-only protections.

### `ground_truth_adjudications`

Each row stores:

- integer primary key and unique durable `adjudication_identity`;
- restrictive reference to one exact `ground_truth_member_id`;
- one controlled scientific result;
- optional adjudicated scientific/common-name claim under result-specific rules;
- explicit reason code, reasoning, actor, Ground Truth authority role, and policy
  version;
- optional same-member `supersedes_adjudication_id`;
- unique deterministic input fingerprint and idempotency key;
- immutable creation timestamp.

Supported results are exactly:

| Result | Taxon rule | Meaning |
|---|---|---|
| `CONFIRMED_TAXON` | Required | Evidence supports the stored canonical taxon for this bounded event. |
| `ALTERNATE_TAXON` | Required | Another taxon is established without changing the historical Detection. |
| `DETECTOR_CLAIM_NOT_SUPPORTED` | Must be NULL | This event does not support the detector claim; it is not a broader absence claim. |
| `UNRESOLVED` | Must be NULL | The available Evidence cannot support a defensible scoped conclusion. |

`EXCLUDED` is neither present in the enum nor accepted by the schema. There is no
confidence, mutable current flag, Observation reference, or dataset-release state.

Adjudicator roles are exactly `SCIENTIFIC_OWNER` and `EXPERT`; they are independent
of Review reviewer roles. The schema does not introduce an account or credential
registry.

Indexes support member history, result history, positive taxon lookup, and
supersession traversal. Triggers reject cross-member supersession, mutation, and
deletion. Self-reference is constrained directly. Because immutable new rows can
reference only existing rows, cycles are structurally unreachable through the
supported path; the recursive trigger remains defense in depth.

### `ground_truth_adjudication_evidence`

The append-only relationship contains its primary key, adjudication ID, Evidence ID,
relationship role, and creation time. Roles are exactly `PRIMARY`, `SUPPORTING`, and
`CONTEXT`. The adjudication/Evidence pair is unique, both foreign keys are
`ON DELETE RESTRICT`, and indexes support traversal in both directions.

A database trigger independently resolves:

```text
Adjudication → GroundTruthMember → Assessment → Detection
```

and rejects any Evidence targeting another Detection. Evidence need not have been
cited by the pinned Assessment; the Assessment remains immutable and unchanged.

## Read-only eligibility

`evaluate_ground_truth_adjudication_eligibility()` returns a deterministic structured
result containing eligibility, reason codes, exact member/Assessment/Detection IDs,
the required Recording IDs, and whether a material Review conflict exists. It writes
no adjudication, relationship, protection, or other durable state.

Reason codes include:

- `ELIGIBLE`;
- `CANDIDATE_NOT_FOUND`;
- `NOT_CURRENT_CANDIDATE`;
- `INVALID_EVENT_PROVENANCE`;
- `INVALID_EVIDENCE_PROVENANCE`;
- `SOURCE_UNAVAILABLE`;
- `NO_CANONICAL_HUMAN_EVIDENCE`;
- `UNRESOLVED_REVIEW_CONFLICT`;
- `ADJUDICATOR_IDENTITY_REQUIRED`;
- `ADJUDICATOR_AUTHORITY_REQUIRED`;
- `POLICY_VERSION_REQUIRED`;
- `INVALID_RESULT`.

Eligibility requires a current, unsuperseded `CANDIDATE_POOL` member, its exact pinned
Assessment and bounded Detection, explicit actor/authorized role/policy, cited
same-Detection Evidence, at least one cited `HUMAN` or `EXPERT` Evidence item, and
required bounded source coverage while every qualifying required source is
`AVAILABLE`.

All four Assessment results remain eligible inputs. The helper does not require high
detector confidence, Assessment `SUPPORTED`, two reviewers, universal expert review,
quality scoring, or agreement with the detector.

Canonical non-legacy human contribution is represented by cited Evidence whose
family is `HUMAN` or `EXPERT`. Migration 0007 deliberately created no such Evidence
for legacy Reviews, so legacy Review history and truth-looking compatibility state do
not satisfy this requirement.

## Material Review conflict policy

Conflict inspection considers current, unsuperseded canonical Reviews by `USER` or
`EXPERT` actors. `CONFIRM` resolves to the historical Detection taxon,
`CORRECT_TAXON` to its proposed taxon, `REJECT` to the scoped unsupported position,
and `UNSURE` to unresolved. More than one distinct current position is a material
conflict.

A `SCIENTIFIC_OWNER` cannot record `CONFIRMED_TAXON` or `ALTERNATE_TAXON` while that
material conflict remains. An `EXPERT` may explicitly resolve it. `UNRESOLVED`
remains available without fabricating consensus. Review rows, ReviewEvidence, and
Review supersession remain unchanged and independently auditable.

## Atomic adjudication boundary

`create_ground_truth_adjudication()` accepts the conclusion from its caller; it never
chooses a result. The operation validates:

1. normalized result and taxon semantics;
2. explicit actor, authorized role, policy version, rationale, and retry key;
3. current candidate membership;
4. exact pinned Assessment and bounded Detection;
5. canonical human/expert contribution;
6. every Evidence ID and same-Detection relationship;
7. required bounded source coverage and availability;
8. current material Review conflict and authority policy;
9. same-member supersession;
10. valid relationship roles and no duplicate cited Evidence.

It then writes the immutable adjudication, all adjudication-Evidence relationships,
and required RecordingProtections inside one savepoint. Forced relationship or
protection failure rolls the entire operation back, leaving zero partial rows.

Evidence inputs are sorted before SHA-256 fingerprinting. Exact retries return the
existing adjudication; reuse of the idempotency key with changed scientific inputs is
rejected. Generated identity and creation time do not make a retry scientifically
different.

## Source protection semantics

Candidate nomination and eligibility evaluation still create zero protections.
Successful adjudication creates an active protection with:

```text
protection_type  = GROUND_TRUTH_EVIDENCE
origin_type      = GROUND_TRUTH
origin_reference = <stable adjudication identity>
```

A required source is a bounded EvidenceSource reached from Evidence cited as
`PRIMARY` or `SUPPORTING` whose interval covers the candidate Detection interval. At
least one required source must be on the Detection Recording. Every distinct
qualifying Recording is protected; duplicate Recording IDs are collapsed. `CONTEXT`
sources and sources reachable only through uncited historical Evidence are not
protected.

All qualifying required Recordings must be `AVAILABLE` at creation. `UNRESOLVED`
adjudications receive the same protection because later re-evaluation may require the
source. Existing protection enforcement blocks ordinary intentional expiration.
Automatic protection release was not implemented.

## Supersession and pinned history

Correction appends adjudication B with an explicit reference to adjudication A. Both
must target the same GroundTruthMember. A remains stored, queryable, and protected;
no row is updated or deleted. Current heads are derived from incoming supersession
edges. Multiple unsuperseded heads remain visible rather than being resolved
automatically.

Candidate membership continues to pin its exact Assessment. If a later Assessment
supersedes that Assessment, the candidate and its adjudications continue to resolve
the original. Re-nomination through explicit GroundTruthMember supersession remains
the only way to change candidate basis.

## Migration and compatibility

Migration 0010 is schema-only and performs no backfill. It creates:

- 0 historical Ground Truth adjudications;
- 0 adjudication-Evidence relationships;
- 0 Ground Truth RecordingProtections;
- 0 Observations.

It does not infer adjudication from Detection confidence, Verification V2, legacy or
canonical Reviews, Assessments, candidate membership, or research material. Existing
candidate rows retain `stage = CANDIDATE_POOL`. Detection, Evidence, Review,
Assessment, Verification, and candidate membership content remain unchanged.

## Automated validation

| Validation | Result |
|---|---:|
| Focused Ground Truth adjudication suite | 38 passed |
| Combined adjudication/candidate/Assessment/Review/Evidence/migration suite | 120 passed |
| Complete repository suite | 209 passed |
| Ruff over `app`, `scripts`, and `tests` | passed |
| Ruff formatter check for new Python files | passed |
| `python -m compileall -q app scripts tests` | passed |
| `git diff --check` | passed |
| Synthetic SQLite integrity | `ok` |
| Synthetic foreign-key violations | 0 |

Focused coverage includes all required results and taxon constraints; both authority
roles; human and expert Evidence; missing/legacy-only human provenance; missing,
unavailable, unbounded, duplicate, and cross-Detection Evidence; Assessment
disagreement; material Review conflict; explicit `UNRESOLVED`; idempotence;
atomicity; required source protection; multiple protected sources; protection
failure; append-only history; supersession, ambiguity, self/cross-member/cycle
rejection; exact Assessment pinning; unchanged scientific history; no Observation or
Species Trust state; zero migration backfill; migration rerun; integrity; and foreign
keys.

GitHub Actions was not triggered because this implementation assignment did not
authorize publication. These local checks are the repository's CI-equivalent
validation.

## Safe production-copy validation

The read-only representative production snapshot at
`pfm-storage-evidence-20260826/legacy-source/fieldmouse.db` was copied into an isolated
workspace. The source snapshot, production station, and source audio were never
modified. Its migrations 1–4 were advanced through prerequisite migrations 5–9;
migration 0010 was then measured independently.

| Measure | Result |
|---|---:|
| Source snapshot size | 4,935,680 bytes |
| Database size immediately before migration 0010 | 4,935,680 bytes |
| Database size immediately after migration 0010 | 4,935,680 bytes |
| Allocated-file growth | 0 bytes |
| Migration 0010 duration | 45.987 ms |
| Applied version | 10 only |
| Existing tables compared | 20 |
| Existing table signatures unchanged | yes |
| Recordings | 2,820 |
| Detections | 1,034 |
| Existing Ground Truth members | 0 |
| Historical adjudications created | 0 |
| AdjudicationEvidence rows created | 0 |
| RecordingProtections before/after | 0 / 0 |
| Observation tables | 0 |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | 0 |
| Idempotent rerun | 0 migrations in 8.445 ms |

No Pi benchmark was run. Migration 0010 creates only empty tables, indexes, and
triggers and performs no row scan, backfill, or populated index construction. The
safe copy completed in 45.987 ms with zero allocated growth, so an on-device benchmark
would not materially reduce migration risk.

## Limitations and exact deferred scope

- The schema cannot express a deferred parent-must-have-child-or-protection assertion
  at transaction commit without duplicated anchors or a different staging design.
  The supported atomic write boundary enforces Evidence and protection cardinality;
  unmanaged direct SQL remains outside that boundary.
- Authority is recorded as explicit actor text and controlled role, with no account
  registry or credential system.
- Taxon identity uses the existing scientific/common-name representation; no taxonomy
  redesign was introduced.
- Material Review conflict is exposed by deterministic current-position comparison;
  no consensus score or winner selection exists.
- There is no adjudication engine, automatic result, Ground Truth Dataset Program,
  release/exclusion policy, calibration split, research-pool import, Observation,
  Species Trust, dashboard/API/UI work, model work, protection release, cleanup, or
  audio operation.

No production database, production service, or audio file was modified or deleted.

## Recommendation

The RC1.2 Ground Truth Adjudication Provenance Foundation is ready for HQ review.
Stop here; dataset release, automated reasoning, Observation, Ground Truth program
governance, and Species Trust require separate authorization.
