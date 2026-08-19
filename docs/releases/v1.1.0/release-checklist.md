# v1.1.0 HQ release checklist

Release candidate: `fb9b131`  
Target tag: `v1.1.0`  
Status: **HOLD pending production soak and the unchecked release-day controls below**

## Candidate evidence

- [x] Candidate commit is pushed to `origin/integration/rc1.1`.
- [x] GitHub Actions run `32224121200` passed for `fb9b131`.
- [x] Transactional production deployment completed successfully.
- [x] Verified predeployment backup exists.
- [x] Current and previous rollback releases are retained.
- [x] SQLite integrity returned `ok`; migrations 1 through 5 are unchanged.
- [x] Recorder, BirdNET, dashboard, cleanup, and reliability sampling passed immediate
  production validation.
- [x] Health and metrics returned HTTP 200.
- [x] Overview, Activity, Life List, Species, and Device pages returned HTTP 200.
- [x] Audio playback returned HTTP 200 and byte-range seeking returned HTTP 206.
- [x] Storage cleanup reclaimed space while preserving database history.
- [x] Release pruning retained current, previous, and one inactive release.
- [x] Optional webhook-disabled configuration loads safely and logs no credential.

## Acceptance gates

- [ ] Minimum 24-hour production soak completed after deployment at
  2026-08-18 23:51:35 PDT.
- [ ] Final soak report confirms stable cadence, near-zero queue, healthy freshness,
  accurate forecast, successful timers, and no unexpected restarts.
- [ ] Controlled reboot validation passes after the final candidate deployment.
- [ ] No open P0 or P1 defects.
- [ ] HQ accepts all listed v1.1.0 limitations.
- [ ] RC1.1 Release Acceptance Report recommends release.

## Documentation and presentation

- [x] Release notes cover features, upgrade procedure, compatibility, and limitations.
- [x] Changelog accounts for the merged RC1.1 initiatives and hardening fixes.
- [x] README and documentation index point to the v1.1.0 package.
- [x] Installation, configuration, troubleshooting, verification, dashboard, Device,
  operations, deployment, and rollback guides were reviewed.
- [x] Public-safe Overview, Activity, Species, Life List, and mobile captures are staged.
- [ ] Final Device-page screenshot is captured and approved. Automated capture is
  blocked by the available Chromium headless renderer; use a normal browser capture.
- [ ] Screenshot package receives HQ visual approval.

## Release-day controls

- [ ] Update `app/version.py` from `1.0.0-rc1` to `1.1.0` in the administrative release
  commit. This was deliberately not changed during the no-production-code soak task.
- [ ] Replace `Unreleased` in `CHANGELOG.md` with the publication date.
- [ ] Confirm the release commit contains documentation/version metadata only beyond
  the already validated candidate.
- [ ] CI passes on the final primary-branch release commit.
- [ ] Merge `integration/rc1.1` to `master` using the approved merge strategy.
- [ ] Confirm `master` contains `fb9b131` and the final release-administration commit.
- [ ] Create signed or annotated tag `v1.1.0` at the approved `master` commit.
- [ ] Push `master` and `v1.1.0`; verify the remote tag target.
- [ ] Publish GitHub Release using `RELEASE_NOTES.md` and the approved screenshots.
- [ ] Verify installation, documentation, and screenshot links on GitHub.
- [ ] Confirm the release is publicly visible and CI remains green.

## Post-publication transition

- [ ] Close the v1.1.0 milestone and archive completed integration work.
- [ ] Delete the merged integration branch only after its tip is verified in `master`.
- [ ] Create `develop` from released `master` only after publication.
- [ ] Open RC1.2 tracking from the approved transition plan; do not inherit release-only
  blockers as feature scope.
