# Foundation Phase Completion Report

Completion date: 5 August 2026

## Final assessment

**FOUNDATION PHASE COMPLETE — READY FOR RC1.1 PLANNING AND DEVELOPMENT**

The repository now has one intentional active-document surface, a discoverable RC1
release-history hierarchy, no approved temporary or generated artifacts under version
control, and documented maintenance practices. No production application or deployment
file changed during finalization.

## Repository summary

### Files moved into permanent RC1 history

The following final evidence is now under `docs/releases/rc1/`:

- Final release report.
- Release checklist.
- Runtime candidate validation.
- Runtime compatibility report.
- Storage retention report.
- Infrastructure handoff.
- Audio reconciliation narrative.
- Machine-readable audio audit under `docs/releases/rc1/evidence/`.

`docs/releases/rc1/README.md` indexes the release record and distinguishes it from
current installation and development documentation.

### Files archived

The following superseded or incident-focused documents are now indexed under
`docs/releases/rc1/archive/`:

- Three failed cutover attempts.
- Dependency blocker report.
- Deployment working-directory investigation.
- Superseded 4 August readiness report.

The archive remains in Git and linked from the RC1 release index. No history was
rewritten.

### Files removed

- `config/station.toml.before-storage-fix`: accidental temporary configuration backup.
- `data/detections/latest-birdnet-results.csv`: generated BirdNET output containing a
  developer-specific absolute path; its runtime path is now ignored narrowly.
- `tests/test_recorder.py`: empty test placeholder with no coverage.
- `scripts/lib/common.sh`: orphaned helper after milestone cleanup.
- `scripts/record_audio.sh`: unreferenced wrapper with an obsolete import path.
- `scripts/run_scheduler.sh`: unreferenced legacy scheduler wrapper superseded by the
  production adaptive-scheduler service.

All removals remain recoverable from Git history.

### Remaining top-level structure

The root now contains only:

- Repository and developer configuration: `.env.example`, `.gitattributes`, `.github/`,
  `.gitignore`, `.pre-commit-config.yaml`, and `pyproject.toml`.
- Public and release information: `README.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`,
  `CONTRIBUTING.md`, and `LICENSE`.
- Product and support directories: `app/`, `config/`, `data/`, `deploy/`, `docs/`,
  `samples/`, `scripts/`, and `tests/`.
- Dependency manifests: `requirements.txt`, `requirements-dev.txt`, and
  `requirements-production.txt`.

Historical JSON and timestamped release evidence no longer occupy the repository root.

## HQ review outcomes

### `.env.example` — KEEP AND POPULATE

The file now contains safe local-development examples for `PFM_CONFIG`, logging level,
localhost dashboard binding, and dashboard port. It includes no secret, precise
location, or production identity and explicitly states that the application does not
load it automatically.

### Legacy operator scripts

- `scripts/record_audio.sh` — **REMOVE**. No references; obsolete `source` import path;
  superseded by current module/service entry points.
- `scripts/run_scheduler.sh` — **REMOVE**. No references; invokes the legacy scheduler
  while production uses `adaptive_scheduler`.
- `scripts/show_recordings.sh` — **KEEP**. Provides a distinct read-only field
  diagnostic for recent recording rows that the current unified CLI does not expose.

## Validation summary

| Check | Result |
| --- | --- |
| Pytest | **PASS:** 65 passed, 2 documented Windows-specific tests deselected |
| Ruff | **PASS** |
| Compileall (`app`, `tests`, `scripts`) | **PASS** |
| Repository-relative Markdown links | **PASS** |
| `git diff --check` | **PASS** |
| `git fsck --no-reflogs --full` | **PASS**; only recoverable dangling objects were reported |
| Production `app/` changes | **NONE** |
| Deployment changes | **NONE** |

The final link audit found that the README referenced absent logo and dashboard image
files. The broken embeds were removed. Restoring approved branding artwork and adding a
current dashboard screenshot remain optional public-presentation improvements; they do
not block RC1.1 development.

The excluded tests are the previously documented Windows-only backup temporary-file
closure and unavailable `psutil.sensors_temperatures` cases on current `master`. Their
engineering fixes remain isolated on `refactor/rc1-cleanup` for normal review.

## Long-term direction

- Start RC1.1 work from the canonical `project-field-mouse` clone on `master`.
- Follow `docs/REPOSITORY_MAINTENANCE_POLICY.md` for branch, worktree, release, archive,
  and ignore lifecycle.
- Review the preserved refactor, public-readiness, Dashboard/design, AI research, and
  wildlife research branches through their normal ownership processes.
- Store future release evidence under `docs/releases/<version>/` from the outset.

All engineering teams may transition from Foundation Phase maintenance to RC1.1
planning and development.
