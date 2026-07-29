# Backup and restore guide

`pfm backup` creates a compressed ZIP containing an online SQLite snapshot, station
configuration, and a manifest with SHA-256 checksums. The archive is automatically
verified before success is reported. The maintenance timer creates scheduled backups.

Use `pfm verify-backup ARCHIVE` after copying an archive off-device. To restore, stop
all services, run `pfm restore ARCHIVE`, then run `pfm migrate` and restart services.
Add `--restore-config` only when the archived configuration should replace the current
one. Restore uses a temporary file and atomic replacement.

Retain at least one off-device backup. A backup on the station's SD card does not
protect against card failure or theft.
