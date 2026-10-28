from datetime import date, timedelta

import pandas as pd
import pytest

from lightning.config import load_params
from lightning.monthly_selling import Chain, MonthlyVariant, cycles, simulate


def chain_df(days, expiries, price_fn):
    rows = []
    for d in days:
        for e in expiries:
            if e < d:
                continue
            for k in range(24000, 26050, 50):
                for o in ("CE", "PE"):
                    rows.append({"date": d, "expiry": e, "strike": float(k), "opt": o, "close": price_fn(d, e, k, o), "volume": 10})
    return pd.DataFrame(rows)


def decay(d, e, k, o, spot=25000):
    dte = max((e - d).days, 0)
    intrinsic = max(spot - k, 0) if o == "CE" else max(k - spot, 0)
    tv = 0.004 * spot * (dte / 30) ** 0.5 * max(0.0, 1 - abs(k - spot) / 900)
    return round(intrinsic + tv + 0.5, 2)


@pytest.fixture
def setup():
    days = [d.date() for d in pd.bdate_range("2026-01-02", "2026-03-31")]
    ex = [date(2026, 1, 27), date(2026, 2, 24), date(2026, 3, 31)]
    df = chain_df(days, ex, decay)
    spot = pd.Series(25000.0, index=pd.DatetimeIndex([pd.Timestamp(d) for d in days]))
    return Chain(df), spot, load_params()


def test_cycles_early_and_mid(setup):
    ch, _, _ = setup
    early = cycles(ch, "early")
    assert early[0][0] == date(2026, 1, 28) and early[0][2] == date(2026, 2, 24) and early[0][1] == date(2026, 2, 23)
    mid = cycles(ch, "mid")
    assert all((e - d0).days <= 14 for d0, _, e in mid)


def test_target_hit_on_pure_decay(setup):
    ch, spot, p = setup
    t, _ = simulate(ch, spot, MonthlyVariant("condor_n", "early", "none"), p, 1_000_000)
    assert len(t) == 2 and (t["exit_reason"] == "TARGET").all() and (t["net"] > 0).all()
    assert (t["capital_employed"] <= 0.2 * 1_000_000 * 1.01).all()
    assert all(r >= 0.05 for r in t["r"])


def test_stop_on_crash(setup):
    ch0, spot, p = setup
    days = ch0.days
    ex = [date(2026, 1, 27), date(2026, 2, 24), date(2026, 3, 31)]
    crash = lambda d, e, k, o: decay(d, e, k, o, spot=25000 if d < date(2026, 2, 2) else 24300)
    ch = Chain(chain_df(days, ex, crash))
    s = pd.Series([25000.0 if d < date(2026, 2, 2) else 24300.0 for d in days], index=pd.DatetimeIndex([pd.Timestamp(d) for d in days]))
    t, _ = simulate(ch, s, MonthlyVariant("fly", "early", "stop10"), p, 1_000_000)
    first = t.iloc[0]
    assert first["exit_reason"] == "STOP" and first["net"] < 0
    assert -1.1 < first["r"] <= -0.10  # a gap can blow through the stop to the max loss plus frictions


def test_wing_falls_back_to_listed_strike(setup):
    ch, _, _ = setup
    assert ch.wing(date(2026, 1, 28), date(2026, 2, 24), "CE", 26100, +1) is None  # beyond listed range
    assert ch.wing(date(2026, 1, 28), date(2026, 2, 24), "PE", 23990, -1) is None
    assert ch.wing(date(2026, 1, 28), date(2026, 2, 24), "CE", 25425, +1) == 25450
