# Open Source Readiness Report

Audit date: 16 August 2026

## Overall assessment

**READY WITH MINOR IMPROVEMENTS**

Project Field Mouse has a coherent application layout, an Apache-2.0 license recognized
by GitHub, reproducible automated checks, useful operator documentation, and an active
RC1 release. This audit removed first-time contributor ambiguity and supplied the
missing community-health documents. Remaining work is limited primarily to GitHub
owner settings and public presentation; it does not block contribution or RC1.1
development.

## Repository strengths

- Runtime, configuration, deployment, documentation, samples, scripts, and tests have
  clear top-level ownership.
- Generated recordings, databases, logs, caches, local configuration, and development
  output are narrowly excluded from version control.
- RC1 evidence and superseded reports are separated from current guidance and indexed.
- Installation, deployment, operations, rollback, migration, backup, release, and
  architecture guidance already cover the core operator lifecycle.
- CI runs Ruff, the full test suite, and compile checks; release automation verifies the
  version tag and generates release notes.
- The public repository has a concise description, configured homepage, Discussions,
  Issues, pull requests, and a published RC1 prerelease. GitHub recognizes the license
  as Apache-2.0.

## Areas improved

### First-time contributor experience

- Corrected the developer and simulator guides, which referenced a nonexistent
  `config/development.toml`.
- Corrected the Flask quick start to bind port 8000, matching the documented URL.
- Added Windows PowerShell guidance and clarified that hardware and BirdNET are not
  required for the standard contributor workflow.
- Expanded `CONTRIBUTING.md` with setup, privacy, scope, testing, Raspberry Pi, pull
  request, and conduct expectations.
- Corrected the README project tree, which previously listed a nonexistent top-level
  `services/` directory.

### Documentation

- Added `docs/README.md` as the canonical documentation index.
- Added focused configuration, troubleshooting, and FAQ guides.
- Linked high-value user and contributor documents directly from the README.
- Distinguished historical release records from current operating instructions.

### GitHub community experience

- Added a security policy and concise community Code of Conduct.
- Added an improvement-proposal issue form and issue chooser links for Discussions and
  private security reports.
- Completed required IDs and default metadata in the existing bug form.
- Added validation and privacy checklists to the pull request template.

## Maintainability findings

- No actionable `TODO`, `FIXME`, `XXX`, or `HACK` markers were found in tracked project
  files.
- Each tracked operator and maintenance script has a current code, CI, deployment, or
  documentation reference. `scripts/show_recordings.sh` remains an intentional
  read-only field diagnostic.
- Runtime, development, and production requirements are separated. Their inclusion
  model is understandable and no consolidation is needed for this audit.
- Sample detections are appropriately separated from ignored station data.
- Empty local directories remain under `dashboard-v1-archive/`, old ignored validation
  paths, `scripts/dashboard/`, and `scripts/lib/`. Git does not track empty directories,
  so these are workspace remnants rather than repository content. They may be removed
  locally after confirming no external process relies on them.
- Existing uncommitted migration, performance-report, profiler, and test work was
  treated as active RC1.1 work and deliberately left unchanged.

## GitHub review

Live repository metadata observed during the audit:

- Description: present and clear.
- Homepage: configured as `https://project-field-mouse.com`.
- Topics: none configured.
- Labels: GitHub's nine default labels only.
- Discussions: enabled.
- License: recognized as Apache-2.0.
- Releases: RC1 is published as a prerelease.
- Automatic deletion of merged branches: disabled.
- Community profile before these local additions: 71%, with Code of Conduct and
  security/community surfaces incomplete.

Issue and pull request templates are now appropriate for initial public adoption. The
release template covers highlights, installation, configuration/database impact,
Raspberry Pi validation, known issues, and checksums. Funding configuration is not
recommended until the project has an approved funding or sponsorship channel.

## Validation

| Check | Result |
| --- | --- |
| Contributor configuration smoke test | PASS |
| Pytest | PASS: 75 tests |
| Ruff (`app`, `tests`, `scripts`) | PASS |
| Compileall (`app`, `tests`, `scripts`) | PASS |
| GitHub YAML parsing | PASS: 5 files |
| Repository-relative documentation links | PASS |
| Runtime or deployment changes from this audit | NONE |

## Remaining recommendations

1. Add focused repository topics such as `raspberry-pi`, `wildlife-monitoring`,
   `birdnet`, `bioacoustics`, `conservation`, `python`, `flask`, and `sqlite`.
2. Add project-specific labels for `raspberry-pi`, `hardware`, `birdnet`, `dashboard`,
   `operations`, `privacy`, and `research`, applying them only as triage demand emerges.
3. Enable automatic deletion of merged branches to match the Repository Maintenance
   Policy. Consider enabling branch update prompts and auto-merge only after branch
   protection and required checks are settled.
4. Confirm private vulnerability reporting is enabled so the security-policy and issue
   chooser routes are available to outside reporters.
5. Review Discussion categories for at least Announcements, Help, Ideas, and Show and
   Tell, with a short pinned welcome and privacy reminder.
6. Verify that the configured homepage has valid DNS, TLS, maintained content, and a
   clear link back to the repository before promoting it broadly.
7. Add an approved logo/social preview and a current dashboard screenshot. Existing
   versioned screenshots are Dashboard V2 artifacts and should not be presented as the
   current interface without review.

These recommendations are repository-owner or branding decisions. The checked-in
project is otherwise easy to discover, understand, set up, test, and contribute to.
