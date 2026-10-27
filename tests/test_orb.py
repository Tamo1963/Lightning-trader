import numpy as np
import pandas as pd

from lightning.orb import day_filters, generate_orb

IST = "Asia/Kolkata"


def session(day, closes, highs=None, lows=None):
    idx = pd.date_range(f"{day} 09:15", periods=len(closes), freq="15min", tz=IST)
    c = np.array(closes, float)
    h = np.array(highs, float) if highs is not None else c + 1
    l = np.array(lows, float) if lows is not None else c - 1
    return pd.DataFrame({"open": c, "high": h, "low": l, "close": c, "volume": 1}, index=idx)


def test_first_breakout_only_and_side():
    up = session("2026-11-03", [100, 101, 100, 105, 90, 100] + [100] * 19)  # OR(2): hi 102 lo 99 -> 105 closes above
    dn = session("2026-11-04", [100, 101, 100, 95, 110] + [100] * 20)
    c = generate_orb(pd.concat([up, dn]), 2)
    assert list(c["side"]) == [1, -1]
    assert c.index[0] == up.index[3] and c.index[1] == dn.index[3]


def test_no_breakout_after_13_00():
    closes = [100] * 25
    closes[16] = 120  # bar starting 13:15 -> decision 13:30 > 13:00
    assert generate_orb(session("2026-11-03", closes), 2).empty


def test_day_filter_respected():
    s = session("2026-11-03", [100, 101, 100, 105] + [100] * 21)
    ok = pd.Series({pd.Timestamp("2026-11-03"): False})
    assert generate_orb(s, 2, ok).empty


def test_filters_use_only_prior_days():
    days = pd.bdate_range("2026-01-01", periods=40)
    f = pd.concat([session(d.strftime("%Y-%m-%d"), [100] * 25) for d in days])
    daily = pd.DataFrame({"high": 110.0, "low": 90.0}, index=days)
    base = day_filters(f, daily, None)
    daily2 = daily.copy()
    daily2.loc[days[30], ["high", "low"]] = [100.5, 99.5]  # quiet day 30
    alt = day_filters(f, daily2, None)
    assert base["compression"].iloc[30] == alt["compression"].iloc[30]  # same-day data not used
    assert alt["compression"].iloc[31] and not base["compression"].iloc[31]  # visible the next day
