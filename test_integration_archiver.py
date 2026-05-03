#!/usr/bin/env python3
"""
Integration tests for pfc-archiver — requires live CrateDB.

Run on the server:
  python3 test_integration_archiver.py

CrateDB: localhost:5433 (Docker container crate-test)

Strategy: retention_days=0 so all test data is immediately "archivable".
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

CRATE_HOST = "localhost"
CRATE_PORT = 5433
CRATE_USER = "crate"
CRATE_PASS = ""
CRATE_DB   = "doc"
PFC_BINARY = "/usr/local/bin/pfc_jsonl"
TABLE      = "pfc_archiver_integration_test"

try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


def pfc_binary_available():
    return os.path.isfile(PFC_BINARY) and os.access(PFC_BINARY, os.X_OK)


def get_conn():
    return psycopg2.connect(
        host=CRATE_HOST, port=CRATE_PORT,
        user=CRATE_USER, password=CRATE_PASS,
        dbname=CRATE_DB, connect_timeout=10,
    )


def make_cfg(output_dir, log_dir, delete_after=False, retention_days=0):
    return {
        "db": {
            "host":      CRATE_HOST,
            "port":      CRATE_PORT,
            "user":      CRATE_USER,
            "password":  CRATE_PASS,
            "dbname":    CRATE_DB,
            "schema":    "doc",
            "table":     TABLE,
            "ts_column": "ts",
        },
        "archive": {
            "retention_days":       retention_days,
            "partition_days":       1,
            "output_dir":           str(output_dir),
            "verify":               True,
            "delete_after_archive": delete_after,
            "log_dir":              str(log_dir),
        },
        "pfc": {"binary": PFC_BINARY},
        "daemon": {"interval_seconds": 3600},
    }


@unittest.skipUnless(HAS_PSYCOPG2, "psycopg2 not installed")
@unittest.skipUnless(pfc_binary_available(), "pfc_jsonl binary not found")
class TestArchiverIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = get_conn()
        cls.conn.autocommit = True
        cur = cls.conn.cursor()
        cur.execute(f'DROP TABLE IF EXISTS "{TABLE}"')
        cur.execute(f"""
            CREATE TABLE "{TABLE}" (
                id      INTEGER,
                ts      TIMESTAMP WITH TIME ZONE,
                level   TEXT,
                message TEXT,
                value   DOUBLE PRECISION
            )
        """)
        # 3 days of data: day -3, day -2, day -1 (all older than retention_days=0)
        base = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=3)
        rows = []
        for day in range(3):
            for hour in range(8):
                ts = base + timedelta(days=day, hours=hour)
                i  = day * 8 + hour
                rows.append((i, ts.isoformat(), ["INFO","WARN","ERROR"][i % 3],
                              f"log message {i}", float(i) * 1.5))
        cur.executemany(
            f'INSERT INTO "{TABLE}" (id, ts, level, message, value) VALUES (%s,%s,%s,%s,%s)',
            rows,
        )
        cur.execute(f'REFRESH TABLE "{TABLE}"')
        cur.close()
        cls.total_rows = len(rows)  # 24

    @classmethod
    def tearDownClass(cls):
        cur = cls.conn.cursor()
        cur.execute(f'DROP TABLE IF EXISTS "{TABLE}"')
        cur.close()
        cls.conn.close()

    # ------------------------------------------------------------------
    # 1. SCAN finds correct partitions
    # ------------------------------------------------------------------
    def test_scan_finds_partitions(self):
        from pfc_archiver import get_partition_ranges
        cfg = make_cfg("/tmp", "/tmp")
        partitions = get_partition_ranges(cfg["db"], retention_days=0, partition_days=1)
        # 3 days of data → at least 3 partitions (archiver may add partial today-window)
        self.assertGreaterEqual(len(partitions), 3,
            f"Expected >= 3 partitions, got {len(partitions)}: {partitions}")

    # ------------------------------------------------------------------
    # 2. SCAN returns empty when all data is within retention window
    # ------------------------------------------------------------------
    def test_scan_empty_when_data_is_hot(self):
        from pfc_archiver import get_partition_ranges
        cfg = make_cfg("/tmp", "/tmp")
        partitions = get_partition_ranges(cfg["db"], retention_days=9999, partition_days=1)
        self.assertEqual(len(partitions), 0, "Expected 0 partitions (all data still hot)")

    # ------------------------------------------------------------------
    # 3. Full archive cycle — .pfc files created for all non-empty partitions
    # ------------------------------------------------------------------
    def test_full_archive_cycle_creates_pfc_files(self):
        from pfc_archiver import archive_cycle
        with tempfile.TemporaryDirectory() as out_dir, \
             tempfile.TemporaryDirectory() as log_dir:
            cfg = make_cfg(out_dir, log_dir, delete_after=False)
            archive_cycle(cfg, PFC_BINARY, dry_run=False)
            pfc_files = list(Path(out_dir).glob("*.pfc"))
            self.assertGreaterEqual(len(pfc_files), 3,
                f"Expected >= 3 .pfc files (one per day), got {len(pfc_files)}")

    # ------------------------------------------------------------------
    # 4. VERIFY passes — row counts match between DB export and .pfc
    # ------------------------------------------------------------------
    def test_verify_row_count_matches(self):
        from pfc_archiver import archive_cycle, get_partition_ranges, export_partition_to_pfc, verify_archive
        with tempfile.TemporaryDirectory() as out_dir, \
             tempfile.TemporaryDirectory() as log_dir:
            cfg    = make_cfg(out_dir, log_dir, delete_after=False)
            db_cfg = cfg["db"]

            partitions = get_partition_ranges(db_cfg, retention_days=0, partition_days=1)
            total_archived = 0
            for from_ts, to_ts in partitions:
                out_path = Path(out_dir) / f"test_{from_ts.date()}.pfc"
                stats = export_partition_to_pfc(db_cfg, from_ts, to_ts, out_path, PFC_BINARY)
                if stats["rows"] == 0:
                    continue  # empty partition (e.g. partial today-window) — no .pfc created
                self.assertTrue(verify_archive(out_path, stats["rows"], PFC_BINARY),
                    f"Verify failed for partition {from_ts.date()}")
                total_archived += stats["rows"]

            self.assertEqual(total_archived, self.total_rows,
                f"Total archived rows {total_archived} != inserted rows {self.total_rows}")

    # ------------------------------------------------------------------
    # 5. .bidx files are created for every partition
    # ------------------------------------------------------------------
    def test_bidx_created_for_all_partitions(self):
        from pfc_archiver import archive_cycle
        with tempfile.TemporaryDirectory() as out_dir, \
             tempfile.TemporaryDirectory() as log_dir:
            cfg = make_cfg(out_dir, log_dir)
            archive_cycle(cfg, PFC_BINARY, dry_run=False)
            bidx_files = list(Path(out_dir).glob("*.pfc.bidx"))
            self.assertGreaterEqual(len(bidx_files), 3,
                f"Expected >= 3 .bidx files, got {len(bidx_files)}")

    # ------------------------------------------------------------------
    # 6. Run log written for each partition
    # ------------------------------------------------------------------
    def test_run_log_written(self):
        from pfc_archiver import archive_cycle
        with tempfile.TemporaryDirectory() as out_dir, \
             tempfile.TemporaryDirectory() as log_dir:
            cfg = make_cfg(out_dir, log_dir)
            archive_cycle(cfg, PFC_BINARY, dry_run=False)
            log_file = Path(log_dir) / "archive_runs.jsonl"
            self.assertTrue(log_file.exists(), "archive_runs.jsonl not created")
            with open(log_file) as f:
                entry = json.loads(f.readline())
            self.assertIn("status", entry)
            self.assertIn("rows", entry)

    # ------------------------------------------------------------------
    # 7. Dry-run — no files created
    # ------------------------------------------------------------------
    def test_dry_run_creates_no_files(self):
        from pfc_archiver import archive_cycle
        with tempfile.TemporaryDirectory() as out_dir, \
             tempfile.TemporaryDirectory() as log_dir:
            cfg = make_cfg(out_dir, log_dir)
            archive_cycle(cfg, PFC_BINARY, dry_run=True)
            pfc_files = list(Path(out_dir).glob("*.pfc"))
            self.assertEqual(len(pfc_files), 0,
                f"Dry-run should create no files, found: {pfc_files}")

    # ------------------------------------------------------------------
    # 8. delete_after_archive=True — rows removed from DB after archiving
    # ------------------------------------------------------------------
    def test_delete_after_archive(self):
        from pfc_archiver import archive_cycle
        # Count rows before
        cur = self.conn.cursor()
        cur.execute(f'SELECT COUNT(*) FROM "{TABLE}"')
        count_before = cur.fetchone()[0]
        cur.close()
        self.assertEqual(count_before, self.total_rows)

        with tempfile.TemporaryDirectory() as out_dir, \
             tempfile.TemporaryDirectory() as log_dir:
            cfg = make_cfg(out_dir, log_dir, delete_after=True)
            archive_cycle(cfg, PFC_BINARY, dry_run=False)

        # CrateDB needs refresh before count reflects deletes
        cur = self.conn.cursor()
        cur.execute(f'REFRESH TABLE "{TABLE}"')
        cur.execute(f'SELECT COUNT(*) FROM "{TABLE}"')
        count_after = cur.fetchone()[0]
        cur.close()

        self.assertEqual(count_after, 0,
            f"Expected 0 rows after delete_after_archive, got {count_after}")

        # Restore rows for subsequent tests
        base = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=3)
        cur = self.conn.cursor()
        for day in range(3):
            for hour in range(8):
                ts = base + timedelta(days=day, hours=hour)
                i  = day * 8 + hour
                cur.execute(
                    f'INSERT INTO "{TABLE}" (id, ts, level, message, value) VALUES (%s,%s,%s,%s,%s)',
                    (i, ts.isoformat(), ["INFO","WARN","ERROR"][i % 3],
                     f"log message {i}", float(i) * 1.5),
                )
        cur.execute(f'REFRESH TABLE "{TABLE}"')
        cur.close()


if __name__ == "__main__":
    print(f"Archiver Integration Tests — CrateDB {CRATE_HOST}:{CRATE_PORT}")
    print(f"pfc_jsonl binary: {'found' if pfc_binary_available() else 'NOT FOUND'}")
    print("-" * 60)
    unittest.main(verbosity=2)
