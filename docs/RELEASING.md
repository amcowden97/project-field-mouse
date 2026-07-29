# Release guide

Project Field Mouse uses Semantic Versioning. The canonical version is
`app/version.py`; Git tags use `vMAJOR.MINOR.PATCH`.

1. Ensure CI passes and validate installation, recording, detection, dashboard,
   migration, backup/restore, and rollback on a Raspberry Pi 5 staging station.
2. Update `app/version.py` and generate the changelog with
   `python scripts/changelog.py VERSION --since PREVIOUS_TAG`.
3. Curate user-facing changes, commit `Release: VERSION`, and create the signed tag.
4. Publish notes using `.github/RELEASE_TEMPLATE.md` with upgrade steps and checksums.
5. Install the release on staging from scratch, then upgrade a previous-version copy.
6. Promote to the active station only after a verified backup.

For rollback, stop services, check out the prior tag, reinstall its requirements,
restore the pre-upgrade archive, and restart. Never attempt to reverse schema changes
by hand.
