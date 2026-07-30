# RC1 Storage Retention Report

## Decision

**READY FOR RC1 CUTOVER ATTEMPT 3**

This recommendation covers the storage gate. No application code, deployment
scripts, rollback logic, systemd units, databases, production recordings, or
backups were modified.

## Baseline

The sprint began with:

```text
Filesystem size: 57 GiB
Free:            7.4 GiB
Used:            87%
Current release: none
```

All entries under `/opt/project-field-mouse/releases` were unreferenced failed
deployment candidates.

| Path | Size before | Owner | Retention decision |
| --- | ---: | --- | --- |
| `releases/20260730T201402Z-source` | 2.0 GiB | root:root | Delete; failed cutover candidate |
| `releases/rc1-e04a11b-3` | 14 MiB | root:root | Delete; failed candidate |
| `releases/rc1-e04a11b-2` | 13 MiB | mixed/root content | Delete; failed candidate |
| `releases/rc1-e04a11b` | 4 KiB | mixed/root content | Delete; failed candidate |
| `/var/cache/fieldmouse/pip` | 430 MiB | fieldmouse-managed | Delete; rebuildable deployment cache |
| Isolated runtime rehearsal candidate | 2.0 GiB | amcowden97 | Delete after extracting compact evidence |

## Deleted paths

The following exact paths were removed individually:

```text
/home/amcowden97/pfm-rc1-runtime-candidate
/opt/project-field-mouse/releases/20260730T201402Z-source
/opt/project-field-mouse/releases/rc1-e04a11b-3
/opt/project-field-mouse/releases/rc1-e04a11b-2
/opt/project-field-mouse/releases/rc1-e04a11b
/var/cache/fieldmouse/pip
/home/amcowden97/.cache/chromium
/home/amcowden97/.cache/mesa_shader_cache
/home/amcowden97/.cache/mesa_shader_cache_db
```

Rebuildable Debian package archives and index files were also cleared with
`apt-get clean` and removal of `/var/lib/apt/lists` contents. A future
`apt-get update` recreates the package index.

The old dependency recovery `pip.log` was retained losslessly as
`pip.log.gz`, reducing it from about 20 MiB to 2.6 MiB.

## Preserved assets

The cleanup commands did not target any protected path. The following were
retained:

```text
/var/lib/fieldmouse/database
/var/lib/fieldmouse/recordings
/var/lib/fieldmouse/backups
/opt/project-field-mouse/legacy-rollback
/home/amcowden97/Project-Field-Mouse/data/recordings
/home/amcowden97/pfm-rc1-runtime-evidence
```

Legacy production recordings remain 14 GiB. Runtime validation evidence
remains 236 KiB. Compact cutover, dependency, and wheel evidence remains
available.

## Final validation

```text
Filesystem size: 57 GiB
Free (df -h):    10 GiB
Free bytes:      10,715,885,568
Free binary:     approximately 9.99 GiB
Used:            82%
Remaining failed releases: none
Deployment pip cache: removed; deployer recreates it automatically
Current release: none
```

The small difference between the rounded `df -h` result and exactly 10 GiB is
less than normal live-recording filesystem variation. Operationally, the
station moved from the health-warning range to 82% used.

Post-cleanup validation:

- recorder active;
- BirdNET active;
- dashboard active;
- SQLite `PRAGMA integrity_check` returned `ok`;
- 2,573 recordings and 1,034 detections were present at validation time;
- `/health` returned HTTP 200 with status `ok` and no warnings;
- production recordings and runtime evidence remained present;
- no `/opt/project-field-mouse/current` link existed.

## Long-term retention

Failed release candidates and package caches are disposable only when no
`current` or `previous` symlink references them and their compact diagnostic
logs have been retained. Production recordings, databases, backups, station
identity, rollback artifacts, and validation evidence remain protected.
