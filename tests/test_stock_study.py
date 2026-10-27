from datetime import date

import numpy as np
import pandas as pd

from lightning.stock_study import daily_signals, model_option_r, monthly_expiries, pick_monthly, realized_vol

IST = "Asia/Kolkata"
C = {"brokerage_per_order": 20, "stt_sell_pct": 0.0015, "exchange_txn_pct": 0.00035, "sebi_pct": 1e-6,
     "stamp_buy_pct": 3e-5, "gst_pct": 0.18}


def test_monthly_expiry_holiday_and_weekday_switch():
    sched = [{"from": date(2019, 1, 1), "weekday": 3}, {"from": date(2025, 9, 1), "weekday": 1}]
    days = [d for d in pd.bdate_range("2025-08-01", "2026-01-31").date if d != date(2025, 11, 25)]
    ex = monthly_expiries(days, sched)
    assert date(2025, 8, 28) in ex and date(2025, 9, 30) in ex
    assert date(2025, 11, 24) in ex  # last Tuesday was a holiday -> Monday
    assert pick_monthly(ex, date(2025, 9, 25), 7) == date(2025, 10, 28)


def test_model_option_r_signs_and_decay():
    t0 = pd.Timestamp("2025-10-01 09:15", tz=IST)
    t1 = pd.Timestamp("2025-10-10 15:30", tz=IST)
    up = model_option_r(1000, 1100, 1, t0, t1, date(2025, 10, 28), 0.25, 10, 500, C)
    flat = model_option_r(1000, 1000, 1, t0, t1, date(2025, 10, 28), 0.25, 10, 500, C)
    put_up = model_option_r(1000, 1100, -1, t0, t1, date(2025, 10, 28), 0.25, 10, 500, C)
    assert up["r"] > 0 > flat["r"] > -1 and put_up["r"] < flat["r"]
    assert -1 <= put_up["r"]


def test_realized_vol_is_causal():
    idx = pd.bdate_range("2024-01-01", periods=60)
    c = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.01, 60))), index=idx)
    a = realized_vol(c)
    c2 = c.copy(); c2.iloc[40] *= 1.2  # shock on day 40
    b = realized_vol(c2)
    assert a.iloc[40] == b.iloc[40] and a.iloc[41] != b.iloc[41]


def test_daily_signal_edges_only():
    idx = pd.bdate_range("2018-01-01", periods=900)
    rng = np.random.default_rng(3)
    c = pd.Series(100 * np.exp(np.cumsum(0.002 + rng.normal(0, 0.01, 900))), index=idx)  # noisy uptrend
    d = pd.DataFrame({"open": c, "high": c * 1.005, "low": c * 0.995, "close": c, "volume": 1000.0}, index=idx)
    s = daily_signals(d)
    assert (s == 1).sum() > (s == -1).sum()
    assert not ((s == 1) & (s.shift(1) == 1)).any()
