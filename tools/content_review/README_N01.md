# In-place repair of an existing educational task

The owner explicitly requested correction of existing IDs, without duplicate
bank rows. A private rollback file is the only retained copy of old content.
No pupil tables are read or written by this tool.

`build_n01_manifest.py` authors source-checked, complete task repairs from the
bounded educational export. `guarded_repair.py` verifies complete row hashes,
locks the entire repair set before writes, synchronizes paired columns, revokes
changed display attestations and removes obsolete validation claims. It requires
exactly one explanation per wrong choice. Rollback refuses subsequent content
edits and new attestations. Textbook links and existing IRT parameters are not
modified by the first manifest.

The tool does not read `.env` or fall back to the application's database URL.
Pass a verified target explicitly via `CONTENT_REPAIR_DATABASE_URL`. Dry-run is
its default. Do not infer stage identity merely from a database name: production
uses misleading `algo-staging-*` names; stage is `algo-preview-*`.

After Git push, successful CI, isolated PostgreSQL testing and a private backup:

```sh
python -m tools.content_review.guarded_repair --manifest data/content_repairs/n01-2026-10-05-w1.json
python -m tools.content_review.guarded_repair --manifest data/content_repairs/n01-2026-10-05-w1.json --execute --backup /private/release/bank-before.json
```

Use a clean archive of the exact pushed commit. Run the tool as a separate data
operation, without copying source files over the running application. Record the
source SHA, archive SHA, before/after educational fingerprints and target identity.
Keep secrets and original private backups out of Git. Repeating an already applied
manifest performs no writes and creates no unnecessary duplicate backup.
A manifest listing repair IDs in `historical_protection_required` (w6b) is refused,
for dry-run and execute alike, unless `--ack-protected` is passed after the owner
accepted the effect on existing pupil answers. If an execute fails after the backup
was written, the backup file stays (O_EXCL); use a new `--backup` path for the retry.

A guarded rollback is a separate explicit operation:

```sh
python -m tools.content_review.guarded_repair --rollback /private/release/bank-before.json
python -m tools.content_review.guarded_repair --rollback /private/release/bank-before.json --execute
```

Review historical impact before any key change. Correction of the bank is not a
recalculation of IRT, prior pupil outcomes, adaptive trajectories or saved reports.
The six-task manifest does not close the separate 147-item content review queue.
