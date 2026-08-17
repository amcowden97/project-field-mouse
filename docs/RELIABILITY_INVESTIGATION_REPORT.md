# Reliability Investigation Report

Date: 2026-08-16

Branch: `feature/reliability-investigation`

Baseline: `integration/rc1.1` at `fa8d9ce`

## Executive assessment

The gradual slowdown and occasional loss of reachability cannot yet be assigned a
root cause. No multi-day time series or failure-time capture existed before this
investigation, and the system journal is volatile. The most recent shutdown was
operator-initiated and is explicitly excluded from failure evidence.

The current evidence narrows the investigation to memory/swap pressure, network or
operating-system loss, and power instability. Thermal throttling, current CPU
saturation, SQLite corruption, and current service restart loops are not supported
by the baseline snapshot. These are observations, not exclusions over a multi-day
run.

## Baseline observations

The read-only snapshot was captured at 2026-08-16 22:10 PDT, approximately 12
minutes after an operator-initiated boot:

| Area | Observation |
| --- | --- |
| CPU/load | 0.16 / 0.23 / 0.18; 95-100% idle during the short `vmstat` sample |
| Memory | 1,038,811,136 bytes total; 534,233,088 bytes available |
| Swap | 264,749,056 bytes of 1,038,073,856-byte zram swap allocated |
| Storage | root filesystem 84% used; 9,742,131,200 bytes available |
| I/O | no active wait or sustained writes in the short sample |
| Temperature | 44-45 C |
| Firmware flags | `throttled=0x0` |
| Recorder | active; zero restarts; main process about 12 MiB RSS |
| BirdNET | active; zero restarts; process tree about 166 MiB RSS and 108 MiB swap |
| Gunicorn | active; zero restarts; master/worker about 45 MiB RSS and 14 MiB swap |
| SQLite | health endpoint reported `integrity: ok` |
| Application health | HTTP 200, no warnings, microphone and services healthy |

Swap occupancy soon after boot is worth trending, particularly BirdNET's share, but
one point cannot distinguish normal cold-start paging from a leak. The system had no
OOM kills in the current boot. The short I/O sample cannot prove long-term storage
health or latency.

A second point about seven minutes later showed available memory slightly higher
(about 537 MiB), zram swap slightly lower (about 250 MiB), BirdNET main-process RSS
slightly lower (about 155 MiB), zero restarts, zero OOM kills, 45.5 C, and no
throttle flags. This confirms no immediate runaway trend, but the interval is far
too short to address the reported multi-day behavior.

Storage differs from the assignment background: the measured root filesystem was
84% used with about 9.1 GiB free, not 74% with 15 GiB free. It remained below the
90% health threshold, but its growth must be tracked.

## Confirmed observability gaps

- No long-term CPU, memory, swap, I/O, network, temperature, service RSS, file
  descriptor, thread, or restart-count history was retained.
- `journalctl --list-boots` confirmed no persistent system journal. A hard power
  cycle removes the prior boot's kernel and service evidence.
- The normal operator account cannot inspect another service user's `/proc` file
  descriptors, so root-scoped collection is required for accurate service trees.
- Previous reports contained healthy snapshots and soak summaries, but not a time
  series spanning a degradation event.

## Instrumentation implementation

The new five-minute reliability timer records daily JSONL samples under
`/var/log/fieldmouse/reliability` with 30-day retention. It captures:

- CPU, load averages, memory, zram swap, root disk use, disk I/O counters, and
  network counters;
- recording, database/WAL, and application-log growth plus ext4 error counters;
- temperature, current/historical firmware throttle and undervoltage flags;
- systemd state, restart count, tasks, CPU time, and main PID;
- aggregate and per-process RSS, swap, descriptors, and threads for each service
  process tree;
- boot ID and uptime, so discontinuities are not mistaken for trends.
- backup and cleanup service results and timer trigger times.

Threshold crossings and sudden interval growth produce capped diagnostic snapshots
with the top 30 processes, kernel warnings, and recent recorder, BirdNET, and
dashboard journals. Collection has no recovery actions and does not change service
priority, limits, lifecycle, or application data.

The summarizer reports first, last, minimum/maximum values, boot IDs, inactive
samples, restart changes, network errors, and diagnostic count:

```bash
/opt/project-field-mouse/current/.venv/bin/python \
  -m app.system.reliability_monitor --summarize
```

## Root-cause assessment

1. **Memory or swap pressure — plausible, low confidence.** The 1 GiB station had
   about 252 MiB of zram swap allocated shortly after boot, including about 103 MiB
   for BirdNET. There is no multi-day growth curve, OOM event, or present low-memory
   condition, so a leak is not established.
2. **Network-only loss — plausible, unknown confidence.** “Unreachable” has not yet
   been separated into SSH/network loss versus a locally hung system. No historical
   interface errors, drops, or local-console observation exists.
3. **Power instability — plausible, unknown confidence.** The current firmware flag
   is zero, but there is no record spanning a failure. Historical bits and abrupt
   boot evidence were not persistent.
4. **Storage/I/O pressure — possible, low confidence.** Utilization is higher than
   the stated background, but the snapshot showed no I/O wait and the database was
   healthy. Only rate and latency trends can establish this cause.
5. **Thermal throttling — currently unsupported.** Temperature was 44-45 C and the
   firmware throttle flags were zero.
6. **Service restart loop or SQLite failure — currently unsupported.** All three
   services were active with zero restarts, and SQLite integrity was `ok`.

## Recommendations

### Immediate

1. Deploy the telemetry units through the normal transactional deployer and collect
   at least seven uninterrupted days, preferably until a degradation event.
2. At the next event, record the exact time and test local console and link LEDs
   before power cycling. Preserve the reliability directory immediately afterward.
3. Review and explicitly approve bounded persistent journald storage (for example,
   128 MiB and 30 days). It is not enabled by this change because it changes global
   operating-system logging behavior.
4. Monitor storage trend; investigate if use approaches 90%, independent of the
   reachability issue.

### Medium term, after evidence

- If BirdNET RSS/swap or descriptors grow monotonically, reproduce with a controlled
  soak and profile that process before changing limits or restart policy.
- If interface errors or drops rise while local console remains responsive, focus on
  NetworkManager, Wi-Fi power management, driver, and access-point evidence.
- If firmware power flags appear, validate the power supply, cable, and connector
  before software changes.
- If I/O busy time and load rise together, inspect SD-card health and write sources.

### Long term

- Export the same bounded schema to fleet-level monitoring when stations gain a
  supported synchronization path.
- Add controlled watchdog recovery only after captures prove a system or service
  deadlock and the evidence-preservation order is defined.

## Exit status

**ROOT CAUSE NOT YET CONFIRMED - PRODUCTION ACTIVATION REQUIRED.**

The issue is narrowed to a small evidence-supported set, but a multi-day run or an
actual failure capture is required before a corrective software or hardware change
is justified.

Production activation is pending. The Pi's staged source directory is not a Git
worktree, and the active release is `rc1.1-ic1-99ec4a6`. Activating this branch
therefore requires an explicit source restage, privileged bootstrap refresh for the
narrow reliability sudo entries, and a normal transactional deployment. No files
were copied to the Pi and no production cutover was performed during this
investigation.
