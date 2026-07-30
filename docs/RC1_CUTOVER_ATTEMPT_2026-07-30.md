# RC1 Cutover Attempt — 2026-07-30

## Result

**BLOCKED. No production cutover occurred.**

The production bootstrap completed successfully. The staged and installed
deployers both had SHA-256:

```text
f1c66a123bccaa57be2002d5c3ffbbae1ffbfa288a1ad5947ba1d3eb1b76cff2
```

`sudo -n true` succeeded after a fresh login, while an unrelated
`sudo -n /usr/bin/id` remained denied.

The first deployment invocation exited 2 before mutation because the requested
`/home/amcowden97/pfm-production-bootstrap` source contained deployment
tooling but no `app/` tree. The staging path was completed from the previously
validated integrated RC1 source at
`/home/amcowden97/rc1-deploy-source-e04a11b`, while preserving the hardened
deployer. Release markers, shell syntax, and the staged/installed deployer
hashes were revalidated before one retry.

## Blocking failure

The retry ran from 2026-07-30 19:51:50Z through 20:00:33Z, for a duration of
8 minutes 43 seconds. It:

- copied the legacy recordings into managed state;
- created the candidate release;
- installed the complete pinned Python environment from the warmed cache,
  including TensorFlow, BirdNET, Flask, and Gunicorn;
- failed before migration, unit installation, or current-symlink switching.

The first failing command was the migration preflight:

```text
/opt/project-field-mouse/releases/20260730T195150Z-source/.venv/bin/python:
Error while finding module specification for 'app.cli'
(ModuleNotFoundError: No module named 'app')
```

The deployer invokes `python -m app.cli migrate` without using the candidate
release as its working directory or setting its import path. This is a
deployment-tooling defect, not an application migration, dependency, or data
failure.

Automatic rollback reported:

```text
No prior release was switched; current installation is unchanged.
```

The failed candidate release and deployment logs remain available at:

```text
/opt/project-field-mouse/releases/20260730T195150Z-source
/home/amcowden97/pfm-rc1-cutover-20260730-2/deploy.log
/var/log/fieldmouse/deployments/20260730T195150Z-source-pip.log
```

## Recovery evidence

- `/opt/project-field-mouse/current` does not exist.
- Recorder remains active from the legacy path.
- Dashboard remains active from the legacy path.
- BirdNET returned active after systemd automatic restarts; `NRestarts=7`.
- Legacy cleanup and storage timers remain enabled and active.
- Legacy SQLite integrity is `ok`.
- Post-attempt counts were 2,476 recordings and 1,034 detections.
- No legacy unit was disabled or deleted.
- Measured production switch downtime was zero because switching never began.

Current legacy process RSS after recovery:

| Process | RSS |
| --- | ---: |
| Recorder scheduler | 11,376 KiB |
| BirdNET worker | 358,320 KiB |
| Dashboard development server | 26,192 KiB |

Disk use increased from 74% before the attempt to approximately 90% after the
managed recordings copy and retained candidate environment. About 5.7 GiB
remains free. The legacy health endpoint returns HTTP 503 with database
integrity `ok` and a degraded status caused by the disk-usage warning.

## Required next action

Correct and test the deployer's candidate-release working-directory handling
in a separate narrowly scoped change. Do not retry cutover, retire legacy
services, or remove retained rollback evidence until that defect is reviewed
and the disk-space impact is addressed deliberately.
