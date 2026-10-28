from datetime import date

import numpy as np
import pandas as pd

from lightning.overlays import cycles_for, perf, run_symbol

C = {"brokerage_per_order": 20, "stt_sell_pct": 0.0015, "exchange_txn_pct": 0.00035, "sebi_pct": 1e-6,
     "stamp_buy_pct": 3e-5, "gst_pct": 0.18}


def make(fut_path, put_close_out=1.0, call_close_out=1.0):
    """Two months of a symbol: futures expiring 2026-02-24 and 2026-03-31, options on the March expiry."""
    days = [d.date() for d in pd.bdate_range("2026-01-26", "2026-03-31")]
    rows = []
    for i, d in enumerate(days):
        f = fut_path(i, len(days))
        for e in (date(2026, 2, 24), date(2026, 3, 31)):
            if d <= e:
                rows.append({"symbol": "X", "kind": "FUT", "date": d, "expiry": e, "strike": 0.0, "opt": "XX", "close": f, "volume": 1})
        for k in range(900, 1101, 10):
            for o in ("CE", "PE"):
                last = d == date(2026, 3, 30)
                px = (put_close_out if o == "PE" else call_close_out) if last else 10.0
                rows.append({"symbol": "X", "kind": "OPT", "date": d, "expiry": date(2026, 3, 31), "strike": float(k), "opt": o,
                             "close": px, "volume": 5})
    return pd.DataFrame(rows)


def test_cycle_rolls_day_before_expiry():
    df = make(lambda i, n: 1000.0)
    cyc = cycles_for(df)
    assert cyc == [(date(2026, 2, 23), date(2026, 3, 30), date(2026, 3, 31))]


def test_flat_market_costs_and_overlay_signs():
    r = run_symbol(make(lambda i, n: 1000.0), 100, C).iloc[0]
    assert -0.001 < r["B0"] < 0          # only futures costs
    assert r["P3"] < r["B0"]             # put bought at 10, expires worthless-ish (1.0)
    assert r["C3"] > r["B0"]             # call sold at 10, bought back at 1.0
    assert r["P3_k"] == 970 and r["C5_k"] == 1050


def test_crash_insurance_pays():
    down = make(lambda i, n: 1000.0 if i < n - 6 else 850.0, put_close_out=0.5)  # stale put close below intrinsic
    r = run_symbol(down, 100, C).iloc[0]
    assert r["B0"] < -0.14 and r["P5"] > r["B0"] + 0.085  # intrinsic floor 950-850=100 minus 10 premium and slippage
    assert r["C3"] > r["B0"]


def test_corporate_action_flag_and_perf():
    split = make(lambda i, n: 1000.0 if i < 30 else 500.0)
    assert bool(run_symbol(split, 100, C).iloc[0]["corp_action"])
    p = perf(pd.Series([0.01, -0.02, 0.03, 0.0]))
    assert p["n"] == 4 and 0 < p["max_dd"] < 0.03
