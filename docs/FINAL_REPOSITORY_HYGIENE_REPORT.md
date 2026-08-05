# Final Repository Hygiene Report

Date: 5 August 2026

## Outcome

The approved conservative cleanup is complete. The canonical clone is now the sole
primary Project Field Mouse checkout on `master`; one active refactor worktree remains.
No production application file was changed by this sprint, no history was rewritten,
and no force-push occurred.

Automated static validation passes. The full test suite reaches 67 tests on `master`,
with 65 passing and two pre-existing Windows-specific failures. Those failures require
engineering changes already represented in the preserved refactor line and were not
altered during this administrative sprint.

## Git cleanup

### Local branches removed

Each removed tip was reverified as an ancestor of `master` immediately before deletion:

- `feature/bird-verification`
- `feature/dashboard-v3-complete`
- `feature/infrastructure`
- `feature/runtime-compatibility-rc1`
- `feature/storage-retention-rc1`
- `fix/birdnet-timestamp-processing`
- `integration/v3`

### Local branches retained

- `master`: canonical RC1/RC1.1 starting branch.
- `admin/rc1-public-readiness`: commit `1268399`, preserving the completed public
  documentation and licensing work for intentional review/integration.
- `refactor/rc1-cleanup`: three unique cleanup/tooling commits; active worktree and
  required review candidate.
- `feature/dashboard-american-robin`: eight unique Dashboard/design commits.
- `feature/design-system`: six unique brand/design-system commits.
- `feature/detection-ai-american-robin`: four unique research/design commits.
- `feature/wildlife-research-american-robin`: ten unique research/retention commits.

Every retained branch has unique work and a documented purpose. None was deleted or
rewritten.

### Remote cleanup

- Deleted fully merged `origin/integration/v3` from GitHub.
- Pruned its local remote-tracking ref.
- Retained `origin/master`.
- Retained unmerged `origin/feature/dashboard-v3` because its milestone commit remains
  unique.

### Worktrees and tags

- Removed clean `project-field-mouse-infrastructure` worktree.
- Removed Git's clean `project-field-mouse-integration` worktree registration and all
  accessible residual checkout files.
- Retained `project-field-mouse-refactor` for its unmerged refactor branch.
- Retained both `v1.0.0-rc1` and `v2.0.0-alpha` tags unchanged.

## Repository cleanup

### Files removed

Twenty-nine confirmed obsolete tracked files were removed:

- Empty accidental `.gitignoreprintf`.
- All 26 files under superseded `dashboard-v1-archive/`.
- Obsolete `scripts/dashboard/milestone3.sh` scaffold generator.
- Obsolete `scripts/dashboard/milestone4.sh` completion placeholder.

The source snapshots remain recoverable from Git history; history was not rewritten.
No historical RC1 report, audit evidence, runtime-default CSV, empty environment
example, or empty test placeholder was removed because those items still require an
explicit disposition.

### Documentation

- Added `docs/REPOSITORY_MAINTENANCE_POLICY.md`.
- Added this final report.
- Linked the policy from `README.md` and `CONTRIBUTING.md`.
- Corrected the top-level license reference to Apache License 2.0 and restored the
  canonical root `LICENSE` on `master`.

### `.gitignore`

- Added `.ruff_cache/`, `.mypy_cache/`, `.tox/`, `.nox/`, Python packaging/build output,
  `Thumbs.db`, and `desktop.ini`.
- Consolidated duplicate recording and database rules.
- Preserved narrow rules for runtime data; broad JSON, CSV, image, and documentation
  ignores were deliberately avoided.

## Workspace cleanup

### Active Project Field Mouse paths

- `C:\Users\Andrew Cowden\Workspaces\project-field-mouse`: canonical clone on `master`.
- `C:\Users\Andrew Cowden\Workspaces\project-field-mouse-refactor`: active worktree on
  `refactor/rc1-cleanup` until review/integration.

### Removed paths

- `project-field-mouse-infrastructure`: removed completely.
- `project-field-mouse-integration`: detached and checkout contents removed. Its final
  directory contains only ACL-protected `.pytest_cache` and `.ruff_cache` directories;
  it is no longer a Git repository or worktree.

### Other repositories

- `.tools`: retained shared tooling.
- `project-harbor-porpoise`: retained as an unrelated active repository with its own
  uncommitted work.
- `project-harbor-porpoise-ais-ingestion`: preserved for that project's review; its WSL
  `.git` pointer remains outside this sprint's authority.

No archived repository was created and no unrelated clone was deleted.

## Validation

| Check | Result |
| --- | --- |
| Ruff (`app tests`) | PASS |
| Compileall (`app tests scripts`) | PASS |
| `git diff --check` | PASS after final formatting correction |
| `git fsck --no-reflogs --full` | PASS; only recoverable dangling objects from prior/deleted refs were reported |
| Full pytest suite | 65 PASS, 2 FAIL |
| Production-code diff | NONE |

The two pytest failures are:

1. `test_archive_backup_round_trip`: Windows cannot remove a temporary SQLite backup
   while it remains open on current `master`.
2. `test_health_report_is_station_scoped`: Windows `psutil` lacks
   `sensors_temperatures` on current `master`.

They are unrelated to deleted archives, scripts, documentation, licensing, or ignore
rules. The preserved `refactor/rc1-cleanup` branch contains resource-lifecycle and
platform-guard work intended to address this class of failure. It must be reviewed and
integrated through the normal engineering process rather than silently merged during
an administrative cleanup.

## Remaining recommendations

1. Review and integrate `refactor/rc1-cleanup`, then rerun the suite and retire its
   worktree/branch.
2. Review and integrate or intentionally archive `admin/rc1-public-readiness`.
3. Decide the disposition of the four American Robin/design/research branches and the
   unique remote Dashboard milestone branch before removing any of them.
4. Have the workspace owner remove the two ACL-protected residual cache directories in
   `project-field-mouse-integration`; they contain no tracked or unique work.
5. Decide whether `.env.example`, `tests/test_recorder.py`, and
   `data/detections/latest-birdnet-results.csv` are intentional placeholders/fixtures.
6. Consider organizing RC1 evidence under a documented release-evidence hierarchy in
   a separate link-preserving documentation change.

## RC1.1 readiness

Repository and workspace organization are ready for RC1.1 administrative work from the
canonical `master` clone. Engineering development should begin after the preserved
refactor branch is reviewed or with explicit acceptance of the two known Windows test
failures.
