from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from lightning.config import load_params
from lightning.live.covered_call import CoveredCallEngine, ReplayCCSource
from lightning.live.db import AuditDB
from lightning.overlays import run_symbol

ROOT = Path(__file__).resolve().parent.parent


def synthetic():
    days = [d.date() for d in pd.bdate_range("2026-01-26", "2026-04-30")]
    exps = [date(2026, 2, 24), date(2026, 3, 31), date(2026, 4, 28), date(2026, 5, 26)]
    rows = []
    for i, d in enumerate(days):
        f = 1000.0 + 2 * i
        for e in exps:
            if d <= e:
                rows.append({"symbol": "X", "kind": "FUT", "date": d, "expiry": e, "strike": 0.0, "opt": "XX", "close": f, "volume": 1})
                for k in range(900, 1301, 10):
                    tv = max(0.5, 30 * max(0, (e - d).days) / 35 - abs(k - f) / 20)
                    rows.append({"symbol": "X", "kind": "OPT", "date": d, "expiry": e, "strike": float(k), "opt": "CE",
                                 "close": round(max(f - k, 0) + tv, 2), "volume": 5})
    return pd.DataFrame(rows)


def test_replay_matches_backtest_cycle_by_cycle(tmp_path):
    df, p = synthetic(), load_params()
    src = ReplayCCSource(df)
    db = AuditDB(tmp_path / "cc.sqlite")
    eng = CoveredCallEngine(src, db, {"symbols": ["X"], "otm": 0.05, "min_days_to_open": 10 ** 6}, {"X": 100}, p.costs)
    for d in src.days:
        src.d = d
        eng.step()
    sh = pd.DataFrame(db.query("SELECT expiry, k, ret_b0, ret_c5 FROM cc_cycles WHERE status='CLOSED'"))
    bt = run_symbol(df, 100, p.costs)
    bt["expiry"] = bt["expiry"].astype(str)
    m = sh.merge(bt, on="expiry")
    assert len(m) == len(bt) >= 2
    assert (m["k"] == m["C5_k"]).all()
    assert ((m["ret_b0"] - m["B0"]).abs() < 2e-4).all()   # futures: same fills, same charges
    assert ((m["ret_c5"] - m["C5"]).abs() < 2e-3).all()   # options: intrinsic floor applied at bid vs close


def test_missed_roll_marks_untracked_and_restarts(tmp_path):
    df, p = synthetic(), load_params()
    src = ReplayCCSource(df)
    db = AuditDB(tmp_path / "cc.sqlite")
    eng = CoveredCallEngine(src, db, {"symbols": ["X"], "otm": 0.05, "min_days_to_open": 5}, {"X": 100}, p.costs)
    src.d = date(2026, 3, 2); eng.step()                  # opens mid-cycle on the March expiry
    src.d = date(2026, 4, 6); eng.step()                  # runner was off over the March roll
    st = {r["status"] for r in db.query("SELECT status FROM cc_cycles")}
    assert "EXPIRED_UNTRACKED" in st and "OPEN" in st


def test_no_order_methods_on_live_client():
    from lightning.data.dhan import DhanClient
    assert not any(w in n.lower() for n in dir(DhanClient) for w in ("order", "place", "cancel", "modify"))


def test_far_otm_call_without_quote_is_bought_back_near_zero(tmp_path):
    df, p = synthetic(), load_params()
    src = ReplayCCSource(df)
    db = AuditDB(tmp_path / "cc.sqlite")
    eng = CoveredCallEngine(src, db, {"symbols": ["X"], "otm": 0.05, "min_days_to_open": 10 ** 6}, {"X": 100}, p.costs)
    held = None
    for d in src.days:
        src.d = d
        if held is None:
            eng.step()
            o = db.query("SELECT k FROM cc_cycles WHERE status='OPEN'")
            held = o[0]["k"] if o else None
            continue
        drop = df[(df["date"] == d) & (df["strike"] == held)].index  # the held strike vanishes from the data
        src._by_day[d] = src._by_day[d].drop(drop, errors="ignore")
        eng.step()
    assert db.query("SELECT COUNT(*) n FROM cc_log WHERE event='CALL_NO_QUOTE_FALLBACK'")[0]["n"] >= 1
    assert db.query("SELECT COUNT(*) n FROM cc_cycles WHERE status='EXPIRED_UNTRACKED'")[0]["n"] == 0
