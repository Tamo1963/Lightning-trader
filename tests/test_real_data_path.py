"""Real-data path: Dhan payload parsing, calendars, and the RealPricer on a hand-built option table."""
from datetime import date

import numpy as np
import pandas as pd

from lightning.backtest import simulate_trade
from lightning.calendar import ExpiryCalendar, lot_size_on
from lightning.data.dhan import parse_rolling
from lightning.data.store import attach_option_volume
from lightning.pricing import RealPricer

IST = "Asia/Kolkata"


def test_parse_rolling_payload():
    payload = {"data": {"ce": {"open": [354, 360.3], "high": [360, 365], "low": [350, 358], "close": [358, 362],
                               "iv": [14.1, 14.0], "volume": [10, 20], "strike": [25000, 25000], "oi": [1, 2],
                               "spot": [25010, 25020], "timestamp": [1756698300, 1756699200]}, "pe": None}}
    df = parse_rolling(payload, "ce")
    assert list(df["close"]) == [358, 362] and str(df.index.tz) == IST
    assert parse_rolling(payload, "pe").empty


def test_expiry_holiday_moves_to_previous_trading_day():
    days = list(pd.bdate_range("2026-11-02", "2026-11-27").date)
    days.remove(date(2026, 11, 10))  # Tuesday holiday
    cal = ExpiryCalendar(days, [{"from": date(2019, 1, 1), "weekday": 3}, {"from": date(2025, 9, 1), "weekday": 1}])
    assert cal.is_expiry(date(2026, 11, 3)) and cal.is_expiry(date(2026, 11, 9)) and not cal.is_expiry(date(2026, 11, 10))
    assert cal.choose(date(2026, 11, 2), 2) == (1, date(2026, 11, 9))  # near expiry too close -> next
    assert cal.choose(date(2026, 11, 4), 2) == (0, date(2026, 11, 9))


def test_thursday_era_and_lot_schedule():
    days = list(pd.bdate_range("2024-06-03", "2024-06-28").date)
    cal = ExpiryCalendar(days, [{"from": date(2019, 1, 1), "weekday": 3}, {"from": date(2025, 9, 1), "weekday": 1}])
    assert all(d.weekday() == 3 for d in cal.expiries if d <= date(2024, 6, 28))
    sched = [{"from": date(2000, 1, 1), "lot": 50}, {"from": date(2024, 11, 20), "lot": 75}, {"from": date(2025, 12, 31), "lot": 65}]
    assert lot_size_on(sched, date(2024, 6, 1)) == 50 and lot_size_on(sched, date(2025, 6, 1)) == 75 and lot_size_on(sched, date(2026, 10, 1)) == 65


def _frames(call_closes):
    idx = pd.date_range("2026-11-04 10:00", periods=len(call_closes), freq="15min", tz=IST)
    spot = pd.DataFrame({"open": 25000.0, "high": 25010.0, "low": 24990.0, "close": 25000.0, "volume": 0}, index=idx)
    rows = []
    for t, cl in zip(idx, call_closes):
        for off in range(-1, 2):  # strike for offset 0 is 25000; the held strike must be found by value
            k = 25000 + 50 * off
            px = cl - 25 * off
            rows.append({"ts": t, "slot": 0, "side": "CE", "offset": off, "strike": k,
                         "open": px, "high": px + 2, "low": px - 2, "close": px, "volume": 100})
    return spot, pd.DataFrame(rows)


def test_real_pricer_target_and_volume_proxy(params):
    spot, opt = _frames([150, 150, 260, 260, 260])
    v = attach_option_volume(spot, opt)
    assert (v["volume"] == 300).all()  # 3 strikes x 100, CE only here
    pr = RealPricer(spot, opt)
    cal = ExpiryCalendar(pd.bdate_range("2026-11-02", "2026-11-20").date, params.expiry_schedule)
    t, why = simulate_trade(spot, 0, +1, params.capital, params, pr, cal)
    assert why is None and t["pricer"] == "real" and t["strike"] == 25000
    assert t["entry"] == round(150 * 1.01 + 0.0, 2) or abs(t["entry"] - 151.5) < 0.06
    assert t["exit_reason"] in ("TARGET", "TARGET_GAP") and t["net"] > 0


def test_real_pricer_missing_entry_bar_rejects(params):
    spot, opt = _frames([150, 150, 150])
    opt = opt[opt["ts"] != spot.index[1]]
    cal = ExpiryCalendar(pd.bdate_range("2026-11-02", "2026-11-20").date, params.expiry_schedule)
    t, why = simulate_trade(spot, 0, +1, params.capital, params, RealPricer(spot, opt), cal)
    assert t is None and why == "NO_OPTION_DATA"


def test_real_pricer_gap_mid_trade_exits_flagged(params):
    spot, opt = _frames([150, 150, 150, 150])
    opt = opt[opt["ts"] != spot.index[2]]
    cal = ExpiryCalendar(pd.bdate_range("2026-11-02", "2026-11-20").date, params.expiry_schedule)
    t, _ = simulate_trade(spot, 0, +1, params.capital, params, RealPricer(spot, opt), cal)
    assert t["exit_reason"] == "DATA_GAP"
