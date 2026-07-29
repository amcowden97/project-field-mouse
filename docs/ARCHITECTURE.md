# Architecture

Project Field Mouse is a local-first pipeline with one Raspberry Pi per station:

```text
microphone -> recorder -> WAV storage -> BirdNET -> SQLite -> Flask dashboard
maintenance timer -> online backup + retention cleanup      -> health API
```

Every detection belongs to a station through its recording's stable station ID. Services share validated TOML
configuration with optional `PFM_SECTION_KEY` environment overrides. SQLite stays the
default; foreign keys, WAL, busy timeout, integrity checks, backups, and station/time
indexes support reliable concurrent use.

Repository areas are `app/audio` (recording), `app/detectors` (BirdNET), `app/database`
(persistence), `app/services` (workers), `app/system` (health), `app/web` (UI/API),
`deploy/systemd` (production units), `scripts` (lifecycle commands), and `tests`.

For future multi-station support, never infer identity from hostname or display name.
New station data should include `station_id`. Synchronization should eventually use an
append-only outbox and idempotency keys so collection always works offline.
