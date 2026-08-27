# Performance & Scalability Report

**Audit date:** 2026-08-16  
**Scope:** Project Field Mouse RC1.1  
**Target:** Raspberry Pi 5 station; synthetic dashboard profiling ran under WSL2
on x86-64 and is intended for relative scaling and before/after comparisons.

## Executive summary

The current single-station architecture is healthy for RC1.1 and 10,000
detections. At 100,000 detections, unindexed global time ordering and normalized
timestamp filtering caused visible dashboard degradation. Two narrowly scoped
SQLite indexes remove most of that cost: at 100,000 detections, median Activity
latency fell 60%, homepage latency 39%, Metrics API latency 77%, and dashboard API
latency 20%. The migration preserves behavior and passed the focused regression
suite.

The next scaling limit is not SQLite capacity. It is repeated all-history
aggregation in the homepage and Life List, followed by audio storage and detector
CPU. The Life List remains about 218 ms on the audit host at 100,000 detections.
Additional detectors can reuse recordings and SQLite, but running multiple ML
models serially must fit inside the recording cadence. A centralized multi-station
dashboard is not yet supported: identity is present in the schema, while most
queries intentionally remain station-global because each database currently
represents one station.

No evidence of per-request memory growth was found. Existing production evidence
does show that ML inference dominates memory and CPU, and that audio dominates disk
growth. A 24-hour Pi soak remains necessary to establish time-series trends for
file descriptors, temperature, queue depth, WAL size, and RSS.

## Methodology and limitations

The repeatable profiler is `scripts/profile_performance.py`. It creates temporary,
schema-accurate databases at 1,000, 10,000, and 100,000 detections, with ten
detections per recording and eight species. It warms each route, then records seven
requests using Flask's test client. Measurements include median and p95 wall time,
SQL statement count, response size, Python allocation peak, process RSS, database
size, population time, and `EXPLAIN QUERY PLAN` output.

Synthetic runs used Python 3.12.3, SQLite 3.45.1, Flask 3.1.3, and WSL2 x86-64.
Absolute web latencies must not be treated as Raspberry Pi service-level results:
the test client omits TCP, Gunicorn scheduling, browser parsing, and concurrent
BirdNET contention. The before/after runs used identical code, data generation,
host, and repetition counts. Full evidence is retained in:

- `reports/performance-audit-baseline.json`
- `reports/performance-audit-optimized.json`

BirdNET inference was not rerun on the audit workstation because the pinned ML
runtime and model were not installed. The report uses the repository's existing Pi
measurements instead. Recorder timing is inherently the configured audio duration;
database persistence and scheduling are negligible relative to a 60-second capture.
Network throughput and browser paint were not measured; static/audio endpoint
server timings and response behavior were inspected instead.

## Profiling results

### End-to-end processing pipeline

| Stage | Observed characteristic | Assessment |
|---|---:|---|
| Recorder | 60-second, 48 kHz, mono S16 WAV is 5,760,044 bytes | Capture duration and disk bandwidth dominate; DB insert is one transaction |
| BirdNET | Existing Pi evidence: about 3.71–4.59 seconds mean per recording | Largest compute stage, but comfortably below current cadence |
| Verification V2 | Existing Pi benchmark: 2.213 ms mean, 2.231 ms p95, 40.96 MB peak RSS | Small relative to BirdNET; near one full core only while executing |
| Detection persistence | One transaction per recording; verifier writes occur inside it | Good durability/throughput balance; work grows per accepted detection |
| Dashboard | 16.7 ms homepage at 1k; 225.7 ms at 100k after optimization | Acceptable but all-history aggregation still scales linearly |
| APIs | At 100k: dashboard 58.3 ms; metrics 4.34 ms after optimization | Metrics is ready; dashboard API repeats homepage summary scans |
| Audio | 1.6 ms median for local 4 KiB audit payload; conditional `send_file` enabled | Database lookup is indexed; actual transfer depends on WAV size/network |
| Static asset | Roughly 2–4 ms median in-process | Application serving is fine for one LAN station; proxy offload is optional |

The production evidence comes from `docs/RC1.1_INTEGRATION_REPORT.md`,
`docs/verification-calibration-report.md`,
`docs/releases/rc1/final-release-report.md`, and
`reports/pi5-verification-20260805.json`.

### Dashboard and API scaling

Optimized median latency in milliseconds:

| Route | 1k detections | 10k detections | 100k detections | SQL statements at 100k |
|---|---:|---:|---:|---:|
| Homepage `/` | 16.70 | 39.76 | 225.70 | 14 |
| Activity `/activity` | 11.21 | 15.06 | 37.20 | 5 |
| Activity page 100 | 12.48 | 17.22 | 41.55 | 5 |
| Life List | 30.61 | 49.50 | 218.05 | 7 |
| Species: American Robin | 35.73 | 64.25 | 80.87 | 3 |
| Device | 32.00 | 34.14 | 53.97 | 4 |
| Dashboard API | 2.64 | 7.30 | 58.25 | 4 |
| Metrics API | 1.06 | 1.39 | 4.34 | 2 |

Query counts are bounded and modest. Homepage cost comes from 14 deliberate
summary/timeline/discovery queries rather than an ORM N+1 problem. Life List runs
several independent groupings over all detections. Species detail is capped at 250
rows and uses the existing `(common_name, created_at DESC)` index. Activity uses
offset pagination; page 100 remains inexpensive at 100k after chronological
indexing, but very deep pages will still scale with the offset.

Python allocation peaks stayed approximately flat as the dataset grew: about
216 KiB for the homepage, 305 KiB for Activity, 150 KiB for Life List, and 461 KiB
for the species page. This indicates query execution—not result-set retention or
template expansion—is the primary scaling cost. Process RSS rose during sequential
profiles and then stabilized around 100 MiB on the audit host; that aggregate number
includes Flask, profiler state, and filesystem/SQLite caches and is not a per-route
leak measurement.

### SQLite review

The database uses foreign keys, WAL, `synchronous=NORMAL`, a 10-second busy timeout,
online backups, and short connections. Recorder and detector writes are explicitly
committed. Detection inserts and verification results are batched into one
recording-level transaction, which is efficient and prevents partial pipeline state.

Before the migration, SQLite reported full detection scans plus temporary sorts for
global chronological routes, and a complete covering-index scan for normalized
24-hour filters. After migration it reports:

- `idx_detections_created` for latest and Activity ordering;
- `idx_detections_datetime_created` range search for existing `datetime(created_at)`
  predicates;
- `idx_detections_species_created` for species detail;
- primary/foreign-key indexes for recording and verification joins.

Measured database growth after WAL checkpointing:

| Detections | Recordings | Before indexes | After indexes | Added index space |
|---:|---:|---:|---:|---:|
| 1,000 | 100 | 368 KiB | 476 KiB | 108 KiB |
| 10,000 | 1,000 | 3.04 MiB | 4.10 MiB | 1.06 MiB |
| 100,000 | 10,000 | 30.56 MiB | 41.45 MiB | 10.89 MiB |

Synthetic population time at 100k rose from 840 ms to 1,072 ms (28%) because both
indexes must be maintained. This is a worst-case bulk insert comparison; production
writes are spread over recordings, and the absolute added database work is far below
BirdNET inference time. The read improvement and predictable extra 109 bytes per
detection justify the tradeoff for RC1.1.

SQLite reuses deleted pages but does not return them to the filesystem without
`VACUUM`. There is no scheduled `VACUUM`, `PRAGMA optimize`, or explicit WAL
checkpoint policy. That is acceptable today: routine vacuuming causes exclusive,
I/O-heavy rewrites and should not be added without evidence of material freelist
growth. Track `page_count`, `freelist_count`, WAL size, and backup duration first.
Run `PRAGMA optimize` during low-traffic maintenance after large data changes;
schedule `VACUUM` only when reclaimable pages are persistently significant and a
maintenance window is available.

Web routes open and close one SQLite connection per request. They do not use the
canonical `connect_database()` helper, so they rely on SQLite's default five-second
timeout and the database's persisted WAL mode. This is not currently a measured
bottleneck, but standardizing busy timeout/read pragmas is sensible reliability work
if lock errors appear. Do not add connection pooling for SQLite without contention
evidence.

### Resource usage

Existing Raspberry Pi snapshots show:

- BirdNET inference around 129–341 MiB RSS depending on release/run; one later sample
  was about 218 MiB.
- Dashboard master/worker around 24–63 MiB combined depending on measurement scope.
- Recorder around 10–12 MiB RSS.
- Verification benchmark peak RSS 40.96 MiB.
- Active system memory about 50–69%; one calibration run retained about 523 MiB
  available with swap in use.
- Temperature about 58 C and recorded load averages 0.12 / 1.24 / 1.08 in the final
  release snapshot.

The deployment correctly limits the dashboard to one Gunicorn worker with four
threads and runs one BirdNET worker. SQLite releases connections promptly. BirdNET
0.2.16 previously retained two file descriptors per inference session; the worker
now removes session loggers and closes/join their queues after inference. This needs
the already-recommended 12–24 hour soak to prove descriptor and RSS stability.

Audio is the dominant disk and I/O load. One configured WAV is about 5.49 MiB. At a
60-second interval, the theoretical maximum is roughly 7.7 GiB/day before cleanup;
real volume depends on capture duration, interval, missed cycles, and retention.
Database storage is only about 41 MiB at 100k synthetic detections. Frog/mammal
detectors that reuse the same WAV add compute and database rows, not another audio
copy, and should preserve that property.

Network activity is local browser traffic plus dependency/model acquisition and any
future backups/synchronization. Current pages are server-rendered and static assets
are local. Audio playback dominates LAN transfer (about 5.5 MiB for a full recording);
conditional delivery supports partial/range responses through Werkzeug.

## Ranked bottlenecks

1. **High — all-history dashboard aggregation.** Homepage and Life List remain
   approximately linear in detections; Life List is 218 ms at 100k and homepage is
   226 ms after optimization.
2. **High — audio storage rate.** Continuous one-minute PCM capture can produce
   several GiB/day; retention/cleanup correctness and free-space guardrails matter
   more than database vacuuming.
3. **High — serial ML compute for future detectors.** BirdNET currently consumes
   seconds and hundreds of MiB. Frog/mammal models must be benchmarked together,
   including thermal throttling and queue age.
4. **Medium — verification historical query per detection.** The manager is reused
   per recording, but the historical plugin performs a multi-table aggregate for
   each accepted detection. It is small at today's species history but can become
   an N-per-detection cost with dense detector output.
5. **Medium — centralized multi-station assumptions.** Station IDs exist through
   recordings, but dashboard queries, APIs, and life-list aggregates do not select a
   station. One database per station is sound; central aggregation needs explicit
   partitioning/synchronization design.
6. **Medium — offset pagination.** Activity page 100 is acceptable now, while very
   deep pages require scanning skipped index entries. Keyset pagination becomes
   justified when real traces show deep navigation or API export workloads.
7. **Low — application-served assets.** Current latency is small. A reverse proxy
   can add long-lived cache headers and zero-copy file serving if concurrent clients
   or WAN access become requirements.
8. **Low — recorder initialization per cycle.** Schema/migration checks are repeated
   before each recording insert. This is safe and tiny relative to capture cadence;
   optimize only if measured on constrained storage.

## Implemented optimization

Migration `0005_detection_time_indexes.sql` adds only:

```sql
CREATE INDEX idx_detections_created
ON detections(created_at DESC);

CREATE INDEX idx_detections_datetime_created
ON detections(datetime(created_at));
```

Measured median improvements at 100,000 detections:

| Route | Baseline | Optimized | Improvement |
|---|---:|---:|---:|
| Homepage | 371.01 ms | 225.70 ms | 39.2% |
| Activity | 93.68 ms | 37.20 ms | 60.3% |
| Activity page 100 | 112.98 ms | 41.55 ms | 63.2% |
| Device | 74.78 ms | 53.97 ms | 27.8% |
| Dashboard API | 72.89 ms | 58.25 ms | 20.1% |
| Metrics API | 19.04 ms | 4.34 ms | 77.2% |

Life List and species detail did not materially improve, as expected, because their
plans already use species indexing or require full-history aggregates. No claims are
made for small static/audio timing variation, which is benchmark noise.

## Scalability assessment

### Ten times more recordings and detections

Ready with monitoring. Database writes remain small and transactional. The new time
indexes keep recent browsing responsive. Audio capacity and cleanup throughput must
be sized from the configured schedule. Backup duration should be tracked as the DB
and retained audio grow.

### 100,000 detections

Operationally ready for a single station. Activity and APIs remain responsive; the
homepage and Life List are usable but visibly slower. This is the point to define a
latency budget and consider cached/materialized species summaries if real Pi p95
exceeds it. SQLite itself has ample capacity at this size.

### Frog and mammal detection

Conditionally ready. Preserve a shared recording row/file, add detector identity and
taxon-aware indexes only after query shapes exist, and run models outside the
recorder process. Acceptance must cover combined throughput, peak RSS, temperature,
queue depth, accuracy, and failure isolation. A detector must not hold the sole WAV
open or block recording. If total inference approaches the recording interval,
prioritize/schedule detectors or introduce bounded worker queues before increasing
parallelism.

### Multiple stations

Ready only as independent local-first stations. Stable station identity and
station/time indexes are present. A central database/dashboard is not ready because
queries assume one station database and there is no synchronization/outbox protocol.
Follow the architecture note: append-only outbox records, idempotency keys, and
offline-safe sync should precede central ingestion. At central scale, include
`station_id` directly in detection read models or enforce joins/partition indexes;
do not infer identity from hostnames.

## Recommendations

### Critical

- Complete a 24-hour Pi soak under simultaneous recording, inference, verification,
  dashboard polling, cleanup, and backup. Sample per-process CPU/RSS, temperature,
  throttling, queue age/depth, open file descriptors, database/WAL sizes, disk bytes
  written, free space, route p50/p95, and restart counts. Alert on monotonic growth.
- Capacity-plan audio from the deployed schedule and validate cleanup under both
  zero-detection and detection-heavy retention. Test the minimum-free-space safety
  path before adding detectors.

### High

- Establish Pi route budgets (suggested initial targets: ordinary pages p95 under
  500 ms and JSON APIs under 200 ms during BirdNET inference), then rerun the bundled
  profiler on the Pi using a copied or generated 100k database.
- If homepage/Life List exceed budget, add a transactionally maintained daily/species
  summary or a short-TTL in-process cache with explicit invalidation measurements.
  Do not add rollups solely from the x86 synthetic result.
- Benchmark each frog/mammal model alone and concurrently with BirdNET. Record model
  load time, steady inference, RSS, CPU seconds, thermals, queue delay, and recordings
  processed per hour before activation.
- Define bounded queue/backpressure behavior and per-detector failure metrics before
  multiple detectors share the worker.

### Medium

- Add operational metrics for dashboard route latency, verification duration,
  database write/lock time, queue oldest age, WAL bytes, freelist pages, backup time,
  cleanup duration, and file-descriptor count. Current metrics mainly cover BirdNET
  timing and counts.
- Re-profile the historical verification plugin with dense predictions and long
  station history. If it becomes material, calculate history once per species per
  recording or maintain a verified-species summary.
- Move Activity to keyset pagination if production traces show deep-page use.
- Run `PRAGMA optimize` in low-traffic maintenance after substantial deletes/imports;
  add `VACUUM` only after freelist evidence and with free-space/maintenance-window
  safeguards.
- For centralized multi-station work, design the offline outbox/idempotent ingestion
  contract and station-scoped read indexes before changing dashboard queries.

### Low

- Standardize web SQLite connection timeout/read pragmas with the canonical database
  policy if lock telemetry shows inconsistent behavior.
- Add explicit static-asset cache policy or reverse-proxy serving when client count or
  WAN usage warrants it.
- Consider avoiding recorder schema initialization on every cycle only if profiling
  shows meaningful latency or flash writes; current evidence does not.

## Validation

Focused database, dashboard, web-path, migration, and verification tests passed:
**28 passed**. The BirdNET import was stubbed only because the audit environment did
not include the ML package; inference is mocked by the affected focused tests. The
new migration is ordered and idempotent, and the test expectation now includes
schema version 5.

The audit environment and temporary dependency directories were removed after the
runs. Only the profiler, evidence JSON, report, migration, and migration test update
remain in the repository.
