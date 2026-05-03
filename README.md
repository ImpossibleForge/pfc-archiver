# pfc-archiver — Autonomous archive daemon for time-series databases

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![PFC-JSONL](https://img.shields.io/badge/PFC--JSONL-v3.4-green.svg)](https://github.com/ImpossibleForge/pfc-jsonl)
[![Version](https://img.shields.io/badge/pfc--archiver-v0.2.0-brightgreen.svg)](https://github.com/ImpossibleForge/pfc-archiver/releases)

A standalone daemon that runs alongside your database, watches for data older than a configurable retention window, compresses it to PFC format, and writes it to local storage or S3.

**Runs as a sidecar or cron job — no schema changes, no plugins, no database modifications.**

---

## How it works

Every `interval_seconds` (default: 3600), pfc-archiver runs one archive cycle:

```
SCAN  ->  EXPORT  ->  COMPRESS  ->  UPLOAD  ->  VERIFY  ->  (optional DELETE)  ->  LOG
```

1. **SCAN** — compute which time partitions are older than `retention_days`
2. **EXPORT** — read rows in `partition_days`-sized chunks from the database
3. **COMPRESS** — pipe through `pfc_jsonl compress` → `.pfc` + `.pfc.bidx` + `.pfc.idx`
4. **UPLOAD** — write to `output_dir` (local path or `s3://bucket/prefix/`)
5. **VERIFY** — decompress and count rows; must match exported count exactly
6. **DELETE** _(optional)_ — `DELETE WHERE ts >= from AND ts < to` (only if `delete_after_archive = true`)
7. **LOG** — write a JSON run log to `log_dir`

---

## Supported databases

| Database | Config `db_type` | Protocol | Default port |
|----------|-----------------|----------|-------------|
| CrateDB | `cratedb` | PostgreSQL wire | 5432 |
| TimescaleDB | `timescaledb` | PostgreSQL wire | 5432 |
| QuestDB | `questdb` | PostgreSQL wire | 8812 |
| ClickHouse | `clickhouse` | HTTP API | 8123 |
| Elasticsearch | `elasticsearch` | REST (scroll) | 9200 |
| Grafana Loki | `loki` | HTTP API | 3100 |
| InfluxDB v2 | `influxdb` | Flux API | 8086 |
| Apache Druid | `druid` | SQL HTTP | 8082 |

---

## Install

```bash
pip install pfc-archiver

# Or from source
git clone https://github.com/ImpossibleForge/pfc-archiver
cd pfc-archiver
pip install -r requirements.txt
```

**The `pfc_jsonl` binary must be installed:**

```bash
# Linux x64:
curl -L https://github.com/ImpossibleForge/pfc-jsonl/releases/latest/download/pfc_jsonl-linux-x64 \
     -o /usr/local/bin/pfc_jsonl && chmod +x /usr/local/bin/pfc_jsonl

# macOS (Apple Silicon M1–M4):
curl -L https://github.com/ImpossibleForge/pfc-jsonl/releases/latest/download/pfc_jsonl-macos-arm64 \
     -o /usr/local/bin/pfc_jsonl && chmod +x /usr/local/bin/pfc_jsonl
```

> **macOS Intel (x64):** Binary coming soon.
> **Windows:** No native binary. Use WSL2 or a Linux machine.

**Per-database Python dependencies:**

```bash
# PostgreSQL-wire databases (CrateDB, TimescaleDB, QuestDB)
pip install psycopg2-binary

# HTTP databases (ClickHouse, Elasticsearch, Loki, Druid)
pip install requests

# InfluxDB v2
pip install influxdb-client
```

---

## Quick start

```bash
# 1. Copy the example config for your database
cp config/cratedb.toml my_config.toml

# 2. Edit the config
nano my_config.toml

# 3. Dry run (no writes, prints what would be archived)
python pfc_archiver.py --config my_config.toml --dry-run

# 4. Archive once and exit
python pfc_archiver.py --config my_config.toml --once

# 5. Run as a daemon (loops every interval_seconds)
python pfc_archiver.py --config my_config.toml
```

---

## Configuration

All config is TOML. Copy the example for your database from `config/`.

### Common structure

```toml
[db]
db_type  = "cratedb"   # see supported databases above
host     = "localhost"
port     = 5432
# ... db-specific fields below

[archive]
retention_days       = 30       # archive data older than this
partition_days       = 1        # export this many days per archive file
output_dir           = "./archives/"   # local path or s3://bucket/prefix/
verify               = true     # decompress + count rows after each archive
delete_after_archive = false    # DELETE rows from DB after successful verify
log_dir              = "./archive_logs/"

[daemon]
interval_seconds = 3600   # how often to run (in daemon mode)
```

### Database-specific fields

**CrateDB / TimescaleDB / QuestDB (PostgreSQL wire)**

```toml
[db]
db_type   = "cratedb"        # or "timescaledb" / "questdb"
host      = "localhost"
port      = 5432             # 8812 for QuestDB
user      = "crate"
password  = ""
database  = "doc"
schema    = "doc"            # not used for QuestDB
table     = "logs"
ts_column = "ts"             # your timestamp column
batch_size = 10000
```

**ClickHouse (HTTP API)**

```toml
[db]
db_type   = "clickhouse"
host      = "localhost"
port      = 8123
user      = "default"
password  = ""
database  = "default"
table     = "logs"
ts_column = "event_time"
```

**Elasticsearch (REST)**

```toml
[db]
db_type    = "elasticsearch"
host       = "localhost"
port       = 9200
scheme     = "http"
# user     = "elastic"      # uncomment if X-Pack security is enabled
# password = "changeme"
index      = "logs-*"        # index name or wildcard
ts_field   = "@timestamp"
batch_size = 1000
```

**Grafana Loki (HTTP)**

```toml
[db]
db_type    = "loki"
host       = "localhost"
port       = 3100
scheme     = "http"
# user     = "admin"         # uncomment if auth is enabled
# password = "secret"
query      = '{job="app"}'   # LogQL stream selector
ts_column  = "timestamp"
batch_size = 5000
```

**InfluxDB v2 (Flux)**

```toml
[db]
db_type     = "influxdb"
host        = "localhost"
port        = 8086
scheme      = "http"
token       = "my-api-token"
org         = "my-org"
bucket      = "my-bucket"
measurement = ""             # leave empty to export all measurements
ts_column   = "_time"
```

**Apache Druid (SQL HTTP)**

```toml
[db]
db_type    = "druid"
host       = "localhost"
port       = 8082
scheme     = "http"
# user     = "druid_system"  # uncomment if auth is enabled
# password = "secret"
datasource = "my-datasource"
ts_column  = "__time"
batch_size = 10000
```

---

## Output format

Each archive cycle produces files named:

```
<table>_<YYYYMMDD>_<YYYYMMDD>.pfc
<table>_<YYYYMMDD>_<YYYYMMDD>.pfc.bidx
<table>_<YYYYMMDD>_<YYYYMMDD>.pfc.idx
```

The `.pfc` file is a PFC-JSONL archive. The `.bidx` and `.idx` files are block indexes that let DuckDB decompress only the relevant time window — without reading the whole file.

---

## Log format

Each completed cycle appends a JSON entry to `<log_dir>/archive_<YYYYMMDD>.log`:

```json
{
  "ts":          "2026-04-14T18:00:00",
  "db":          "cratedb://localhost:5432/doc",
  "table":       "logs",
  "from":        "2026-03-01T00:00:00",
  "to":          "2026-03-02T00:00:00",
  "rows":        248721,
  "jsonl_mb":    42.3,
  "pfc_mb":      2.5,
  "ratio_pct":   5.9,
  "output":      "./archives/logs_20260301_20260302.pfc",
  "verified":    true,
  "deleted":     false,
  "status":      "ok"
}
```

---

## Run as a systemd service

```ini
[Unit]
Description=pfc-archiver — PFC archive daemon
After=network.target

[Service]
Type=simple
User=pfc
WorkingDirectory=/opt/pfc-archiver
ExecStart=/usr/bin/python3 /opt/pfc-archiver/pfc_archiver.py --config /etc/pfc-archiver/cratedb.toml
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable pfc-archiver
sudo systemctl start pfc-archiver
sudo journalctl -u pfc-archiver -f
```

---

## Run as a Docker sidecar

```yaml
# docker-compose.yml
services:
  cratedb:
    image: crate:latest
    ports: ["4200:4200", "5432:5432"]

  pfc-archiver:
    image: ghcr.io/impossibleforge/pfc-archiver:latest
    volumes:
      - ./config/cratedb.toml:/etc/pfc-archiver/config.toml
      - ./archives:/archives
      - ./archive_logs:/logs
    environment:
      - PFC_CONFIG=/etc/pfc-archiver/config.toml
    depends_on: [cratedb]
```

---

## Deleting archived data

`delete_after_archive = false` by default — pfc-archiver never modifies your database without explicit opt-in.

After confirming your archives are accessible via DuckDB, set `delete_after_archive = true` and restart. Only partitions that pass the row-count verify step will be deleted.

**Database-specific notes for manual deletion:**

| Database | Deletion command |
|----------|-----------------|
| CrateDB / TimescaleDB / QuestDB | `DELETE FROM table WHERE ts >= '...' AND ts < '...'` |
| ClickHouse | `ALTER TABLE logs DROP PARTITION 'YYYY-MM-DD'` |
| Elasticsearch | `DELETE /index-name` or use ILM |
| Loki | Set `retention_period` in `loki-config.yaml` |
| InfluxDB v2 | `POST /api/v2/delete` with start/stop |
| Druid | `POST /druid/coordinator/v1/datasources/{name}/markUnused` |

---

## Querying cold archives

Once archived, your `.pfc` files are queryable directly from DuckDB:

```sql
INSTALL pfc FROM community;
LOAD pfc;
LOAD json;

-- Scan a single archive
SELECT *
FROM read_pfc_jsonl('./archives/logs_20260301_20260302.pfc')
LIMIT 100;

-- Scan all archives for March
SELECT level, count(*) as cnt
FROM pfc_scan([
    './archives/logs_20260301_20260302.pfc',
    './archives/logs_20260302_20260303.pfc'
])
GROUP BY level;

-- Time-window query (only decompresses the relevant blocks)
SELECT *
FROM read_pfc_jsonl(
    './archives/logs_20260301_20260302.pfc',
    ts_from = epoch(TIMESTAMPTZ '2026-03-01 14:00:00+00'),
    ts_to   = epoch(TIMESTAMPTZ '2026-03-01 15:00:00+00')
);
```

---

## Related Projects

| Project | Description |
|---------|-------------|
| [pfc-jsonl](https://github.com/ImpossibleForge/pfc-jsonl) | Core binary — compress, decompress, query |
| [pfc-duckdb](https://github.com/ImpossibleForge/pfc-duckdb) | DuckDB Community Extension (`INSTALL pfc FROM community`) |
| [pfc-migrate](https://github.com/ImpossibleForge/pfc-migrate) | One-shot migration of existing archives and database exports |
| [pfc-fluentbit](https://github.com/ImpossibleForge/pfc-fluentbit) | Fluent Bit -> PFC forwarder for live pipelines |

---

## License

MIT — see [LICENSE](https://github.com/ImpossibleForge/pfc-archiver/blob/main/LICENSE).

*Built by [ImpossibleForge](https://github.com/ImpossibleForge)*
