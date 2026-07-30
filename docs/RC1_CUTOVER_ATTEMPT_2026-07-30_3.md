# RC1 Cutover Attempt 3 — 2026-07-30

## Result

**BLOCKED. Automatic rollback restored the legacy installation.**

The runtime compatibility and storage-retention branches were integrated into
`integration/v3`. Candidate preflights passed, including production
configuration compatibility and the pinned BirdNET runtime imports. The
transactional deployer built and activated release
`rc1-attempt3-fdee214`, but its health gate returned HTTP 503 after the
candidate installation increased root filesystem usage beyond the configured
warning threshold.

No production code was changed and no second deployment was attempted after
the rollback.

## Baseline

Before activation:

- root filesystem: 57 GiB total, 45 GiB used, 10 GiB free (82%);
- health endpoint: HTTP 200 with no warnings;
- failed systemd units: none;
- legacy recorder, BirdNET worker, and dashboard: active;
- SQLite integrity: `ok`;
- recordings: 2,577;
- detections: 1,034;
- legacy rollback artifacts: present.

## Candidate validation

The staged candidate passed:

- `import app`;
- `from app.config import BirdNETConfig`;
- CLI startup and help rendering;
- BirdNET package resolution from the candidate virtual environment;
- `birdnet.acoustic.inference.prediction_strategy` import;
- legacy `birdnet.poll_interval` translation;
- the consolidated startup preflight;
- migration validation (`Database is current`);
- 36 automated tests;
- Ruff, compilation, shell syntax, and Git whitespace checks.

The deployer installed the pinned BirdNET wheel and verified SHA-256:

```text
e26ee0419446d3cf634a8f5fb65182626590063f2c0a1ed7cb72659a9ce1ce69
```

## Activation failure

The failing health-gate command was:

```text
curl --fail --silent --show-error http://127.0.0.1:8000/health
```

It returned HTTP 503 on all ten attempts. The first relevant diagnostic was the
health response, not an application stack trace:

```text
status: degraded
disk.percent: 87.1
disk.free_bytes: 7471931392
warning: disk usage above threshold
```

Candidate Gunicorn, recorder, and BirdNET processes started successfully.
Their journals showed no configuration exception, BirdNET import exception, or
restart loop. They stopped cleanly when the deployer initiated rollback.

## Rollback and final production state

Automatic rollback completed successfully:

- the legacy service installation was restored;
- the legacy recorder, BirdNET worker, and dashboard were active;
- no systemd units were failed;
- the recorder resumed creating recordings;
- SQLite integrity remained `ok`;
- final recordings: 2,596;
- final detections: 1,034;
- root filesystem: 57 GiB total, 48 GiB used, 7.0 GiB free (88%).

The final legacy health endpoint remains HTTP 503 solely because disk usage is
above the configured warning threshold. The dashboard service is running and
responding.

Rollback and diagnostic artifacts remain available:

```text
/opt/project-field-mouse/legacy-rollback
/opt/project-field-mouse/releases/rc1-attempt3-fdee214
/home/amcowden97/pfm-rc1-attempt3-fdee214/deploy.log
```

`/opt/project-field-mouse/current` and `/opt/project-field-mouse/previous` are
absent, as expected after restoring the pre-candidate legacy installation.

## Decision and ownership

RC1 cutover attempt 3 is blocked by the transactional deployment storage
budget. Building and retaining the candidate virtual environment consumed
enough space to cross the production health threshold.

Storage/Infrastructure should reclaim only confirmed-safe failed-release and
deployment-cache artifacts, or otherwise establish adequate transactional
headroom, before scheduling another cutover. The failed candidate and rollback
artifacts must remain available until the evidence has been reviewed.

Do not merge `integration/v3` into `master` or create `v3.0.0-rc1` from this
attempt.
