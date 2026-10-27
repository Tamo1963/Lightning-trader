-- Audit schema (SQLite/Postgres compatible). Append-only; never update decision rows.
CREATE TABLE candidate (
  candidate_id    TEXT PRIMARY KEY,
  created_at      TIMESTAMP NOT NULL,
  instrument      TEXT NOT NULL,
  direction       TEXT NOT NULL,            -- BUY_CALL | BUY_PUT
  bar_close_time  TIMESTAMP NOT NULL,
  strategy_id     TEXT NOT NULL,
  code_version    TEXT NOT NULL,
  feature_version TEXT NOT NULL,
  config_hash     TEXT NOT NULL,
  features_json   TEXT NOT NULL,
  mode            TEXT NOT NULL             -- REPLAY | SHADOW | PAPER | LIVE
);
CREATE TABLE gate_result (
  candidate_id TEXT NOT NULL REFERENCES candidate(candidate_id),
  gate         TEXT NOT NULL,               -- G1..G5
  variant      TEXT NOT NULL,               -- A | A+S | A+J | A+S+J
  passed       BOOLEAN NOT NULL,
  reason_code  TEXT,
  detail_json  TEXT,
  PRIMARY KEY (candidate_id, gate, variant)
);
CREATE TABLE jev_call (
  call_id       TEXT PRIMARY KEY,
  candidate_id  TEXT NOT NULL REFERENCES candidate(candidate_id),
  variant       TEXT NOT NULL,
  requested_at  TIMESTAMP NOT NULL,
  latency_ms    INTEGER,
  request_json  TEXT NOT NULL,
  response_json TEXT,                       -- raw, as received
  schema_valid  BOOLEAN,
  decision      TEXT,                       -- fail-closed REJECT recorded on error
  model_version TEXT,
  error         TEXT
);
CREATE TABLE paper_trade (                  -- one per candidate and variant, taken or not
  trade_id        TEXT PRIMARY KEY,
  candidate_id    TEXT NOT NULL REFERENCES candidate(candidate_id),
  variant         TEXT NOT NULL,
  would_trade     BOOLEAN NOT NULL,         -- false = counterfactual only
  contract        TEXT, lots INTEGER,
  entry_time TIMESTAMP, entry_premium REAL,
  stop_premium REAL, target_premium REAL,
  exit_time TIMESTAMP, exit_premium REAL, exit_reason TEXT,  -- TARGET|STOP|TIME|SQUAREOFF|MANUAL
  costs_inr REAL, net_pnl_inr REAL, net_r REAL
);
CREATE TABLE live_order (
  order_id TEXT PRIMARY KEY, trade_id TEXT REFERENCES paper_trade(trade_id),
  idempotency_key TEXT UNIQUE NOT NULL, broker_order_id TEXT,
  status TEXT, fill_price REAL, fill_time TIMESTAMP, reconciled_at TIMESTAMP
);
