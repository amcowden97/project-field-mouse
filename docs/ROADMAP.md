# Technical roadmap

## RC1.1.1 — storage reliability

Ship graduated storage watermarks, ENOSPC-safe emergency cleanup, functional
recording/BirdNET freshness, storage forecasting, off-device operational alerts,
and bounded release-environment retention. This is a focused production reliability
patch and does not change the scientific roadmap.

## v1.1.0 — release

Promote after RC1.1.1 passes production storage fault injection and unattended soak.

## RC1.2 — next scientific milestone

Resume the planned detector and verification roadmap after the reliability gate.

## Version 2 — dependable single station

Complete shared-config adoption, ordered migrations, failure events, ARM64 locks, hard
disk-limit pruning, and release rollback. Target 30 days unattended operation.

## Version 3 — extensible local station

Define stable detector/storage interfaces, an upload outbox, API versioning, export,
plugin lifecycle, and hardware profiles. All networking remains optional.

## Version 4 — opt-in federation

Add authenticated registration, encrypted/idempotent sync, resumable media upload,
fleet health, and privacy controls while stations remain fully offline-capable.

Realistic plugins include alternate acoustic models, camera traps, weather sensors,
MQTT/Home Assistant output, object storage, and research exports.
