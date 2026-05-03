# Changelog — pfc-archiver-cratedb

All notable changes are documented here.

---

## v0.2.1 — 2026-04-30

### Fixed

- **File handle leak in `verify_archive`** — the decompressed verification file was
  opened without a context manager (`with` block), leaving it unclosed after each
  partition verify. Under sustained load with many partitions this would exhaust the
  OS file descriptor limit and crash the daemon mid-run. Fixed by using `with open()`
  throughout. Bug found via live CrateDB integration tests (8/8 passing).

---

## v0.2.0 — 2026-04-14

Initial public release.

### Features

- TOML config file — one file, all settings in one place
- `--dry-run` — print what would be archived without writing anything
- `--once` — archive one cycle and exit (good for cron jobs)
- `--config` — point to any TOML config file
- SCAN → EXPORT → COMPRESS → UPLOAD → VERIFY → DELETE → LOG cycle
- `delete_after_archive = false` default — safe by default, opt-in deletion
- Local and S3 output (`output_dir = "s3://bucket/prefix/"`)
- JSON run log per cycle written to `log_dir`
- Graceful shutdown on SIGTERM / SIGINT — waits for current partition to finish

---

## v0.1.0 — 2026-04-13

- Initial build — CrateDB export via PostgreSQL wire protocol
