# Changelog — pfc-archiver

All notable changes to pfc-archiver are documented here.

---

## v0.1.0 — 2026-04-14

Initial release — CrateDB cold storage archiving daemon.

### Features

- TOML config file — one file, all settings in one place
- `--dry-run` — print what would be archived without writing anything
- `--once` — archive one cycle and exit (good for cron jobs)
- `--config` — point to any TOML config file
- Full archive cycle: SCAN → EXPORT → COMPRESS → UPLOAD → VERIFY → DELETE → LOG
- `delete_after_archive = false` default — safe by default, opt-in deletion
- Local and S3 output (`output_dir = "s3://bucket/prefix/"`)
- JSON run log per cycle written to `log_dir`
- Graceful shutdown on SIGTERM / SIGINT — waits for current partition to finish
- 0-row guard — empty partitions are skipped cleanly without crashing

### Database support

| Database | Protocol | Port |
|----------|----------|------|
| CrateDB | PostgreSQL wire (psycopg2) | 5432 |

### Config example

See `config/cratedb.toml` for a ready-to-use configuration file.
