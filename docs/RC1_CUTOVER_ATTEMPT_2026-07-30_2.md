# RC1 Cutover Attempt 2 — 2026-07-30

## Result

**BLOCKED. Automatic rollback restored the legacy installation.**

Before deployment:

- branch, staged, and installed deployer content matched SHA-256
  `451f5cf0b6f13fd412ccf17fea40e9b924260241de5e681a65592150a308ec74`;
- `sudo -n true` succeeded and unrelated passwordless sudo remained denied;
- source `import app` succeeded;
- SQLite integrity was `ok`;
- recorder, BirdNET, and dashboard were active;
- 9.9 GiB disk space was free.

The attempt ran from 2026-07-30 20:14:02Z through 20:17:48Z, or 3 minutes
46 seconds.

## Infrastructure validation

The corrected deployment path passed:

- early source import preflight;
- complete pinned dependency installation;
- candidate-venv import preflight;
- release-relative CLI invocation;
- migration check (`Database is current`).

This proves the working-directory correction in `d5dc08b`.

## Runtime blockers

The transactional switch exposed two independent runtime blockers.

### Production configuration incompatibility

Gunicorn started, bound port 8000, and attempted to boot its worker. Application
configuration loading then failed:

```text
app.config.ConfigurationError: Invalid configuration:
BirdNETConfig.__init__() got an unexpected keyword argument 'poll_interval'
```

The preserved production station configuration contains
`birdnet.poll_interval`, while the staged application configuration class does
not accept that field. Gunicorn exited 3 because its worker could not boot.

### BirdNET package runtime failure

The candidate BirdNET service also failed:

```text
ModuleNotFoundError:
No module named 'birdnet.acoustic.inference.prediction_strategy'
```

The import originated from the pinned `birdnet==0.2.16` environment. Successful
package installation and `pip check` do not cover this missing runtime module.

These blockers require application/configuration and dependency-compatibility
ownership. Infrastructure must not patch around them or modify production
configuration ad hoc.

## Rollback evidence

The deployer exited 3 and automatic rollback:

- removed `/opt/project-field-mouse/current`;
- restored the legacy systemd units;
- restored and restarted the legacy recorder, BirdNET, and dashboard;
- re-enabled the legacy cleanup and storage timers;
- retained the candidate and all deployment logs.

Post-rollback:

- all three legacy services were active;
- no systemd units remained failed;
- SQLite integrity remained `ok`;
- counts were 2,491 recordings and 1,034 detections;
- no legacy service was retired or deleted.

The candidate activation window was approximately 12 seconds, from initial
candidate service startup at 13:17:36 PDT through legacy restoration at
13:17:48 PDT. Disk free space was 7.8 GiB after retaining the new candidate.

Evidence is retained at:

```text
/opt/project-field-mouse/releases/20260730T201402Z-source
/home/amcowden97/pfm-rc1-cutover-20260730-3/deploy.log
/var/log/fieldmouse/deployments/20260730T201402Z-source-pip.log
```

## Decision

Do not retry cutover or retire legacy services until both runtime blockers are
resolved and validated in a controlled candidate environment.
