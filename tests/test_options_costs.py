import math
from datetime import date

import pandas as pd

from lightning.costs import round_trip_costs
from lightning.options import atm_strike, bs_price, pick_expiry, years_to


def test_bs_known_value_and_parity():
    assert abs(bs_price(100, 100, 1.0, 0.2, True) - 7.9656) < 1e-3
    c, pu = bs_price(105, 100, 0.5, 0.25, True), bs_price(105, 100, 0.5, 0.25, False)
    assert abs((c - pu) - (105 - 100)) < 1e-9  # r = 0


def test_bs_monotonic_and_expiry_intrinsic():
    assert bs_price(101, 100, 0.1, 0.2, True) > bs_price(100, 100, 0.1, 0.2, True)
    assert bs_price(101, 100, 0.1, 0.2, False) < bs_price(100, 100, 0.1, 0.2, False)
    assert bs_price(110, 100, 0.0, 0.2, True) == 10 and bs_price(90, 100, 0.0, 0.2, True) == 0
    assert bs_price(100, 100, 0.2, 0.2, True) < bs_price(100, 100, 0.4, 0.2, True)  # time value


def test_expiry_and_strike():
    mon = date(2026, 10, 26)  # Monday
    assert pick_expiry(mon, 1, 2).weekday() == 1 and (pick_expiry(mon, 1, 2) - mon).days >= 2
    assert atm_strike(25012.0, 50) == 25000 and atm_strike(25030.0, 50) == 25050


def test_years_to_floor_zero():
    ts = pd.Timestamp("2026-10-27 16:00", tz="Asia/Kolkata")
    assert years_to(date(2026, 10, 27), ts) == 0.0


def test_costs_positive_and_scale():
    c = {"brokerage_per_order": 20, "stt_sell_pct": 0.0015, "exchange_txn_pct": 0.00035,
         "sebi_pct": 1e-6, "stamp_buy_pct": 3e-5, "gst_pct": 0.18}
    a, b = round_trip_costs(650, 100, 100, c), round_trip_costs(1300, 100, 100, c)
    assert 40 < a < b < 2 * a + 1e-9
    sell_t = 650 * 100
    expected = -(0.0015 + 0.00035 + 1e-6 + 0.18 * (0.00035 + 1e-6)) * sell_t
    assert math.isclose(round_trip_costs(650, 100, 0, c) - round_trip_costs(650, 100, 100, c), expected, rel_tol=1e-9)
