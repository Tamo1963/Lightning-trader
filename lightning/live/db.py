"""SQLite audit store for shadow testing. Append-only for decisions; paper trades are updated on exit."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (underlying TEXT, ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL,
  PRIMARY KEY (underlying, ts));
CREATE TABLE IF NOT EXISTS candidates (id TEXT PRIMARY KEY, created_at TEXT, underlying TEXT, strategy TEXT, side INTEGER,
  decision_ts TEXT, status TEXT, features_json TEXT, code_version TEXT, config_hash TEXT, mode TEXT);
CREATE TABLE IF NOT EXISTS gates (candidate_id TEXT, gate TEXT, passed INTEGER, reason TEXT, detail_json TEXT,
  PRIMARY KEY (candidate_id, gate));
CREATE TABLE IF NOT EXISTS jev_calls (id TEXT PRIMARY KEY, candidate_id TEXT, requested_at TEXT, latency_ms INTEGER,
  model TEXT, request_json TEXT, response_json TEXT, decision TEXT, detail_json TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS paper_trades (id TEXT PRIMARY KEY, candidate_id TEXT, strategy TEXT, underlying TEXT, side INTEGER,
  strike REAL, expiry TEXT, lots INTEGER, qty INTEGER, entry_ts TEXT, entry_bid REAL, entry_ask REAL, entry_px REAL,
  stop REAL, target REAL, horizon_bars INTEGER, bars_held INTEGER, status TEXT, exit_ts TEXT, exit_bid REAL, exit_ask REAL,
  exit_px REAL, exit_reason TEXT, costs REAL, net REAL, net_r REAL, net_mid REAL, jev_decision TEXT);
CREATE TABLE IF NOT EXISTS quotes (ts TEXT, underlying TEXT, expiry TEXT, strike REAL, side TEXT, bid REAL, ask REAL,
  ltp REAL, iv REAL, oi REAL, volume REAL, spot REAL);
CREATE TABLE IF NOT EXISTS heartbeat (ts TEXT, status TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS quotes_ts ON quotes (ts);
"""


class AuditDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)

    def insert(self, table: str, row: dict, replace: bool = False):
        cols = ",".join(row)
        q = ",".join("?" for _ in row)
        verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        self.con.execute(f"{verb} INTO {table} ({cols}) VALUES ({q})", [_v(x) for x in row.values()])

    def insert_many(self, table: str, rows: list[dict]):
        if rows:
            cols = list(rows[0])
            self.con.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                                 [[_v(r[c]) for c in cols] for r in rows])

    def update(self, table: str, key: str, value, fields: dict):
        sets = ",".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE {table} SET {sets} WHERE {key}=?", [_v(x) for x in fields.values()] + [value])

    def query(self, sql: str, args=()):
        cur = self.con.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _v(x):
    if isinstance(x, (dict, list)):
        return json.dumps(x, default=str)
    if hasattr(x, "isoformat"):
        return x.isoformat()
    if hasattr(x, "item"):  # numpy scalar
        return x.item()
    return x
