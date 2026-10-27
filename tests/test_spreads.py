from datetime import date, time

import numpy as np
import pandas as pd
import pytest

from lightning.calendar import ExpiryCalendar
from lightning.spreads import OptionBook, SpreadVariant, run_selling, simulate_day

IST = "Asia/Kolkata"


def make(prices_by_leg, n=25, day="2026-11-04"):
    """prices_by_leg: {(side, strike): [close per bar]}; open = previous close. Spot flat at 25000."""
    idx = pd.date_range(f"{day} 09:15", periods=n, freq="15min", tz=IST)
    f = pd.DataFrame({"open": 25000.0, "high": 25000.0, "low": 25000.0, "close": 25000.0, "volume": 1, "atr": 30.0}, index=idx)
    rows = []
    for (side, k), closes in prices_by_leg.items():
        for t, c, o in zip(idx, closes, [closes[0]] + list(closes[:-1])):
            rows.append({"ts": t, "slot": 0, "side": side, "offset": int((k - 25000) / 50), "strike": k,
                         "open": o, "high": max(o, c), "low": min(o, c), "close": c, "iv": 12.0, "volume": 1})
    return f, pd.DataFrame(rows)


def flat_book(short=60.0, wing=10.0, n=25):
    legs = {("CE", 25000): [short] * n, ("PE", 25000): [short] * n,
            ("CE", 25150): [wing] * n, ("PE", 24850): [wing] * n}
    return make(legs, n)


@pytest.fixture
def cal(params):
    return ExpiryCalendar(pd.bdate_range("2026-11-02", "2026-11-20").date, params.expiry_schedule)


def test_flat_prices_time_exit_loses_only_slippage_and_costs(params):
    f, opt = flat_book()
    t, why = simulate_day(OptionBook(f, opt), 2, SpreadVariant("fly", time(10, 0), "time"), params.capital, params, date(2026, 11, 9))
    assert why is None and t["exit_reason"] == "TIME"
    assert t["credit"] == pytest.approx(2 * 59.4 - 2 * 10.5)  # sells 60-0.6 (1%), buys 10+0.5 (min slip)
    assert t["net"] < 0 and t["risk_inr"] <= params.capital * params.risk_pct / 100 + 1e-6


def test_decay_is_profit(params):
    n = 25
    decay = list(np.linspace(60, 35, n))
    f, opt = make({("CE", 25000): decay, ("PE", 25000): decay, ("CE", 25150): [10] * n, ("PE", 24850): [10] * n}, n)
    t, _ = simulate_day(OptionBook(f, opt), 2, SpreadVariant("fly", time(10, 0), "time"), params.capital, params, date(2026, 11, 9))
    assert t["net"] > 0


def test_stop_triggers_and_exits_next_open(params):
    n = 25
    ce = [60.0] * 5 + [150.0] * (n - 5)  # call side explodes
    f, opt = make({("CE", 25000): ce, ("PE", 25000): [60.0] * n, ("CE", 25150): [10.0] * 5 + [60.0] * (n - 5),
                   ("PE", 24850): [10.0] * n}, n)
    t, _ = simulate_day(OptionBook(f, opt), 2, SpreadVariant("fly", time(10, 0), "stop_tp"), params.capital, params, date(2026, 11, 9))
    assert t["exit_reason"] == "STOP" and t["exit_ts"] == f.index[6]  # seen at bar-5 close, filled at bar-6 open and t["net"] < 0


def test_take_profit(params):
    n = 25
    s = [60.0] * 4 + [15.0] * (n - 4)
    f, opt = make({("CE", 25000): s, ("PE", 25000): s, ("CE", 25150): [10.0] * n, ("PE", 24850): [10.0] * n}, n)
    t, _ = simulate_day(OptionBook(f, opt), 2, SpreadVariant("fly", time(10, 0), "stop_tp"), params.capital, params, date(2026, 11, 9))
    assert t["exit_reason"] == "TARGET" and t["net"] > 0


def test_missing_wing_is_modelled_and_counted(params):
    n = 25
    f, opt = make({("CE", 25000): [60.0] * n, ("PE", 25000): [60.0] * n, ("CE", 24950): [80.0] * n,
                   ("PE", 24850): [10.0] * n}, n)  # CE 25150 absent from the band
    book = OptionBook(f, opt)
    t, why = simulate_day(book, 2, SpreadVariant("fly", time(10, 0), "time"), params.capital, params, date(2026, 11, 9))
    assert why is None and book.modelled > 0


def test_run_selling_one_per_day_and_expiry_block(params, cal):
    f, opt = flat_book()
    trades, log = run_selling(f, OptionBook(f, opt), SpreadVariant("condor", time(10, 0), "time"), params, cal)
    assert len(log) == 1 and len(trades) <= 1
