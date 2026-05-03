# Changelog — pfc-archiver

All notable changes to pfc-archiver are documented here.

---

## v0.2.1 — 2026-04-30

### Fixed

- **File handle leak in `verify_archive`** — the decompressed verification file was
  opened without a context manager (`with` block), leaving it unclosed after each
  partition verify. Under sustained load with many partitions this would exhaust the
  OS file descriptor limit and crash the daemon mid-run. Fixed by using `with open()`
  throughout.

---

## v0.2.0 — 2026-04-14

Initial public release supporting all major time-series databases.

### Databases supported

| Database | Config `db_type` | Protocol |
|----------|-----------------|----------|
| CrateDB | `cratedb` | PostgreSQL wire |
| TimescaleDB | `timescaledb` | PostgreSQL wire |
| QuestDB | `questdb` | PostgreSQL wire |
| ClickHouse | `clickhouse` | HTTP API (JSONEachRow) |
| Elasticsearch | `elasticsearch` | REST scroll API |
| Grafana Loki | `loki` | HTTP query_range API |
| InfluxDB v2 | `influxdb` | Flux pivot API |
| Apache Druid | `druid` | SQL HTTP |

### Features

- TOML config file — one file per database, all settings in one place
- `--dry-run` — print what would be archived without writing anything
- `--once` — archive one cycle and exit (good for cron jobs)
- `--config` — point to any TOML config file
- SCAN → EXPORT → COMPRESS → UPLOAD → VERIFY → DELETE → LOG cycle
- `delete_after_archive = false` default — safe by default, opt-in deletion
- Local and S3 output (`output_dir = "s3://bucket/prefix/"`)
- JSON run log per cycle written to `log_dir`
- Graceful shutdown on SIGTERM / SIGINT — waits for current partition to finish

### Config examples

See the `config/` directory for ready-to-use TOML files for each database.

---

## v0.1.0 — 2026-04-13

- Initial build with CrateDB, TimescaleDB, QuestDB support (PostgreSQL wire only)
