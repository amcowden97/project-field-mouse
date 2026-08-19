# v1.1.0 documentation audit

Date: 2026-08-19  
Scope: release documentation only; no production code or deployment state changed.

## Review results

| Area | Authoritative document | Result | Notes |
|---|---|---|---|
| Project entry point | `README.md` | Pass | Points to current install, operations, release notes, and v1.1.0 package. |
| Installation | `docs/INSTALLATION.md` | Pass | Covers Pi install, station configuration, restart, verification, backup, update, and repair. |
| Configuration | `docs/CONFIGURATION.md` | Pass | Documents precedence, production path, privacy, BirdNET location, and safe environment overrides. |
| Troubleshooting | `docs/TROUBLESHOOTING.md` | Pass | Covers microphone, BirdNET, dashboard, migrations, disk pressure, and sanitized diagnostics. |
| Verification | `docs/ai-verification-v2.md` | Pass | Explains evidence semantics, safe failures, consensus, persistence, and calibration limits. |
| Dashboard | `docs/dashboard-v2-rc1.1-design.md` | Pass | Describes wildlife hierarchy, verification presentation, responsiveness, and accessibility. |
| Device/operations | `docs/OPERATIONS.md` | Pass | Device behavior, APIs, timers, freshness, and reliability telemetry are operator-accessible. |
| Deployment | `docs/PRODUCTION_DEPLOYMENT.md` | Pass | Transactional deployment remains the supported production path. |
| Rollback | `docs/ROLLBACK.md` | Pass | Rollback remains explicit and separate from schema reversal. |
| Storage hardening | `docs/RC1.1.1_STORAGE_RELIABILITY.md` | Pass | Covers thresholds, forecast, cleanup, notification, and release retention. |
| Release process | `docs/RELEASING.md` | Pass with release-day action | Canonical version remains `app/version.py`; checklist requires its administrative bump. |

## Link and screenshot review

- Relative documentation links were checked against the repository tree after the
  release-package update.
- README now points to the v1.1.0 checklist instead of the historical RC1 checklist.
- The documentation index exposes the complete v1.1.0 HQ handoff.
- Historical RC1 and design reports remain intentionally available and are labeled as
  historical evidence rather than current deployment instructions.
- The screenshot manifest distinguishes curated public-safe captures from the final
  Device capture still awaiting a normal-browser screenshot.

## Findings

1. **Release-day required:** `app/version.py` still reports `1.0.0-rc1`. The assignment
   prohibits production-code changes, so the exact `1.1.0` metadata update is isolated
   in the release checklist instead of silently changing the soaked candidate.
2. **Presentation follow-up:** automated current-production screenshot capture is
   blocked by the available Chromium headless renderer. Five approved public-safe
   images are staged; Device must be captured in a normal browser before publication.
3. **Accepted limitation:** optional webhook configuration is documented but is not a
   core product or v1.1.0 release gate.

No stale documentation was found that requires an application, architecture, migration,
or deployment change during the soak.

