# RC1.2 transition plan

RC1.2 does not begin until v1.1.0 is published and the released `master` commit is
verified. This plan creates no branch, milestone, issue, or feature during the soak.

## Branch transition

1. Finish every v1.1.0 release-checklist item and publish tag `v1.1.0`.
2. Confirm local and remote `master` point at the accepted release commit.
3. Create `develop` from that exact commit and push it once:

   ```bash
   git checkout master
   git pull --ff-only origin master
   git checkout -b develop
   git push -u origin develop
   ```

4. Continue to treat `master` as releasable. Begin RC1.2 work from `develop` using the
   prefixes in `docs/REPOSITORY_MAINTENANCE_POLICY.md`.
5. Do not recreate a versionless integration branch. If RC1.2 needs a stabilization
   branch, use a bounded `release/<version>` branch with a named owner and end condition.

## Milestone preparation

After publication, create an RC1.2 milestone with:

- a written scientific objective and explicit non-goals;
- an owner and acceptance evidence for every issue;
- separate labels for research, calibration, UI, infrastructure, and release work;
- no automatic carry-over of optional v1.1.0 enhancements;
- a field-data gate before changing Verification V2 weights;
- Raspberry Pi performance and rollback criteria for operational changes.

## Planning entry points

- [Technical roadmap](../../ROADMAP.md)
- [Architecture](../../ARCHITECTURE.md)
- [Verification V2](../../ai-verification-v2.md)
- [Verification evaluation](../../verification-evaluation.md)
- [Calibration report](../../verification-calibration-report.md)
- [Performance and scalability report](../../PERFORMANCE_SCALABILITY_REPORT.md)
- [Repository maintenance policy](../../REPOSITORY_MAINTENANCE_POLICY.md)
- [Contributor workflow](../../../CONTRIBUTING.md)

## Release boundary

RC1.2 planning may refine issue statements after v1.1.0, but implementation, calibration,
new modules, and user-facing changes are outside this transition task. The production
soak and v1.1.0 tag remain based on the validated RC1.1 candidate.
