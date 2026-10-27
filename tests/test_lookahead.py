"""The most important tests: features at time t must not depend on anything after t."""
import numpy as np
import pandas as pd

from lightning.features import build_features, htf_rsi_asof

COLS = ["vwap", "vwma", "st_dir", "atr", "adx", "monthly_rsi", "weekly_rsi_chg"]


def test_features_identical_on_truncated_history(synth, params):
    fut, daily = synth
    full = build_features(fut, daily, params)
    for cut in (4000, 9000, 14000):
        t = fut.index[cut]
        part = build_features(fut.iloc[: cut + 1], daily[daily.index <= t.tz_localize(None).normalize()], params)
        a, b = full.iloc[: cut + 1][COLS], part[COLS]
        pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-9)


def test_htf_ignores_incomplete_month(synth):
    fut, daily = synth
    dc = daily["close"]
    mid = dc.index[300]
    month_start = mid.replace(day=1)
    base = htf_rsi_asof(dc, fut.index, "M")
    pert = dc.copy()
    pert[(pert.index >= month_start) & (pert.index <= month_end(mid))] *= 1.2  # distort the in-progress month
    alt = htf_rsi_asof(pert, fut.index, "M")
    in_month = (fut.index.tz_localize(None).normalize() >= month_start) & (fut.index.tz_localize(None).normalize() <= month_end(mid))
    np.testing.assert_array_equal(base[in_month], alt[in_month])  # unchanged inside the month
    assert not np.array_equal(base[~in_month & (fut.index.tz_localize(None) > month_end(mid))],
                              alt[~in_month & (fut.index.tz_localize(None) > month_end(mid))])  # visible afterwards


def month_end(ts):
    return (ts + pd.offsets.MonthEnd(0)).normalize()


def test_weekly_change_available_after_week_ends(synth):
    fut, daily = synth
    w = htf_rsi_asof(daily["close"], fut.index, "W-FRI", change=True)
    days = fut.index.tz_localize(None).normalize()
    monday = np.flatnonzero(days.weekday == 0)[25 * 100]
    friday = monday + 25 * 4  # same week, Friday bars
    assert not np.isnan(w[monday]) and w[monday] == w[friday]  # constant through the week
