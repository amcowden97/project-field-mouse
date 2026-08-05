# Repository Curation Report

Review date: 5 August 2026

Scope: tracked `master` tree at `c8584bd`. This review made no deletion, move, archive,
or application change. Git metadata and ignored local caches are workspace state rather
than repository content and are excluded from the tracked-item classifications.

## Top-level review

| Item | Current purpose | Active usage | Regenerability | Historical value | Recommendation | Justification |
| --- | --- | --- | --- | --- | --- | --- |
| `.env.example` | Intended environment-variable example, but empty | None | Yes, from documented `PFM_*` settings | None | **HQ REVIEW REQUIRED** | Either populate it as the supported environment interface or remove the misleading empty placeholder. |
| `.gitattributes` | Enforces LF for migrations, shell scripts, and deployment executables | Git checkout and release packaging | Yes, but platform-safe line endings are release-critical | Records the cross-platform line-ending decision | **KEEP** | It prevents Windows checkouts from breaking Linux deployment scripts and migration checksums. |
| `.github/` | Issue/PR/release templates and CI/release workflows | GitHub contribution, validation, and publishing workflows | Reconstructable, but not generated | Captures repository process | **KEEP** | Every contained file supports CI, releases, or community workflow. |
| `.gitignore` | Excludes local caches, build output, secrets, and runtime state | Git in every clone/worktree | Yes | Low | **KEEP** | It is required for clean, safe development workspaces. |
| `.pre-commit-config.yaml` | Runs Ruff, formatting, YAML/TOML, EOF, and whitespace hooks | Contributor development workflow | Yes from tool choices | Records local quality gates | **KEEP** | It aligns local checks with documented contribution expectations. |
| `CHANGELOG.md` | User-facing version history and upgrade notes | Release preparation and users | Partly from Git, but curation is manual | High | **KEEP** | Git history does not replace a curated changelog. |
| `CONTRIBUTING.md` | Contributor setup, validation, privacy, and maintenance guidance | Contributors and PR authors | Reconstructable | Medium | **KEEP** | Required public-development guidance. |
| `LICENSE` | Apache License 2.0 terms | Users, redistributors, GitHub license detection | Canonical text is obtainable, but must travel with the project | Legal record | **KEEP** | Required for the project's open-source status. |
| `README.md` | Primary project overview, navigation, installation entry point, and branding | Every first-time visitor and GitHub | Manually maintained | Medium | **KEEP** | It is the repository's essential public entry point. |
| `RELEASE_NOTES.md` | Current RC1 highlights, migration notes, and limitations | Linked from README and release checklist | Partly derivable, but curated | High for the supported release | **KEEP** | Keep at root while RC1 is current; rotate intentionally when RC1.1 is prepared. |
| `app/` | Production application, services, dashboard, storage, detection, and verification | Runtime, tests, deployment | No | Core product history | **KEEP** | It builds and runs the software. |
| `audio-audit-report-post-cleanup-20260804.json` | Machine-readable RC1 audio reconciliation evidence | Referenced by `docs/audio-reconciliation-rc1.md`; not runtime input | Yes, by rerunning the audio audit against the original state, which may no longer be reproducible exactly | High release/audit value | **MOVE** | Keep it with its narrative under `docs/releases/rc1/evidence/`; root placement obscures its historical role. |
| `config/` | Default station, verification, calibration, and regional configuration | Runtime defaults, tools, tests, and operator examples | Manually maintained; some profiles can be regenerated | Configuration decisions matter across releases | **KEEP** | The directory is active, though one nested backup file should be removed separately. |
| `data/` | Database schema/migrations plus a committed BirdNET CSV | Migrations/schema are runtime-critical; CSV is only a generated detector output | SQL is not disposable; CSV is regenerable by BirdNET inference | Migration history is critical; CSV history is negligible | **KEEP** | Keep the directory for schema history, but remove the generated CSV as identified below. |
| `deploy/` | Production bootstrap, deploy, rollback, validation, sudoers, environment, and systemd units | Installation and Raspberry Pi production operations | Manually maintained and environment-sensitive | High operational value | **KEEP** | It installs and runs production safely. |
| `docs/` | Architecture, operations, development, release, research, and maintenance documentation | Users, operators, contributors, and release owners | Manually maintained | High | **KEEP** | The directory is essential; historical RC1 evidence needs internal curation rather than deletion. |
| `pyproject.toml` | Pytest, Ruff, mypy, and Black configuration | Tests, linting, typing, formatting, CI | Yes, but authoritative configuration is required | Low | **KEEP** | Central development-tool configuration. |
| `requirements.txt` | Fully pinned shared Python dependency closure | Development, runtime, repair, and production requirements | Can be regenerated only through a controlled dependency resolution | Important reproducibility record | **KEEP** | Required for repeatable installs and BirdNET runtime compatibility. |
| `requirements-dev.txt` | Extends runtime requirements with test and quality tools | Contributor setup and CI | Yes | Low | **KEEP** | Cleanly separates development-only tooling. |
| `requirements-production.txt` | Extends runtime requirements with Gunicorn | Production deployer | Yes | Low | **KEEP** | Explicitly required by `pfm-deploy`. |
| `samples/` | Small synthetic detection input | Simulator/examples and development | Yes from documented species ranges | Low | **KEEP** | A compact, privacy-safe fixture is appropriate in version control. |
| `scripts/` | Supported lifecycle, CLI, verification, recording, scheduler, database display, and changelog entry points | Operators, contributors, release workflows, or manual diagnostics | Manually maintained wrappers | Medium | **KEEP** | The directory has an ongoing tooling role, with one orphaned helper requiring removal. |
| `tests/` | Automated behavior and regression coverage | Pytest and CI | No practical equivalent outside source control | High regression value | **KEEP** | Required to validate the software; one empty test placeholder should be removed. |

## Nested candidate review

These items deserve individual disposition even though their parent directory is kept.

| Item | Current purpose | Active usage | Regenerability | Historical value | Recommendation | Justification |
| --- | --- | --- | --- | --- | --- | --- |
| `config/station.toml.before-storage-fix` | Timestamp-free backup of an earlier station configuration | No references; ignored naming pattern indicates temporary origin | Exact content remains recoverable from Git history | Low; superseded configuration history already exists in Git | **REMOVE** | It is an accidental working backup, contains a duplicate `[storage]` section, and does not belong in the active configuration tree. |
| `data/detections/latest-birdnet-results.csv` | Output from one local BirdNET run | Application writes to this default path but does not require a pre-existing file | Yes, on every BirdNET run | None; embeds a developer-specific absolute recording path | **REMOVE** | Runtime output and local paths do not belong in version control; add a narrow ignore rule when removing it. |
| `tests/test_recorder.py` | Intended recorder-test module | Empty; pytest gains no coverage from it | Yes, when real recorder tests are written | None | **REMOVE** | An empty test file communicates coverage that does not exist. Track future tests when implemented. |
| `scripts/lib/common.sh` | Shared colored-output shell helpers formerly used by milestone scripts | No remaining references after milestone-script removal | Easy to recreate | None | **REMOVE** | It is orphaned and contains no active lifecycle logic. |
| `scripts/record_audio.sh` | Manual wrapper for `app.audio.recorder` | No documentation, deployment, or CI references; sets obsolete `PYTHONPATH=$PROJECT_ROOT/source` | Easy wrapper around `python -m app.audio.recorder` | Low | **HQ REVIEW REQUIRED** | Confirm whether operators still use it; otherwise prefer the supported CLI and remove it. |
| `scripts/run_scheduler.sh` | Manual wrapper for the legacy scheduler module | No documentation, deployment, or CI references; production uses `adaptive_scheduler` | Easy wrapper | Low | **HQ REVIEW REQUIRED** | It may represent a legacy execution path, but removal should follow operator confirmation. |
| `scripts/show_recordings.sh` | Direct SQLite diagnostic query | No documentation or automation references | Easily replaced by a documented CLI query | Low | **HQ REVIEW REQUIRED** | Decide whether this is an intentionally supported field diagnostic or an undocumented convenience script. |
| `app/**/__init__.py` and `tests/__init__.py` | Python package markers | Import/package semantics and test organization | Yes, but removal can change import behavior across tools | Low | **KEEP** | Empty package markers are intentional, unlike empty feature/test placeholders. |
| `docs/images/logo.png` and `dashboard-home.png` | Public branding and dashboard screenshot | Directly embedded in README | Regenerable only from source artwork/application state | High public-release value | **KEEP** | Both are actively displayed and improve first-visitor comprehension. |
| `docs/FINAL_REPOSITORY_HYGIENE_REPORT.md` | Records the approved cleanup and retained exceptions | Referenced by ongoing repository governance | Manually reconstructable only with loss of detail | Medium | **KEEP** | Retain through RC1.1; archive with maintenance evidence later. |
| `docs/RC1_FINAL_RELEASE_REPORT_2026-08-04.md`, `RC1_RUNTIME_CANDIDATE_VALIDATION.md`, `RC1_STORAGE_RETENTION_REPORT.md`, `RC1_HANDOFF.md`, `RUNTIME_COMPATIBILITY_RC1.md`, `RELEASE_CHECKLIST.md`, `audio-reconciliation-rc1.md`, and root audio-audit JSON | Final RC1 acceptance, operational handoff, validation, retention, compatibility, checklist, and reconciliation evidence | Release/maintenance reference, not routine navigation | Some checks rerunnable, but exact production evidence is not reproducible | High | **MOVE** | Group under `docs/releases/rc1/` with an index so the active docs surface remains clear. |
| `docs/RC1_CUTOVER_ATTEMPT_2026-07-30*.md`, `RC1_DEPENDENCY_BLOCKER.md`, `RC1_DEPLOYMENT_WORKING_DIRECTORY.md`, and `RC1_READINESS_REPORT_2026-08-04.md` | Failed-attempt and blocker narratives | No active runtime/deployment use; final report summarizes the outcome | Events cannot be recreated exactly; Git preserves their text | Medium, primarily forensic | **ARCHIVE** | Move to a clearly labeled historical release archive or attach to the RC1 release; keep out of routine operator documentation. |
| `docs/DEPLOYMENT.md` and `docs/PRODUCTION_DEPLOYMENT.md` | Short deployment overview and detailed immutable-release process | Both remain relevant but overlap | Manually maintained | Medium | **KEEP** | Preserve both for now; improve cross-linking and scope labels rather than merging during curation. |
| `docs/ai-verification-v2.md`, `continuous-learning.md`, `second-verifier-research.md`, and `verification-evaluation.md` | Verification architecture and research reference | Supports future maintenance and model decisions | Research can be repeated only at cost and may change | High decision value | **KEEP** | These are durable engineering references, not abandoned experiments. |

## Summary

### KEEP

- 20 of 23 top-level items: all active code, deployment, configuration, tests,
  development tooling, public documentation, licensing, release notes, and samples.
- Active nested package markers, README images, current hygiene evidence, deployment
  guides, and verification research.

### MOVE

- Root `audio-audit-report-post-cleanup-20260804.json` and its final RC1 evidence set to
  `docs/releases/rc1/`, with an index and corrected links.

### ARCHIVE

- Failed RC1 cutover attempts and superseded blocker/readiness incident narratives.
  Preserve them under an explicitly historical release archive or release attachment.

### REMOVE

- `config/station.toml.before-storage-fix`.
- `data/detections/latest-birdnet-results.csv`, paired with a narrow ignore rule.
- Empty `tests/test_recorder.py`.
- Orphaned `scripts/lib/common.sh`.

### HQ REVIEW REQUIRED

- Empty `.env.example`: populate or remove.
- `scripts/record_audio.sh`: supported operator entry point or legacy wrapper.
- `scripts/run_scheduler.sh`: legacy scheduler wrapper or supported fallback.
- `scripts/show_recordings.sh`: supported diagnostic or undocumented convenience.

## Curation conclusion

Every remaining top-level item now has a documented purpose and disposition. The
repository's core structure is appropriate for RC1.1. HQ can make the remaining
decisions as a small, bounded follow-up without touching application behavior or Git
history.
